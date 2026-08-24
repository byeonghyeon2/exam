from datetime import timedelta

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.v1.auth import current_user, reject_learner_during_maintenance, session_identity
from app.api.v1.notices import _validate_maintenance_overlap, update_notice
from app.api.v1.router import save_study_draft
from app.core.config import Settings, get_settings
from app.db.base import Base, utcnow
from app.db.session import get_db
from app.main import create_app
from app.models.entities import (
    AuthSession,
    Certification,
    Domain,
    MockExam,
    Notice,
    Question,
    QuestionAnswerVersion,
    QuestionChoice,
    StudyAttempt,
    StudySessionRecord,
    User,
    WrongNote,
)
from app.schemas.api import NoticeWrite, StudyDraftUpdate
from app.services.auth import hash_password
from app.services.maintenance import active_maintenance, enforce_active_maintenance


def _factory():
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    return sessionmaker(bind=engine, expire_on_commit=False)


def _notice_payload(now, **changes):
    payload = {
        "notice_type": "maintenance",
        "title": "정기 점검",
        "content": "점검 중입니다.",
        "display_start_at": now - timedelta(hours=1),
        "display_end_at": now + timedelta(hours=2),
        "maintenance_start_at": now,
        "maintenance_end_at": now + timedelta(hours=1),
        "maintenance_screen_enabled": True,
        "is_published": True,
    }
    payload.update(changes)
    return payload


def test_notice_schema_rejects_invalid_time_ranges_and_maintenance_shape() -> None:
    now = utcnow()
    with pytest.raises(ValueError, match="display_end_at"):
        NoticeWrite(**_notice_payload(now, display_end_at=now - timedelta(hours=1)))
    with pytest.raises(ValueError, match="maintenance_end_at"):
        NoticeWrite(**_notice_payload(now, maintenance_end_at=now))
    with pytest.raises(ValueError, match="maintenance screen"):
        NoticeWrite(**_notice_payload(now, notice_type="general", maintenance_screen_enabled=True))
    with pytest.raises(ValueError, match="maintenance dates"):
        NoticeWrite(
            **_notice_payload(
                now, maintenance_start_at=None, maintenance_end_at=None
            )
        )

    popup_only = NoticeWrite(
        **_notice_payload(
            now,
            maintenance_screen_enabled=False,
            maintenance_start_at=None,
            maintenance_end_at=None,
        )
    )
    assert popup_only.notice_type == "maintenance"
    assert popup_only.maintenance_start_at is None


def test_maintenance_periods_allow_shared_boundary_but_reject_real_overlap() -> None:
    factory = _factory()
    now = utcnow()
    with factory() as db:
        db.add(Notice(**_notice_payload(now)))
        db.commit()

        # [start, end) means the next maintenance may start at the previous end.
        boundary = NoticeWrite(
            **_notice_payload(
                now,
                maintenance_start_at=now + timedelta(hours=1),
                maintenance_end_at=now + timedelta(hours=2),
            )
        )
        _validate_maintenance_overlap(db, boundary)

        overlapping = NoticeWrite(
            **_notice_payload(
                now,
                maintenance_start_at=now + timedelta(minutes=59),
                maintenance_end_at=now + timedelta(hours=2),
            )
        )
        with pytest.raises(Exception) as error:
            _validate_maintenance_overlap(db, overlapping)
        assert getattr(error.value, "status_code", None) == 409


