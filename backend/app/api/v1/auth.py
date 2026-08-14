import hmac
from datetime import UTC, timedelta
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

from app.core.config import Settings, get_settings
from app.db.base import utcnow
from app.db.session import get_db
from app.models.entities import AuthSession, PasskeyCredential, User
from app.schemas.api import LoginRequest, PasskeyCredentialRequest, UserCreate, UserOut, UserUpdate
from app.services import passkeys
from app.services.auth import (
    bootstrap_admin,
    create_session,
    find_session,
    hash_password,
    verify_password,
)

SESSION_COOKIE = "certexam_session"
Db = Annotated[Session, Depends(get_db)]
AppSettings = Annotated[Settings, Depends(get_settings)]


def session_identity(
    db: Db,
    settings: AppSettings,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> tuple[AuthSession, User] | None:
    if not settings.auth_required:
        return None
    found = find_session(db, session_token) if session_token else None
    if not found:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다")
    return found


def current_user(
    identity: Annotated[tuple[AuthSession, User] | None, Depends(session_identity)],
    settings: AppSettings,
) -> User | None:
    if not settings.auth_required:
        return None
    if identity is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다")
    if identity[0].purpose != "full":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Passkey 인증을 완료해야 합니다")
    return identity[1]


def require_admin(
    user: Annotated[User | None, Depends(current_user)], settings: AppSettings
) -> User | None:
    if not settings.auth_required:
        return None
    if user is None or user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "관리자 권한이 필요합니다")
    return user


def user_response(db: Session, user: User, session: AuthSession, settings: Settings) -> UserOut:
    registered = db.scalar(
        select(PasskeyCredential.id).where(PasskeyCredential.user_id == user.id)
    ) is not None
    is_environment_admin = user.username == settings.initial_admin_username.strip().lower()
    return UserOut.model_validate(user).model_copy(
        update={
            "password_managed_by_environment": is_environment_admin,
            "passkey_registered": registered,
            "passkey_registration_required": session.purpose == "passkey_registration",
            "passkey_authentication_required": session.purpose == "passkey_authentication",
        }
    )


def set_session_cookie(response: Response, raw_token: str, settings: Settings) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        max_age=settings.auth_session_minutes * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def require_ceremony(
    identity: tuple[AuthSession, User] | None, purpose: str
) -> tuple[AuthSession, User]:
    if identity is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다")
    session, user = identity
    if user.role == "admin" or session.purpose != purpose:
        raise HTTPException(status.HTTP_409_CONFLICT, "현재 계정에서 진행할 수 없는 인증 단계입니다")
    return session, user


def save_challenge(
    db: Session,
    session: AuthSession,
    challenge: bytes,
    challenge_type: str,
    settings: Settings,
) -> None:
    session.challenge = bytes_to_base64url(challenge)
    session.challenge_type = challenge_type
    session.challenge_expires_at = utcnow() + timedelta(minutes=settings.passkey_challenge_minutes)
    db.commit()


def expected_challenge(session: AuthSession, challenge_type: str) -> bytes:
    expires_at = session.challenge_expires_at
    if expires_at is not None and expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if (
        not session.challenge
        or session.challenge_type != challenge_type
        or expires_at is None
        or expires_at <= utcnow()
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "Passkey 요청이 만료되었습니다. 다시 시도하세요")
    return base64url_to_bytes(session.challenge)


def complete_session(db: Session, session: AuthSession, user: User) -> None:
    db.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id == user.id,
            AuthSession.id != session.id,
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow())
    )
    session.purpose = "full"
    session.challenge = None
    session.challenge_type = None
    session.challenge_expires_at = None
    user.last_login_at = utcnow()


public = APIRouter()


