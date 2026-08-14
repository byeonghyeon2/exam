import base64
import hashlib
import hmac
import secrets
from datetime import timedelta

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core.config import Settings
from app.db.base import utcnow
from app.models.entities import AuthSession, User

PASSWORD_ALGORITHM = "pbkdf2_sha256"
PASSWORD_ITERATIONS = 310_000


def hash_password(password: str) -> str:
    salt = secrets.token_bytes(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, PASSWORD_ITERATIONS)
    return "$".join((PASSWORD_ALGORITHM, str(PASSWORD_ITERATIONS), base64.urlsafe_b64encode(salt).decode(), base64.urlsafe_b64encode(digest).decode()))


def verify_password(password: str, encoded: str) -> bool:
    try:
        algorithm, iterations, salt_text, expected_text = encoded.split("$", 3)
        if algorithm != PASSWORD_ALGORITHM:
            return False
        salt = base64.urlsafe_b64decode(salt_text.encode())
        expected = base64.urlsafe_b64decode(expected_text.encode())
        actual = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, int(iterations))
        return hmac.compare_digest(actual, expected)
    except (ValueError, TypeError):
        return False


def create_session(
    db: Session, user: User, settings: Settings, purpose: str = "full"
) -> tuple[AuthSession, str]:
    db.execute(
        update(AuthSession)
        .where(AuthSession.user_id == user.id, AuthSession.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    raw_token = secrets.token_urlsafe(32)
    session = AuthSession(
        user_id=user.id,
        token_hash=hashlib.sha256(raw_token.encode()).hexdigest(),
        purpose=purpose,
        expires_at=utcnow() + timedelta(minutes=settings.auth_session_minutes),
    )
    db.add(session)
    return session, raw_token


def find_session(db: Session, raw_token: str) -> tuple[AuthSession, User] | None:
    token_hash = hashlib.sha256(raw_token.encode()).hexdigest()
    row = db.execute(
        select(AuthSession, User)
        .join(User, AuthSession.user_id == User.id)
        .where(
            AuthSession.token_hash == token_hash,
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > utcnow(),
            User.is_active.is_(True),
        )
    ).first()
    return (row[0], row[1]) if row else None


def revoke_active_sessions() -> int:
    """Invalidate every browser session once before a server process starts."""
    from app.db.session import SessionLocal

    revoked_at = utcnow()
    with SessionLocal() as db:
        result = db.execute(
            update(AuthSession)
            .where(AuthSession.revoked_at.is_(None))
            .values(revoked_at=revoked_at)
        )
        db.commit()
        return int(result.rowcount or 0)


def bootstrap_admin(db: Session, settings: Settings) -> bool:
    if db.scalar(select(User.id).where(User.role == "admin")) is not None:
        return False
    password = settings.initial_admin_password
    if not password:
        return False
    db.add(User(username=settings.initial_admin_username.strip().lower(), password_hash=hash_password(password), role="admin"))
    db.commit()
    return True
