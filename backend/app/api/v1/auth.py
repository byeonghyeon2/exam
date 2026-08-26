import hashlib
import hmac
import logging
import secrets
from datetime import UTC, timedelta
from threading import Lock
from time import monotonic
from typing import Annotated, Any

from fastapi import APIRouter, Cookie, Depends, HTTPException, Request, Response, status
from sqlalchemy import delete, select, update
from sqlalchemy.orm import Session
from webauthn.helpers import base64url_to_bytes, bytes_to_base64url

from app.core.config import Settings, get_settings
from app.core.http_security import rate_limit_keys
from app.db.base import utcnow
from app.db.session import get_db
from app.models.entities import (
    AuthSession,
    MockExam,
    MockExamQuestion,
    PasskeyChallenge,
    PasskeyCredential,
    StudyAttempt,
    StudySessionRecord,
    User,
    WrongNote,
)
from app.schemas.api import (
    AdminRecoveryRequest,
    LoginRequest,
    PasskeyCredentialRequest,
    SessionActivityRequest,
    UserCreate,
    UserOut,
    UserUpdate,
)
from app.services import passkeys
from app.services.auth import (
    bootstrap_admin,
    create_session,
    find_session,
    hash_password,
    refresh_session,
    verify_password,
)
from app.services.maintenance import enforce_active_maintenance

SESSION_COOKIE = "certexam_session"
PASSKEY_CHALLENGE_COOKIE = "certexam_passkey_challenge"
RECOVERY_ATTEMPTS: dict[str, list[float]] = {}
RECOVERY_LOCK = Lock()
logger = logging.getLogger(__name__)


def recovery_allowed(key: str, limit: int, window_seconds: int) -> tuple[bool, int]:
    now = monotonic()
    with RECOVERY_LOCK:
        for stale_key, stamps in list(RECOVERY_ATTEMPTS.items()):
            fresh = [stamp for stamp in stamps if now - stamp < window_seconds]
            if fresh:
                RECOVERY_ATTEMPTS[stale_key] = fresh
            else:
                RECOVERY_ATTEMPTS.pop(stale_key, None)
        if key not in RECOVERY_ATTEMPTS and len(RECOVERY_ATTEMPTS) >= 10_000:
            oldest_key = min(RECOVERY_ATTEMPTS, key=lambda item: RECOVERY_ATTEMPTS[item][0])
            RECOVERY_ATTEMPTS.pop(oldest_key, None)
        attempts = [stamp for stamp in RECOVERY_ATTEMPTS.get(key, []) if now - stamp < window_seconds]
        if len(attempts) >= limit:
            RECOVERY_ATTEMPTS[key] = attempts
            return False, max(1, int(window_seconds - (now - attempts[0])))
        attempts.append(now)
        RECOVERY_ATTEMPTS[key] = attempts
        return True, 0
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


def maintenance_current_user(
    user: Annotated[User | None, Depends(current_user)], db: Db, settings: AppSettings
) -> User | None:
    if not settings.auth_required or user is None or user.role == "admin":
        return user
    reject_learner_during_maintenance(db, user)
    return user


def reject_learner_during_maintenance(db: Session, user: User) -> None:
    if user.role != "admin" and enforce_active_maintenance(db) is not None:
        raise HTTPException(status.HTTP_503_SERVICE_UNAVAILABLE, "현재 점검 중입니다")


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


def set_session_cookie(
    response: Response,
    raw_token: str,
    settings: Settings,
    max_age_seconds: int | None = None,
) -> None:
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        max_age=max_age_seconds or settings.auth_session_minutes * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )


def set_passkey_challenge_cookie(
    response: Response, raw_token: str, settings: Settings
) -> None:
    response.set_cookie(
        PASSKEY_CHALLENGE_COOKIE,
        raw_token,
        max_age=settings.passkey_challenge_minutes * 60,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="strict",
        path="/api/v1/auth/passkeys/authentication",
    )


def delete_passkey_challenge_cookie(response: Response, settings: Settings) -> None:
    response.delete_cookie(
        PASSKEY_CHALLENGE_COOKIE,
        path="/api/v1/auth/passkeys/authentication",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="strict",
    )


def require_ceremony(
    identity: tuple[AuthSession, User] | None, purpose: str
) -> tuple[AuthSession, User]:
    if identity is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다")
    session, user = identity
    if session.purpose != purpose:
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


