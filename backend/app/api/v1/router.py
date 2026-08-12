import random
from datetime import timedelta
from pathlib import Path
from typing import Annotated, Any
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select, update
from sqlalchemy.orm import Session, selectinload

from app.api.v1.auth import current_user, require_admin
from app.classifiers.domain_classifier import classify_questions
from app.classifiers.domain_classifier import report as classification_report
from app.core.config import Settings, get_settings
from app.db.base import utcnow
from app.db.session import get_db
from app.importers.jsonl import import_jsonl
from app.models.entities import (
    AppSetting,
    Certification,
    Domain,
    ImportJob,
    MockExam,
    MockExamQuestion,
    Question,
    QuestionAnswerVersion,
    QuestionExplanation,
    QuestionReport,
    StudyAttempt,
    StudySessionRecord,
    User,
    WrongNote,
)
from app.repositories.exams import ExamRepository
from app.schemas.api import *
from app.services.ai import AIOutputError, AIUnavailableError, build_ai_adapter
from app.services.allocation import allocate_by_domain
from app.services.scoring import percentage, scaled_score, score_answer

router = APIRouter(dependencies=[Depends(current_user)])
Db = Annotated[Session, Depends(get_db)]
CurrentUser = Annotated[User | None, Depends(current_user)]


def owner_id(user: User | None) -> int:
    return user.id if user is not None else 0


def get_study_record(db: Session, session_id: str, user: User | None) -> StudySessionRecord:
    record = db.scalar(select(StudySessionRecord).where(StudySessionRecord.session_id == session_id, StudySessionRecord.user_id == owner_id(user)))
    if record is None:
        raise HTTPException(404, "Study session not found")
    return record


def current_answers(question: Question) -> list[str]:
    versions = [v for v in question.answer_versions if v.is_current and v.answer_source == "admin_final"]
    if len(versions) != 1:
        raise HTTPException(409, "Question does not have exactly one current answer version")
    return versions[0].answers_json


def get_question(db: Session, question_id: int) -> Question:
    question = db.scalar(select(Question).where(Question.id == question_id).options(selectinload(Question.choices), selectinload(Question.answer_versions)))
    if not question:
        raise HTTPException(404, "Question not found")
    return question


def may_access_explanation(db: Session, user: User | None, question_id: int) -> bool:
    """Allow explanations only after this learner submitted an answer."""
    if user is None:
        return False
    if user.role == "admin":
        return True
    study_attempt = db.scalar(
        select(StudyAttempt.id).where(
            StudyAttempt.user_id == user.id,
            StudyAttempt.question_id == question_id,
        ).limit(1)
    )
    if study_attempt is not None:
        return True
    submitted_exam_question = db.scalar(
        select(MockExamQuestion.id)
        .join(MockExam, MockExam.id == MockExamQuestion.mock_exam_id)
        .where(
            MockExam.user_id == user.id,
            MockExam.status == "submitted",
            MockExamQuestion.question_id == question_id,
        )
        .limit(1)
    )
    return submitted_exam_question is not None


def require_answer_before_explanation(
    db: Session,
    user: User | None,
    question_id: int,
    settings: Settings,
) -> None:
    # Authentication can be disabled for isolated local development and existing test fixtures.
    if settings.auth_required and not may_access_explanation(db, user, question_id):
        raise HTTPException(404, "Explanation is not available for this user")


@router.get("/certifications", response_model=list[CertificationOut])
def certifications(db: Db) -> list[Certification]:
    return list(db.scalars(select(Certification).where(Certification.is_active.is_(True)).order_by(Certification.certification_code)))


@router.get("/certifications/{code}", response_model=CertificationOut)
def certification(code: str, db: Db) -> Certification:
    item = ExamRepository(db).certification(code)
    if not item or not item.is_active: raise HTTPException(404, "Certification not found")
    return item


@router.get("/certifications/{code}/domains", response_model=list[DomainOut])
def domains(code: str, db: Db) -> list[Domain]:
    cert = ExamRepository(db).certification(code)
    if not cert or not cert.is_active: raise HTTPException(404, "Certification not found")
    return list(db.scalars(select(Domain).where(Domain.certification_id == cert.id, Domain.is_active.is_(True)).order_by(Domain.sort_order)))


