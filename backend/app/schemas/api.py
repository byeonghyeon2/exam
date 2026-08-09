from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, computed_field, model_validator


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class LoginRequest(BaseModel):
    username: str = Field(min_length=3, max_length=64, pattern=r"^[A-Za-z0-9._-]+$")
    password: str = Field(min_length=8, max_length=128)


class UserCreate(LoginRequest):
    role: Literal["user", "admin"] = "user"


class UserUpdate(BaseModel):
    password: str | None = Field(None, min_length=8, max_length=128)
    is_active: bool | None = None


class UserOut(ORMModel):
    id: int
    username: str
    role: Literal["user", "admin"]
    is_active: bool
    created_at: datetime
    last_login_at: datetime | None


class ChoiceOut(ORMModel):
    choice_key: str
    text_en: str
    text_ko: str

    @computed_field
    @property
    def id(self) -> str:
        return self.choice_key


class DomainOut(ORMModel):
    id: int
    domain_code: str
    name_en: str
    name_ko: str
    exam_weight: float
    sort_order: int


class CertificationOut(ORMModel):
    id: int
    certification_code: str
    name_en: str
    name_ko: str
    exam_version: str
    default_question_count: int
    default_duration_minutes: int
    passing_score: float
    score_type: str
    official_reference_url: str | None
    official_verified_at: datetime | None

    @computed_field
    @property
    def code(self) -> str:
        return self.certification_code


class QuestionOut(ORMModel):
    id: int
    question_uid: str
    question_type: str
    question_en: str
    question_ko: str
    required_answer_count: int
    difficulty: str
    choices: list[ChoiceOut] = []


class SubmitAnswer(BaseModel):
    selected_answers: list[str]


class AnswerResult(BaseModel):
    correct: bool
    selected_answers: list[str]
    correct_answers: list[str]

    @computed_field
    @property
    def is_correct(self) -> bool:
        return self.correct


class StudySessionCreate(BaseModel):
    certification_code: str
    domain_code: str | None = None
    # None means every eligible question in the selected domain.
    question_count: int | None = Field(10, ge=1, le=1000)
    seed: int | None = None


class StudySessionOut(BaseModel):
    id: str
    question_ids: list[int]


class StudyHistoryQuestion(BaseModel):
    id: int
    question_uid: str
    question_ko: str


class StudyHistoryOut(BaseModel):
    session_id: str
    certification_code: str
    certification_name: str
    completed_at: datetime
    total_count: int
    correct_count: int
    wrong_count: int
    wrong_questions: list[StudyHistoryQuestion]


class MockExamCreate(BaseModel):
    certification_code: str
    question_count: int | None = Field(None, ge=1, le=200)
    duration_minutes: int | None = Field(None, ge=1, le=600)
    seed: int | None = None


class ExamAnswerUpdate(BaseModel):
    selected_answers: list[str]


class ReviewMarkUpdate(BaseModel):
    marked: bool


class WrongNoteUpdate(BaseModel):
    status: Literal["active", "reviewing", "mastered"]


class WrongNoteDelete(BaseModel):
    question_ids: list[int] = Field(min_length=1, max_length=1000)


class WrongNoteOut(BaseModel):
    question_id: int
    question_uid: str
    question_ko: str
    wrong_count: int
    status: str
    last_wrong_at: datetime


class ReportCreate(BaseModel):
    report_type: Literal["wrong_answer", "missing_content", "translation_error", "language_mismatch", "wrong_answer_count", "missing_asset", "wrong_explanation", "duplicate", "other"]
    description: str = Field(min_length=1, max_length=4000)


class AdminReportOut(BaseModel):
    id: int
    question_id: int
    question_uid: str
    question_ko: str
    question_en: str
    report_type: str
    description: str
    status: str
    resolution_note: str | None
    created_at: datetime
    resolved_at: datetime | None


class ReportUpdate(BaseModel):
    status: Literal["received", "reviewing", "resolved", "excluded", "rejected"]
    resolution_note: str | None = Field(None, max_length=4000)


class QuestionPatch(BaseModel):
    question_en: str | None = None
    question_ko: str | None = None
    domain_id: int | None = None
    required_answer_count: int | None = Field(None, ge=1)
    is_active: bool | None = None


class VerifyRequest(BaseModel):
    answers: list[str]
    reason: str = ""


class SettingPatch(BaseModel):
    values: dict[str, Any]


class ImportRequest(BaseModel):
    path: str
    mode: Literal["dry-run", "strict", "partial"] = "dry-run"


class ExplanationOut(ORMModel):
    language: str
    correct_answer_summary: str
    core_reason: str
    keywords_json: list[str]
    choice_analysis_json: dict[str, Any]
    related_concepts: str
    exam_traps: str
    memory_summary: str


class ExplanationGenerate(BaseModel):
    language: Literal["en", "ko"] = "ko"


class ClassificationRequest(BaseModel):
    question_ids: list[int] | None = None
    only_unclassified: bool = True
    force: bool = False
    batch_size: int = Field(10, ge=1, le=25)


class ManualDomainUpdate(BaseModel):
    domain_code: Literal["DEA-D1", "DEA-D2", "DEA-D3", "DEA-D4", "DEA-UNCLASSIFIED"]
    reason: str = Field("Administrator classification", max_length=2000)


class DatasetChoice(BaseModel):
    id: str
    text_en: str
    text_ko: str = ""


class DatasetQuestion(BaseModel):
    question_id: str
    certification_code: str
    domain_code: str
    question_type: Literal["multiple_choice", "multiple_response"]
    question_en: str
    question_ko: str = ""
    choices: list[DatasetChoice]
    provided_answers: list[str] = []
    verified_answers: list[str] = []
    final_answers: list[str]
    required_answer_count: int = Field(ge=1)
    verification_status: str = "verified"
    verification_confidence: float | None = Field(None, ge=0, le=1)
    verification_reason: str = ""
    classification_confidence: float | None = Field(None, ge=0, le=1)
    classification_reason: str | None = None
    classification_method: str | None = None
    classification_status: str | None = None
    difficulty: str = "medium"
    source_page: int | None = None
    is_active: bool = True

    @model_validator(mode="after")
    def validate_answers(self) -> "DatasetQuestion":
        keys = [choice.id for choice in self.choices]
        if len(keys) != len(set(keys)):
            raise ValueError("choice ids must be unique")
        if len(self.final_answers) != self.required_answer_count:
            raise ValueError("final answer count does not match required_answer_count")
        if not set(self.final_answers) <= set(keys):
            raise ValueError("final answers must reference choices")
        if self.question_type == "multiple_choice" and self.required_answer_count != 1:
            raise ValueError("multiple_choice requires exactly one answer")
        return self
