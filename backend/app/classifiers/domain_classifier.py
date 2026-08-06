from __future__ import annotations

import argparse
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.orm import Session, selectinload

from app.core.config import get_settings
from app.db.base import utcnow
from app.db.session import SessionLocal
from app.models.entities import AppSetting, Certification, Domain, Question

PROMPT_VERSION = "dea-domain-v1"
DOMAIN_CODES = {"DEA-D1", "DEA-D2", "DEA-D3", "DEA-D4"}


class ClassificationItem(BaseModel):
    question_id: int
    domain_code: str
    confidence: float = Field(ge=0, le=1)
    reason: str


class ClassificationBatch(BaseModel):
    results: list[ClassificationItem]


def _threshold(db: Session) -> float:
    setting = db.get(AppSetting, "classification_confidence_threshold")
    if setting and isinstance(setting.value_json, (int, float)):
        return float(setting.value_json)
    return 0.80


def report(db: Session, certification_code: str) -> dict[str, Any]:
    certification = db.scalar(
        select(Certification).where(Certification.certification_code == certification_code)
    )
    if certification is None:
        raise ValueError("certification not found")
    counts = dict(
        db.execute(
            select(Domain.domain_code, func.count(Question.id))
            .outerjoin(Question, Question.domain_id == Domain.id)
            .where(Domain.certification_id == certification.id)
            .group_by(Domain.domain_code)
        ).all()
    )
    statuses = dict(
        db.execute(
            select(Question.classification_status, func.count(Question.id))
            .where(Question.certification_id == certification.id)
            .group_by(Question.classification_status)
        ).all()
    )
    return {"certification": certification_code, "domain_counts": counts, "status_counts": statuses}


def _payload(question: Question) -> dict[str, Any]:
    return {
        "question_id": question.id,
        "question_en": question.question_en,
        "question_ko": question.question_ko,
        "choices": [
            {"id": choice.choice_key, "en": choice.text_en, "ko": choice.text_ko}
            for choice in question.choices
        ],
        "final_answers": next(
            (
                version.answers_json
                for version in question.answer_versions
                if version.answer_source == "admin_final" and version.is_current
            ),
            [],
        ),
    }


def classify_questions(
    db: Session,
    certification_code: str,
    question_ids: list[int] | None = None,
    only_unclassified: bool = True,
    force: bool = False,
    batch_size: int = 10,
) -> dict[str, int]:
    settings = get_settings()
    model = settings.openai_verification_model or settings.openai_model
    if not settings.openai_api_key or not model:
        raise RuntimeError("OPENAI_API_KEY and OPENAI_VERIFICATION_MODEL or OPENAI_MODEL are required")
    certification = db.scalar(
        select(Certification).where(Certification.certification_code == certification_code)
    )
    if certification is None or certification_code != "DEA-C01":
        raise ValueError("DEA-C01 certification not found")
    unclassified = db.scalar(
        select(Domain).where(
            Domain.certification_id == certification.id,
            Domain.domain_code == "DEA-UNCLASSIFIED",
        )
    )
    if unclassified is None:
        raise ValueError("DEA-UNCLASSIFIED domain not found")
    stmt = (
        select(Question)
        .where(Question.certification_id == certification.id)
        .options(selectinload(Question.choices), selectinload(Question.answer_versions))
    )
    if question_ids:
        stmt = stmt.where(Question.id.in_(question_ids))
    if only_unclassified:
        stmt = stmt.where(Question.domain_id == unclassified.id)
    if not force:
        stmt = stmt.where(
            (Question.classification_status.is_(None))
            | (Question.classification_status.in_(["needs_review", "failed"]))
        )
    questions = list(db.scalars(stmt))

    from openai import OpenAI

    client = OpenAI(
        api_key=settings.openai_api_key,
        timeout=settings.openai_timeout_seconds,
        max_retries=settings.openai_max_retries,
    )
    threshold = _threshold(db)
    applied = needs_review = failed = 0
    domain_map = {
        domain.domain_code: domain
        for domain in db.scalars(select(Domain).where(Domain.certification_id == certification.id))
    }
    for offset in range(0, len(questions), max(1, batch_size)):
        batch = questions[offset : offset + max(1, batch_size)]
        try:
            response = client.responses.parse(
                model=model,
                input=[
                    {
                        "role": "system",
                        "content": (
                            "Classify AWS DEA-C01 questions into exactly one official domain: "
                            "DEA-D1 Data Ingestion and Transformation; DEA-D2 Data Store Management; "
                            "DEA-D3 Data Operations and Support; DEA-D4 Data Security and Governance. "
                            "Use the question, choices, final answer, AWS services, core requirement, "
                            "and exam guide task statements. Return concise evidence-based reasons."
                        ),
                    },
                    {"role": "user", "content": str([_payload(question) for question in batch])},
                ],
                text_format=ClassificationBatch,
            )
            parsed = response.output_parsed
            if parsed is None:
                raise ValueError("empty structured classification output")
            by_id = {item.question_id: item for item in parsed.results}
            for question in batch:
                result = by_id.get(question.id)
                if result is None or result.domain_code not in DOMAIN_CODES:
                    question.classification_status = "failed"
                    question.classification_reason = "missing or invalid structured result"
                    failed += 1
                    continue
                question.classification_confidence = result.confidence
                question.classification_reason = result.reason
                question.classification_model = model
                question.classification_prompt_version = PROMPT_VERSION
                question.classified_at = utcnow()
                if result.confidence >= threshold:
                    question.domain_id = domain_map[result.domain_code].id
                    question.classification_status = "classified"
                    applied += 1
                else:
                    question.classification_status = "needs_review"
                    needs_review += 1
        except Exception as exc:
            for question in batch:
                question.classification_status = "failed"
                question.classification_reason = str(exc)[:2000]
                question.classification_model = model
                question.classification_prompt_version = PROMPT_VERSION
                question.classified_at = utcnow()
                failed += 1
        db.commit()
    return {"requested": len(questions), "classified": applied, "needs_review": needs_review, "failed": failed}


def main() -> int:
    parser = argparse.ArgumentParser(description="Classify DEA-C01 domains")
    parser.add_argument("--certification", default="DEA-C01")
    parser.add_argument("--only-unclassified", action="store_true")
    parser.add_argument("--report-only", action="store_true")
    parser.add_argument("--batch-size", type=int, default=10)
    args = parser.parse_args()
    with SessionLocal() as db:
        if args.report_only:
            print(report(db, args.certification))
            return 0
        print(
            classify_questions(
                db,
                args.certification,
                only_unclassified=args.only_unclassified,
                batch_size=args.batch_size,
            )
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
