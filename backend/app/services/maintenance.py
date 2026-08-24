"""Server-authoritative maintenance state and safe learner shutdown."""

from datetime import UTC, datetime

from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.models.entities import (
    AuthSession,
    MockExam,
    Notice,
    Question,
    QuestionAnswerVersion,
    StudyAttempt,
    StudySessionRecord,
    User,
    WrongNote,
)
from app.services.scoring import score_answer


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo is not None else value.replace(tzinfo=UTC)


def active_maintenance(db: Session, now: datetime | None = None) -> Notice | None:
    current = now or utcnow()
    notices = db.scalars(
        select(Notice)
        .where(
            Notice.notice_type == "maintenance",
            Notice.is_published.is_(True),
            Notice.maintenance_screen_enabled.is_(True),
            Notice.maintenance_start_at.is_not(None),
            Notice.maintenance_end_at.is_not(None),
        )
        .order_by(Notice.maintenance_start_at)
    )
    return next(
        (notice for notice in notices if _aware(notice.maintenance_start_at) <= current < _aware(notice.maintenance_end_at)),
        None,
    )


def finalize_user_for_maintenance(db: Session, user_id: int) -> None:
    """Make learner progress durable once; safe to retry after network failures."""
    now = utcnow()
    records = list(db.scalars(
        select(StudySessionRecord).where(
            StudySessionRecord.user_id == user_id,
            StudySessionRecord.status == "in_progress",
        ).with_for_update()
    ))
    for record in records:
        if record.pending_question_id is not None and record.pending_selected_answers_json:
            question = db.scalar(select(Question).where(Question.id == record.pending_question_id))
            answers = list(db.scalars(select(QuestionAnswerVersion.answers_json).where(
                QuestionAnswerVersion.question_id == record.pending_question_id,
                QuestionAnswerVersion.is_current.is_(True),
                QuestionAnswerVersion.answer_source == "admin_final",
            )))
            exists = db.scalar(select(StudyAttempt.id).where(
                StudyAttempt.user_id == user_id,
                StudyAttempt.session_id == record.session_id,
                StudyAttempt.question_id == record.pending_question_id,
            ))
            if question is not None and len(answers) == 1 and exists is None:
                db.add(StudyAttempt(
                    user_id=user_id, session_id=record.session_id,
                    question_id=record.pending_question_id,
                    selected_answers_json=record.pending_selected_answers_json,
                    is_correct=score_answer(record.pending_selected_answers_json, answers[0]),
                ))
        record.pending_question_id = None
        record.pending_selected_answers_json = None
        record.pending_updated_at = None
        attempts = list(db.scalars(select(StudyAttempt).where(
            StudyAttempt.user_id == user_id,
            StudyAttempt.session_id == record.session_id,
        )))
        for attempt in attempts:
            if attempt.wrong_note_processed:
                continue
            note = db.scalar(select(WrongNote).where(
                WrongNote.user_id == user_id, WrongNote.question_id == attempt.question_id
            ))
            if record.retry_of_session_id:
                if attempt.is_correct:
                    if note is not None:
                        note.correct_after_wrong_count += 1
                        note.status = "mastered"
                    original = db.scalar(select(StudyAttempt).where(
                        StudyAttempt.session_id == record.retry_of_session_id,
                        StudyAttempt.user_id == user_id,
                        StudyAttempt.question_id == attempt.question_id,
                        StudyAttempt.wrong_note_processed.is_(True),
                    ))
                    if original is not None:
                        original.is_correct = True
                        original.selected_answers_json = attempt.selected_answers_json
                elif note is None:
                    db.add(WrongNote(user_id=user_id, question_id=attempt.question_id, wrong_count=1))
                else:
                    note.wrong_count += 1
                    note.last_wrong_at = now
                    note.status = "active"
                continue
            if attempt.is_correct:
                if note is not None:
                    note.correct_after_wrong_count += 1
            elif note is None:
                db.add(WrongNote(user_id=user_id, question_id=attempt.question_id, wrong_count=1))
            else:
                note.wrong_count += 1
                note.last_wrong_at = now
                note.status = "active"
            attempt.wrong_note_processed = True
        record.status = "partial_saved"
        record.completed_at = now
    db.execute(
        update(MockExam)
        .where(MockExam.user_id == user_id, MockExam.status == "in_progress")
        .values(status="maintenance_cancelled", submitted_at=now)
    )


def enforce_active_maintenance(db: Session, now: datetime | None = None) -> Notice | None:
    """Finalize all learners and revoke their sessions when a screen is active."""
    notice = active_maintenance(db, now)
    if notice is None:
        return None
    locked = db.scalar(select(Notice).where(Notice.id == notice.id).with_for_update())
    if locked is None or locked.maintenance_started_at is not None:
        return notice
    locked.maintenance_started_at = now or utcnow()
    learner_ids = list(db.scalars(select(User.id).where(User.role != "admin")))
    for user_id in learner_ids:
        finalize_user_for_maintenance(db, user_id)
    db.execute(
        update(AuthSession)
        .where(
            AuthSession.user_id.in_(learner_ids),
            AuthSession.revoked_at.is_(None),
        )
        .values(revoked_at=utcnow())
    )
    db.commit()
    return notice


def enforce_scheduled_maintenance() -> int | None:
    """Run from the process scheduler; every worker remains safe via the notice row lock."""
    from app.db.session import SessionLocal

    with SessionLocal() as db:
        notice = enforce_active_maintenance(db)
        return notice.id if notice is not None else None
