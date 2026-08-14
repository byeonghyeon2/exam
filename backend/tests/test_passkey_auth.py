import hashlib
from collections.abc import Iterator
from datetime import timedelta

import pytest
from fastapi import HTTPException, Response
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.dialects import mysql
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool
from sqlalchemy.schema import CreateTable

from app.api.v1 import auth as auth_api
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
from app.models.entities import AuthSession, PasskeyChallenge, PasskeyCredential, User
from app.schemas.api import PasskeyCredentialRequest
from app.services import auth as auth_service
from app.services import passkeys
from app.services.auth import create_session, hash_password


def test_passkey_credential_id_is_mysql_indexable() -> None:
    ddl = str(CreateTable(PasskeyCredential.__table__).compile(dialect=mysql.dialect()))

    assert "credential_id VARBINARY(1024)" in ddl


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
        passkey_rp_name="합격비서",
        auth_rate_limit_requests=1000,
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
            assert client.get("/api/v1/health").json() == {"status": "ok"}
            assert client.post(
                "/api/v1/auth/login",
                json={"username": "missing", "password": "temporary-password"},
            ).status_code == 401
            initial = client.post(
                "/api/v1/auth/login",
                json={"username": "learner", "password": "temporary-password"},
            )
            assert initial.status_code == 200
            assert initial.json()["passkey_registration_required"] is True
            assert client.get("/api/v1/certifications").status_code == 403

            options = client.post("/api/v1/auth/passkeys/registration/options")
            assert options.status_code == 200
            assert options.json()["rp"]["name"] == "합격비서"
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
            assert pending.status_code == 409
            assert pending.json()["detail"] == "등록된 계정입니다. Passkey로 로그인해주세요"

            # Password entry must not revoke the existing device. Revocation happens only
            # after a new device proves possession of the registered Passkey.
            client.cookies.set("certexam_session", first_cookie)
            assert client.get("/api/v1/certifications").status_code == 200
            client.cookies.clear()
            assert client.post(
                "/api/v1/auth/passkeys/authentication/verify",
                json={"credential": {"id": "Y3JlZGVudGlhbC1vbmU"}},
            ).status_code == 401

            authentication_options = client.post("/api/v1/auth/passkeys/authentication/options")
            assert authentication_options.status_code == 200
            assert "allowCredentials" not in authentication_options.json()
            assert client.cookies.get("certexam_passkey_challenge")
            assert client.post(
                "/api/v1/auth/passkeys/authentication/verify",
                json={"credential": {"id": "wrong-credential"}},
            ).status_code == 401

            # A ceremony token is single use, even when credential verification fails.
            assert client.post(
                "/api/v1/auth/passkeys/authentication/verify",
                json={"credential": {"id": "Y3JlZGVudGlhbC1vbmU"}},
            ).status_code == 401

            monkeypatch.setattr(
                "app.services.passkeys.verify_authentication",
                lambda **_: (_ for _ in ()).throw(ValueError("invalid signature")),
            )
            with TestClient(app, client=("198.51.100.64", 50000)) as signature_client:
                assert signature_client.post("/api/v1/auth/passkeys/authentication/options").status_code == 200
                assert signature_client.post(
                    "/api/v1/auth/passkeys/authentication/verify",
                    json={"credential": {"id": "Y3JlZGVudGlhbC1vbmU"}},
                ).status_code == 401
            monkeypatch.setattr("app.services.passkeys.verify_authentication", lambda **_: authentication)
            with TestClient(app, client=("198.51.100.65", 50000)) as success_client:
                assert success_client.post("/api/v1/auth/passkeys/authentication/options").status_code == 200
                verified = success_client.post(
                    "/api/v1/auth/passkeys/authentication/verify",
                    json={"credential": {"id": "Y3JlZGVudGlhbC1vbmU"}},
                )
                assert verified.status_code == 200
                assert verified.json()["passkey_authentication_required"] is False
                assert success_client.get("/api/v1/certifications").status_code == 200

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
                assert db.scalar(select(PasskeyChallenge).where(PasskeyChallenge.consumed_at.is_not(None)))

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

        with TestClient(app, client=("198.51.100.63", 50000)) as learner_client:
            new_registration = learner_client.post(
                "/api/v1/auth/login",
                json={"username": "learner", "password": "temporary-password"},
            )
            assert new_registration.status_code == 200
            assert new_registration.json()["passkey_registration_required"] is True
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


