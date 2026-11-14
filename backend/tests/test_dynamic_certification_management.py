from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.entities import (
    Certification,
    Domain,
    MockExam,
    Question,
    QuestionAnswerVersion,
    QuestionChoice,
    QuestionReport,
)


def test_problem_management_and_mock_exams_follow_the_selected_certification() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    factory = sessionmaker(bind=engine)
    with factory() as db:
        dea = Certification(
            certification_code="DEA-C01", name_en="AWS DEA", name_ko="AWS 데이터",
            exam_version="DEA-C01", default_question_count=1,
            default_duration_minutes=10, passing_score=70,
        )
        snow = Certification(
            certification_code="SNOW-CORE", name_en="SnowPro Core", name_ko="스노우프로 코어",
            exam_version="SNOW-CORE", default_question_count=5,
            default_duration_minutes=115, passing_score=750,
        )
        db.add_all([dea, snow])
        db.flush()
        dea_domain = Domain(
            certification_id=dea.id, domain_code="DEA-D1", name_en="AWS Domain",
            name_ko="AWS 단원", exam_weight=100, sort_order=1,
        )
        snow_storage = Domain(
            certification_id=snow.id, domain_code="SNOW-STORAGE", name_en="Storage",
            name_ko="스토리지", exam_weight=60, sort_order=1,
        )
        snow_security = Domain(
            certification_id=snow.id, domain_code="SNOW-SECURITY", name_en="Security",
            name_ko="보안", exam_weight=40, sort_order=2,
        )
        db.add_all([dea_domain, snow_storage, snow_security])
        db.flush()

        def add_question(
            uid: str, certification: Certification, domain: Domain,
            verification_status: str = "verified",
        ) -> Question:
            question = Question(
                question_uid=uid, certification_id=certification.id, domain_id=domain.id,
                question_type="multiple_choice", question_en=uid, question_ko=uid,
                content_hash=uid.lower(), verification_status=verification_status,
                choices=[QuestionChoice(choice_key="A", text_en="A", sort_order=1)],
                answer_versions=[QuestionAnswerVersion(
                    answer_source="admin_final", answers_json=["A"], is_current=True,
                )],
            )
            db.add(question)
            db.flush()
            return question

        dea_question = add_question("DEA-ONLY", dea, dea_domain)
        snow_questions = [
            add_question(f"SNOW-STORAGE-{index}", snow, snow_storage)
            for index in range(3)
        ] + [
            add_question(f"SNOW-SECURITY-{index}", snow, snow_security)
            for index in range(2)
        ]
        excluded_question = add_question(
            "SNOW-STORAGE-EXCLUDED", snow, snow_storage, "needs_review",
        )
        db.add_all([
            QuestionReport(question_id=dea_question.id, report_type="other", description="AWS 신고"),
            QuestionReport(question_id=snow_questions[0].id, report_type="other", description="Snow 신고"),
        ])
        db.commit()
        snow_id = snow.id

    def override_db() -> Iterator[Session]:
        with factory() as db:
            yield db

    settings = Settings(
        database_url="sqlite://", database_host="", database_name="",
        database_user="", database_password="", auth_required=False,
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            report = client.get(
                "/api/v1/admin/classification/report",
                params={"certification_code": "SNOW-CORE"},
            )
            assert report.status_code == 200
            assert report.json()["domains"] == [
                {"domain_code": "SNOW-STORAGE", "name_ko": "스토리지", "name_en": "Storage", "total_count": 4, "excluded_count": 1, "available_count": 3},
                {"domain_code": "SNOW-SECURITY", "name_ko": "보안", "name_en": "Security", "total_count": 2, "excluded_count": 0, "available_count": 2},
            ]

            readiness = client.get(
                "/api/v1/admin/mock-exam-readiness",
                params={"certification_code": "SNOW-CORE"},
            )
            assert readiness.status_code == 200
            assert readiness.json()["ready"] is True
            assert readiness.json()["question_count"] == 5
            assert [item["required"] for item in readiness.json()["domains"]] == [3, 2]
            assert [item["name_ko"] for item in readiness.json()["domains"]] == ["스토리지", "보안"]

            reports = client.get(
                "/api/v1/admin/reports", params={"certification_code": "SNOW-CORE"}
            )
            assert [item["description"] for item in reports.json()] == ["Snow 신고"]

            created = client.post(
                "/api/v1/mock-exams", json={"certification_code": "SNOW-CORE", "seed": 7}
            )
            assert created.status_code == 201
            study = client.post(
                "/api/v1/study/sessions",
                json={"certification_code": "SNOW-CORE", "mode": "random", "question_count": 5, "seed": 7},
            )
            assert study.status_code == 201
            assert excluded_question.id not in study.json()["question_ids"]
            assert client.get(
                "/api/v1/admin/mock-exam-readiness",
                params={"certification_code": "MISSING"},
            ).status_code == 404

        with factory() as db:
            exam = db.scalar(select(MockExam).where(MockExam.certification_id == snow_id))
            assert exam is not None
            assert exam.question_count == 5
            assert exam.duration_minutes == 115
    finally:
        app.dependency_overrides.clear()