def test_study_draft_rejects_unknown_duplicate_and_excess_choices_and_clears_empty() -> None:
    factory = _factory()
    with factory() as db:
        learner = User(username="draft-learner", password_hash="hash")
        certification = Certification(
            certification_code="DEA-C01", name_en="DEA", name_ko="데이터",
            exam_version="v1", default_question_count=1,
            default_duration_minutes=10, passing_score=70,
        )
        db.add_all((learner, certification)); db.flush()
        domain = Domain(
            certification_id=certification.id, domain_code="D1", name_en="D1",
            name_ko="D1", exam_weight=100,
        )
        db.add(domain); db.flush()
        question = Question(
            question_uid="draft-question", certification_id=certification.id,
            domain_id=domain.id, question_type="multiple_response",
            required_answer_count=2, question_en="Q", question_ko="문제",
            content_hash="draft-question", verification_status="verified",
            choices=[
                QuestionChoice(choice_key="A", text_en="A", sort_order=1),
                QuestionChoice(choice_key="B", text_en="B", sort_order=2),
            ],
        )
        db.add(question); db.flush()
        record = StudySessionRecord(
            session_id="draft-session", user_id=learner.id,
            certification_id=certification.id, question_ids_json=[question.id],
        )
        db.add(record); db.commit()

        for selected in (["Z"], ["A", "A"], ["A", "B", "Z"]):
            with pytest.raises(Exception) as rejected:
                save_study_draft(
                    "draft-session",
                    StudyDraftUpdate(question_id=question.id, selected_answers=selected),
                    db,
                    learner,
                )
            assert getattr(rejected.value, "status_code", None) == 422
            db.rollback()

        save_study_draft(
            "draft-session",
            StudyDraftUpdate(question_id=question.id, selected_answers=["A"]),
            db,
            learner,
        )
        assert record.pending_selected_answers_json == ["A"]
        save_study_draft(
            "draft-session",
            StudyDraftUpdate(question_id=question.id, selected_answers=[]),
            db,
            learner,
        )
        assert record.pending_question_id is None


def test_active_maintenance_obeys_start_and_end_boundaries() -> None:
    factory = _factory()
    now = utcnow()
    with factory() as db:
        notice = Notice(**_notice_payload(now))
        db.add(notice)
        db.commit()

        assert active_maintenance(db, now - timedelta(microseconds=1)) is None
        assert active_maintenance(db, now).id == notice.id
        assert active_maintenance(db, now + timedelta(hours=1) - timedelta(microseconds=1)).id == notice.id
        assert active_maintenance(db, now + timedelta(hours=1)) is None


def test_executed_maintenance_notice_must_be_recreated_instead_of_rescheduled() -> None:
    factory = _factory()
    now = utcnow()
    with factory() as db:
        notice = Notice(**_notice_payload(now), maintenance_started_at=now)
        db.add(notice); db.commit()
        rescheduled = NoticeWrite(**_notice_payload(
            now,
            maintenance_start_at=now + timedelta(days=1),
            maintenance_end_at=now + timedelta(days=1, hours=1),
        ))
        with pytest.raises(Exception) as rejected:
            update_notice(notice.id, rescheduled, db)
        assert getattr(rejected.value, "status_code", None) == 409


def test_active_maintenance_denies_learners_but_keeps_admin_access() -> None:
    factory = _factory()
    now = utcnow()
    with factory() as db:
        learner = User(username="learner", password_hash="hash", role="user")
        admin = User(username="admin", password_hash="hash", role="admin")
        db.add_all((learner, admin, Notice(**_notice_payload(now))))
        db.commit()
        with pytest.raises(Exception) as denied:
            reject_learner_during_maintenance(db, learner)
        assert getattr(denied.value, "status_code", None) == 503
        reject_learner_during_maintenance(db, admin)


