from app.core.config import Settings
from app.services import passkeys


def test_passkey_service_derives_local_rp_and_verifies_both_ceremonies(monkeypatch) -> None:
    settings = Settings(
        frontend_origin="http://localhost:5173/", passkey_rp_id="", passkey_rp_name="CertExam"
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
