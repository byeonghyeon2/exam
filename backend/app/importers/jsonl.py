import hashlib
import json
from collections.abc import Iterator
from dataclasses import dataclass
from pathlib import Path

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.entities import Certification, Domain, Question, QuestionAnswerVersion, QuestionChoice
from app.schemas.api import DatasetQuestion


@dataclass(frozen=True)
class ImportErrorItem:
    line: int
    question_uid: str | None
    message: str


@dataclass(frozen=True)
class ImportResult:
    total: int
    imported: int
    errors: list[ImportErrorItem]


def iter_questions(path: Path) -> Iterator[tuple[int, DatasetQuestion | None, ImportErrorItem | None]]:
    with path.open("r", encoding="utf-8-sig") as source:
        for line_number, line in enumerate(source, 1):
            try:
                raw = json.loads(line)
                yield line_number, DatasetQuestion.model_validate(raw), None
            except (json.JSONDecodeError, ValidationError) as exc:
                uid = raw.get("question_id") if "raw" in locals() and isinstance(raw, dict) else None
                yield line_number, None, ImportErrorItem(line_number, uid, str(exc))


def content_hash(item: DatasetQuestion) -> str:
    normalized = json.dumps({"en": item.question_en.strip(), "choices": sorted((c.id, c.text_en.strip()) for c in item.choices)}, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(normalized.encode()).hexdigest()


def import_jsonl(db: Session, path: Path, mode: str) -> ImportResult:
    if not path.is_file():
        raise ValueError("questions.jsonl file not found")
    total = imported = 0
    errors: list[ImportErrorItem] = []
    for line_number, item, error in iter_questions(path):
        total += 1
        if error:
            errors.append(error)
            if mode == "strict":
                db.rollback()
                return ImportResult(total, 0, errors)
            continue
        assert item is not None
        cert = db.scalar(select(Certification).where(Certification.certification_code == item.certification_code))
        domain = db.scalar(select(Domain).where(Domain.domain_code == item.domain_code, Domain.certification_id == cert.id)) if cert else None
        duplicate = db.scalar(select(Question.id).where((Question.question_uid == item.question_id) | (Question.content_hash == content_hash(item))))
        if not cert or not domain or duplicate:
            reason = "unknown certification/domain" if not cert or not domain else "duplicate question uid or content"
            errors.append(ImportErrorItem(line_number, item.question_id, reason))
            if mode == "strict":
                db.rollback()
                return ImportResult(total, 0, errors)
            continue
        if mode != "dry-run":
            question = Question(question_uid=item.question_id, certification_id=cert.id, domain_id=domain.id, question_type=item.question_type, question_en=item.question_en, question_ko=item.question_ko, required_answer_count=item.required_answer_count, difficulty=item.difficulty, verification_status=item.verification_status, verification_confidence=item.verification_confidence, source_page=item.source_page, is_active=item.is_active, content_hash=content_hash(item))
            question.choices = [QuestionChoice(choice_key=c.id, text_en=c.text_en, text_ko=c.text_ko, sort_order=i) for i, c in enumerate(item.choices)]
            question.answer_versions = [QuestionAnswerVersion(answer_source="admin_final", answers_json=item.final_answers, reason=item.verification_reason, confidence=item.verification_confidence, is_current=True)]
            db.add(question)
            imported += 1
    if mode != "dry-run":
        db.commit()
    return ImportResult(total, imported, errors)