def test_maintenance_finalization_scores_pending_answer_updates_wrong_note_and_preserves_admin_session() -> None:
    factory = _factory()
    now = utcnow()
    with factory() as db:
        learner = User(username="learner", password_hash="hash", role="user")
        admin = User(username="admin", password_hash="hash", role="admin")
        db.add_all((learner, admin))
        db.flush()
        certification = Certification(
            certification_code="DEA-C01", name_en="DEA", name_ko="데이터",
            exam_version="v1", default_question_count=1,
            default_duration_minutes=10, passing_score=70,
        )
        db.add(certification)
        db.flush()
        domain = Domain(
            certification_id=certification.id, domain_code="D1", name_en="D1",
            name_ko="D1", exam_weight=100,
        )
        db.add(domain)
        db.flush()
        question = Question(
            question_uid="maintenance-question", certification_id=certification.id,
            domain_id=domain.id, question_type="multiple_choice", question_en="Q",
            question_ko="문제", content_hash="maintenance-question",
            verification_status="verified",
            answer_versions=[QuestionAnswerVersion(
                answer_source="admin_final", answers_json=["A"], is_current=True
            )],
        )
        db.add(question)
        db.flush()
        db.add_all((
            StudySessionRecord(
                session_id="study-under-maintenance", user_id=learner.id,
                certification_id=certification.id, question_ids_json=[question.id],
                pending_question_id=question.id, pending_selected_answers_json=["B"],
            ),
            WrongNote(user_id=learner.id, question_id=question.id, wrong_count=2),
            MockExam(
                user_id=learner.id, certification_id=certification.id,
                status="in_progress", question_count=1, duration_minutes=10,
                expires_at=now + timedelta(hours=1), passing_score=70,
            ),
            AuthSession(
                user_id=learner.id, token_hash="l" * 64,
                expires_at=now + timedelta(minutes=30),
            ),
            AuthSession(
                user_id=admin.id, token_hash="a" * 64,
                expires_at=now + timedelta(minutes=30),
            ),
            Notice(**_notice_payload(now)),
        ))
        db.commit()

        enforce_active_maintenance(db, now)
        # A repeated detection must not create another attempt or increment the note.
        enforce_active_maintenance(db, now)
        db.expire_all()

        record = db.get(StudySessionRecord, "study-under-maintenance")
        assert record is not None
        assert record.status == "partial_saved"
        assert record.pending_question_id is None
        assert record.pending_selected_answers_json is None

        attempts = list(db.scalars(select(StudyAttempt)))
        assert len(attempts) == 1
        assert attempts[0].selected_answers_json == ["B"]
        assert attempts[0].is_correct is False
        assert attempts[0].wrong_note_processed is True

        note = db.scalar(select(WrongNote).where(WrongNote.user_id == learner.id))
        assert note is not None
        assert note.wrong_count == 3
        assert db.scalar(select(MockExam.status)) == "maintenance_cancelled"

        sessions = {item.user_id: item for item in db.scalars(select(AuthSession))}
        assert sessions[learner.id].revoked_at is not None
        assert sessions[admin.id].revoked_at is None


def test_maintenance_finalization_preserves_wrong_note_retry_semantics() -> None:
    factory = _factory()
    now = utcnow()
    with factory() as db:
        learner = User(username="retry-learner", password_hash="hash", role="user")
        certification = Certification(
            certification_code="DEA-C01", name_en="DEA", name_ko="데이터",
            exam_version="v1", default_question_count=1,
            default_duration_minutes=10, passing_score=70,
        )
        db.add_all((learner, certification)); db.flush()
        domain = Domain(
            certification_id=certification.id, domain_code="D1", name_en="D1",
            name_ko="D1", exam_weight=100,
        )
        db.add(domain); db.flush()
        question = Question(
            question_uid="retry-maintenance", certification_id=certification.id,
            domain_id=domain.id, question_type="multiple_choice", question_en="Q",
            question_ko="문제", content_hash="retry-maintenance",
            verification_status="verified",
            answer_versions=[QuestionAnswerVersion(
                answer_source="admin_final", answers_json=["A"], is_current=True,
            )],
        )
        db.add(question); db.flush()
        db.add_all((
            StudySessionRecord(
                session_id="original", user_id=learner.id,
                certification_id=certification.id, question_ids_json=[question.id],
                status="partial_saved", completed_at=now,
            ),
            StudyAttempt(
                user_id=learner.id, session_id="original", question_id=question.id,
                selected_answers_json=["B"], is_correct=False, wrong_note_processed=True,
            ),
            StudySessionRecord(
                session_id="retry", user_id=learner.id,
                certification_id=certification.id, question_ids_json=[question.id],
                retry_of_session_id="original", pending_question_id=question.id,
                pending_selected_answers_json=["A"],
            ),
            WrongNote(user_id=learner.id, question_id=question.id, wrong_count=1),
            Notice(**_notice_payload(now)),
        ))
        db.commit()

        enforce_active_maintenance(db, now)
        db.expire_all()

        original = db.scalar(select(StudyAttempt).where(StudyAttempt.session_id == "original"))
        retry = db.scalar(select(StudyAttempt).where(StudyAttempt.session_id == "retry"))
        note = db.scalar(select(WrongNote).where(WrongNote.user_id == learner.id))
        assert original is not None and original.is_correct is True
        assert original.selected_answers_json == ["A"]
        assert retry is not None and retry.wrong_note_processed is False
        assert note is not None and note.status == "mastered"
        assert note.correct_after_wrong_count == 1


