from app.core.config import Settings
from app.services import passkeys


def test_passkey_service_derives_local_rp_and_verifies_both_ceremonies(monkeypatch) -> None:
    settings = Settings(
        frontend_origin="http://localhost:5173/", passkey_rp_id="", passkey_rp_name="합격비서"
    )
    assert passkeys.relying_party_id(settings) == "localhost"
    assert passkeys.expected_origin(settings) == "http://localhost:5173"

    registration_calls = {}
    authentication_calls = {}
    monkeypatch.setattr(
        passkeys,
        "verify_registration_response",
        lambda **kwargs: registration_calls.update(kwargs) or "registered",
    )
    monkeypatch.setattr(
        passkeys,
        "verify_authentication_response",
        lambda **kwargs: authentication_calls.update(kwargs) or "authenticated",
    )

    assert passkeys.verify_registration(settings, {"id": "credential"}, b"challenge") == "registered"
    assert registration_calls["expected_rp_id"] == "localhost"
    assert registration_calls["require_user_verification"] is True
    assert passkeys.verify_authentication(
        settings, {"id": "credential"}, b"challenge", b"public-key", 3
    ) == "authenticated"
    assert authentication_calls["credential_current_sign_count"] == 3
    assert authentication_calls["require_user_verification"] is True


def test_authentication_uses_discoverable_passkey_selection() -> None:
    settings = Settings(frontend_origin="http://localhost:5173", passkey_rp_id="localhost")

    options = passkeys.authentication_options(settings, b"challenge")

    assert options["rpId"] == "localhost"
    assert options["userVerification"] == "required"
    assert "allowCredentials" not in options


def test_registration_prefers_the_current_devices_platform_authenticator() -> None:
    settings = Settings(frontend_origin="https://exam.example.com", passkey_rp_id="exam.example.com")

    options = passkeys.registration_options(settings, "learner", 7, b"challenge")

    selection = options["authenticatorSelection"]
    assert selection["authenticatorAttachment"] == "platform"
    assert selection["residentKey"] == "required"
    assert selection["requireResidentKey"] is True
    assert selection["userVerification"] == "required"
