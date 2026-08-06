from __future__ import annotations

import argparse
import csv
import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.base import utcnow
from app.db.session import SessionLocal
from app.models.entities import (
    Certification,
    Domain,
    Question,
    QuestionAnswerVersion,
    QuestionChoice,
)
from app.schemas.api import DatasetQuestion


@dataclass
class ImportSummary:
    total: int = 0
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    excluded: int = 0
    failed: int = 0
    errors: list[str] = field(default_factory=list)


def _read_json(path: Path) -> Any:
    if not path.is_file():
        raise ValueError(f"required dataset file is missing: {path.name}")
    return json.loads(path.read_text(encoding="utf-8-sig"))


def _dt(value: str | None) -> datetime | None:
    return datetime.fromisoformat(value.replace("Z", "+00:00")) if value else None


def _excluded_ids(path: Path) -> set[str]:
    if not path.is_file():
        return set()
    with path.open("r", encoding="utf-8-sig", newline="") as stream:
        rows = csv.DictReader(stream)
        return {
            str(row.get("question_id") or row.get("question_uid") or "").strip()
            for row in rows
            if row.get("question_id") or row.get("question_uid")
        }


def _content_hash(item: DatasetQuestion) -> str:
    body = {
        "question_en": item.question_en.strip(),
        "question_ko": item.question_ko.strip(),
        "choices": [(choice.id, choice.text_en.strip(), choice.text_ko.strip()) for choice in item.choices],
    }
    return hashlib.sha256(
        json.dumps(body, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()


def _load_metadata(db: Session, root: Path) -> None:
    certifications = _read_json(root / "certifications.json")
    domains = _read_json(root / "domains.json")
    allowed_codes = {"DEA-C01"}
    for raw in certifications:
        code = raw["certification_code"]
        if code not in allowed_codes:
            continue
        item = db.scalar(select(Certification).where(Certification.certification_code == code))
        if item is None:
            item = Certification(certification_code=code)
            db.add(item)
        raw = {
            **raw,
            "name_en": raw.get("name_en") or raw.get("certification_name") or code,
            "name_ko": raw.get("name_ko") or raw.get("certification_name") or code,
            "exam_version": raw.get("exam_version") or code,
        }
        for name in (
            "name_en", "name_ko", "exam_version", "default_question_count",
            "default_duration_minutes", "passing_score", "score_type",
            "official_reference_url", "is_active",
        ):
            if name in raw:
                setattr(item, name, raw[name])
        item.is_active = code == "DEA-C01" and bool(raw.get("is_active", True))
        item.official_verified_at = _dt(raw.get("official_verified_at"))
    db.flush()

    for raw in domains:
        if raw["certification_code"] != "DEA-C01":
            continue
        certification = db.scalar(
            select(Certification).where(Certification.certification_code == "DEA-C01")
        )
        if certification is None:
            raise ValueError("DEA-C01 certification metadata is missing")
        item = db.scalar(
            select(Domain).where(
                Domain.certification_id == certification.id,
                Domain.domain_code == raw["domain_code"],
            )
        )
        if item is None:
            item = Domain(certification_id=certification.id, domain_code=raw["domain_code"])
            db.add(item)
        raw = {
            **raw,
            "name_en": raw.get("name_en") or raw.get("domain_name_en") or raw["domain_code"],
            "name_ko": raw.get("name_ko") or raw.get("domain_name_ko") or raw.get("domain_name_en") or raw["domain_code"],
        }
        for name in ("name_en", "name_ko", "exam_weight", "sort_order", "is_active"):
            if name in raw:
                setattr(item, name, raw[name])
    db.flush()


def _ensure_unclassified_domain(db: Session, certification: Certification) -> Domain:
    domain = db.scalar(
        select(Domain).where(
            Domain.certification_id == certification.id,
            Domain.domain_code == "DEA-UNCLASSIFIED",
        )
    )
    if domain is None:
        domain = Domain(
            certification_id=certification.id,
            domain_code="DEA-UNCLASSIFIED",
            name_en="Unclassified",
            name_ko="미분류",
            exam_weight=0,
            sort_order=99,
            is_active=True,
        )
        db.add(domain)
        db.flush()
    return domain


def _sync_answers(question: Question, item: DatasetQuestion) -> None:
    versions = [
        ("provided", item.provided_answers),
        ("ai_verified", item.verified_answers),
        ("admin_final", item.final_answers),
    ]
    for version in question.answer_versions:
        version.is_current = False
    for source, answers in versions:
        if not answers:
            continue
        existing = next(
            (
                version
                for version in question.answer_versions
                if version.answer_source == source and version.answers_json == answers
            ),
            None,
        )
        if existing is None:
            existing = QuestionAnswerVersion(
                answer_source=source,
                answers_json=answers,
                reason=item.verification_reason,
                confidence=item.verification_confidence,
            )
            question.answer_versions.append(existing)
        existing.is_current = source == "admin_final"


def _upsert_question(db: Session, item: DatasetQuestion) -> str:
    certification = db.scalar(
        select(Certification).where(Certification.certification_code == item.certification_code)
    )
    if certification is None or item.certification_code != "DEA-C01":
        raise ValueError("only DEA-C01 questions are accepted in phase 1")
    domain = db.scalar(
        select(Domain).where(
            Domain.certification_id == certification.id,
            Domain.domain_code == item.domain_code,
        )
    )
    if domain is None and item.domain_code == "DEA-UNCLASSIFIED":
        domain = _ensure_unclassified_domain(db, certification)
    if domain is None:
        raise ValueError(f"unknown domain_code: {item.domain_code}")

    digest = _content_hash(item)
    question = db.scalar(select(Question).where(Question.question_uid == item.question_id))
    if question is None:
        collision = db.scalar(select(Question).where(Question.content_hash == digest))
        if collision is not None:
            raise ValueError(f"content duplicate of {collision.question_uid}")
        question = Question(
            question_uid=item.question_id,
            certification_id=certification.id,
            domain_id=domain.id,
            question_type=item.question_type,
            question_en=item.question_en,
            question_ko=item.question_ko,
            required_answer_count=item.required_answer_count,
            difficulty=item.difficulty,
            verification_status=item.verification_status,
            verification_confidence=item.verification_confidence,
            source_page=item.source_page,
            is_active=item.is_active,
            content_hash=digest,
            classification_status=(
                item.classification_status
                or ("needs_review" if item.domain_code == "DEA-UNCLASSIFIED" else "classified")
            ),
            classification_confidence=item.classification_confidence,
            classification_reason=item.classification_reason,
            classification_model=item.classification_method,
            classification_prompt_version="dataset-1.1",
            classified_at=utcnow() if item.classification_status else None,
        )
        db.add(question)
        state = "added"
    else:
        state = "unchanged" if question.content_hash == digest else "updated"
        question.certification_id = certification.id
        question.domain_id = domain.id
        question.question_type = item.question_type
        question.question_en = item.question_en
        question.question_ko = item.question_ko
        question.required_answer_count = item.required_answer_count
        question.difficulty = item.difficulty
        question.verification_status = item.verification_status
        question.verification_confidence = item.verification_confidence
        question.source_page = item.source_page
        question.is_active = item.is_active
        question.content_hash = digest
        if item.domain_code == "DEA-UNCLASSIFIED" and question.classification_status != "manual":
            question.classification_status = "needs_review"
        elif question.classification_status != "manual":
            question.classification_status = item.classification_status or "classified"
            question.classification_confidence = item.classification_confidence
            question.classification_reason = item.classification_reason
            question.classification_model = item.classification_method
            question.classification_prompt_version = "dataset-1.1"
            question.classified_at = utcnow() if item.classification_status else question.classified_at

    existing_choices = {choice.choice_key: choice for choice in question.choices}
    incoming_keys = {choice.id for choice in item.choices}
    for stale_key in existing_choices.keys() - incoming_keys:
        db.delete(existing_choices[stale_key])
    for index, choice in enumerate(item.choices):
        stored = existing_choices.get(choice.id)
        if stored is None:
            stored = QuestionChoice(choice_key=choice.id)
            question.choices.append(stored)
        stored.text_en = choice.text_en
        stored.text_ko = choice.text_ko
        stored.sort_order = index
    _sync_answers(question, item)
    db.flush()
    return state


def import_dataset(db: Session, root: Path, mode: str) -> ImportSummary:
    if mode not in {"dry-run", "strict", "partial"}:
        raise ValueError("mode must be dry-run, strict, or partial")
    root = root.resolve()
    manifest = _read_json(root / "manifest.json")
    report_path = root / "verification_report.json"
    if not report_path.is_file():
        report_path = root / "validation_report.json"
    _read_json(report_path)
    questions_path = root / "questions.jsonl"
    if not questions_path.is_file():
        raise ValueError("required dataset file is missing: questions.jsonl")
    _load_metadata(db, root)
    excluded = _excluded_ids(root / "excluded_questions.csv")
    summary = ImportSummary()

    with questions_path.open("r", encoding="utf-8-sig") as stream:
        for line_number, line in enumerate(stream, 1):
            if not line.strip():
                continue
            summary.total += 1
            try:
                raw = json.loads(line)
                uid = str(raw.get("question_id", ""))
                if raw.get("certification_code") != "DEA-C01" or uid in excluded:
                    summary.excluded += 1
                    continue
                item = DatasetQuestion.model_validate(raw)
                state = _upsert_question(db, item)
                setattr(summary, state, getattr(summary, state) + 1)
            except (json.JSONDecodeError, ValidationError, ValueError) as exc:
                summary.failed += 1
                summary.errors.append(f"line={line_number}: {exc}")
                if mode == "strict":
                    db.rollback()
                    return summary

    expected = manifest.get("question_count")
    if isinstance(expected, int) and expected != summary.total:
        summary.failed += 1
        summary.errors.append(
            f"manifest question_count={expected} does not match streamed rows={summary.total}"
        )
    if mode == "dry-run" or (mode == "strict" and summary.failed):
        db.rollback()
    else:
        db.commit()
    return summary


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate or import a DEA-C01 dataset package")
    parser.add_argument("--path", required=True, type=Path)
    parser.add_argument("--mode", choices=["dry-run", "strict", "partial"], default="dry-run")
    args = parser.parse_args()
    with SessionLocal() as db:
        summary = import_dataset(db, args.path, args.mode)
    print(
        f"total={summary.total} added={summary.added} updated={summary.updated} "
        f"unchanged={summary.unchanged} excluded={summary.excluded} failed={summary.failed}"
    )
    for error in summary.errors:
        print(error)
    return 1 if summary.failed else 0


if __name__ == "__main__":
    raise SystemExit(main())
