from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Float, ForeignKey, Index, Integer, JSON, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base, TimestampMixin, utcnow


class Certification(Base, TimestampMixin):
    __tablename__ = "certifications"
    id: Mapped[int] = mapped_column(primary_key=True)
    certification_code: Mapped[str] = mapped_column(String(32), unique=True, index=True)
    name_en: Mapped[str] = mapped_column(String(255))
    name_ko: Mapped[str] = mapped_column(String(255), default="")
    exam_version: Mapped[str] = mapped_column(String(64), default="")
    default_question_count: Mapped[int] = mapped_column(Integer)
    default_duration_minutes: Mapped[int] = mapped_column(Integer)
    passing_score: Mapped[float] = mapped_column(Float)
    score_type: Mapped[str] = mapped_column(String(32), default="percentage")
    official_reference_url: Mapped[str | None] = mapped_column(String(1000))
    official_verified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    domains: Mapped[list["Domain"]] = relationship(back_populates="certification", cascade="all, delete-orphan")


class Domain(Base, TimestampMixin):
    __tablename__ = "domains"
    __table_args__ = (UniqueConstraint("certification_id", "domain_code"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    certification_id: Mapped[int] = mapped_column(ForeignKey("certifications.id"), index=True)
    domain_code: Mapped[str] = mapped_column(String(64))
    name_en: Mapped[str] = mapped_column(String(255))
    name_ko: Mapped[str] = mapped_column(String(255), default="")
    exam_weight: Mapped[float] = mapped_column(Float)
    sort_order: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    certification: Mapped[Certification] = relationship(back_populates="domains")


class Question(Base, TimestampMixin):
    __tablename__ = "questions"
    __table_args__ = (Index("ix_question_pool", "certification_id", "domain_id", "is_active", "verification_status"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    question_uid: Mapped[str] = mapped_column(String(128), unique=True)
    certification_id: Mapped[int] = mapped_column(ForeignKey("certifications.id"), index=True)
    domain_id: Mapped[int] = mapped_column(ForeignKey("domains.id"), index=True)
    question_type: Mapped[str] = mapped_column(String(32))
    question_en: Mapped[str] = mapped_column(Text)
    question_ko: Mapped[str] = mapped_column(Text, default="")
    required_answer_count: Mapped[int] = mapped_column(Integer, default=1)
    difficulty: Mapped[str] = mapped_column(String(16), default="medium")
    verification_status: Mapped[str] = mapped_column(String(32), default="needs_review", index=True)
    verification_confidence: Mapped[float | None] = mapped_column(Float)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, index=True)
    is_reported: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    review_status: Mapped[str] = mapped_column(String(32), default="pending")
    source_page: Mapped[int | None] = mapped_column(Integer)
    content_hash: Mapped[str] = mapped_column(String(64), unique=True)
    classification_confidence: Mapped[float | None] = mapped_column(Float)
    classification_reason: Mapped[str | None] = mapped_column(Text)
    classification_model: Mapped[str | None] = mapped_column(String(128))
    classification_prompt_version: Mapped[str | None] = mapped_column(String(32))
    classified_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    classification_status: Mapped[str | None] = mapped_column(String(32), index=True)
    choices: Mapped[list["QuestionChoice"]] = relationship(cascade="all, delete-orphan", order_by="QuestionChoice.sort_order")
    answer_versions: Mapped[list["QuestionAnswerVersion"]] = relationship(cascade="all, delete-orphan")


class QuestionChoice(Base, TimestampMixin):
    __tablename__ = "question_choices"
    __table_args__ = (UniqueConstraint("question_id", "choice_key"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    choice_key: Mapped[str] = mapped_column(String(8))
    text_en: Mapped[str] = mapped_column(Text)
    text_ko: Mapped[str] = mapped_column(Text, default="")
    sort_order: Mapped[int] = mapped_column(Integer)


class QuestionAnswerVersion(Base):
    __tablename__ = "question_answer_versions"
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    answer_source: Mapped[str] = mapped_column(String(32))
    answers_json: Mapped[list[str]] = mapped_column(JSON)
    reason: Mapped[str | None] = mapped_column(Text)
    model_name: Mapped[str | None] = mapped_column(String(128))
    confidence: Mapped[float | None] = mapped_column(Float)
    is_current: Mapped[bool] = mapped_column(Boolean, default=False, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class QuestionExplanation(Base, TimestampMixin):
    __tablename__ = "question_explanations"
    __table_args__ = (UniqueConstraint("question_id", "language"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    language: Mapped[str] = mapped_column(String(8))
    correct_answer_summary: Mapped[str] = mapped_column(Text)
    core_reason: Mapped[str] = mapped_column(Text)
    keywords_json: Mapped[list[str]] = mapped_column(JSON, default=list)
    choice_analysis_json: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    related_concepts: Mapped[str] = mapped_column(Text, default="")
    exam_traps: Mapped[str] = mapped_column(Text, default="")
    memory_summary: Mapped[str] = mapped_column(Text, default="")
    model_name: Mapped[str | None] = mapped_column(String(128))
    prompt_version: Mapped[str] = mapped_column(String(32), default="v1")
    generation_status: Mapped[str] = mapped_column(String(32), default="complete")
    token_input: Mapped[int] = mapped_column(Integer, default=0)
    token_output: Mapped[int] = mapped_column(Integer, default=0)


class StudyAttempt(Base):
    __tablename__ = "study_attempts"
    id: Mapped[int] = mapped_column(primary_key=True)
    session_id: Mapped[str] = mapped_column(String(36), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    selected_answers_json: Mapped[list[str]] = mapped_column(JSON)
    is_correct: Mapped[bool] = mapped_column(Boolean)
    attempted_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MockExam(Base):
    __tablename__ = "mock_exams"
    id: Mapped[int] = mapped_column(primary_key=True)
    certification_id: Mapped[int] = mapped_column(ForeignKey("certifications.id"), index=True)
    status: Mapped[str] = mapped_column(String(32), default="in_progress", index=True)
    question_count: Mapped[int] = mapped_column(Integer)
    duration_minutes: Mapped[int] = mapped_column(Integer)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
    raw_score: Mapped[float | None] = mapped_column(Float)
    scaled_score: Mapped[float | None] = mapped_column(Float)
    passing_score: Mapped[float] = mapped_column(Float)
    result: Mapped[str | None] = mapped_column(String(16))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    questions: Mapped[list["MockExamQuestion"]] = relationship(cascade="all, delete-orphan", order_by="MockExamQuestion.question_order")


class MockExamQuestion(Base):
    __tablename__ = "mock_exam_questions"
    __table_args__ = (
        UniqueConstraint("mock_exam_id", "question_id", name="uq_mock_exam_question_question"),
        UniqueConstraint("mock_exam_id", "question_order", name="uq_mock_exam_question_order"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    mock_exam_id: Mapped[int] = mapped_column(ForeignKey("mock_exams.id"), index=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    question_order: Mapped[int] = mapped_column(Integer)
    selected_answers_json: Mapped[list[str] | None] = mapped_column(JSON)
    is_correct: Mapped[bool | None] = mapped_column(Boolean)
    is_marked_for_review: Mapped[bool] = mapped_column(Boolean, default=False)
    answered_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class WrongNote(Base, TimestampMixin):
    __tablename__ = "wrong_notes"
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), unique=True)
    wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    correct_after_wrong_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(32), default="active", index=True)
    first_wrong_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_wrong_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class QuestionReport(Base):
    __tablename__ = "question_reports"
    id: Mapped[int] = mapped_column(primary_key=True)
    question_id: Mapped[int] = mapped_column(ForeignKey("questions.id"), index=True)
    report_type: Mapped[str] = mapped_column(String(32), index=True)
    description: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(32), default="received", index=True)
    resolution_note: Mapped[str | None] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))


class AppSetting(Base, TimestampMixin):
    __tablename__ = "app_settings"
    key: Mapped[str] = mapped_column(String(128), primary_key=True)
    value_json: Mapped[Any] = mapped_column(JSON)


class AIUsageLog(Base):
    __tablename__ = "ai_usage_logs"
    id: Mapped[int] = mapped_column(primary_key=True)
    operation: Mapped[str] = mapped_column(String(32), index=True)
    model_name: Mapped[str] = mapped_column(String(128))
    status: Mapped[str] = mapped_column(String(32))
    token_input: Mapped[int] = mapped_column(Integer, default=0)
    token_output: Mapped[int] = mapped_column(Integer, default=0)
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    error_code: Mapped[str | None] = mapped_column(String(64))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ImportJob(Base):
    __tablename__ = "import_jobs"
    id: Mapped[int] = mapped_column(primary_key=True)
    mode: Mapped[str] = mapped_column(String(16))
    status: Mapped[str] = mapped_column(String(32), index=True)
    source_path: Mapped[str] = mapped_column(String(1000))
    total_count: Mapped[int] = mapped_column(Integer, default=0)
    imported_count: Mapped[int] = mapped_column(Integer, default=0)
    updated_count: Mapped[int] = mapped_column(Integer, default=0)
    excluded_count: Mapped[int] = mapped_column(Integer, default=0)
    rejected_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ImportJobError(Base):
    __tablename__ = "import_job_errors"
    id: Mapped[int] = mapped_column(primary_key=True)
    import_job_id: Mapped[int] = mapped_column(ForeignKey("import_jobs.id"), index=True)
    line_number: Mapped[int | None] = mapped_column(Integer)
    question_uid: Mapped[str | None] = mapped_column(String(128))
    error_code: Mapped[str] = mapped_column(String(64))
    message: Mapped[str] = mapped_column(Text)
