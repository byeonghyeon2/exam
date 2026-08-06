from typing import Any, Protocol

from app.core.config import Settings


class AIUnavailableError(RuntimeError):
    pass


class AIOutputError(RuntimeError):
    pass


class AIAdapter(Protocol):
    def explain(self, payload: dict[str, Any], language: str) -> dict[str, Any]: ...


class DisabledAIAdapter:
    def explain(self, payload: dict[str, Any], language: str) -> dict[str, Any]:
        raise AIUnavailableError("AI explanation is not configured. Set OPENAI_API_KEY and an explanation model.")


class OpenAIAdapter:
    def __init__(self, settings: Settings) -> None:
        from openai import OpenAI
        self.model = settings.openai_explanation_model or settings.openai_model
        self.client = OpenAI(api_key=settings.openai_api_key, timeout=settings.openai_timeout_seconds, max_retries=settings.openai_max_retries)

    def explain(self, payload: dict[str, Any], language: str) -> dict[str, Any]:
        from pydantic import BaseModel

        class Output(BaseModel):
            correct_answer_summary: str
            core_reason: str
            keywords: list[str]
            choice_analysis: dict[str, str]
            related_concepts: str
            exam_traps: str
            memory_summary: str

        response = self.client.responses.parse(model=self.model, input=[{"role": "system", "content": f"Explain only the supplied verified answer in {language}; never change it."}, {"role": "user", "content": str(payload)}], text_format=Output)
        if response.output_parsed is None:
            raise AIOutputError("AI returned no structured explanation")
        return response.output_parsed.model_dump()


def build_ai_adapter(settings: Settings) -> AIAdapter:
    if not settings.openai_api_key or not (settings.openai_explanation_model or settings.openai_model):
        return DisabledAIAdapter()
    return OpenAIAdapter(settings)

