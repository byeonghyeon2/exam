"""Safely preflight or apply a supplied question-audit bundle.

The default is read-only.  ``--apply`` is deliberately required and the script
refuses a partial update when any audit record cannot be matched exactly.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from app.db.session import SessionLocal
from app.models.entities import (
    Question,
    QuestionAnswerVersion,
    QuestionExplanation,
    QuestionReviewAudit,
)

AUDIT_BATCH = "dea-c01-audit-2026-11-09"


def normalized(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


def choices_from(record: dict[str, Any]) -> dict[str, str]:
    raw = record.get("preconditions", {}).get("original_choices_ko", record.get("choices", {}))
    return {
        key: normalized(value.get("ko", "") if isinstance(value, dict) else value)
        for key, value in raw.items()
    }


def question_text_from(record: dict[str, Any]) -> str:
    raw = record.get("preconditions", {}).get("original_question_ko", record.get("question", {}).get("ko", ""))
    return normalized(raw)


def current_answers(question: Question) -> list[str] | None:
    answers = [item.answers_json for item in question.answer_versions if item.is_current and item.answer_source == "admin_final"]
    return answers[0] if len(answers) == 1 else None


def exact_match(question: Question, record: dict[str, Any]) -> bool:
    expected_uid = record.get("question_uid")
    if expected_uid and question.question_uid != expected_uid:
        return False
    if normalized(question.question_ko) != question_text_from(record):
        return False
    actual_choices = {item.choice_key: normalized(item.text_ko) for item in question.choices}
    return actual_choices == choices_from(record)


def resolve_question(db: Session, record: dict[str, Any], all_questions: list[Question]) -> tuple[Question | None, str]:
    question_id = record.get("question_id")
    if question_id is not None:
        direct = next((item for item in all_questions if item.id == question_id), None)
        return (direct, "id") if direct is not None and exact_match(direct, record) else (None, "id_mismatch")
    matches = [item for item in all_questions if exact_match(item, record)]
    return (matches[0], "content") if len(matches) == 1 else (None, f"content_matches={len(matches)}")


def audit_row(question: Question, record: dict[str, Any], disposition: str, status: str, issue: str, action: str) -> QuestionReviewAudit:
    return QuestionReviewAudit(
        question_id=question.id,
        audit_batch=AUDIT_BATCH,
        disposition=disposition,
        audit_status=status,
        issue_summary=issue,
        correction_summary=action,
        source_pdf_page=record.get("source_pdf_page"),
        sources_json=record.get("sources", []),
        proposed_answers=record.get("verified_answers", record.get("unapproved_suggested_answers", [])),
        content_fingerprint=record.get("preconditions", {}).get("normalized_question_choices_sha256", record.get("expected_question_sha256", "")),
    )


def load(path: Path, field: str) -> list[dict[str, Any]]:
    data = json.loads(path.read_text(encoding="utf-8"))
    return data[field]


def attach_review_identity(changes: list[dict[str, Any]], holds: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Hydrate compact explanation-only corrections with their audited source identity."""
    reviews = {item.get("source_question_no"): item for item in holds}
    hydrated: list[dict[str, Any]] = []
    for change in changes:
        if "preconditions" in change:
            hydrated.append(change)
            continue
        review = reviews.get(change.get("source_question_no"))
        if review is None:
            raise ValueError(f"No review identity found for source question {change.get('source_question_no')}")
        hydrated.append({
            **change,
            "question_id": review.get("question_id"),
            "question_uid": review.get("question_uid"),
            "source_pdf_page": review.get("source_pdf_page"),
            "sources": review.get("sources", []),
            "question": review.get("question", {}),
            "choices": review.get("choices", {}),
            "preconditions": {
                "existing_verified_answers": change["existing_verified_answers"],
                "normalized_question_choices_sha256": review.get("expected_question_sha256", ""),
            },
        })
    return hydrated


def preflight(db: Session, changes: list[dict[str, Any]], holds: list[dict[str, Any]]) -> tuple[list[tuple[dict[str, Any], Question]], list[tuple[dict[str, Any], Question]], list[dict[str, Any]]]:
    questions = list(db.scalars(select(Question).options(selectinload(Question.choices), selectinload(Question.answer_versions))))
    resolved_changes: list[tuple[dict[str, Any], Question]] = []
    resolved_holds: list[tuple[dict[str, Any], Question]] = []
    blocked: list[dict[str, Any]] = []
    for kind, records, resolved in (("change", changes, resolved_changes), ("hold", holds, resolved_holds)):
        for record in records:
            question, method = resolve_question(db, record, questions)
            if question is None:
                blocked.append({"kind": kind, "source_question_no": record.get("source_question_no"), "reason": method})
                continue
            if kind == "change":
                expected = record["preconditions"]["existing_verified_answers"]
                if current_answers(question) != expected:
                    blocked.append({"kind": kind, "question_id": question.id, "source_question_no": record.get("source_question_no"), "reason": "current_answer_mismatch"})
                    continue
            resolved.append((record, question))
    return resolved_changes, resolved_holds, blocked


