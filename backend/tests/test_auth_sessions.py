from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select, update
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
    refresh_session,
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


def test_user_activity_slides_the_existing_session_without_creating_another_row() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        database_url="sqlite://", database_host="", database_name="",
        database_user="", database_password="", auth_session_minutes=30,
    )
    with factory() as db:
        user = User(username="active-user", password_hash="hash", role="user")
        db.add(user); db.flush()
        session, _token = create_session(db, user, settings)
        db.commit()
        original_id = session.id
        before = utcnow()

        remaining_seconds = refresh_session(db, session, settings, idle_seconds=45)
        db.commit()
        after = utcnow()

        assert session.id == original_id
        assert db.scalar(select(func.count(AuthSession.id))) == 1
        assert before + timedelta(minutes=29, seconds=15) <= session.expires_at
        assert session.expires_at <= after + timedelta(minutes=29, seconds=15)
        assert 1754 <= remaining_seconds <= 1755


def test_new_login_removes_older_stale_rows_but_retains_the_latest_revoked_session() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        database_url="sqlite://", database_host="", database_name="",
        database_user="", database_password="", auth_session_minutes=30,
    )
    with factory() as db:
        user = User(username="cleanup-user", password_hash="hash", role="user")
        db.add(user); db.flush()
        first, _ = create_session(db, user, settings); db.commit()
        second, _ = create_session(db, user, settings); db.commit()
        db.refresh(first)
        assert first.revoked_at is not None

        third, _ = create_session(db, user, settings); db.commit()
        sessions = list(db.scalars(select(AuthSession).order_by(AuthSession.id)))

        assert [item.id for item in sessions] == [second.id, third.id]
        assert second.revoked_at is not None
        assert third.revoked_at is None


def test_creating_a_new_session_revokes_every_previous_session_for_the_user() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        database_url="sqlite://", database_host="", database_name="",
        database_user="", database_password="", auth_session_minutes=30,
    )
    with factory() as db:
        user = User(username="single-login", password_hash="hash", role="user")
        db.add(user); db.flush()
        first, first_token = create_session(db, user, settings)
        db.commit()
        second, second_token = create_session(db, user, settings)
        db.commit()

        db.refresh(first)
        assert first.revoked_at is not None
        assert second.revoked_at is None
        assert find_session(db, first_token) is None
        assert find_session(db, second_token) is not None


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
            client.cookies.set("certexam_session", raw_token)
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


def test_activity_endpoint_refreshes_the_cookie_and_rejects_incomplete_authentication() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine, expire_on_commit=False)
    settings = Settings(
        database_url="sqlite://", database_host="", database_name="",
        database_user="", database_password="", auth_required=True,
        auth_session_minutes=30,
    )
    with factory() as db:
        user = User(username="heartbeat-user", password_hash="hash", role="user")
        db.add(user); db.flush()
        _full, full_token = create_session(db, user, settings)
        pending, pending_token = create_session(
            db, user, settings, purpose="passkey_registration", revoke_existing=False
        )
        db.commit()
        pending_id = pending.id

    def override_db():
        with factory() as db:
            yield db

    application = create_app(settings)
    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(application) as client:
            assert client.post("/api/v1/auth/session/activity", json={"idle_seconds": 0}).status_code == 401
            client.cookies.set("certexam_session", pending_token)
            assert client.post("/api/v1/auth/session/activity", json={"idle_seconds": 0}).status_code == 403
            client.cookies.set("certexam_session", full_token)
            refreshed = client.post("/api/v1/auth/session/activity", json={"idle_seconds": 30})
            assert refreshed.status_code == 204
            assert "Max-Age=1770" in refreshed.headers["set-cookie"]
            assert client.post(
                "/api/v1/auth/session/activity", json={"idle_seconds": 1801}
            ).status_code == 422
    finally:
        application.dependency_overrides.clear()

    with factory() as db:
        assert db.scalar(select(func.count(AuthSession.id))) == 2
        assert db.get(AuthSession, pending_id) is not None

    disabled_settings = settings.model_copy(update={"auth_required": False})
    disabled_application = create_app(disabled_settings)
    disabled_application.dependency_overrides[get_settings] = lambda: disabled_settings
    try:
        with TestClient(disabled_application) as client:
            assert client.post(
                "/api/v1/auth/session/activity", json={"idle_seconds": 0}
            ).status_code == 401
    finally:
        disabled_application.dependency_overrides.clear()