@router.post("/study/sessions", response_model=StudySessionOut, status_code=201)
def create_study(payload: StudySessionCreate, db: Db, user: CurrentUser) -> StudySessionOut:
    repo = ExamRepository(db); cert = repo.certification(payload.certification_code)
    if not cert or not cert.is_active: raise HTTPException(404, "Certification not found")
    domain = repo.domain_by_code(cert.id, payload.domain_code) if payload.domain_code else None
    if payload.domain_code and not domain: raise HTTPException(404, "Domain not found")
    pool = repo.eligible_questions(cert.id, domain.id if domain else None)
    rng = random.Random(payload.seed); rng.shuffle(pool)
    question_count = len(pool) if payload.question_count is None else payload.question_count
    if not pool: raise HTTPException(409, "No eligible questions in the selected domain")
    if len(pool) < question_count: raise HTTPException(409, "Insufficient verified questions")
    session_id = str(uuid4()); ids = [q.id for q in pool[:question_count]]
    db.add(StudySessionRecord(session_id=session_id, user_id=owner_id(user), certification_id=cert.id, question_ids_json=ids))
    db.commit()
    return StudySessionOut(id=session_id, question_ids=ids)


@router.get("/study/sessions/{session_id}", response_model=None)
def study_session(session_id: str, db: Db, user: CurrentUser) -> dict[str, Any]:
    record = get_study_record(db, session_id, user); ids = record.question_ids_json
    attempts = list(db.scalars(select(StudyAttempt).where(StudyAttempt.session_id == session_id, StudyAttempt.user_id == owner_id(user))))
    attempted = {attempt.question_id for attempt in attempts}
    next_id = next((question_id for question_id in ids if question_id not in attempted), None) if record.status == "in_progress" else None
    question = QuestionOut.model_validate(get_question(db, next_id)) if next_id is not None else None
    return {
        "id": session_id,
        "question_ids": ids,
        "total_questions": len(ids),
        "current_index": len(attempted),
        "question": question,
        "summary": {
            "total_questions": len(ids),
            "answered_count": len(attempted),
            "correct_count": sum(attempt.is_correct for attempt in attempts),
            "wrong_count": sum(not attempt.is_correct for attempt in attempts),
            "finalized": record.status in {"completed", "partial_saved"},
        },
    }


@router.get("/study/sessions/{session_id}/next", response_model=QuestionOut)
def next_study(session_id: str, db: Db, user: CurrentUser) -> Question:
    record = get_study_record(db, session_id, user); ids = record.question_ids_json
    if record.status != "in_progress": raise HTTPException(409, "Study session is no longer active")
    attempted = set(db.scalars(select(StudyAttempt.question_id).where(StudyAttempt.session_id == session_id, StudyAttempt.user_id == owner_id(user))))
    next_id = next((qid for qid in ids if qid not in attempted), None)
    if next_id is None: raise HTTPException(404, "No remaining question")
    return get_question(db, next_id)


def update_wrong_note(db: Session, user_id: int, question_id: int, correct: bool) -> None:
    note = db.scalar(select(WrongNote).where(WrongNote.user_id == user_id, WrongNote.question_id == question_id))
    if not correct:
        if note: note.wrong_count += 1; note.last_wrong_at = utcnow(); note.status = "active"
        else: db.add(WrongNote(user_id=user_id, question_id=question_id, wrong_count=1))
    elif note:
        note.correct_after_wrong_count += 1


def finalize_study(db: Session, record: StudySessionRecord, attempts: list[StudyAttempt], status: str) -> dict[str, int | bool]:
    user_id = record.user_id
    if record.retry_of_session_id:
        for attempt in attempts:
            update_wrong_note(db, user_id, attempt.question_id, attempt.is_correct)
            if attempt.is_correct:
                original = db.scalar(select(StudyAttempt).where(
                    StudyAttempt.session_id == record.retry_of_session_id,
                    StudyAttempt.user_id == user_id,
                    StudyAttempt.question_id == attempt.question_id,
                    StudyAttempt.wrong_note_processed.is_(True),
                ))
                if original:
                    original.is_correct = True
                    original.selected_answers_json = attempt.selected_answers_json
                note = db.scalar(select(WrongNote).where(WrongNote.user_id == user_id, WrongNote.question_id == attempt.question_id))
                if note: note.status = "mastered"
        record.status = status; record.completed_at = utcnow(); db.commit()
        correct_count = sum(attempt.is_correct for attempt in attempts)
        return {"total_questions": len(record.question_ids_json), "answered_count": len(attempts), "correct_count": correct_count, "wrong_count": len(attempts) - correct_count, "finalized": True}
    for attempt in attempts:
        if not attempt.wrong_note_processed:
            update_wrong_note(db, user_id, attempt.question_id, attempt.is_correct)
            attempt.wrong_note_processed = True
    record.status = status; record.completed_at = utcnow(); db.commit()
    correct_count = sum(attempt.is_correct for attempt in attempts)
    return {"total_questions": len(record.question_ids_json), "answered_count": len(attempts), "correct_count": correct_count, "wrong_count": len(attempts) - correct_count, "finalized": True}


