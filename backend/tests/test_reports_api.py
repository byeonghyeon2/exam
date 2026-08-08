from collections.abc import Iterator

import pytest
from fastapi.testclient import TestClient
from pydantic import ValidationError
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.entities import Certification, Domain, Question, QuestionReport
from app.schemas.api import ReportCreate


def test_report_is_stored_and_returned_with_question_context() -> None:
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)

    with session_factory() as db:
        certification = Certification(
            certification_code="DEA-C01",
            name_en="AWS Data Engineer",
            name_ko="AWS 데이터 엔지니어",
            exam_version="DEA-C01",
            default_question_count=65,
            default_duration_minutes=130,
            passing_score=720,
        )
        db.add(certification)
        db.flush()
        domain = Domain(
            certification_id=certification.id,
            domain_code="DEA-D1",
            name_en="Data ingestion",
            name_ko="데이터 수집",
            exam_weight=34,
        )
        db.add(domain)
        db.flush()
        question = Question(
            question_uid="DEA-REPORT-1",
            certification_id=certification.id,
            domain_id=domain.id,
            question_type="multiple_choice",
            question_en="Which answer is correct?",
            question_ko="어떤 답이 맞습니까?",
            content_hash="report-test-hash",
        )
        db.add(question)
        db.commit()
        question_id = question.id

    def override_db() -> Iterator[Session]:
        with session_factory() as db:
            yield db

    settings = Settings(
        database_url="sqlite://",
        database_host="",
        database_name="",
        database_user="",
        database_password="",
        admin_access_key="test-admin",
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings

    try:
        with TestClient(app) as client:
            created = client.post(
                f"/api/v1/questions/{question_id}/reports",
                json={"report_type": "wrong_answer", "description": "정답이 이상한 것 같음"},
            )
            assert created.status_code == 201

            reports = client.get(
                "/api/v1/admin/reports",
                headers={"X-Admin-Key": "test-admin"},
            )
            assert reports.status_code == 200
            assert reports.json()[0] == {
                "id": created.json()["id"],
                "question_id": question_id,
                "question_uid": "DEA-REPORT-1",
                "question_ko": "어떤 답이 맞습니까?",
                "question_en": "Which answer is correct?",
                "report_type": "wrong_answer",
                "description": "정답이 이상한 것 같음",
                "status": "received",
                "resolution_note": None,
                "created_at": reports.json()[0]["created_at"],
                "resolved_at": None,
            }
    finally:
        app.dependency_overrides.clear()

    with session_factory() as db:
        stored = db.scalar(select(QuestionReport))
        assert stored is not None
        assert stored.description == "정답이 이상한 것 같음"
        stored_question = db.get(Question, question_id)
        assert stored_question is not None
        assert stored_question.is_reported is True


def test_report_requires_description() -> None:
    with pytest.raises(ValidationError):
        ReportCreate(report_type="wrong_answer", description="")
