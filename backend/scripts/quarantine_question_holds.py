"""Safely quarantine only HOLD_REVIEW questions from a supplied audit JSON.

This utility is intentionally independent of the administrator audit-table
migration so an urgent learner-pool quarantine can be performed first.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import SessionLocal
from app.models.entities import Question


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def question_text(record: dict[str, Any]) -> str:
    return normalized(record["question"]["ko"])


def choice_texts(record: dict[str, Any]) -> dict[str, str]:
    return {key: normalized(value["ko"]) for key, value in record["choices"].items()}


def exact_match(question: Question, record: dict[str, Any]) -> bool:
    if record.get("question_uid") and question.question_uid != record["question_uid"]:
        return False
    if normalized(question.question_ko) != question_text(record):
        return False
    return {choice.choice_key: normalized(choice.text_ko) for choice in question.choices} == choice_texts(record)


def preflight(
    db: Session,
    records: list[dict[str, Any]],
    manual_matches: dict[int, int] | None = None,
    not_in_production: set[int] | None = None,
    resolved_valid: set[int] | None = None,
) -> tuple[list[Question], list[dict[str, Any]], list[int], list[int]]:
    manual_matches = manual_matches or {}
    not_in_production = not_in_production or set()
    resolved_valid = resolved_valid or set()
    questions = list(db.scalars(select(Question).options(selectinload(Question.choices))))
    matched: list[Question] = []
    blocked: list[dict[str, Any]] = []
    absent: list[int] = []
    valid: list[int] = []
    for record in records:
        source_no = record.get("source_question_no")
        if source_no in not_in_production:
            absent.append(source_no)
            continue
        if source_no in resolved_valid:
            valid.append(source_no)
            continue
        if record.get("db_action") != "DO_NOT_APPLY" or record.get("status") != "HOLD_REVIEW":
            blocked.append({"source_question_no": source_no, "reason": "invalid_audit_status"})
            continue
        if source_no in manual_matches:
            candidate = next((item for item in questions if item.id == manual_matches[source_no]), None)
            if candidate is not None and record.get("question_uid") in (None, candidate.question_uid) and normalized(candidate.question_ko) == question_text(record):
                matched.append(candidate)
                continue
            blocked.append({"source_question_no": source_no, "reason": "manual_match_mismatch"})
            continue
        if record.get("question_id") is not None:
            candidate = next((item for item in questions if item.id == record["question_id"]), None)
            if candidate is not None and exact_match(candidate, record):
                matched.append(candidate)
                continue
            blocked.append({"source_question_no": record.get("source_question_no"), "reason": "id_or_content_mismatch"})
            continue
        candidates = [item for item in questions if exact_match(item, record)]
        if len(candidates) == 1:
            matched.append(candidates[0])
        else:
            blocked.append({"source_question_no": record.get("source_question_no"), "reason": f"content_matches={len(candidates)}"})
    return matched, blocked, absent, valid


def parse_mapping(value: str) -> tuple[int, int]:
    try:
        source_no, question_id = (int(part) for part in value.split("=", maxsplit=1))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use SOURCE_QUESTION_NO=QUESTION_ID") from exc
    return source_no, question_id


def main() -> int:
    parser = argparse.ArgumentParser(description="Quarantine HOLD_REVIEW questions after exact matching.")
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--apply", action="store_true", help="Apply only after a clean preflight.")
    parser.add_argument("--manual-match", action="append", type=parse_mapping, default=[], metavar="SOURCE=ID")
    parser.add_argument("--not-in-production", action="append", type=int, default=[], metavar="SOURCE")
    parser.add_argument("--resolved-valid", action="append", type=int, default=[], metavar="SOURCE")
    args = parser.parse_args()
    records = json.loads(args.review.read_text(encoding="utf-8"))["review_cases"]
    with SessionLocal() as db:
        matched, blocked, absent, valid = preflight(
            db, records, dict(args.manual_match), set(args.not_in_production), set(args.resolved_valid)
        )
        report = {
            "requested": len(records), "matched": len(matched), "blocked": blocked,
            "not_in_production": absent,
            "resolved_valid": valid,
            "mode": "apply" if args.apply else "preflight",
        }
        if blocked or not args.apply:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 2 if blocked else 0
        for question in matched:
            question.verification_status = "needs_review"
        db.commit()
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
