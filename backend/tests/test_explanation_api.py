from collections.abc import Iterator
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import router as router_module
from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.entities import (
    Certification,
    Domain,
    Question,
    QuestionAnswerVersion,
    QuestionChoice,
    QuestionExplanation,
)


class FakeExplanationAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], str]] = []

    def explain(self, payload: dict[str, Any], language: str) -> dict[str, Any]:
        self.calls.append((payload, language))
        return {
            "correct_answer_summary": "C가 검증된 정답입니다.",
            "core_reason": "C만 요구사항을 충족합니다.",
            "keywords": ["AWS", "데이터"],
            "choice_analysis": {
                "A": "A는 다른 기능을 설명합니다.",
                "B": "B는 조건이 부족합니다.",
                "C": "C가 요구사항에 맞습니다.",
                "D": "D는 반대 방향의 동작입니다.",
            },
            "related_concepts": "관련 개념",
            "exam_traps": "비슷한 서비스 이름을 구분합니다.",
            "memory_summary": "요구사항과 서비스 기능을 연결합니다.",
        }


def test_generate_explanation_uses_verified_content_and_reuses_cache(monkeypatch: Any) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as db:
        certification = Certification(certification_code="DEA-C01", name_en="AWS Data Engineer", name_ko="AWS 데이터 엔지니어", exam_version="DEA-C01", default_question_count=65, default_duration_minutes=130, passing_score=720)
        db.add(certification); db.flush()
        domain = Domain(certification_id=certification.id, domain_code="DEA-D1", name_en="Ingestion", name_ko="수집", exam_weight=34)
        db.add(domain); db.flush()
        question = Question(
            question_uid="DEA-EXPLAIN-1", certification_id=certification.id, domain_id=domain.id,
            question_type="multiple_choice", question_en="Which choice is correct?", question_ko="어떤 선택지가 맞습니까?",
            verification_status="verified", content_hash="explanation-test-hash",
            choices=[QuestionChoice(choice_key=key, text_en=f"Choice {key}", text_ko=f"선택지 {key}", sort_order=index) for index, key in enumerate("ABCD")],
            answer_versions=[QuestionAnswerVersion(answer_source="admin_final", answers_json=["C"], is_current=True)],
        )
        db.add(question); db.commit(); question_id = question.id

    def override_db() -> Iterator[Session]:
        with session_factory() as db:
            yield db

    settings = Settings(database_url="sqlite://", database_host="", database_name="", database_user="", database_password="", openai_api_key="test-key", openai_explanation_model="test-model", auth_required=False)
    adapter = FakeExplanationAdapter()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(router_module, "build_ai_adapter", lambda _settings: adapter)
    try:
        with TestClient(app) as client:
            first = client.post(f"/api/v1/questions/{question_id}/explanation/generate", json={"language": "ko"})
            second = client.post(f"/api/v1/questions/{question_id}/explanation/generate", json={"language": "ko"})
            assert first.status_code == 200
            assert second.status_code == 200
            assert first.json()["choice_analysis_json"]["A"] == "A는 다른 기능을 설명합니다."
            with session_factory() as db:
                stored = db.scalar(select(QuestionExplanation))
                assert stored is not None
                stored.generation_status = "stale"
                db.commit()
            regenerated = client.post(f"/api/v1/questions/{question_id}/explanation/generate", json={"language": "ko"})
            assert regenerated.status_code == 200
    finally:
        app.dependency_overrides.clear()

    assert len(adapter.calls) == 2
    payload, language = adapter.calls[0]
    assert language == "ko"
    assert payload["question"] == {"ko": "어떤 선택지가 맞습니까?", "en": "Which choice is correct?"}
    assert payload["choices"]["A"] == {"ko": "선택지 A", "en": "Choice A"}
    assert payload["verified_answers"] == ["C"]
    with session_factory() as db:
        assert db.scalar(select(func.count(QuestionExplanation.id))) == 1