@public.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@public.post("/auth/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, db: Db, settings: AppSettings) -> UserOut:
    username = payload.username.strip().lower()
    admin_username = settings.initial_admin_username.strip().lower()
    is_environment_admin = username == admin_username
    if is_environment_admin:
        bootstrap_admin(db, settings)
    user = db.scalar(select(User).where(User.username == username).with_for_update())
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "아이디 또는 비밀번호가 올바르지 않습니다")
    password_valid = (
        bool(settings.initial_admin_password)
        and hmac.compare_digest(payload.password, settings.initial_admin_password)
        if is_environment_admin
        else verify_password(payload.password, user.password_hash)
    )
    if not password_valid or (not is_environment_admin and not user.is_active):
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "아이디 또는 비밀번호가 올바르지 않습니다")
    if is_environment_admin:
        user.is_active = True
        user.role = "admin"
        purpose = "full"
    else:
        registered = db.scalar(
            select(PasskeyCredential.id).where(PasskeyCredential.user_id == user.id)
        ) is not None
        purpose = "passkey_authentication" if registered else "passkey_registration"
    session, raw_token = create_session(db, user, settings, purpose=purpose)
    if purpose == "full":
        user.last_login_at = utcnow()
    db.commit()
    set_session_cookie(response, raw_token, settings)
    return user_response(db, user, session, settings)


