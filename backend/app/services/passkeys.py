import json
import secrets
from urllib.parse import urlparse

from webauthn import (
    generate_authentication_options,
    generate_registration_options,
    options_to_json,
    verify_authentication_response,
    verify_registration_response,
)
from webauthn.helpers.structs import (
    AuthenticatorAttachment,
    AuthenticatorSelectionCriteria,
    ResidentKeyRequirement,
    UserVerificationRequirement,
)

from app.core.config import Settings


def relying_party_id(settings: Settings) -> str:
    configured = settings.passkey_rp_id.strip()
    if configured:
        return configured
    return urlparse(settings.frontend_origin).hostname or "localhost"


def expected_origin(settings: Settings) -> str:
    return settings.frontend_origin.rstrip("/")


def new_challenge() -> bytes:
    return secrets.token_bytes(32)


def registration_options(settings: Settings, username: str, user_id: int, challenge: bytes) -> dict:
    options = generate_registration_options(
        rp_id=relying_party_id(settings),
        rp_name=settings.passkey_rp_name,
        user_id=str(user_id).encode(),
        user_name=username,
        user_display_name=username,
        challenge=challenge,
        authenticator_selection=AuthenticatorSelectionCriteria(
            authenticator_attachment=AuthenticatorAttachment.PLATFORM,
            resident_key=ResidentKeyRequirement.REQUIRED,
            require_resident_key=True,
            user_verification=UserVerificationRequirement.REQUIRED,
        ),
    )
    return json.loads(options_to_json(options))


def authentication_options(settings: Settings, challenge: bytes) -> dict:
    options = generate_authentication_options(
        rp_id=relying_party_id(settings),
        challenge=challenge,
        user_verification=UserVerificationRequirement.REQUIRED,
    )
    payload = json.loads(options_to_json(options))
    payload.pop("allowCredentials", None)
    return payload


def verify_registration(settings: Settings, credential: dict, challenge: bytes):
    return verify_registration_response(
        credential=credential,
        expected_challenge=challenge,
        expected_rp_id=relying_party_id(settings),
        expected_origin=expected_origin(settings),
        require_user_verification=True,
    )


def verify_authentication(
    settings: Settings,
    credential: dict,
    challenge: bytes,
    public_key: bytes,
    sign_count: int,
):
    return verify_authentication_response(
        credential=credential,
        expected_challenge=challenge,
        expected_rp_id=relying_party_id(settings),
        expected_origin=expected_origin(settings),
        credential_public_key=public_key,
        credential_current_sign_count=sign_count,
        require_user_verification=True,
    )
