"""Persist administrator-facing history for already quarantined audit questions."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

BACKEND_ROOT = Path(__file__).resolve().parents[1]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from sqlalchemy import select

from app.db.session import SessionLocal
from app.models.entities import QuestionReviewAudit
from scripts.quarantine_question_holds import preflight

AUDIT_BATCH = "dea-c01-audit-2026-11-09"


def parse_mapping(value: str) -> tuple[int, int]:
    try:
        source_no, question_id = (int(part) for part in value.split("=", maxsplit=1))
    except ValueError as exc:
        raise argparse.ArgumentTypeError("use SOURCE_QUESTION_NO=QUESTION_ID") from exc
    return source_no, question_id


def unique_question_pairs(
    pairs: list[tuple[dict[str, Any], Any]],
) -> tuple[list[tuple[dict[str, Any], Any]], list[dict[str, Any]]]:
    """Keep one administrator record per DB question and disclose duplicate source entries."""
    unique: dict[int, tuple[dict[str, Any], Any]] = {}
    duplicates: dict[int, list[int]] = {}
    for record, question in pairs:
        source_no = record["source_question_no"]
        if question.id not in unique:
            unique[question.id] = (record, question)
            duplicates[question.id] = [source_no]
        else:
            duplicates[question.id].append(source_no)
    duplicate_sources = [
        {"question_id": question_id, "source_question_nos": source_nos}
        for question_id, source_nos in duplicates.items()
        if len(source_nos) > 1
    ]
    return list(unique.values()), duplicate_sources


def main() -> int:
    parser = argparse.ArgumentParser(description="Import review history for quarantined DEA-C01 questions.")
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--manual-match", action="append", type=parse_mapping, default=[], metavar="SOURCE=ID")
    parser.add_argument("--not-in-production", action="append", type=int, default=[], metavar="SOURCE")
    parser.add_argument("--resolved-valid", action="append", type=int, default=[], metavar="SOURCE")
    args = parser.parse_args()
    records = json.loads(args.review.read_text(encoding="utf-8"))["review_cases"]
    with SessionLocal() as db:
        matched, blocked, absent, valid = preflight(
            db, records, dict(args.manual_match), set(args.not_in_production), set(args.resolved_valid)
        )
        if blocked:
            print(json.dumps({
                "requested": len(records), "matched": len(matched), "blocked": blocked,
                "not_in_production": absent, "resolved_valid": valid, "mode": "preflight",
            }, ensure_ascii=False, indent=2))
            return 2
        pairs: list[tuple[dict[str, Any], Any]] = []
        for record in records:
            source_no = record["source_question_no"]
            if source_no in set(args.not_in_production) | set(args.resolved_valid):
                continue
            one_match, one_blocked, _, _ = preflight(
                db, [record], dict(args.manual_match), set(), set()
            )
            if one_blocked or len(one_match) != 1:
                raise RuntimeError(f"Unable to resolve source question {source_no}")
            pairs.append((record, one_match[0]))
        unique_pairs, duplicate_sources = unique_question_pairs(pairs)
        if {question.id for _, question in unique_pairs} != {question.id for question in matched}:
            raise RuntimeError("Preflight resolution changed before import")
        report = {
            "requested": len(records), "matched": len(matched),
            "unique_questions": len(unique_pairs), "duplicate_source_matches": duplicate_sources,
            "blocked": blocked, "not_in_production": absent, "resolved_valid": valid,
            "mode": "apply" if args.apply else "preflight",
        }
        if not args.apply:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 0
        for record, question in unique_pairs:
            if question.verification_status != "needs_review":
                raise RuntimeError(f"Question {question.id} is not quarantined")
            existing = db.scalar(select(QuestionReviewAudit).where(
                QuestionReviewAudit.question_id == question.id,
                QuestionReviewAudit.audit_batch == AUDIT_BATCH,
            ))
            if existing is None:
                existing = QuestionReviewAudit(question_id=question.id, audit_batch=AUDIT_BATCH)
                db.add(existing)
            existing.disposition = "quarantined"
            existing.audit_status = "HOLD_REVIEW"
            existing.issue_summary = record["ambiguity"]
            existing.correction_summary = record["review_required"]
            existing.source_pdf_page = record.get("source_pdf_page")
            existing.sources_json = record.get("sources", [])
            existing.proposed_answers = record.get("unapproved_suggested_answers", [])
            existing.content_fingerprint = record.get("expected_question_sha256", "")
        db.commit()
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