@public.post("/auth/logout", status_code=204)
def logout(
    response: Response,
    db: Db,
    settings: AppSettings,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    if session_token:
        found = find_session(db, session_token)
        if found:
            found[0].revoked_at = utcnow()
            db.commit()
    response.delete_cookie(
        SESSION_COOKIE, path="/", secure=settings.auth_cookie_secure, httponly=True, samesite="lax"
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


@public.get("/auth/me", response_model=UserOut)
def me(
    identity: Annotated[tuple[AuthSession, User] | None, Depends(session_identity)],
    db: Db,
    settings: AppSettings,
) -> UserOut:
    if identity is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다")
    return user_response(db, identity[1], identity[0], settings)


@public.post("/auth/passkeys/registration/options")
def passkey_registration_options(
    identity: Annotated[tuple[AuthSession, User] | None, Depends(session_identity)],
    db: Db,
    settings: AppSettings,
) -> dict[str, Any]:
    session, user = require_ceremony(identity, "passkey_registration")
    if db.scalar(select(PasskeyCredential.id).where(PasskeyCredential.user_id == user.id)):
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 Passkey가 등록되어 있습니다")
    challenge = passkeys.new_challenge()
    options = passkeys.registration_options(settings, user.username, user.id, challenge)
    save_challenge(db, session, challenge, "registration", settings)
    return options


@public.post("/auth/passkeys/registration/verify", response_model=UserOut)
def passkey_registration_verify(
    payload: PasskeyCredentialRequest,
    identity: Annotated[tuple[AuthSession, User] | None, Depends(session_identity)],
    db: Db,
    settings: AppSettings,
) -> UserOut:
    session, user = require_ceremony(identity, "passkey_registration")
    challenge = expected_challenge(session, "registration")
    try:
        verified = passkeys.verify_registration(
            settings=settings, credential=payload.credential, challenge=challenge
        )
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Passkey 등록을 검증하지 못했습니다") from exc
    credential_id = verified.credential_id
    if db.scalar(
        select(PasskeyCredential.id).where(
            (PasskeyCredential.user_id == user.id)
            | (PasskeyCredential.credential_id == credential_id)
        )
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "이미 등록된 Passkey입니다")
    response_data = payload.credential.get("response")
    transports = response_data.get("transports", []) if isinstance(response_data, dict) else []
    device_type = getattr(verified.credential_device_type, "value", verified.credential_device_type)
    db.add(
        PasskeyCredential(
            user_id=user.id,
            credential_id=credential_id,
            public_key=verified.credential_public_key,
            sign_count=verified.sign_count,
            transports_json=[str(item) for item in transports],
            device_type=str(device_type),
            backed_up=bool(verified.credential_backed_up),
        )
    )
    complete_session(db, session, user)
    db.commit()
    return user_response(db, user, session, settings)


@public.post("/auth/passkeys/authentication/options")
def passkey_authentication_options(
    identity: Annotated[tuple[AuthSession, User] | None, Depends(session_identity)],
    db: Db,
    settings: AppSettings,
) -> dict[str, Any]:
    session, user = require_ceremony(identity, "passkey_authentication")
    credential = db.scalar(select(PasskeyCredential).where(PasskeyCredential.user_id == user.id))
    if credential is None:
        raise HTTPException(status.HTTP_409_CONFLICT, "등록된 Passkey가 없습니다")
    challenge = passkeys.new_challenge()
    options = passkeys.authentication_options(
        settings, credential.credential_id, challenge
    )
    save_challenge(db, session, challenge, "authentication", settings)
    return options


@public.post("/auth/passkeys/authentication/verify", response_model=UserOut)
def passkey_authentication_verify(
    payload: PasskeyCredentialRequest,
    identity: Annotated[tuple[AuthSession, User] | None, Depends(session_identity)],
    db: Db,
    settings: AppSettings,
) -> UserOut:
    session, user = require_ceremony(identity, "passkey_authentication")
    challenge = expected_challenge(session, "authentication")
    credential = db.scalar(select(PasskeyCredential).where(PasskeyCredential.user_id == user.id))
    if credential is None or payload.credential.get("id") != bytes_to_base64url(credential.credential_id):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "등록된 Passkey와 일치하지 않습니다")
    try:
        verified = passkeys.verify_authentication(
            settings=settings,
            credential=payload.credential,
            challenge=challenge,
            public_key=credential.public_key,
            sign_count=credential.sign_count,
        )
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Passkey 인증에 실패했습니다") from exc
    credential.sign_count = verified.new_sign_count
    credential.last_used_at = utcnow()
    complete_session(db, session, user)
    db.commit()
    return user_response(db, user, session, settings)


protected = APIRouter(dependencies=[Depends(current_user)])
admin_users = APIRouter(prefix="/admin/users", dependencies=[Depends(require_admin)])


@admin_users.get("", response_model=list[UserOut])
def list_users(db: Db) -> list[UserOut]:
    users = list(db.scalars(select(User).where(User.role == "user").order_by(User.created_at.desc())))
    registered_ids = set(db.scalars(select(PasskeyCredential.user_id)))
    return [
        UserOut.model_validate(user).model_copy(
            update={"passkey_registered": user.id in registered_ids}
        )
        for user in users
    ]


@admin_users.post("", response_model=UserOut, status_code=201)
def create_user(
    payload: UserCreate, db: Db, admin: Annotated[User | None, Depends(require_admin)]
) -> User:
    if payload.role != "user":
        raise HTTPException(409, "시스템 admin 계정은 환경변수로만 관리합니다")
    username = payload.username.strip().lower()
    if db.scalar(select(User.id).where(User.username == username)) is not None:
        raise HTTPException(409, "이미 사용 중인 아이디입니다")
    user = User(
        username=username,
        password_hash=hash_password(payload.password),
        role=payload.role,
        created_by_id=admin.id if admin else None,
    )
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@admin_users.patch("/{user_id}", response_model=UserOut)
def update_user(
    user_id: int,
    payload: UserUpdate,
    db: Db,
    admin: Annotated[User | None, Depends(require_admin)],
) -> User:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "계정을 찾을 수 없습니다")
    if user.role == "admin":
        raise HTTPException(409, "시스템 admin 계정은 .env의 INITIAL_ADMIN_PASSWORD로만 관리합니다")
    if payload.password is not None:
        user.password_hash = hash_password(payload.password)
        db.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=utcnow())
        )
    if payload.is_active is not None:
        user.is_active = payload.is_active
        if not user.is_active:
            db.execute(
                update(AuthSession)
                .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
                .values(revoked_at=utcnow())
            )
    db.commit()
    db.refresh(user)
    return user


@admin_users.delete("/{user_id}/passkey", status_code=204)
def reset_passkey(user_id: int, db: Db) -> Response:
    user = db.get(User, user_id)
    if user is None or user.role == "admin":
        raise HTTPException(404, "계정을 찾을 수 없습니다")
    db.execute(delete(PasskeyCredential).where(PasskeyCredential.user_id == user.id))
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
