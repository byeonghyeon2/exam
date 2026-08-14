from pathlib import Path

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.auth import current_user
from app.api.v1.router import may_access_explanation
from app.core.config import Settings
from app.core.http_security import FixedWindowRateLimiter
from app.db.base import Base, utcnow
from app.db.session import get_db
from app.main import create_app
from app.models.entities import (
    Certification,
    Domain,
    MockExam,
    MockExamQuestion,
    Question,
    QuestionExplanation,
    StudyAttempt,
    User,
)


def settings_for(environment: str = "development", **overrides: object) -> Settings:
    values: dict[str, object] = {
        "app_env": environment,
        "database_url": "sqlite://",
        "database_host": "",
        "database_name": "",
        "database_user": "",
        "database_password": "",
        "auth_required": False,
        "question_rate_limit_requests": 120,
        "question_rate_limit_window_seconds": 60,
    }
    values.update(overrides)
    return Settings(**values)


def test_api_documentation_is_available_locally_but_hidden_in_production() -> None:
    with TestClient(create_app(settings_for())) as client:
        assert client.get("/docs").status_code == 200
        assert client.get("/openapi.json").status_code == 200

    with TestClient(create_app(settings_for("production"))) as client:
        assert client.get("/docs").status_code == 404
        assert client.get("/redoc").status_code == 404
        assert client.get("/openapi.json").status_code == 404


def test_api_responses_disable_storage_and_enable_browser_security_headers() -> None:
    with TestClient(create_app(settings_for())) as client:
        response = client.get("/api/v1/health")

    assert response.status_code == 200
    assert response.headers["cache-control"] == "no-store, max-age=0"
    assert response.headers["pragma"] == "no-cache"
    assert response.headers["x-content-type-options"] == "nosniff"
    assert response.headers["x-frame-options"] == "DENY"
    assert response.headers["referrer-policy"] == "no-referrer"
    assert response.headers["permissions-policy"] == "camera=(), microphone=(), geolocation=()"


def test_problem_data_rate_limit_is_scoped_by_client_and_returns_retry_after() -> None:
    app = create_app(settings_for(question_rate_limit_requests=2))
    with TestClient(app, client=("198.51.100.10", 50000)) as first_client:
        assert first_client.get("/api/v1/study/sessions/not-found").status_code != 429
        assert first_client.get("/api/v1/study/sessions/not-found").status_code != 429
        limited = first_client.get("/api/v1/study/sessions/not-found")
        assert limited.status_code == 429
        assert int(limited.headers["retry-after"]) >= 1
        assert limited.headers["cache-control"] == "no-store, max-age=0"

    with TestClient(app, client=("198.51.100.11", 50000)) as second_client:
        assert second_client.get("/api/v1/study/sessions/not-found").status_code != 429


def test_rate_limit_only_honors_forwarded_client_ip_from_configured_proxy() -> None:
    trusted_app = create_app(settings_for(
        question_rate_limit_requests=2,
        proxy_trusted_ips=",invalid-network,127.0.0.1",
    ))
    with TestClient(trusted_app, client=("127.0.0.1", 50000)) as client:
        first = client.get(
            "/api/v1/study/sessions/not-found", headers={"X-Real-IP": "198.51.100.20"}
        )
        second = client.get(
            "/api/v1/study/sessions/not-found", headers={"X-Real-IP": "198.51.100.21"}
        )
        assert first.status_code != 429
        assert second.status_code != 429
        assert client.get(
            "/api/v1/study/sessions/not-found", headers={"X-Real-IP": "invalid-address"}
        ).status_code != 429

    untrusted_app = create_app(settings_for(
        question_rate_limit_requests=1,
        proxy_trusted_ips="192.0.2.1",
    ))
    with TestClient(untrusted_app, client=("127.0.0.1", 50000)) as client:
        assert client.get(
            "/api/v1/study/sessions/not-found", headers={"X-Real-IP": "198.51.100.30"}
        ).status_code != 429
        assert client.get(
            "/api/v1/study/sessions/not-found", headers={"X-Real-IP": "198.51.100.31"}
        ).status_code == 429

    with TestClient(untrusted_app, client=("not-an-ip", 50000)) as client:
        assert client.get(
            "/api/v1/study/sessions/not-found", headers={"X-Real-IP": "198.51.100.40"}
        ).status_code != 429


def test_health_and_login_are_not_counted_as_problem_data_requests() -> None:
    app = create_app(settings_for(question_rate_limit_requests=1))
    with TestClient(app) as client:
        assert client.get("/api/v1/health").status_code == 200


def test_login_and_passkey_endpoints_have_a_separate_brute_force_limit() -> None:
    app = create_app(settings_for(auth_rate_limit_requests=1))
    with TestClient(app, client=("198.51.100.50", 50000)) as client:
        assert client.post("/api/v1/auth/login", json={}).status_code != 429
        limited = client.post("/api/v1/auth/login", json={})
        assert limited.status_code == 429
        assert int(limited.headers["retry-after"]) >= 1

    with TestClient(app, client=("198.51.100.51", 50000)) as other_client:
        assert other_client.post("/api/v1/auth/passkeys/registration/options").status_code != 429
        assert client.get("/api/v1/health").status_code == 200


