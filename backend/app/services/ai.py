import json
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
        from openai import OpenAIError
        from pydantic import BaseModel

        class ChoiceAnalysis(BaseModel):
            choice_key: str
            explanation: str

        class Output(BaseModel):
            correct_answer_summary: str
            core_reason: str
            keywords: list[str]
            choice_analysis: list[ChoiceAnalysis]
            related_concepts: str
            exam_traps: str
            memory_summary: str

        system_prompt = f"""
You are an expert certification-exam tutor. Write the explanation in {language}.
Treat verified_answers as immutable ground truth; never propose or imply a different answer.
Explain why the verified answer solves the question, then analyze every choice by its key.
For an incorrect choice, state what it actually describes and what would need to change for it
to become appropriate. Keep each choice analysis concise and concrete. Do not invent facts that
are not supported by the supplied question and choices. Return every requested field.
""".strip()
        try:
            response = self.client.responses.parse(
                model=self.model,
                input=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": json.dumps(payload, ensure_ascii=False)},
                ],
                text_format=Output,
            )
        except OpenAIError as exc:
            raise AIUnavailableError(
                "OpenAI API request failed. Check the API key, explanation model, and network."
            ) from exc
        if response.output_parsed is None:
            raise AIOutputError("AI returned no structured explanation")
        result = response.output_parsed.model_dump()
        result["choice_analysis"] = {
            item["choice_key"]: item["explanation"]
            for item in result["choice_analysis"]
        }
        return result


def build_ai_adapter(settings: Settings) -> AIAdapter:
    if not settings.openai_api_key or not (settings.openai_explanation_model or settings.openai_model):
        return DisabledAIAdapter()
    return OpenAIAdapter(settings)