def create_authentication_challenge(
    db: Session, settings: Settings
) -> tuple[bytes, str]:
    now = utcnow()
    db.execute(
        delete(PasskeyChallenge).where(
            (PasskeyChallenge.expires_at <= now)
            | (PasskeyChallenge.consumed_at.is_not(None))
        )
    )
    challenge = passkeys.new_challenge()
    raw_token = secrets.token_urlsafe(32)
    db.add(
        PasskeyChallenge(
            token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
            challenge=bytes_to_base64url(challenge),
            expires_at=now + timedelta(minutes=settings.passkey_challenge_minutes),
        )
    )
    db.commit()
    return challenge, raw_token


def consume_authentication_challenge(db: Session, raw_token: str | None) -> bytes:
    if not raw_token:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Passkey 인증 요청이 필요합니다")
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    ceremony = db.scalar(
        select(PasskeyChallenge)
        .where(PasskeyChallenge.token_hash == token_hash)
        .with_for_update()
    )
    if ceremony is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Passkey 인증 요청이 유효하지 않습니다")
    expires_at = ceremony.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=UTC)
    if ceremony.consumed_at is not None or expires_at <= utcnow():
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Passkey 인증 요청이 만료되었습니다")
    ceremony.consumed_at = utcnow()
    challenge = base64url_to_bytes(ceremony.challenge)
    db.commit()
    return challenge


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
    reject_learner_during_maintenance(db, user)
    if is_environment_admin:
        user.is_active = True
        user.role = "admin"
        session, raw_token = create_session(db, user, settings, purpose="full")
        user.last_login_at = utcnow()
        db.commit()
        set_session_cookie(response, raw_token, settings)
        return user_response(db, user, session, settings)
    registered = db.scalar(
        select(PasskeyCredential.id).where(PasskeyCredential.user_id == user.id)
    ) is not None
    if registered:
        raise HTTPException(
            status.HTTP_409_CONFLICT,
            "등록된 계정입니다. Passkey로 로그인해주세요",
        )
    purpose = "passkey_registration"
    session, raw_token = create_session(
        db,
        user,
        settings,
        purpose=purpose,
        revoke_existing=False,
    )
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


@public.post("/auth/session/activity", status_code=204)
def session_activity(
    payload: SessionActivityRequest,
    response: Response,
    identity: Annotated[tuple[AuthSession, User] | None, Depends(session_identity)],
    db: Db,
    settings: AppSettings,
    session_token: str | None = Cookie(default=None, alias=SESSION_COOKIE),
) -> Response:
    if identity is None or session_token is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다")
    session, user = identity
    if session.purpose != "full":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Passkey 인증을 완료해야 합니다")
    reject_learner_during_maintenance(db, user)
    max_age = refresh_session(db, session, settings, payload.idle_seconds)
    db.commit()
    set_session_cookie(response, session_token, settings, max_age_seconds=max_age)
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
    reject_learner_during_maintenance(db, identity[1])
    return user_response(db, identity[1], identity[0], settings)


@public.post("/auth/passkeys/registration/options")
def passkey_registration_options(
    identity: Annotated[tuple[AuthSession, User] | None, Depends(session_identity)],
    db: Db,
    settings: AppSettings,
) -> dict[str, Any]:
    session, user = require_ceremony(identity, "passkey_registration")
    reject_learner_during_maintenance(db, user)
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
    reject_learner_during_maintenance(db, user)
    challenge = expected_challenge(session, "registration")
    try:
        verified = passkeys.verify_registration(
            settings=settings, credential=payload.credential, challenge=challenge
        )
    except Exception as exc:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Passkey 등록을 검증하지 못했습니다") from exc
    locked_user = db.scalar(select(User).where(User.id == user.id).with_for_update())
    locked_session = db.scalar(
        select(AuthSession).where(AuthSession.id == session.id).with_for_update()
    )
    if (
        locked_user is None
        or not locked_user.is_active
        or locked_session is None
        or locked_session.revoked_at is not None
        or locked_session.purpose != "passkey_registration"
    ):
        raise HTTPException(status.HTTP_409_CONFLICT, "기기 등록 세션이 만료되었습니다")
    current_challenge = expected_challenge(locked_session, "registration")
    if not hmac.compare_digest(challenge, current_challenge):
        raise HTTPException(status.HTTP_409_CONFLICT, "기기 등록 요청이 변경되었습니다")
    session, user = locked_session, locked_user
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
    response: Response,
    db: Db,
    settings: AppSettings,
) -> dict[str, Any]:
    challenge, raw_token = create_authentication_challenge(db, settings)
    options = passkeys.authentication_options(settings, challenge)
    set_passkey_challenge_cookie(response, raw_token, settings)
    return options


