from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base
from app.db.session import get_db
from app.main import app
from app.models.entities import Certification, Domain, Question, User, WrongNote


def test_admin_bootstrap_login_and_managed_user_access() -> None:
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as db:
        certification = Certification(certification_code="DEA-C01", name_en="AWS Data Engineer", name_ko="AWS 데이터 엔지니어", exam_version="DEA-C01", default_question_count=2, default_duration_minutes=10, passing_score=70)
        db.add(certification); db.flush()
        domain = Domain(certification_id=certification.id, domain_code="DEA-D1", name_en="Data ingestion", name_ko="데이터 수집", exam_weight=100)
        db.add(domain); db.flush()
        db.add_all([
            Question(question_uid="ADMIN-WRONG", certification_id=certification.id, domain_id=domain.id, question_type="multiple_choice", question_en="Admin question", question_ko="관리자 문제", content_hash="admin-wrong"),
            Question(question_uid="LEARNER-WRONG", certification_id=certification.id, domain_id=domain.id, question_type="multiple_choice", question_en="Learner question", question_ko="학습자 문제", content_hash="learner-wrong"),
        ]); db.commit()

    def override_db() -> Iterator[Session]:
        with session_factory() as db:
            yield db

    settings = Settings(
        database_url="sqlite://",
        database_host="",
        database_name="",
        database_user="",
        database_password="",
        initial_admin_username="admin",
        initial_admin_password="strong-admin-password",
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            assert client.get("/api/v1/certifications").status_code == 401
            logged_in = client.post("/api/v1/auth/login", json={"username": "admin", "password": "strong-admin-password"})
            assert logged_in.status_code == 200
            assert logged_in.json()["role"] == "admin"
            assert logged_in.cookies.get("certflow_session")

            created = client.post("/api/v1/admin/users", json={"username": "learner", "password": "learner-password", "role": "user"})
            assert created.status_code == 201
            assert created.json()["username"] == "learner"
            assert client.get("/api/v1/admin/users").status_code == 200

            with session_factory() as db:
                admin_user = db.scalar(select(User).where(User.username == "admin"))
                learner_user = db.scalar(select(User).where(User.username == "learner"))
                admin_question = db.scalar(select(Question).where(Question.question_uid == "ADMIN-WRONG"))
                learner_question = db.scalar(select(Question).where(Question.question_uid == "LEARNER-WRONG"))
                db.add_all([WrongNote(user_id=admin_user.id, question_id=admin_question.id, wrong_count=1), WrongNote(user_id=learner_user.id, question_id=learner_question.id, wrong_count=1)]); db.commit()

            assert client.post("/api/v1/auth/logout").status_code == 204
            learner_login = client.post("/api/v1/auth/login", json={"username": "learner", "password": "learner-password"})
            assert learner_login.status_code == 200
            assert client.get("/api/v1/certifications").status_code == 200
            assert client.get("/api/v1/admin/users").status_code == 403
            assert [note["question_uid"] for note in client.get("/api/v1/wrong-notes").json()] == ["LEARNER-WRONG"]

            assert client.post("/api/v1/auth/logout").status_code == 204
            assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "strong-admin-password"}).status_code == 200
            assert [note["question_uid"] for note in client.get("/api/v1/wrong-notes").json()] == ["ADMIN-WRONG"]
    finally:
        app.dependency_overrides.clear()

    with session_factory() as db:
        users = list(db.scalars(select(User).order_by(User.username)))
        assert [(user.username, user.role) for user in users] == [("admin", "admin"), ("learner", "user")]
