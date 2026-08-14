from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi import HTTPException
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable

from app.api.v1.auth import (
    current_user,
    expected_challenge,
    require_admin,
    require_ceremony,
    session_identity,
)
from app.core.config import Settings, get_settings
from app.db.base import Base, utcnow
from app.db.session import get_db
from app.main import app
from app.models.entities import AuthSession, PasskeyCredential, User


def test_passkey_credential_id_is_mysql_indexable() -> None:
    ddl = str(CreateTable(PasskeyCredential.__table__).compile(dialect=mysql.dialect()))

    assert "credential_id VARBINARY(1024)" in ddl
from app.services.auth import hash_password


def test_managed_user_must_register_then_authenticate_with_one_passkey(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        db.add(User(username="learner", password_hash=hash_password("temporary-password")))
        db.commit()

    def override_db() -> Iterator[Session]:
        with factory() as db:
            yield db

    settings = Settings(
        database_url="sqlite://",
        database_host="",
        database_name="",
        database_user="",
        database_password="",
        frontend_origin="https://exam.example.com",
        passkey_rp_id="exam.example.com",
        passkey_rp_name="CertExam",
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings

    registration = type(
        "Registration",
        (),
        {
            "credential_id": b"credential-one",
            "credential_public_key": b"public-key",
            "sign_count": 1,
            "credential_device_type": "single_device",
            "credential_backed_up": False,
        },
    )()
    authentication = type("Authentication", (), {"new_sign_count": 2})()
    monkeypatch.setattr("app.services.passkeys.verify_registration", lambda **_: registration)
    monkeypatch.setattr("app.services.passkeys.verify_authentication", lambda **_: authentication)

    try:
        with TestClient(app, client=("198.51.100.61", 50000)) as client:
            initial = client.post(
                "/api/v1/auth/login",
                json={"username": "learner", "password": "temporary-password"},
            )
            assert initial.status_code == 200
            assert initial.json()["passkey_registration_required"] is True
            assert client.get("/api/v1/certifications").status_code == 403

            options = client.post("/api/v1/auth/passkeys/registration/options")
            assert options.status_code == 200
            assert options.json()["rp"]["name"] == "CertExam"
            monkeypatch.setattr(
                "app.services.passkeys.verify_registration",
                lambda **_: (_ for _ in ()).throw(ValueError("invalid attestation")),
            )
            assert client.post(
                "/api/v1/auth/passkeys/registration/verify",
                json={"credential": {"id": "invalid"}},
            ).status_code == 400
            monkeypatch.setattr("app.services.passkeys.verify_registration", lambda **_: registration)
            registered = client.post(
                "/api/v1/auth/passkeys/registration/verify",
                json={"credential": {"id": "Y3JlZGVudGlhbC1vbmU"}},
            )
            assert registered.status_code == 200
            assert registered.json()["passkey_registered"] is True
            assert registered.json()["passkey_registration_required"] is False
            assert client.get("/api/v1/certifications").status_code == 200

            first_cookie = client.cookies.get("certexam_session")
            client.cookies.clear()
            pending = client.post(
                "/api/v1/auth/login",
                json={"username": "learner", "password": "temporary-password"},
            )
            assert pending.json()["passkey_authentication_required"] is True
            assert client.get("/api/v1/certifications").status_code == 403
            assert client.post("/api/v1/auth/passkeys/authentication/options").status_code == 200
            assert client.post(
                "/api/v1/auth/passkeys/authentication/verify",
                json={"credential": {"id": "wrong-credential"}},
            ).status_code == 400
            monkeypatch.setattr(
                "app.services.passkeys.verify_authentication",
                lambda **_: (_ for _ in ()).throw(ValueError("invalid signature")),
            )
            assert client.post(
                "/api/v1/auth/passkeys/authentication/verify",
                json={"credential": {"id": "Y3JlZGVudGlhbC1vbmU"}},
            ).status_code == 401
            monkeypatch.setattr("app.services.passkeys.verify_authentication", lambda **_: authentication)
            verified = client.post(
                "/api/v1/auth/passkeys/authentication/verify",
                json={"credential": {"id": "Y3JlZGVudGlhbC1vbmU"}},
            )
            assert verified.status_code == 200
            assert verified.json()["passkey_authentication_required"] is False
            assert client.get("/api/v1/certifications").status_code == 200

            with factory() as db:
                credential = db.scalar(select(PasskeyCredential))
                assert credential is not None
                assert credential.sign_count == 2
                old = db.scalar(
                    select(AuthSession).where(
                        AuthSession.token_hash.is_not(None),
                        AuthSession.revoked_at.is_not(None),
                    )
                )
                assert old is not None

            client.cookies.clear()
            client.cookies.set("certexam_session", first_cookie)
            assert client.get("/api/v1/auth/me").status_code == 401
    finally:
        app.dependency_overrides.clear()


def test_admin_can_reset_a_users_passkey_and_remains_password_only() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        learner = User(username="learner", password_hash=hash_password("temporary-password"))
        db.add(learner)
        db.flush()
        db.add(
            PasskeyCredential(
                user_id=learner.id,
                credential_id=b"credential",
                public_key=b"public-key",
                sign_count=0,
                transports_json=["internal"],
            )
        )
        db.add(
            AuthSession(
                user_id=learner.id,
                token_hash="a" * 64,
                purpose="full",
                expires_at=utcnow() + timedelta(minutes=30),
            )
        )
        db.commit()

    def override_db() -> Iterator[Session]:
        with factory() as db:
            yield db

    settings = Settings(
        database_url="sqlite://",
        database_host="",
        database_name="",
        database_user="",
        database_password="",
        initial_admin_password="strong-admin-password",
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app, client=("198.51.100.62", 50000)) as client:
            admin = client.post(
                "/api/v1/auth/login",
                json={"username": "admin", "password": "strong-admin-password"},
            )
            assert admin.status_code == 200
            assert admin.json()["passkey_registration_required"] is False
            learner_id = client.get("/api/v1/admin/users").json()[0]["id"]
            reset = client.delete(f"/api/v1/admin/users/{learner_id}/passkey")
            assert reset.status_code == 204
            assert client.delete("/api/v1/admin/users/999999/passkey").status_code == 404

        with factory() as db:
            assert db.scalar(select(PasskeyCredential)) is None
            learner_id = db.scalar(select(User.id).where(User.username == "learner"))
            assert db.scalar(
                select(AuthSession.revoked_at).where(AuthSession.user_id == learner_id)
            ) is not None
    finally:
        app.dependency_overrides.clear()


def test_passkey_auth_helpers_reject_invalid_or_expired_stages() -> None:
    disabled = Settings(auth_required=False)
    assert session_identity(None, disabled, None) is None
    assert current_user(None, disabled) is None
    assert require_admin(None, disabled) is None
    with pytest.raises(HTTPException) as missing:
        require_ceremony(None, "passkey_registration")
    assert missing.value.status_code == 401

    user = User(id=1, username="learner", password_hash="hash", role="user")
    wrong_stage = AuthSession(
        id=1, user_id=1, token_hash="a" * 64, purpose="full",
        expires_at=utcnow() + timedelta(minutes=30),
    )
    with pytest.raises(HTTPException) as invalid_stage:
        require_ceremony((wrong_stage, user), "passkey_registration")
    assert invalid_stage.value.status_code == 409

    wrong_stage.challenge = "AQ"
    wrong_stage.challenge_type = "registration"
    wrong_stage.challenge_expires_at = utcnow() - timedelta(seconds=1)
    with pytest.raises(HTTPException) as expired:
        expected_challenge(wrong_stage, "registration")
    assert expired.value.status_code == 409
