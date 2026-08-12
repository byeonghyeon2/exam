from collections.abc import Iterator

from fastapi.testclient import TestClient
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session, sessionmaker
from sqlalchemy.pool import StaticPool

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
    StudyAttempt,
    StudySessionRecord,
    WrongNote,
)


def test_wrong_notes_are_written_once_when_study_is_completed() -> None:
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
            default_question_count=2,
            default_duration_minutes=10,
            passing_score=70,
        )
        db.add(certification)
        db.flush()
        domain = Domain(
            certification_id=certification.id,
            domain_code="DEA-D1",
            name_en="Data ingestion",
            name_ko="데이터 수집",
            exam_weight=100,
        )
        db.add(domain)
        db.flush()
        questions = []
        for number in (1, 2):
            question = Question(
                question_uid=f"DEA-STUDY-{number}",
                certification_id=certification.id,
                domain_id=domain.id,
                question_type="multiple_choice",
                question_en=f"Question {number}",
                question_ko=f"문제 {number}",
                content_hash=f"study-completion-{number}",
                verification_status="verified",
                choices=[
                    QuestionChoice(choice_key="A", text_en="Correct", sort_order=1),
                    QuestionChoice(choice_key="B", text_en="Wrong", sort_order=2),
                ],
                answer_versions=[
                    QuestionAnswerVersion(
                        answer_source="admin_final",
                        answers_json=["A"],
                        is_current=True,
                    )
                ],
            )
            db.add(question)
            questions.append(question)
        db.commit()
        question_ids = [question.id for question in questions]
        certification_id = certification.id
        db.add(StudySessionRecord(session_id="batch-session", user_id=0, certification_id=certification_id, question_ids_json=question_ids))
        db.commit()

    def override_db() -> Iterator[Session]:
        with session_factory() as db:
            yield db

    settings = Settings(
        database_url="sqlite://",
        database_host="",
        database_name="",
        database_user="",
        database_password="",
        auth_required=False,
    )
    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_settings] = lambda: settings
    try:
        with TestClient(app) as client:
            wrong = client.post(
                f"/api/v1/study/questions/{question_ids[0]}/submit?session_id=batch-session",
                json={"selected_answers": ["B"]},
            )
            correct = client.post(
                f"/api/v1/study/questions/{question_ids[1]}/submit?session_id=batch-session",
                json={"selected_answers": ["A"]},
            )
            assert (wrong.status_code, correct.status_code) == (200, 200)
            with session_factory() as db:
                assert db.scalar(select(func.count(WrongNote.id))) == 0

            completed = client.post("/api/v1/study/sessions/batch-session/complete")
            assert completed.status_code == 200
            assert completed.json() == {
                "total_questions": 2,
                "answered_count": 2,
                "correct_count": 1,
                "wrong_count": 1,
                "finalized": True,
            }
            assert client.get("/api/v1/study/sessions/batch-session").status_code == 409

            history = client.get("/api/v1/study/history")
            assert history.status_code == 200
            assert len(history.json()) == 1
            batch = history.json()[0]
            assert batch["session_id"] == "batch-session"
            assert (batch["total_count"], batch["correct_count"], batch["wrong_count"]) == (2, 1, 1)
            assert [question["id"] for question in batch["wrong_questions"]] == [question_ids[0]]

            retry = client.post("/api/v1/study/history/batch-session/retry")
            assert retry.status_code == 201
            assert retry.json()["question_ids"] == [question_ids[0]]
            assert retry.json()["retry_of_session_id"] == "batch-session"
            retry_session_id = retry.json()["id"]
            assert client.get(f"/api/v1/study/sessions/{retry_session_id}").json()["retry_of_session_id"] == "batch-session"
            assert client.post(
                f"/api/v1/study/questions/{question_ids[0]}/submit?session_id={retry_session_id}",
                json={"selected_answers": ["B"]},
            ).status_code == 200
            assert client.post(f"/api/v1/study/sessions/{retry_session_id}/complete").status_code == 200
            assert client.get(f"/api/v1/study/sessions/{retry_session_id}").status_code == 409

            history_after_wrong_retry = client.get("/api/v1/study/history").json()
            assert len(history_after_wrong_retry) == 1
            assert history_after_wrong_retry[0]["session_id"] == "batch-session"
            assert (history_after_wrong_retry[0]["correct_count"], history_after_wrong_retry[0]["wrong_count"]) == (1, 1)

            retry_again = client.post("/api/v1/study/history/batch-session/retry")
            assert retry_again.status_code == 201
            assert retry_again.json()["retry_of_session_id"] == "batch-session"
            retry_again_session_id = retry_again.json()["id"]
            assert client.post(
                f"/api/v1/study/questions/{question_ids[0]}/submit?session_id={retry_again_session_id}",
                json={"selected_answers": ["A"]},
            ).status_code == 200
            assert client.post(f"/api/v1/study/sessions/{retry_again_session_id}/complete").status_code == 200

            completed_history = client.get("/api/v1/study/history").json()
            assert len(completed_history) == 1
            assert completed_history[0]["session_id"] == "batch-session"
            assert (completed_history[0]["total_count"], completed_history[0]["correct_count"], completed_history[0]["wrong_count"]) == (2, 2, 0)
            assert completed_history[0]["wrong_questions"] == []
            assert client.post("/api/v1/study/history/batch-session/retry").status_code == 409

            with session_factory() as db:
                note = db.scalar(select(WrongNote).where(WrongNote.question_id == question_ids[0]))
                assert note is not None
                assert note.wrong_count == 2
                assert note.correct_after_wrong_count == 1
                assert note.status == "mastered"
            repeated = client.post("/api/v1/study/sessions/batch-session/complete")
            assert repeated.status_code == 200

            deleted = client.delete("/api/v1/study/history/batch-session")
            assert deleted.status_code == 200
            assert deleted.json() == {"deleted_count": 2}
            assert client.get("/api/v1/study/history").json() == []
            assert client.delete("/api/v1/study/history/batch-session").status_code == 404

            with session_factory() as db:
                db.add(StudySessionRecord(session_id="partial-session", user_id=0, certification_id=certification_id, question_ids_json=question_ids))
                db.commit()
            assert client.post(f"/api/v1/study/questions/{question_ids[0]}/submit?session_id=partial-session", json={"selected_answers": ["B"]}).status_code == 200
            partial = client.post("/api/v1/study/sessions/partial-session/leave", json={"save_results": True})
            assert partial.status_code == 200
            assert partial.json()["answered_count"] == 1
            assert partial.json()["wrong_count"] == 1
            assert [item["session_id"] for item in client.get("/api/v1/study/history").json()] == ["partial-session"]
            assert client.delete("/api/v1/study/history/partial-session").status_code == 200

            with session_factory() as db:
                db.add(StudySessionRecord(session_id="discarded-session", user_id=0, certification_id=certification_id, question_ids_json=question_ids))
                db.commit()
            assert client.post(f"/api/v1/study/questions/{question_ids[0]}/submit?session_id=discarded-session", json={"selected_answers": ["B"]}).status_code == 200
            discarded = client.post("/api/v1/study/sessions/discarded-session/leave", json={"save_results": False})
            assert discarded.status_code == 200
            assert discarded.json()["finalized"] is False
            assert client.get("/api/v1/study/history").json() == []
    finally:
        app.dependency_overrides.clear()

    with session_factory() as db:
        note = db.scalar(select(WrongNote))
        assert note is None
        attempts = list(db.scalars(select(StudyAttempt)))
        assert len(attempts) == 1
        assert attempts[0].session_id == "discarded-session"
        assert attempts[0].wrong_note_processed is False