@router.post("/study/sessions/{session_id}/complete")
def complete_study(session_id: str, db: Db, user: CurrentUser) -> dict[str, int | bool]:
    record = get_study_record(db, session_id, user); ids = record.question_ids_json
    attempts = list(db.scalars(select(StudyAttempt).where(StudyAttempt.session_id == session_id, StudyAttempt.user_id == owner_id(user))))
    attempted_ids = {attempt.question_id for attempt in attempts}
    if len(attempted_ids) != len(ids) or not set(ids) <= attempted_ids:
        raise HTTPException(409, "Complete every assigned question before finishing the session")
    return finalize_study(db, record, attempts, "completed")


@router.post("/study/sessions/{session_id}/leave")
def leave_study(session_id: str, payload: StudyLeaveRequest, db: Db, user: CurrentUser) -> dict[str, int | bool]:
    record = get_study_record(db, session_id, user)
    if record.status != "in_progress": raise HTTPException(409, "Study session is no longer active")
    attempts = list(db.scalars(select(StudyAttempt).where(StudyAttempt.session_id == session_id, StudyAttempt.user_id == owner_id(user)).order_by(StudyAttempt.id)))
    if payload.save_results:
        if not attempts: raise HTTPException(409, "Answer at least one question before saving results")
        return finalize_study(db, record, attempts, "partial_saved")
    record.status = "abandoned"; record.completed_at = utcnow(); db.commit()
    correct_count = sum(attempt.is_correct for attempt in attempts)
    return {"total_questions": len(record.question_ids_json), "answered_count": len(attempts), "correct_count": correct_count, "wrong_count": len(attempts) - correct_count, "finalized": False}


@router.get("/study/history", response_model=list[StudyHistoryOut])
def study_history(db: Db, user: CurrentUser) -> list[StudyHistoryOut]:
    rows = db.execute(
        select(StudyAttempt, Question, Certification)
        .join(Question, Question.id == StudyAttempt.question_id)
        .join(Certification, Certification.id == Question.certification_id)
        .where(StudyAttempt.user_id == owner_id(user), StudyAttempt.wrong_note_processed.is_(True))
        .order_by(StudyAttempt.attempted_at.desc(), StudyAttempt.id.desc())
    ).all()
    grouped: dict[str, dict[str, Any]] = {}
    for attempt, question, certification in rows:
        group = grouped.setdefault(attempt.session_id, {
            "session_id": attempt.session_id,
            "certification_code": certification.certification_code,
            "certification_name": certification.name_ko or certification.name_en,
            "completed_at": attempt.attempted_at,
            "total_count": 0,
            "correct_count": 0,
            "wrong_count": 0,
            "wrong_questions": [],
        })
        group["total_count"] += 1
        if attempt.is_correct:
            group["correct_count"] += 1
        else:
            group["wrong_count"] += 1
            group["wrong_questions"].append({
                "id": question.id,
                "question_uid": question.question_uid,
                "question_ko": question.question_ko,
            })
    return [StudyHistoryOut(**group) for group in grouped.values()]


@router.post("/study/history/{session_id}/retry", response_model=StudySessionOut, status_code=201)
def retry_study_history(session_id: str, db: Db, user: CurrentUser) -> StudySessionOut:
    question_ids = list(db.scalars(
        select(StudyAttempt.question_id)
        .where(
            StudyAttempt.session_id == session_id,
            StudyAttempt.user_id == owner_id(user),
            StudyAttempt.wrong_note_processed.is_(True),
            StudyAttempt.is_correct.is_(False),
        )
        .order_by(StudyAttempt.id)
    ))
    if not question_ids:
        completed = db.scalar(select(StudyAttempt.id).where(StudyAttempt.session_id == session_id, StudyAttempt.user_id == owner_id(user), StudyAttempt.wrong_note_processed.is_(True)))
        raise HTTPException(409 if completed else 404, "There are no remaining wrong answers to retry")
    first_question = db.get(Question, question_ids[0]); retry_session_id = str(uuid4())
    db.add(StudySessionRecord(session_id=retry_session_id, user_id=owner_id(user), certification_id=first_question.certification_id, question_ids_json=question_ids, retry_of_session_id=session_id)); db.commit()
    return StudySessionOut(id=retry_session_id, question_ids=question_ids)


def rebuild_wrong_note(db: Session, user_id: int, question_id: int) -> None:
    attempts = list(db.scalars(
        select(StudyAttempt)
        .where(
            StudyAttempt.question_id == question_id,
            StudyAttempt.user_id == user_id,
            StudyAttempt.wrong_note_processed.is_(True),
        )
        .order_by(StudyAttempt.attempted_at, StudyAttempt.id)
    ))
    wrong_attempts = [attempt for attempt in attempts if not attempt.is_correct]
    note = db.scalar(select(WrongNote).where(WrongNote.user_id == user_id, WrongNote.question_id == question_id))
    if not wrong_attempts:
        if note:
            db.delete(note)
        return
    first_wrong_index = attempts.index(wrong_attempts[0])
    correct_after_wrong = sum(attempt.is_correct for attempt in attempts[first_wrong_index + 1:])
    if not note:
        note = WrongNote(user_id=user_id, question_id=question_id)
        db.add(note)
    note.wrong_count = len(wrong_attempts)
    note.correct_after_wrong_count = correct_after_wrong
    note.first_wrong_at = wrong_attempts[0].attempted_at
    note.last_wrong_at = wrong_attempts[-1].attempted_at