@public.post("/auth/passkeys/authentication/verify", response_model=UserOut)
def passkey_authentication_verify(
    payload: PasskeyCredentialRequest,
    response: Response,
    db: Db,
    settings: AppSettings,
    challenge_token: str | None = Cookie(default=None, alias=PASSKEY_CHALLENGE_COOKIE),
) -> UserOut:
    challenge = consume_authentication_challenge(db, challenge_token)
    try:
        credential_id = base64url_to_bytes(str(payload.credential.get("id", "")))
    except Exception as exc:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Passkey 인증에 실패했습니다") from exc
    credential_owner_id = db.scalar(
        select(PasskeyCredential.user_id).where(PasskeyCredential.credential_id == credential_id)
    )
    user = db.scalar(
        select(User).where(User.id == credential_owner_id).with_for_update()
    ) if credential_owner_id is not None else None
    credential = db.scalar(
        select(PasskeyCredential).where(
            PasskeyCredential.credential_id == credential_id,
            PasskeyCredential.user_id == credential_owner_id,
        ).with_for_update()
    ) if user is not None else None
    if credential is None or user is None or not user.is_active:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Passkey 인증에 실패했습니다")
    reject_learner_during_maintenance(db, user)
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
    session, raw_token = create_session(db, user, settings, purpose="full")
    user.last_login_at = utcnow()
    db.commit()
    set_session_cookie(response, raw_token, settings)
    delete_passkey_challenge_cookie(response, settings)
    return user_response(db, user, session, settings)


@public.post("/auth/admin/recovery", status_code=status.HTTP_204_NO_CONTENT)
def admin_recovery(payload: AdminRecoveryRequest, request: Request, db: Db, settings: AppSettings) -> Response:
    """Reset only the administrator device credential; never create a login session."""
    username = payload.username.strip().lower()
    client_key = rate_limit_keys(request, settings.proxy_trusted_ips)[0]
    allowed, retry_after = recovery_allowed(
        client_key,
        settings.admin_recovery_rate_limit_requests,
        settings.admin_recovery_rate_limit_window_seconds,
    )
    if not allowed:
        logger.warning(
            "Admin device recovery rate limited",
            extra={"client_key_hash": hashlib.sha256(client_key.encode()).hexdigest()[:16]},
        )
        raise HTTPException(
            status.HTTP_429_TOO_MANY_REQUESTS,
            "관리자 기기 복구 시도 횟수를 초과했습니다",
            headers={"Retry-After": str(retry_after)},
        )
    expected_username = settings.initial_admin_username.strip().lower()
    # Deliberately keep the public error indistinguishable for unknown users,
    # missing configuration and invalid recovery material.
    configured_hash = settings.admin_recovery_key_hash
    valid = (
        username == expected_username
        and bool(configured_hash)
        and verify_password(payload.recovery_key, configured_hash)
    )
    if not valid:
        logger.warning(
            "Admin device recovery rejected",
            extra={"client_key_hash": hashlib.sha256(client_key.encode()).hexdigest()[:16]},
        )
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "관리자 기기 복구 정보를 확인할 수 없습니다")
    admin = db.scalar(select(User).where(User.username == expected_username).with_for_update())
    if admin is None or admin.role != "admin":
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "관리자 기기 복구 정보를 확인할 수 없습니다")
    db.execute(delete(PasskeyCredential).where(PasskeyCredential.user_id == admin.id))
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == admin.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    db.commit()
    logger.info(
        "Admin device recovery completed",
        extra={"client_key_hash": hashlib.sha256(client_key.encode()).hexdigest()[:16]},
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


protected = APIRouter(dependencies=[Depends(maintenance_current_user)])
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


@admin_users.delete("/{user_id}", status_code=204)
def delete_user(user_id: int, db: Db) -> Response:
    user = db.get(User, user_id)
    if user is None:
        raise HTTPException(404, "계정을 찾을 수 없습니다")
    if user.role == "admin":
        raise HTTPException(409, "시스템 admin 계정은 삭제할 수 없습니다")

    exam_ids = select(MockExam.id).where(MockExam.user_id == user.id)
    db.execute(delete(MockExamQuestion).where(MockExamQuestion.mock_exam_id.in_(exam_ids)))
    db.execute(delete(MockExam).where(MockExam.user_id == user.id))
    db.execute(delete(StudyAttempt).where(StudyAttempt.user_id == user.id))
    db.execute(delete(StudySessionRecord).where(StudySessionRecord.user_id == user.id))
    db.execute(delete(WrongNote).where(WrongNote.user_id == user.id))
    db.execute(delete(PasskeyCredential).where(PasskeyCredential.user_id == user.id))
    db.execute(delete(AuthSession).where(AuthSession.user_id == user.id))
    db.delete(user)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