def apply(db: Session, changes: list[tuple[dict[str, Any], Question]], holds: list[tuple[dict[str, Any], Question]]) -> None:
    for record, question in changes:
        old_answers = current_answers(question) or []
        answers_changed = old_answers != record["verified_answers"]
        if answers_changed:
            for version in question.answer_versions:
                version.is_current = False
            question.answer_versions.append(QuestionAnswerVersion(
                answer_source="admin_final", answers_json=record["verified_answers"],
                reason=record["reason"], is_current=True,
            ))
        payload = record["explanation"]
        explanation = db.scalar(select(QuestionExplanation).where(
            QuestionExplanation.question_id == question.id, QuestionExplanation.language == "ko"
        ))
        if explanation is None:
            explanation = QuestionExplanation(question_id=question.id, language="ko")
            db.add(explanation)
        explanation.correct_answer_summary = payload["correct_answer_summary"]
        explanation.core_reason = payload["core_reason"]
        explanation.choice_analysis_json = payload["choice_analysis"]
        explanation.related_concepts = payload["related_concepts"]
        explanation.exam_traps = payload["exam_traps"]
        explanation.memory_summary = payload["memory_summary"]
        explanation.model_name = "manual_audit_2026_11_09"
        explanation.prompt_version = "audit-v1"
        explanation.generation_status = "complete"
        question.verification_status = "verified"
        existing = db.scalar(select(QuestionReviewAudit).where(
            QuestionReviewAudit.question_id == question.id, QuestionReviewAudit.audit_batch == AUDIT_BATCH
        ))
        if existing is not None:
            db.delete(existing)
            db.flush()
        db.add(audit_row(
            question, record, "corrected", "APPLIED", record["reason"],
            (f"정답 {'/'.join(old_answers)} → {'/'.join(record['verified_answers'])} 및 AI 해설을 교정했습니다."
             if answers_changed else f"정답 {'/'.join(old_answers)}는 유지하고 AI 해설을 교정했습니다."),
        ))
    for record, question in holds:
        question.verification_status = "needs_review"
        existing = db.scalar(select(QuestionReviewAudit).where(
            QuestionReviewAudit.question_id == question.id, QuestionReviewAudit.audit_batch == AUDIT_BATCH
        ))
        if existing is not None:
            db.delete(existing)
            db.flush()
        db.add(audit_row(question, record, "quarantined", "HOLD_REVIEW", record["ambiguity"], record["review_required"]))


def main() -> int:
    parser = argparse.ArgumentParser(description="Preflight or apply the DEA-C01 question audit bundle.")
    parser.add_argument("--changes", type=Path, required=True)
    parser.add_argument("--review", type=Path, required=True)
    parser.add_argument(
        "--source-question-no", type=int, action="append", dest="source_question_nos",
        help="Apply only the specified audited source question number. Repeatable.",
    )
    parser.add_argument("--apply", action="store_true", help="Apply only after a clean preflight.")
    args = parser.parse_args()
    changes = load(args.changes, "changes")
    holds = load(args.review, "review_cases")
    review_identity = holds
    if args.source_question_nos:
        selected = set(args.source_question_nos)
        changes = [item for item in changes if item.get("source_question_no") in selected]
        review_identity = [item for item in holds if item.get("source_question_no") in selected]
        # A supplied correction supersedes its earlier hold.  Never mark a
        # corrected question as needs_review again in the same transaction.
        corrected = {item.get("source_question_no") for item in changes}
        holds = [
            item for item in review_identity
            if item.get("source_question_no") not in corrected
        ]
    changes = attach_review_identity(changes, review_identity)
    with SessionLocal() as db:
        resolved_changes, resolved_holds, blocked = preflight(db, changes, holds)
        report = {
            "batch": AUDIT_BATCH,
            "ready_changes": len(resolved_changes),
            "ready_holds": len(resolved_holds),
            "blocked": blocked,
            "mode": "apply" if args.apply else "preflight",
        }
        if blocked or not args.apply:
            print(json.dumps(report, ensure_ascii=False, indent=2))
            return 2 if blocked else 0
        apply(db, resolved_changes, resolved_holds)
        db.commit()
        print(json.dumps(report, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