@router.delete("/study/history/{session_id}")
def delete_study_history(session_id: str, db: Db, user: CurrentUser) -> dict[str, int]:
    attempts = list(db.scalars(
        select(StudyAttempt).where(
            StudyAttempt.session_id == session_id,
            StudyAttempt.user_id == owner_id(user),
            StudyAttempt.wrong_note_processed.is_(True),
        )
    ))
    if not attempts:
        raise HTTPException(404, "Completed study session not found")
    retry_ids = list(db.scalars(select(StudySessionRecord.session_id).where(
        StudySessionRecord.retry_of_session_id == session_id,
        StudySessionRecord.user_id == owner_id(user),
    )))
    for retry_attempt in db.scalars(select(StudyAttempt).where(StudyAttempt.session_id.in_(retry_ids)) if retry_ids else select(StudyAttempt).where(False)):
        db.delete(retry_attempt)
    for retry_id in retry_ids:
        retry_record = db.get(StudySessionRecord, retry_id)
        if retry_record: db.delete(retry_record)
    question_ids = {attempt.question_id for attempt in attempts}
    for attempt in attempts:
        db.delete(attempt)
    db.flush()
    for question_id in question_ids:
        rebuild_wrong_note(db, owner_id(user), question_id)
    record = db.get(StudySessionRecord, session_id)
    if record and record.user_id == owner_id(user): db.delete(record)
    db.commit()
    return {"deleted_count": len(attempts)}


@router.post("/study/questions/{question_id}/submit", response_model=AnswerResult)
def submit_study(question_id: int, payload: SubmitAnswer, db: Db, user: CurrentUser, session_id: str = Query(...)) -> AnswerResult:
    record = get_study_record(db, session_id, user)
    if record.status != "in_progress" or question_id not in record.question_ids_json: raise HTTPException(409, "Question is not assigned to an active session")
    existing = db.scalar(select(StudyAttempt).where(StudyAttempt.session_id == session_id, StudyAttempt.user_id == owner_id(user), StudyAttempt.question_id == question_id))
    if existing: raise HTTPException(409, "Question already answered in this session")
    question = get_question(db, question_id); answers = current_answers(question); correct = score_answer(payload.selected_answers, answers)
    db.add(StudyAttempt(user_id=owner_id(user), session_id=session_id, question_id=question_id, selected_answers_json=payload.selected_answers, is_correct=correct)); db.commit()
    return AnswerResult(correct=correct, selected_answers=payload.selected_answers, correct_answers=answers)


@router.post("/mock-exams", status_code=201)
def create_mock(payload: MockExamCreate, db: Db, user: CurrentUser) -> dict[str, Any]:
    if payload.certification_code != "DEA-C01": raise HTTPException(409, "Only DEA-C01 is enabled in phase 1")
    repo = ExamRepository(db); cert = repo.certification(payload.certification_code)
    if not cert: raise HTTPException(404, "Certification not found")
    count = payload.question_count or cert.default_question_count
    domains = list(db.scalars(select(Domain).where(Domain.certification_id == cert.id, Domain.is_active.is_(True), Domain.domain_code.in_(["DEA-D1", "DEA-D2", "DEA-D3", "DEA-D4"]))))
    eligible = repo.eligible_questions(cert.id)
    try: allocation = allocate_by_domain(eligible, {d.id: d.exam_weight for d in domains}, count, payload.seed, allow_fallback=False)
    except ValueError as exc:
        readiness = mock_exam_readiness(db)
        raise HTTPException(409, {"message": str(exc), "readiness": readiness}) from exc
    duration = payload.duration_minutes or cert.default_duration_minutes; now = utcnow()
    exam = MockExam(user_id=owner_id(user), certification_id=cert.id, question_count=count, duration_minutes=duration, expires_at=now + timedelta(minutes=duration), passing_score=cert.passing_score)
    exam.questions = [MockExamQuestion(question_id=q.id, question_order=i + 1) for i, q in enumerate(allocation.questions)]; db.add(exam); db.commit()
    return {"id": exam.id, "status": exam.status, "expires_at": exam.expires_at, "used_fallback": allocation.used_fallback}


def get_exam(db: Session, exam_id: int, user: User | None) -> MockExam:
    exam = db.scalar(select(MockExam).where(MockExam.id == exam_id, MockExam.user_id == owner_id(user)).options(selectinload(MockExam.questions)))
    if not exam: raise HTTPException(404, "Mock exam not found")
    return exam


