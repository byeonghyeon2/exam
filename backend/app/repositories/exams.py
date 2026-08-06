from sqlalchemy import Select, select
from sqlalchemy.orm import Session, selectinload

from app.models.entities import Certification, Domain, Question, QuestionAnswerVersion


class ExamRepository:
    def __init__(self, db: Session) -> None:
        self.db = db

    def certification(self, code: str) -> Certification | None:
        return self.db.scalar(select(Certification).where(Certification.certification_code == code))

    def eligible_questions(self, certification_id: int, domain_id: int | None = None) -> list[Question]:
        stmt: Select[tuple[Question]] = select(Question).where(
            Question.certification_id == certification_id,
            Question.is_active.is_(True),
            Question.verification_status.in_(["verified", "provided"]),
            Question.answer_versions.any(
                QuestionAnswerVersion.is_current.is_(True)
                & (QuestionAnswerVersion.answer_source == "admin_final")
            ),
        ).options(selectinload(Question.choices), selectinload(Question.answer_versions))
        if domain_id is not None:
            stmt = stmt.where(Question.domain_id == domain_id)
        questions = list(self.db.scalars(stmt))
        return [
            question
            for question in questions
            if len(
                next(
                    (
                        version.answers_json
                        for version in question.answer_versions
                        if version.is_current and version.answer_source == "admin_final"
                    ),
                    [],
                )
            )
            == question.required_answer_count
        ]

    def domain_by_code(self, certification_id: int, code: str) -> Domain | None:
        return self.db.scalar(select(Domain).where(Domain.certification_id == certification_id, Domain.domain_code == code))
