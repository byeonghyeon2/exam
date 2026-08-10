import hmac
from typing import Annotated

from fastapi import APIRouter, Cookie, Depends, HTTPException, Response, status
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings, get_settings
from app.db.base import utcnow
from app.db.session import get_db
from app.models.entities import AuthSession, User
from app.schemas.api import LoginRequest, UserCreate, UserOut, UserUpdate
from app.services.auth import (
    bootstrap_admin,
    create_session,
    find_session,
    hash_password,
    verify_password,
)

SESSION_COOKIE = "certflow_session"
Db = Annotated[Session, Depends(get_db)]


def current_user(
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
    certflow_session: Annotated[str | None, Cookie()] = None,
) -> User | None:
    if not settings.auth_required:
        return None
    found = find_session(db, certflow_session) if certflow_session else None
    if not found:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다")
    return found[1]


def require_admin(user: Annotated[User | None, Depends(current_user)], settings: Annotated[Settings, Depends(get_settings)]) -> User | None:
    if not settings.auth_required:
        return None
    if user is None or user.role != "admin":
        raise HTTPException(status.HTTP_403_FORBIDDEN, "관리자 권한이 필요합니다")
    return user


public = APIRouter()


@public.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@public.post("/auth/login", response_model=UserOut)
def login(payload: LoginRequest, response: Response, db: Db, settings: Annotated[Settings, Depends(get_settings)]) -> UserOut:
    username = payload.username.strip().lower()
    admin_username = settings.initial_admin_username.strip().lower()
    is_environment_admin = username == admin_username
    if is_environment_admin:
        bootstrap_admin(db, settings)
    user = db.scalar(select(User).where(User.username == username))
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
    _session, raw_token = create_session(db, user, settings)
    user.last_login_at = utcnow()
    db.commit()
    response.set_cookie(
        SESSION_COOKIE,
        raw_token,
        max_age=settings.auth_session_days * 86400,
        httponly=True,
        secure=settings.auth_cookie_secure,
        samesite="lax",
        path="/",
    )
    return UserOut.model_validate(user).model_copy(update={"password_managed_by_environment": is_environment_admin})


@public.post("/auth/logout", status_code=204)
def logout(
    response: Response,
    db: Db,
    settings: Annotated[Settings, Depends(get_settings)],
    certflow_session: Annotated[str | None, Cookie()] = None,
) -> Response:
    if certflow_session:
        found = find_session(db, certflow_session)
        if found:
            found[0].revoked_at = utcnow()
            db.commit()
    response.delete_cookie(
        SESSION_COOKIE,
        path="/",
        secure=settings.auth_cookie_secure,
        httponly=True,
        samesite="lax",
    )
    response.status_code = status.HTTP_204_NO_CONTENT
    return response


protected = APIRouter(dependencies=[Depends(current_user)])


@protected.get("/auth/me", response_model=UserOut)
def me(user: Annotated[User | None, Depends(current_user)], settings: Annotated[Settings, Depends(get_settings)]) -> UserOut:
    if user is None:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "로그인이 필요합니다")
    return UserOut.model_validate(user).model_copy(
        update={"password_managed_by_environment": user.username == settings.initial_admin_username.strip().lower()}
    )


admin_users = APIRouter(prefix="/admin/users", dependencies=[Depends(require_admin)])


@admin_users.get("", response_model=list[UserOut])
def list_users(db: Db) -> list[User]:
    return list(db.scalars(select(User).where(User.role == "user").order_by(User.created_at.desc())))


@admin_users.post("", response_model=UserOut, status_code=201)
def create_user(payload: UserCreate, db: Db, admin: Annotated[User | None, Depends(require_admin)]) -> User:
    if payload.role != "user":
        raise HTTPException(409, "시스템 admin 계정은 환경변수로만 관리합니다")
    username = payload.username.strip().lower()
    if db.scalar(select(User.id).where(User.username == username)) is not None:
        raise HTTPException(409, "이미 사용 중인 아이디입니다")
    user = User(username=username, password_hash=hash_password(payload.password), role=payload.role, created_by_id=admin.id if admin else None)
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
        db.execute(update(AuthSession).where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None)).values(revoked_at=utcnow()))
    if payload.is_active is not None:
        user.is_active = payload.is_active
    db.commit()
    db.refresh(user)
    return user