@router.get("/mock-exams/{exam_id}", response_model=None)
def mock_exam(exam_id: int, db: Db, user: CurrentUser) -> MockExam: return get_exam(db, exam_id, user)


@router.get("/mock-exams/{exam_id}/questions")
def mock_questions(exam_id: int, db: Db, user: CurrentUser) -> dict[str, Any]:
    """Return navigation metadata without exposing every assigned question body."""
    exam = get_exam(db, exam_id, user)
    question_ids = [item.question_id for item in exam.questions]
    return {"total": len(question_ids), "question_ids": question_ids}


@router.get("/mock-exams/{exam_id}/questions/{question_id}", response_model=QuestionOut)
def mock_question(exam_id: int, question_id: int, db: Db, user: CurrentUser) -> Question:
    exam = get_exam(db, exam_id, user)
    if not any(item.question_id == question_id for item in exam.questions):
        raise HTTPException(404, "Question not assigned to exam")
    question = db.scalar(
        select(Question)
        .where(Question.id == question_id)
        .options(selectinload(Question.choices))
    )
    if question is None:
        raise HTTPException(404, "Question not found")
    return question


def ensure_open(exam: MockExam) -> None:
    if exam.status != "in_progress": raise HTTPException(409, "Exam is already submitted")
    if utcnow() >= exam.expires_at: raise HTTPException(409, "Exam time has expired; submit the exam")


@router.put("/mock-exams/{exam_id}/answers/{question_id}")
def save_answer(exam_id: int, question_id: int, payload: ExamAnswerUpdate, db: Db, user: CurrentUser) -> dict[str, str]:
    exam = get_exam(db, exam_id, user); ensure_open(exam); item = next((x for x in exam.questions if x.question_id == question_id), None)
    if not item: raise HTTPException(404, "Question not assigned to exam")
    item.selected_answers_json = payload.selected_answers; item.answered_at = utcnow(); db.commit(); return {"status": "saved"}


@router.put("/mock-exams/{exam_id}/review-marks/{question_id}")
def mark_review(exam_id: int, question_id: int, payload: ReviewMarkUpdate, db: Db, user: CurrentUser) -> dict[str, bool]:
    exam = get_exam(db, exam_id, user); ensure_open(exam); item = next((x for x in exam.questions if x.question_id == question_id), None)
    if not item: raise HTTPException(404, "Question not assigned to exam")
    item.is_marked_for_review = payload.marked; db.commit(); return {"marked": payload.marked}


@router.post("/mock-exams/{exam_id}/submit")
def submit_mock(exam_id: int, db: Db, user: CurrentUser) -> dict[str, Any]:
    exam = get_exam(db, exam_id, user)
    if exam.status != "in_progress": raise HTTPException(409, "Exam is already submitted")
    correct_count = 0
    for item in exam.questions:
        question = get_question(db, item.question_id); item.is_correct = score_answer(item.selected_answers_json or [], current_answers(question)); correct_count += int(item.is_correct); update_wrong_note(db, owner_id(user), item.question_id, item.is_correct)
    exam.raw_score = percentage(correct_count, exam.question_count); exam.scaled_score = scaled_score(correct_count, exam.question_count); exam.result = "pass" if (exam.scaled_score if exam.passing_score > 100 else exam.raw_score) >= exam.passing_score else "fail"; exam.status = "submitted"; exam.submitted_at = utcnow(); db.commit()
    return {"correct_count": correct_count, "total": exam.question_count, "total_count": exam.question_count, "raw_score": exam.raw_score, "scaled_score": exam.scaled_score, "passing_score": exam.passing_score, "result": exam.result}


@router.get("/mock-exams/{exam_id}/result")
def mock_result(exam_id: int, db: Db, user: CurrentUser) -> dict[str, Any]:
    exam = get_exam(db, exam_id, user)
    if exam.status != "submitted": raise HTTPException(409, "Exam is not submitted")
    return {"raw_score": exam.raw_score, "scaled_score": exam.scaled_score, "passing_score": exam.passing_score, "result": exam.result}


@router.get("/mock-exams/{exam_id}/review/{question_id}")
def review_question(exam_id: int, question_id: int, db: Db, user: CurrentUser) -> dict[str, Any]:
    exam = get_exam(db, exam_id, user)
    if exam.status != "submitted": raise HTTPException(409, "Exam is not submitted")
    item = next((x for x in exam.questions if x.question_id == question_id), None)
    if not item: raise HTTPException(404, "Question not assigned")
    return {"question": QuestionOut.model_validate(get_question(db, question_id)), "selected_answers": item.selected_answers_json or [], "correct_answers": current_answers(get_question(db, question_id)), "is_correct": item.is_correct}


