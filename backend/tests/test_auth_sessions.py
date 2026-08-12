from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base, utcnow
from app.db.session import get_db
from app.main import create_app
from app.models.entities import AuthSession, User
from app.services.auth import (
    create_session,
    find_session,
    hash_password,
    revoke_active_sessions,
    verify_password,
)


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


def test_password_validation_rejects_unsupported_and_malformed_hashes() -> None:
    assert verify_password("password", "legacy$310000$salt$digest") is False
    assert verify_password("password", "not-a-password-hash") is False


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


def test_application_startup_invalidates_an_existing_browser_session() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        database_url="sqlite://", database_host="", database_name="",
        database_user="", database_password="", auth_required=True,
        auth_session_minutes=30,
    )
    with factory() as db:
        user = User(username="restart-user", password_hash=hash_password("password"), role="user")
        db.add(user); db.flush()
        _session, raw_token = create_session(db, user, settings)
        db.commit()

    def override_db():
        with factory() as db:
            yield db

    def revoke_test_sessions() -> int:
        with factory() as db:
            result = db.execute(
                update(AuthSession)
                .where(AuthSession.revoked_at.is_(None))
                .values(revoked_at=utcnow())
            )
            db.commit()
            return result.rowcount

    application = create_app(settings, session_revoker=revoke_test_sessions)
    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(application) as client:
            client.cookies.set("certflow_session", raw_token)
            assert client.get("/api/v1/auth/me").status_code == 401
    finally:
        application.dependency_overrides.clear()

    with factory() as db:
        assert db.scalar(select(AuthSession.revoked_at)) is not None


def test_application_startup_does_not_revoke_sessions_when_auth_is_disabled() -> None:
    revoked = []
    application = create_app(
        Settings(auth_required=False),
        session_revoker=lambda: revoked.append(True) or 0,
    )

    with TestClient(application) as client:
        assert client.get("/api/v1/health").status_code == 200

    assert revoked == []
