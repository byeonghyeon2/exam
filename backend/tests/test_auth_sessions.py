from datetime import timedelta

from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings
from app.db.base import Base, utcnow
from app.models.entities import AuthSession, User
from app.services.auth import create_session, find_session, hash_password, revoke_active_sessions


def test_session_expires_after_thirty_minutes() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        database_url="sqlite://", database_host="", database_name="",
        database_user="", database_password="", auth_session_minutes=30,
    )
    with factory() as db:
        user = User(username="learner", password_hash=hash_password("password-123"), role="user")
        db.add(user); db.flush()
        before = utcnow()
        session, token = create_session(db, user, settings)
        db.commit()
        after = utcnow()
        assert before + timedelta(minutes=30) <= session.expires_at <= after + timedelta(minutes=30)
        assert find_session(db, token) is not None

        session.expires_at = utcnow() - timedelta(seconds=1)
        db.commit()
        assert find_session(db, token) is None


def test_server_restart_revokes_every_active_session(monkeypatch) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    with factory() as db:
        user = User(username="learner", password_hash="hash", role="user")
        db.add(user); db.flush()
        db.add_all([
            AuthSession(user_id=user.id, token_hash="a" * 64, expires_at=utcnow() + timedelta(minutes=30)),
            AuthSession(user_id=user.id, token_hash="b" * 64, expires_at=utcnow() + timedelta(minutes=30), revoked_at=utcnow()),
        ])
        db.commit()

    monkeypatch.setattr("app.db.session.SessionLocal", factory)
    assert revoke_active_sessions() == 1
    with factory() as db:
        sessions = list(db.scalars(select(AuthSession).order_by(AuthSession.id)))
        assert all(session.revoked_at is not None for session in sessions)