def test_authentication_edge_cases_and_auth_module_coverage(monkeypatch) -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    settings = Settings(
        database_url="sqlite://", database_host="", database_name="",
        database_user="", database_password="", frontend_origin="https://exam.example.com",
        passkey_rp_id="exam.example.com",
    )
    with factory() as db:
        user = User(username="edge-user", password_hash=hash_password("temporary-password"))
        db.add(user)
        db.commit()
        db.refresh(user)

        with pytest.raises(HTTPException) as missing_user:
            auth_api.current_user(None, settings)
        assert missing_user.value.status_code == 401
        with pytest.raises(HTTPException) as missing_me:
            auth_api.me(None, db, settings)
        assert missing_me.value.status_code == 401
        with pytest.raises(HTTPException) as unknown_challenge:
            auth_api.consume_authentication_challenge(db, "unknown-token")
        assert unknown_challenge.value.status_code == 401

        session, _ = create_session(
            db, user, settings, purpose="passkey_registration", revoke_existing=False
        )
        credential = PasskeyCredential(
            user_id=user.id, credential_id=b"existing-key", public_key=b"public-key",
            transports_json=[],
        )
        db.add(credential)
        db.commit()
        assert auth_api.me((session, user), db, settings).username == "edge-user"
        with pytest.raises(HTTPException) as already_registered:
            auth_api.passkey_registration_options((session, user), db, settings)
        assert already_registered.value.status_code == 409

        session.challenge = "AQ"
        session.challenge_type = "registration"
        session.challenge_expires_at = utcnow() + timedelta(minutes=1)
        db.commit()
        duplicate = type(
            "Registration", (), {
                "credential_id": b"existing-key", "credential_public_key": b"public-key",
                "sign_count": 0, "credential_device_type": "single_device",
                "credential_backed_up": False,
            },
        )()
        monkeypatch.setattr(passkeys, "verify_registration", lambda **_: duplicate)
        with pytest.raises(HTTPException) as duplicate_key:
            auth_api.passkey_registration_verify(
                PasskeyCredentialRequest(credential={"id": "ZXhpc3Rpbmcta2V5"}),
                (session, user), db, settings,
            )
        assert duplicate_key.value.status_code == 409

        consume_challenge = auth_api.consume_authentication_challenge
        decode_challenge = auth_api.base64url_to_bytes
        monkeypatch.setattr(auth_api, "consume_authentication_challenge", lambda *_: b"challenge")
        monkeypatch.setattr(
            auth_api, "base64url_to_bytes", lambda _value: (_ for _ in ()).throw(ValueError()),
        )
        with pytest.raises(HTTPException) as malformed_id:
            auth_api.passkey_authentication_verify(
                PasskeyCredentialRequest(credential={"id": "malformed"}),
                Response(), db, settings, "challenge-token",
            )
        assert malformed_id.value.status_code == 401
        monkeypatch.setattr(auth_api, "consume_authentication_challenge", consume_challenge)
        monkeypatch.setattr(auth_api, "base64url_to_bytes", decode_challenge)

        db.add(PasskeyChallenge(
            token_hash=hashlib.sha256(b"expired-token").hexdigest(), challenge="AQ",
            expires_at=utcnow() - timedelta(seconds=1),
        ))
        db.commit()
        with pytest.raises(HTTPException) as expired_challenge:
            auth_api.consume_authentication_challenge(db, "expired-token")
        assert expired_challenge.value.status_code == 401


def test_password_session_and_webauthn_service_edge_cases(monkeypatch) -> None:
    encoded = hash_password("correct-password")
    assert auth_service.verify_password("correct-password", encoded) is True
    assert auth_service.verify_password("wrong-password", encoded) is False
    assert auth_service.verify_password("password", encoded.replace("pbkdf2_sha256", "unknown")) is False
    assert auth_service.verify_password("password", "malformed") is False

    settings = Settings(
        database_url="sqlite://", database_host="", database_name="",
        database_user="", database_password="", frontend_origin="https://exam.example.com/",
    )
    assert passkeys.relying_party_id(settings) == "exam.example.com"
    assert passkeys.expected_origin(settings) == "https://exam.example.com"
    configured = settings.model_copy(update={"passkey_rp_id": "rp.example.com"})
    assert passkeys.relying_party_id(configured) == "rp.example.com"
    invalid_origin = settings.model_copy(update={"frontend_origin": "not-a-url"})
    assert passkeys.relying_party_id(invalid_origin) == "localhost"

    monkeypatch.setattr(passkeys, "verify_registration_response", lambda **kwargs: kwargs)
    registration = passkeys.verify_registration(configured, {"id": "key"}, b"challenge")
    assert registration["expected_rp_id"] == "rp.example.com"
    assert registration["require_user_verification"] is True
    monkeypatch.setattr(passkeys, "verify_authentication_response", lambda **kwargs: kwargs)
    authentication = passkeys.verify_authentication(
        configured, {"id": "key"}, b"challenge", b"public", 3,
    )
    assert authentication["credential_current_sign_count"] == 3

    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    monkeypatch.setattr("app.db.session.SessionLocal", factory)
    assert auth_service.revoke_active_sessions() == 0
    with factory() as db:
        no_password = settings.model_copy(update={"initial_admin_password": ""})
        assert auth_service.bootstrap_admin(db, no_password) is False
        with_password = settings.model_copy(update={"initial_admin_password": "admin-password"})
        assert auth_service.bootstrap_admin(db, with_password) is True
        assert auth_service.bootstrap_admin(db, with_password) is False
        admin = db.scalar(select(User).where(User.role == "admin"))
        create_session(db, admin, with_password)
        db.commit()
    assert auth_service.revoke_active_sessions() == 1