def test_rate_limiter_expires_old_events_and_also_fingerprints_session_cookie() -> None:
    limiter = FixedWindowRateLimiter(limit=1, window_seconds=10)
    assert limiter.consume("ip:test", now=1) == (True, 0)
    assert limiter.consume("ip:test", now=2) == (False, 9)
    assert limiter.consume("ip:test", now=11) == (True, 0)

    app = create_app(settings_for(question_rate_limit_requests=2))
    with TestClient(app) as client:
        client.cookies.set("certexam_session", "opaque-secret-token")
        assert client.get("/api/v1/study/sessions/not-found").status_code != 429


def test_unhandled_api_error_is_sanitized_and_keeps_security_headers() -> None:
    app = create_app(settings_for())

    @app.get("/api/v1/crash")
    def crash() -> None:
        raise RuntimeError("sensitive internal detail")

    with TestClient(app) as client:
        response = client.get("/api/v1/crash")

    assert response.status_code == 500
    assert response.json()["detail"] == "Internal server error"
    assert "sensitive" not in response.text
    assert response.headers["cache-control"] == "no-store, max-age=0"


def test_explanation_requires_this_users_submitted_answer_with_admin_exception() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        learner = User(username="learner", password_hash="hash", role="user")
        other = User(username="other", password_hash="hash", role="user")
        admin = User(username="admin", password_hash="hash", role="admin")
        db.add_all([learner, other, admin])
        db.flush()

        assert may_access_explanation(db, learner, 42) is False
        assert may_access_explanation(db, admin, 42) is True

        db.add(StudyAttempt(
            user_id=other.id,
            session_id="other-session",
            question_id=42,
            selected_answers_json=["A"],
            is_correct=False,
        ))
        db.flush()
        assert may_access_explanation(db, learner, 42) is False

        db.add(StudyAttempt(
            user_id=learner.id,
            session_id="learner-session",
            question_id=42,
            selected_answers_json=["B"],
            is_correct=True,
        ))
        db.flush()
        assert may_access_explanation(db, learner, 42) is True


def test_mock_answer_only_unlocks_explanation_after_exam_submission() -> None:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        learner = User(username="learner", password_hash="hash", role="user")
        db.add(learner)
        db.flush()
        exam = MockExam(
            user_id=learner.id,
            certification_id=1,
            status="in_progress",
            question_count=1,
            duration_minutes=10,
            expires_at=utcnow(),
            passing_score=70,
        )
        db.add(exam)
        db.flush()
        db.add(MockExamQuestion(
            mock_exam_id=exam.id,
            question_id=77,
            question_order=1,
            selected_answers_json=["A"],
            answered_at=utcnow(),
        ))
        db.flush()

        assert may_access_explanation(db, learner, 77) is False
        exam.status = "submitted"
        exam.submitted_at = utcnow()
        db.flush()
        assert may_access_explanation(db, learner, 77) is True


def test_explanation_endpoints_enforce_answer_ownership() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    session_factory = sessionmaker(bind=engine)
    with session_factory() as db:
        learner = User(username="learner", password_hash="hash", role="user")
        certification = Certification(
            certification_code="DEA-C01", name_en="DEA", name_ko="DEA",
            exam_version="DEA-C01", default_question_count=1,
            default_duration_minutes=10, passing_score=70,
        )
        db.add_all([learner, certification])
        db.flush()
        domain = Domain(
            certification_id=certification.id, domain_code="DEA-D1",
            name_en="Domain", name_ko="Domain", exam_weight=100,
        )
        db.add(domain)
        db.flush()
        question = Question(
            question_uid="SECURITY-Q1", certification_id=certification.id,
            domain_id=domain.id, question_type="multiple_choice",
            question_en="Question", question_ko="Question", content_hash="security-q1",
        )
        db.add(question)
        db.flush()
        db.add(QuestionExplanation(
            question_id=question.id, language="ko", correct_answer_summary="summary",
            core_reason="reason", related_concepts="concepts", exam_traps="traps",
            memory_summary="memory", generation_status="complete",
        ))
        db.commit()
        learner_id, question_id = learner.id, question.id

    def override_db():
        with session_factory() as db:
            yield db

    def override_user():
        with session_factory() as db:
            return db.get(User, learner_id)

    settings = settings_for(auth_required=True)
    app = create_app(settings)
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[current_user] = override_user
    from app.core.config import get_settings
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            path = f"/api/v1/questions/{question_id}/explanation"
            assert client.get(path).status_code == 404
            assert client.post(f"{path}/generate", json={"language": "ko"}).status_code == 404

            with session_factory() as db:
                db.add(StudyAttempt(
                    user_id=learner_id, session_id="submitted", question_id=question_id,
                    selected_answers_json=["A"], is_correct=False,
                ))
                db.commit()

            assert client.get(path).status_code == 200
            assert client.post(f"{path}/generate", json={"language": "ko"}).status_code == 200
    finally:
        app.dependency_overrides.clear()


def test_production_build_and_nginx_keep_problem_data_out_of_caches_and_rate_limit() -> None:
    root = Path(__file__).resolve().parents[2]
    vite_config = (root / "frontend" / "vite.config.ts").read_text(encoding="utf-8")
    nginx_config = (root / "deploy" / "nginx" / "exam.conf.example").read_text(encoding="utf-8")

    assert "sourcemap:false" in vite_config.replace(" ", "")
    assert "limit_req_zone" in nginx_config
    assert "limit_req zone=exam_api_per_ip" in nginx_config
    assert 'add_header Cache-Control "no-store, max-age=0" always;' in nginx_config
    assert "Content-Security-Policy" in nginx_config
    assert "connect-src 'self'" in nginx_config
    assert 'add_header Cache-Control "no-cache" always;' in nginx_config