@router.get("/wrong-notes", response_model=list[WrongNoteOut])
def wrong_notes(db: Db, user: CurrentUser, status_filter: str | None = Query(None, alias="status")) -> list[WrongNoteOut]:
    stmt = select(WrongNote, Question).join(Question, Question.id == WrongNote.question_id).where(WrongNote.user_id == owner_id(user)).order_by(WrongNote.last_wrong_at.desc())
    if status_filter: stmt = stmt.where(WrongNote.status == status_filter)
    return [WrongNoteOut(
        question_id=note.question_id,
        question_uid=question.question_uid,
        question_ko=question.question_ko,
        wrong_count=note.wrong_count,
        status=note.status,
        last_wrong_at=note.last_wrong_at,
    ) for note, question in db.execute(stmt)]


@router.delete("/wrong-notes")
def delete_wrong_notes(payload: WrongNoteDelete, db: Db, user: CurrentUser) -> dict[str, int]:
    notes = list(db.scalars(select(WrongNote).where(WrongNote.user_id == owner_id(user), WrongNote.question_id.in_(set(payload.question_ids)))))
    for note in notes: db.delete(note)
    db.commit()
    return {"deleted_count": len(notes)}


@router.post("/wrong-notes/{question_id}/review")
def review_note(question_id: int, db: Db, user: CurrentUser) -> dict[str, str]:
    note = db.scalar(select(WrongNote).where(WrongNote.user_id == owner_id(user), WrongNote.question_id == question_id))
    if not note: raise HTTPException(404, "Wrong note not found")
    note.reviewed_at = utcnow(); note.status = "reviewing"; db.commit(); return {"status": note.status}


@router.patch("/wrong-notes/{question_id}")
def patch_note(question_id: int, payload: WrongNoteUpdate, db: Db, user: CurrentUser) -> dict[str, str]:
    note = db.scalar(select(WrongNote).where(WrongNote.user_id == owner_id(user), WrongNote.question_id == question_id))
    if not note: raise HTTPException(404, "Wrong note not found")
    note.status = payload.status; db.commit(); return {"status": note.status}


@router.post("/questions/{question_id}/reports", status_code=201)
def report(question_id: int, payload: ReportCreate, db: Db) -> dict[str, int]:
    get_question(db, question_id); item = QuestionReport(question_id=question_id, **payload.model_dump()); db.add(item); db.execute(update(Question).where(Question.id == question_id).values(is_reported=True)); db.commit(); return {"id": item.id}


@router.get("/questions/{question_id}/explanation", response_model=ExplanationOut)
def explanation(
    question_id: int,
    db: Db,
    user: CurrentUser,
    settings: Annotated[Settings, Depends(get_settings)],
    language: str = "ko",
) -> QuestionExplanation:
    require_answer_before_explanation(db, user, question_id, settings)
    item = db.scalar(select(QuestionExplanation).where(QuestionExplanation.question_id == question_id, QuestionExplanation.language == language, QuestionExplanation.generation_status == "complete"))
    if not item: raise HTTPException(404, "Explanation not generated")
    return item


@router.post("/questions/{question_id}/explanation/generate", response_model=ExplanationOut)
def generate_explanation(question_id: int, payload: ExplanationGenerate, db: Db, user: CurrentUser, settings: Annotated[Settings, Depends(get_settings)]) -> QuestionExplanation:
    require_answer_before_explanation(db, user, question_id, settings)
    existing = db.scalar(select(QuestionExplanation).where(QuestionExplanation.question_id == question_id, QuestionExplanation.language == payload.language))
    if existing and existing.generation_status == "complete": return existing
    question = get_question(db, question_id); answers = current_answers(question)
    explanation_input = {
        "question": {"ko": question.question_ko, "en": question.question_en},
        "choices": {
            choice.choice_key: {"ko": choice.text_ko, "en": choice.text_en}
            for choice in question.choices
        },
        "verified_answers": answers,
        "required_answer_count": question.required_answer_count,
    }
    try:
        data = build_ai_adapter(settings).explain(explanation_input, payload.language)
    except AIUnavailableError as exc:
        raise HTTPException(503, str(exc)) from exc
    except AIOutputError as exc:
        raise HTTPException(502, str(exc)) from exc
    item = existing or QuestionExplanation(question_id=question_id, language=payload.language)
    item.correct_answer_summary = data["correct_answer_summary"]
    item.core_reason = data["core_reason"]
    item.keywords_json = data["keywords"]
    item.choice_analysis_json = data["choice_analysis"]
    item.related_concepts = data["related_concepts"]
    item.exam_traps = data["exam_traps"]
    item.memory_summary = data["memory_summary"]
    item.model_name = settings.openai_explanation_model or settings.openai_model
    item.generation_status = "complete"
    db.add(item); db.commit(); return item


admin = APIRouter(prefix="/admin", dependencies=[Depends(require_admin)])