def test_maintenance_api_blocks_learner_keeps_admin_and_finalizes_current_user() -> None:
    factory = _factory()
    now = utcnow()
    with factory() as db:
        certification = Certification(
            certification_code="DEA-C01", name_en="DEA", name_ko="데이터",
            exam_version="v1", default_question_count=1,
            default_duration_minutes=10, passing_score=70,
        )
        learner = User(username="learner-api", password_hash="hash", role="user")
        admin = User(username="admin-api", password_hash="hash", role="admin")
        db.add_all((certification, learner, admin, Notice(**_notice_payload(now))))
        db.commit()
        learner_id, admin_id = learner.id, admin.id

    def override_db():
        with factory() as db:
            yield db

    settings = Settings(
        database_url="sqlite://", database_host="", database_name="",
        database_user="", database_password="", auth_required=True,
    )
    application = create_app(settings)
    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_settings] = lambda: settings
    learner = User(id=learner_id, username="learner-api", password_hash="hash", role="user")
    admin = User(id=admin_id, username="admin-api", password_hash="hash", role="admin")
    try:
        application.dependency_overrides[current_user] = lambda: learner
        application.dependency_overrides[session_identity] = lambda: (object(), learner)
        with TestClient(application) as client:
            assert client.get("/api/v1/certifications").status_code == 503
            assert client.post("/api/v1/maintenance/finalize-current-user").status_code == 204

        application.dependency_overrides[current_user] = lambda: admin
        application.dependency_overrides[session_identity] = lambda: (object(), admin)
        with TestClient(application) as client:
            assert client.get("/api/v1/certifications").status_code == 200
            assert client.post("/api/v1/maintenance/finalize-current-user").status_code == 204
    finally:
        application.dependency_overrides.clear()


def test_active_maintenance_rejects_new_learner_login_but_allows_admin_registration() -> None:
    factory = _factory()
    now = utcnow()
    with factory() as db:
        db.add_all((
            User(
                username="learner-login", password_hash=hash_password("learner-password"),
                role="user",
            ),
            Notice(**_notice_payload(now)),
        ))
        db.commit()

    def override_db():
        with factory() as db:
            yield db

    settings = Settings(
        database_url="sqlite://", database_host="", database_name="",
        database_user="", database_password="", auth_required=True,
        initial_admin_username="admin", initial_admin_password="admin-password",
        auth_rate_limit_requests=20,
    )
    application = create_app(settings)
    application.dependency_overrides[get_db] = override_db
    application.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(application) as client:
            learner = client.post("/api/v1/auth/login", json={
                "username": "learner-login", "password": "learner-password",
            })
            assert learner.status_code == 503
            admin = client.post("/api/v1/auth/login", json={
                "username": "admin", "password": "admin-password",
            })
            assert admin.status_code == 200
            assert admin.json()["passkey_registration_required"] is True
    finally:
        application.dependency_overrides.clear()
