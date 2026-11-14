from collections.abc import Iterator
from datetime import timedelta
from typing import Any

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1 import router as router_module
from app.api.v1.router import concept_summary_status
from app.core.config import Settings, get_settings
from app.db.base import Base, utcnow
from app.db.session import get_db
from app.main import app
from app.models.entities import AIConceptSummary, Certification, Domain, Question, StudyAttempt, StudySessionRecord


class FakeConceptSummaryAdapter:
    def __init__(self) -> None:
        self.calls: list[tuple[dict[str, Any], str]] = []

    def concept_summary(self, payload: dict[str, Any], language: str) -> dict[str, Any]:
        self.calls.append((payload, language))
        return {
            "overview": "수집 영역의 반복 오답을 먼저 정리하세요.",
            "weaknesses": [{"domain": "수집", "diagnosis": "반복 오답", "concepts": ["S3"], "actions": ["핵심 차이를 복습하세요."]}],
            "priority_concepts": ["S3"],
            "related_questions": [{"question_id": payload["wrong_choice_patterns"][0]["question_id"], "question_uid": payload["wrong_choice_patterns"][0]["question_uid"], "concept": "S3", "why_review": "반복 오답"}],
            "study_plan": ["S3를 복습하세요."],
            "memory_summary": "요구사항과 서비스를 연결하세요.",
        }


def test_pattern_analysis_requires_ten_completed_answers_and_uses_wrong_choice_patterns(monkeypatch: Any) -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as db:
        certification = Certification(certification_code="DEA-C01", name_en="AWS Data Engineer", name_ko="AWS 데이터 엔지니어", exam_version="DEA-C01", default_question_count=65, default_duration_minutes=130, passing_score=720)
        db.add(certification); db.flush()
        domain = Domain(certification_id=certification.id, domain_code="D1", name_en="Ingestion", name_ko="수집", exam_weight=100)
        db.add(domain); db.flush()
        questions = [Question(question_uid=f"DEA-{number}", certification_id=certification.id, domain_id=domain.id, question_type="multiple_choice", question_en=f"Question {number}", question_ko=f"문제 {number}", content_hash=f"concept-summary-{number}", verification_status="verified") for number in range(10)]
        db.add_all(questions); db.flush()
        question_ids = [question.id for question in questions]
        certification_id = certification.id
        db.commit()

    def add_completed_sessions(count: int, *, retry: bool, start: int = 0, future: bool = False) -> None:
        with session_factory() as db:
            for number in range(start, start + count):
                session_id = f"{'retry' if retry else 'study'}-{number}"
                completed_at = utcnow() + timedelta(minutes=number + 1) if future else utcnow() - timedelta(minutes=number + 1)
                db.add(StudySessionRecord(session_id=session_id, user_id=0, certification_id=certification_id, question_ids_json=question_ids, status="completed", completed_at=completed_at, retry_of_session_id="original" if retry else None))
                db.add_all([StudyAttempt(user_id=0, session_id=session_id, question_id=question_id, selected_answers_json=["B"], is_correct=False, wrong_note_processed=True) for question_id in question_ids])
            db.commit()

    def override_db() -> Iterator[Session]:
        with session_factory() as db:
            yield db

    settings = Settings(database_url="sqlite://", database_host="", database_name="", database_user="", database_password="", openai_api_key="test-key", openai_explanation_model="test-model", auth_required=False)
    adapter = FakeConceptSummaryAdapter()
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    monkeypatch.setattr(router_module, "build_ai_adapter", lambda _settings: adapter)
    try:
        with TestClient(app) as client:
            initial = client.get("/api/v1/wrong-notes/ai-concept-summary/DEA-C01").json()
            assert initial["can_generate"] is False
            assert initial["answer_count"] == 0
            assert client.post("/api/v1/wrong-notes/ai-concept-summary/DEA-C01").status_code == 409
            add_completed_sessions(1, retry=False)
            ready = client.get("/api/v1/wrong-notes/ai-concept-summary/DEA-C01")
            assert ready.status_code == 200
            assert ready.json()["answer_count"] == 10
            assert ready.json()["minimum_answer_count"] == 10
            assert ready.json()["can_generate"] is True
            generated = client.post("/api/v1/wrong-notes/ai-concept-summary/DEA-C01")
            assert generated.status_code == 200
            assert generated.json()["result"]["summary"]["overview"] == "수집 영역의 반복 오답을 먼저 정리하세요."
            assert generated.json()["can_generate"] is True
            refreshed = client.get("/api/v1/wrong-notes/ai-concept-summary/DEA-C01")
            assert refreshed.json()["answer_count"] == 10
            deleted = client.delete("/api/v1/study/history/study-0")
            assert deleted.status_code == 200
            assert client.get("/api/v1/study/history").json() == []
            assert client.get("/api/v1/wrong-notes/ai-concept-summary/DEA-C01").json()["answer_count"] == 10
            assert client.post("/api/v1/wrong-notes/ai-concept-summary/DEA-C01").status_code == 200
    finally:
        app.dependency_overrides.clear()

    assert len(adapter.calls) == 2
    assert adapter.calls[0][1] == "ko"
    assert adapter.calls[0][0]["answer_count"] == 10
    assert len(adapter.calls[0][0]["wrong_choice_patterns"]) <= 12
    assert adapter.calls[0][0]["wrong_choice_patterns"][0]["selected_answers"] == ["B"]
    with session_factory() as db:
        summary = db.scalar(select(AIConceptSummary))
        certification = db.scalar(select(Certification))
        assert summary is not None and certification is not None
        assert concept_summary_status(db, 999, certification).answer_count == 0