def mock_exam_readiness(db: Session) -> dict[str, Any]:
    cert = db.scalar(select(Certification).where(Certification.certification_code == "DEA-C01"))
    if cert is None:
        return {"ready": False, "reason": "DEA-C01 metadata is missing", "domains": []}
    official = list(db.scalars(select(Domain).where(Domain.certification_id == cert.id, Domain.domain_code.in_(["DEA-D1", "DEA-D2", "DEA-D3", "DEA-D4"])).order_by(Domain.sort_order)))
    eligible = ExamRepository(db).eligible_questions(cert.id)
    available = {domain.id: sum(1 for question in eligible if question.domain_id == domain.id) for domain in official}
    total_weight = sum(domain.exam_weight for domain in official) or 1
    exact = {domain.id: cert.default_question_count * domain.exam_weight / total_weight for domain in official}
    required = {domain.id: int(value) for domain, value in ((domain, exact[domain.id]) for domain in official)}
    remaining = cert.default_question_count - sum(required.values())
    for domain in sorted(official, key=lambda item: exact[item.id] - required[item.id], reverse=True)[:remaining]:
        required[domain.id] += 1
    details = [{"domain_code": domain.domain_code, "required": required[domain.id], "available": available[domain.id], "shortage": max(0, required[domain.id] - available[domain.id])} for domain in official]
    unclassified = db.scalar(select(func.count(Question.id)).join(Domain, Question.domain_id == Domain.id).where(Question.certification_id == cert.id, Domain.domain_code == "DEA-UNCLASSIFIED", Question.is_active.is_(True))) or 0
    return {"ready": len(official) == 4 and all(item["shortage"] == 0 for item in details), "question_count": cert.default_question_count, "unclassified": unclassified, "domains": details}


@admin.get("/dashboard")
def dashboard(db: Db) -> dict[str, int]:
    return {"questions": db.scalar(select(func.count(Question.id))) or 0, "verified": db.scalar(select(func.count(Question.id)).where(Question.verification_status == "verified")) or 0, "needs_review": db.scalar(select(func.count(Question.id)).where(Question.verification_status == "needs_review")) or 0, "reports": db.scalar(select(func.count(QuestionReport.id)).where(QuestionReport.status.in_(["received", "reviewing"]))) or 0}


@admin.get("/classification/unclassified", response_model=None)
def unclassified_questions(db: Db, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200)) -> dict[str, Any]:
    stmt = select(Question).join(Domain, Question.domain_id == Domain.id).where(Domain.domain_code == "DEA-UNCLASSIFIED").options(selectinload(Question.choices)).order_by(Question.id)
    total = db.scalar(select(func.count(Question.id)).join(Domain, Question.domain_id == Domain.id).where(Domain.domain_code == "DEA-UNCLASSIFIED")) or 0
    return {"items": list(db.scalars(stmt.offset((page - 1) * page_size).limit(page_size))), "total": total}


@admin.get("/classification/report")
def get_classification_report(db: Db) -> dict[str, Any]:
    return classification_report(db, "DEA-C01")


@admin.post("/classification/run")
def run_classification(payload: ClassificationRequest, db: Db) -> dict[str, int]:
    try:
        return classify_questions(db, "DEA-C01", payload.question_ids, payload.only_unclassified, payload.force, payload.batch_size)
    except (RuntimeError, ValueError) as exc:
        raise HTTPException(503 if isinstance(exc, RuntimeError) else 422, str(exc)) from exc


@admin.patch("/questions/{question_id}/domain")
def manual_domain(question_id: int, payload: ManualDomainUpdate, db: Db) -> dict[str, str]:
    question = get_question(db, question_id)
    domain = db.scalar(select(Domain).where(Domain.certification_id == question.certification_id, Domain.domain_code == payload.domain_code))
    if domain is None: raise HTTPException(422, "Domain not found")
    question.domain_id = domain.id; question.classification_status = "manual"; question.classification_confidence = 1.0; question.classification_reason = payload.reason; question.classification_model = "admin"; question.classification_prompt_version = "manual"; question.classified_at = utcnow(); db.commit()
    return {"status": "manual", "domain_code": domain.domain_code}


@admin.get("/mock-exam-readiness")
def readiness(db: Db) -> dict[str, Any]:
    return mock_exam_readiness(db)


@admin.get("/questions")
def admin_questions(db: Db, page: int = Query(1, ge=1), page_size: int = Query(50, ge=1, le=200), certification_id: int | None = None, verification_status: str | None = None) -> dict[str, Any]:
    stmt = select(Question); count_stmt = select(func.count(Question.id))
    for condition in [Question.certification_id == certification_id if certification_id else None, Question.verification_status == verification_status if verification_status else None]:
        if condition is not None: stmt = stmt.where(condition); count_stmt = count_stmt.where(condition)
    return {"items": list(db.scalars(stmt.offset((page-1)*page_size).limit(page_size))), "total": db.scalar(count_stmt) or 0}


