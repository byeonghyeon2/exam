from collections.abc import Iterator
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.auth import current_user
from app.core.config import Settings, get_settings
from app.db.base import Base, utcnow
from app.db.session import get_db
from app.main import app
from app.models.entities import (
    Certification,
    Domain,
    MockExam,
    MockExamQuestion,
    Question,
    QuestionAnswerVersion,
    QuestionChoice,
    User,
)


def test_mock_exam_delivers_only_one_owned_question_body_at_a_time() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        owner = User(username="owner", password_hash="hash", role="user")
        other = User(username="other", password_hash="hash", role="user")
        certification = Certification(
            certification_code="DEA-C01", name_en="DEA", name_ko="DEA",
            exam_version="DEA-C01", default_question_count=2,
            default_duration_minutes=10, passing_score=70,
        )
        db.add_all([owner, other, certification])
        db.flush()
        domain = Domain(
            certification_id=certification.id, domain_code="DEA-D1",
            name_en="Domain", name_ko="Domain", exam_weight=100,
        )
        db.add(domain)
        db.flush()
        questions = []
        for number in range(1, 4):
            question = Question(
                question_uid=f"SECURE-MOCK-{number}", certification_id=certification.id,
                domain_id=domain.id, question_type="multiple_choice",
                question_en=f"Secret question {number}", question_ko=f"비공개 문제 {number}",
                content_hash=f"secure-mock-{number}", verification_status="verified",
                choices=[QuestionChoice(choice_key="A", text_en="Choice", sort_order=1)],
                answer_versions=[QuestionAnswerVersion(
                    answer_source="admin_final", answers_json=["A"], is_current=True,
                )],
            )
            db.add(question)
            questions.append(question)
        db.flush()
        exam = MockExam(
            user_id=owner.id, certification_id=certification.id, question_count=2,
            duration_minutes=10, expires_at=utcnow() + timedelta(minutes=10), passing_score=70,
            questions=[
                MockExamQuestion(question_id=questions[0].id, question_order=1),
                MockExamQuestion(question_id=questions[1].id, question_order=2),
            ],
        )
        db.add(exam)
        abandoned_exam = MockExam(
            user_id=owner.id, certification_id=certification.id, question_count=1,
            duration_minutes=10, expires_at=utcnow() + timedelta(minutes=10), passing_score=70,
            questions=[MockExamQuestion(question_id=questions[2].id, question_order=1)],
        )
        db.add(abandoned_exam)
        db.commit()
        owner_id, other_id, exam_id, abandoned_exam_id = owner.id, other.id, exam.id, abandoned_exam.id
        assigned_ids = [questions[0].id, questions[1].id]
        unassigned_id = questions[2].id

    active_user_id = [owner_id]

    def override_db() -> Iterator[Session]:
        with factory() as db:
            yield db

    def override_user() -> User:
        with factory() as db:
            return db.get(User, active_user_id[0])  # type: ignore[return-value]

    settings = Settings(
        database_url="sqlite://", database_host="", database_name="",
        database_user="", database_password="", auth_required=False,
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = override_user
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            listing = client.get(f"/api/v1/mock-exams/{exam_id}/questions")
            assert listing.status_code == 200
            listing_data = listing.json()
            assert listing_data["total"] == 2
            assert listing_data["question_ids"] == assigned_ids
            assert listing_data["answers"] == {}
            assert listing_data["expires_at"].endswith("+00:00")
            assert "Secret question" not in listing.text
            assert "answers_json" not in listing.text

            single = client.get(
                f"/api/v1/mock-exams/{exam_id}/questions/{assigned_ids[0]}"
            )
            assert single.status_code == 200
            assert single.json()["question_en"] == "Secret question 1"
            assert "answer_versions" not in single.json()
            assert client.get(
                f"/api/v1/mock-exams/{exam_id}/questions/{unassigned_id}"
            ).status_code == 404

            assert client.post(f"/api/v1/mock-exams/{exam_id}/submit").status_code == 200
            assert client.get(f"/api/v1/mock-exams/{exam_id}/questions").status_code == 409
            assert client.get(
                f"/api/v1/mock-exams/{exam_id}/questions/{assigned_ids[0]}"
            ).status_code == 409

            assert client.post(f"/api/v1/mock-exams/{abandoned_exam_id}/leave").status_code == 200
            assert client.get(f"/api/v1/mock-exams/{abandoned_exam_id}/questions").status_code == 409

            active_user_id[0] = other_id
            assert client.get(f"/api/v1/mock-exams/{exam_id}/questions").status_code == 404
            assert client.get(
                f"/api/v1/mock-exams/{exam_id}/questions/{assigned_ids[0]}"
            ).status_code == 404
    finally:
        app.dependency_overrides.clear()
