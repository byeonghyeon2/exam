from collections.abc import Iterator
from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.config import Settings, get_settings
from app.db.base import Base, utcnow
from app.db.session import get_db
from app.main import app
from app.models.entities import (
    Certification,
    Domain,
    MockExam,
    MockExamQuestion,
    PasskeyCredential,
    Question,
    StudyAttempt,
    StudySessionRecord,
    User,
    WrongNote,
)
from app.services.auth import create_session, hash_password


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
        auth_session_minutes=30,
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app, client=("198.51.100.60", 50000)) as client:
            cors = client.options(
                "/api/v1/certifications",
                headers={"Origin": "http://192.168.0.10:5173", "Access-Control-Request-Method": "GET"},
            )
            assert cors.status_code == 200
            assert cors.headers["access-control-allow-origin"] == "http://192.168.0.10:5173"
            assert client.get("/api/v1/certifications").status_code == 401
            logged_in = client.post("/api/v1/auth/login", json={"username": "admin", "password": "strong-admin-password"})
            assert logged_in.status_code == 200
            assert logged_in.json()["role"] == "admin"
            assert logged_in.json()["password_managed_by_environment"] is True
            assert logged_in.cookies.get("certexam_session")
            assert "HttpOnly" in logged_in.headers["set-cookie"]
            assert "SameSite=lax" in logged_in.headers["set-cookie"]
            assert "Secure" not in logged_in.headers["set-cookie"]
            assert "Max-Age=1800" in logged_in.headers["set-cookie"]

            created = client.post("/api/v1/admin/users", json={"username": "learner", "password": "learner-password", "role": "user"})
            assert created.status_code == 201
            assert created.json()["username"] == "learner"
            assert [user["username"] for user in client.get("/api/v1/admin/users").json()] == ["learner"]
            assert client.post("/api/v1/admin/users", json={"username": "learner", "password": "other-password", "role": "user"}).status_code == 409
            assert client.post("/api/v1/admin/users", json={"username": "second-admin", "password": "another-password", "role": "admin"}).status_code == 409

            with session_factory() as db:
                admin_user = db.scalar(select(User).where(User.username == "admin"))
                learner_user = db.scalar(select(User).where(User.username == "learner"))
                admin_question = db.scalar(select(Question).where(Question.question_uid == "ADMIN-WRONG"))
                learner_question = db.scalar(select(Question).where(Question.question_uid == "LEARNER-WRONG"))
                db.add_all([WrongNote(user_id=admin_user.id, question_id=admin_question.id, wrong_count=1), WrongNote(user_id=learner_user.id, question_id=learner_question.id, wrong_count=1)]); db.commit()

            assert client.patch(f"/api/v1/admin/users/{logged_in.json()['id']}", json={"password": "database-password"}).status_code == 409
            assert client.post("/api/v1/auth/logout").status_code == 204
            with session_factory() as db:
                admin_user = db.scalar(select(User).where(User.username == "admin"))
                admin_user.password_hash = hash_password("database-password")
                admin_user.is_active = False
                db.commit()
            environment_admin = client.post("/api/v1/auth/login", json={"username": "admin", "password": "strong-admin-password"})
            assert environment_admin.status_code == 200
            with session_factory() as db:
                assert db.scalar(select(User.is_active).where(User.username == "admin")) is True
            assert client.post("/api/v1/auth/logout").status_code == 204
            assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "database-password"}).status_code == 401

            learner_login = client.post("/api/v1/auth/login", json={"username": "learner", "password": "learner-password"})
            assert learner_login.status_code == 200
            assert learner_login.json()["password_managed_by_environment"] is False
            assert learner_login.json()["passkey_registration_required"] is True
            assert client.get("/api/v1/certifications").status_code == 403
            with session_factory() as db:
                learner_user = db.scalar(select(User).where(User.username == "learner"))
                _session, learner_token = create_session(db, learner_user, settings, purpose="full")
                db.commit()
            client.cookies.set("certexam_session", learner_token)
            assert client.get("/api/v1/certifications").status_code == 200
            assert client.get("/api/v1/admin/users").status_code == 403
            assert [note["question_uid"] for note in client.get("/api/v1/wrong-notes").json()] == ["LEARNER-WRONG"]

            assert client.post("/api/v1/auth/logout").status_code == 204
            client.cookies.clear()
            assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "strong-admin-password"}).status_code == 200
            assert [note["question_uid"] for note in client.get("/api/v1/wrong-notes").json()] == ["ADMIN-WRONG"]
            assert client.patch("/api/v1/admin/users/999999", json={"is_active": False}).status_code == 404
            updated = client.patch(
                f"/api/v1/admin/users/{learner_login.json()['id']}",
                json={"password": "updated-password", "is_active": False},
            )
            assert updated.status_code == 200
            assert updated.json()["is_active"] is False
            settings.auth_cookie_secure = True
            secure_login = client.post("/api/v1/auth/login", json={"username": "admin", "password": "strong-admin-password"})
            assert "Secure" in secure_login.headers["set-cookie"]
            secure_logout = client.post("/api/v1/auth/logout")
            assert "Secure" in secure_logout.headers["set-cookie"]
            settings.auth_cookie_secure = False
            assert client.post("/api/v1/auth/login", json={"username": "admin", "password": "strong-admin-password"}).status_code == 200
            with session_factory() as db:
                learner = db.scalar(select(User).where(User.username == "learner"))
                certification = db.scalar(select(Certification))
                question = db.scalar(select(Question).where(Question.question_uid == "LEARNER-WRONG"))
                db.add(StudySessionRecord(
                    session_id="delete-owned-study", user_id=learner.id,
                    certification_id=certification.id, question_ids_json=[question.id],
                ))
                db.add(StudyAttempt(
                    user_id=learner.id, session_id="delete-owned-study", question_id=question.id,
                    selected_answers_json=["A"], is_correct=False,
                ))
                exam = MockExam(
                    user_id=learner.id, certification_id=certification.id, question_count=1,
                    duration_minutes=10, expires_at=utcnow() + timedelta(minutes=10), passing_score=70,
                )
                db.add(exam)
                db.flush()
                db.add(MockExamQuestion(mock_exam_id=exam.id, question_id=question.id, question_order=1))
                db.add(PasskeyCredential(
                    user_id=learner.id, credential_id=b"delete-owned-key",
                    public_key=b"public-key", transports_json=["internal"],
                ))
                db.commit()
            assert client.delete(f"/api/v1/admin/users/{learner_login.json()['id']}").status_code == 204
            assert client.delete(f"/api/v1/admin/users/{logged_in.json()['id']}").status_code == 409
            assert client.delete("/api/v1/admin/users/999999").status_code == 404
    finally:
        app.dependency_overrides.clear()

    with session_factory() as db:
        users = list(db.scalars(select(User).order_by(User.username)))
        assert [(user.username, user.role) for user in users] == [("admin", "admin")]
        learner_question_id = db.scalar(
            select(Question.id).where(Question.question_uid == "LEARNER-WRONG")
        )
        assert learner_question_id is not None
        assert db.scalar(select(WrongNote).where(WrongNote.question_id == learner_question_id)) is None
        assert db.scalar(select(StudySessionRecord)) is None
        assert db.scalar(select(StudyAttempt)) is None
        assert db.scalar(select(MockExam)) is None
        assert db.scalar(select(MockExamQuestion)) is None
        assert db.scalar(select(PasskeyCredential)) is None