@admin.get("/questions/{question_id}", response_model=QuestionOut)
def admin_question(question_id: int, db: Db) -> Question: return get_question(db, question_id)


@admin.patch("/questions/{question_id}")
def patch_question(question_id: int, payload: QuestionPatch, db: Db) -> dict[str, str]:
    item = get_question(db, question_id); changed_content = any(value is not None for key, value in payload.model_dump().items() if key in {"question_en", "question_ko", "domain_id", "required_answer_count"})
    for key, value in payload.model_dump(exclude_none=True).items(): setattr(item, key, value)
    if changed_content:
        item.verification_status = "needs_review"
        db.execute(update(QuestionExplanation).where(QuestionExplanation.question_id == item.id).values(generation_status="stale"))
    db.commit(); return {"status": "updated"}


@admin.post("/questions/{question_id}/verify")
def verify(question_id: int, payload: VerifyRequest, db: Db) -> dict[str, str]:
    question = get_question(db, question_id); keys = {c.choice_key for c in question.choices}
    if len(set(payload.answers)) != question.required_answer_count or not set(payload.answers) <= keys: raise HTTPException(422, "Invalid answer keys/count")
    for version in question.answer_versions: version.is_current = False
    db.add(QuestionAnswerVersion(question_id=question.id, answer_source="admin_final", answers_json=payload.answers, reason=payload.reason, is_current=True)); question.verification_status = "verified"; db.commit(); return {"status": "verified"}


@admin.post("/questions/{question_id}/regenerate-explanation")
def regenerate(question_id: int, db: Db) -> dict[str, str]:
    get_question(db, question_id); db.execute(update(QuestionExplanation).where(QuestionExplanation.question_id == question_id).values(generation_status="stale")); db.commit(); return {"status": "stale"}


@admin.get("/settings")
def settings(db: Db) -> dict[str, Any]: return {item.key: item.value_json for item in db.scalars(select(AppSetting))}


@admin.patch("/settings")
def patch_settings(payload: SettingPatch, db: Db) -> dict[str, str]:
    for key, value in payload.values.items():
        item = db.get(AppSetting, key)
        if item: item.value_json = value
        else: db.add(AppSetting(key=key, value_json=value))
    db.commit(); return {"status": "updated"}


def run_import(payload: ImportRequest, db: Session) -> dict[str, Any]:
    source = Path(payload.path).resolve(); file = source / "questions.jsonl" if source.is_dir() else source
    result = import_jsonl(db, file, payload.mode)
    return {"total": result.total, "imported": result.imported, "errors": [e.__dict__ for e in result.errors]}


@admin.post("/imports/validate")
def validate_import(payload: ImportRequest, db: Db) -> dict[str, Any]: return run_import(payload.model_copy(update={"mode": "dry-run"}), db)


@admin.post("/imports", status_code=201)
def create_import(payload: ImportRequest, db: Db) -> dict[str, Any]:
    result = run_import(payload, db); job = ImportJob(mode=payload.mode, status="partial" if result["errors"] else "complete", source_path=payload.path, total_count=result["total"], imported_count=result["imported"], rejected_count=len(result["errors"])); db.add(job); db.commit(); return {"job_id": job.id, **result}


@admin.get("/imports/{job_id}", response_model=None)
def import_job(job_id: int, db: Db) -> ImportJob:
    item = db.get(ImportJob, job_id)
    if not item: raise HTTPException(404, "Import job not found")
    return item


@admin.get("/reports", response_model=list[AdminReportOut])
def reports(db: Db, report_status: str | None = Query(None, alias="status")) -> list[AdminReportOut]:
    stmt = select(QuestionReport, Question).join(Question, QuestionReport.question_id == Question.id).order_by(QuestionReport.created_at.desc())
    if report_status: stmt = stmt.where(QuestionReport.status == report_status)
    return [
        AdminReportOut(
            id=item.id,
            question_id=item.question_id,
            question_uid=question.question_uid,
            question_ko=question.question_ko,
            question_en=question.question_en,
            report_type=item.report_type,
            description=item.description,
            status=item.status,
            resolution_note=item.resolution_note,
            created_at=item.created_at,
            resolved_at=item.resolved_at,
        )
        for item, question in db.execute(stmt).all()
    ]


@admin.patch("/reports/{report_id}")
def patch_report(report_id: int, payload: ReportUpdate, db: Db) -> dict[str, str]:
    item = db.get(QuestionReport, report_id)
    if not item: raise HTTPException(404, "Report not found")
    item.status = payload.status; item.resolution_note = payload.resolution_note; item.resolved_at = utcnow() if payload.status in {"resolved", "excluded", "rejected"} else None; db.commit(); return {"status": item.status}


router.include_router(admin)
