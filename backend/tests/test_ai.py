import pytest

from app.core.config import Settings
from app.services.ai import AIUnavailableError, DisabledAIAdapter, build_ai_adapter


def test_missing_key_uses_safe_disabled_adapter() -> None:
    adapter = build_ai_adapter(Settings(database_url="sqlite://", openai_api_key="", openai_model=""))
    assert isinstance(adapter, DisabledAIAdapter)
    with pytest.raises(AIUnavailableError): adapter.explain({}, "ko")

