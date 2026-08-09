from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.entities import User


def test_admin_bootstrap_login_and_managed_user_access() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    def override_db() -> Iterator[Session]:
        with session_factory() as db:
            yield db

    settings = Settings(
        database_url="sqlite://",
        database_host="",
        database_name="",
        database_user="",
        database_password="",
        initial_admin_username="admin",
        initial_admin_password="strong-admin-password",
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/certifications").status_code == 401
            logged_in = client.post("/api/v1/auth/login", json={"username": "admin", "password": "strong-admin-password"})
            assert logged_in.status_code == 200
            assert logged_in.json()["role"] == "admin"
            assert logged_in.cookies.get("certflow_session")

            created = client.post("/api/v1/admin/users", json={"username": "learner", "password": "learner-password", "role": "user"})
            assert created.status_code == 201
            assert created.json()["username"] == "learner"
            assert client.get("/api/v1/admin/users").status_code == 200

            assert client.post("/api/v1/auth/logout").status_code == 204
            learner_login = client.post("/api/v1/auth/login", json={"username": "learner", "password": "learner-password"})
            assert learner_login.status_code == 200
            assert client.get("/api/v1/certifications").status_code == 200
            assert client.get("/api/v1/admin/users").status_code == 403
    finally:
        app.dependency_overrides.clear()

    with session_factory() as db:
        users = list(db.scalars(select(User).order_by(User.username)))
        assert [(user.username, user.role) for user in users] == [("admin", "admin"), ("learner", "user")]
