from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session
from sqlalchemy.pool import StaticPool

from app.api.v1.router import (
    admin_question_review_detail,
    admin_question_reviews,
    get_classification_report,
)
from app.db.base import Base
from app.models.entities import (
    Certification,
    Domain,
    Question,
    QuestionAnswerVersion,
    QuestionChoice,
    QuestionReviewAudit,
)
from scripts.apply_question_audit import apply, preflight
from scripts.import_question_review_history import unique_question_pairs
from scripts.quarantine_question_holds import preflight as quarantine_preflight
from app.repositories.exams import ExamRepository


def test_excluded_questions_are_not_eligible_for_study_and_are_counted_by_domain() -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        certification = Certification(
            certification_code="DEA-C01", name_en="AWS DEA", name_ko="AWS 데이터",
            exam_version="DEA-C01", default_question_count=65,
            default_duration_minutes=130, passing_score=720,
        )
        db.add(certification)
        db.flush()
        domain = Domain(
            certification_id=certification.id, domain_code="DEA-D1", name_en="Ingestion",
            name_ko="수집 및 변환", exam_weight=100, sort_order=1,
        )
        db.add(domain)
        db.flush()

        def question(uid: str, status: str) -> Question:
            return Question(
                question_uid=uid, certification_id=certification.id, domain_id=domain.id,
                question_type="multiple_choice", question_en=uid, question_ko=uid,
                content_hash=uid, verification_status=status,
                choices=[QuestionChoice(choice_key="A", text_en="A", sort_order=1)],
                answer_versions=[QuestionAnswerVersion(
                    answer_source="admin_final", answers_json=["A"], is_current=True,
                )],
            )

        available = question("DEA-AVAILABLE", "verified")
        excluded = question("DEA-EXCLUDED", "needs_review")
        db.add_all([available, excluded])
        db.commit()

        report = get_classification_report(db, "DEA-C01")
        assert report["domains"] == [{
            "domain_code": "DEA-D1", "name_ko": "수집 및 변환", "name_en": "Ingestion",
            "total_count": 2, "excluded_count": 1, "available_count": 1,
        }]
        assert [item.question_uid for item in ExamRepository(db).eligible_questions(certification.id)] == ["DEA-AVAILABLE"]


def test_admin_question_reviews_are_groupable_by_certification_and_concise() -> None:
    engine = create_engine(
        "sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool
    )
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        certification = Certification(
            certification_code="DEA-C01", name_en="AWS DEA", name_ko="AWS 데이터",
            exam_version="DEA-C01", default_question_count=65,
            default_duration_minutes=130, passing_score=720,
        )
        db.add(certification)
        db.flush()
        domain = Domain(
            certification_id=certification.id, domain_code="DEA-D1", name_en="Ingestion",
            name_ko="수집 및 변환", exam_weight=100, sort_order=1,
        )
        db.add(domain)
        db.flush()
        question = Question(
            question_uid="AWS-DEA-C01-000437", certification_id=certification.id,
            domain_id=domain.id, question_type="multiple_choice", question_en="Question",
            question_ko="문제", content_hash="question-review-audit", verification_status="needs_review",
        )
        db.add(question)
        db.flush()
        db.add(QuestionReviewAudit(
            question_id=question.id, audit_batch="dea-c01-audit-2026-11-09",
            disposition="quarantined", audit_status="HOLD_REVIEW",
            issue_summary="문항 조건이 부족해 정답을 확정할 수 없습니다.",
            correction_summary="조건을 보완한 뒤 다시 검증합니다.", source_pdf_page=10,
            sources_json=["AWS 공식 문서"], proposed_answers=["B"],
            content_fingerprint="a" * 64,
        ))
        db.commit()

        assert admin_question_reviews(db, "DEA-C01") == {
            "items": [{
                "question_id": question.id,
                "question_uid": "AWS-DEA-C01-000437",
                "domain_code": "DEA-D1",
                "domain_name": "수집 및 변환",
                "verification_status": "needs_review",
                "disposition": "quarantined",
                "audit_status": "HOLD_REVIEW",
                "issue_summary": "문항 조건이 부족해 정답을 확정할 수 없습니다.",
                "correction_summary": "조건을 보완한 뒤 다시 검증합니다.",
                "source_pdf_page": 10,
                "sources": ["AWS 공식 문서"],
                "proposed_answers": ["B"],
            }],
            "total": 1, "page": 1, "page_size": 3,
        }
        detail = admin_question_review_detail(question.id, db, "DEA-C01")
        assert detail["question"].question_uid == "AWS-DEA-C01-000437"
        assert detail["issue_summary"] == "문항 조건이 부족해 정답을 확정할 수 없습니다."


def test_explanation_only_correction_restores_question_without_duplicate_answer_version() -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        certification = Certification(
            certification_code="DEA-C01", name_en="AWS DEA", name_ko="AWS 데이터",
            exam_version="DEA-C01", default_question_count=65,
            default_duration_minutes=130, passing_score=720,
        )
        db.add(certification); db.flush()
        domain = Domain(
            certification_id=certification.id, domain_code="DEA-D1", name_en="Ingestion",
            name_ko="수집 및 변환", exam_weight=100, sort_order=1,
        )
        db.add(domain); db.flush()
        question = Question(
            question_uid="AWS-DEA-C01-000003", certification_id=certification.id,
            domain_id=domain.id, question_type="multiple_choice", question_en="Question",
            question_ko="동일한 문제", content_hash="explanation-only", verification_status="needs_review",
            choices=[QuestionChoice(choice_key="C", text_en="C", text_ko="선택지 C", sort_order=1)],
            answer_versions=[QuestionAnswerVersion(
                answer_source="admin_final", answers_json=["C"], is_current=True,
            )],
        )
        db.add(question); db.commit()
        record = {
            "question_id": question.id, "question_uid": question.question_uid, "source_question_no": 3,
            "preconditions": {
                "original_question_ko": "동일한 문제", "original_choices_ko": {"C": "선택지 C"},
                "existing_verified_answers": ["C"],
            },
            "verified_answers": ["C"], "reason": "정답 C를 유지하고 해설을 교정했습니다.",
            "explanation": {
                "correct_answer_summary": "정답 C", "core_reason": "교정된 근거",
                "choice_analysis": {"C": "정답"}, "related_concepts": "Kinesis",
                "exam_traps": "직접 적재 아님", "memory_summary": "소비자 경유",
            },
        }
        changes, holds, blocked = preflight(db, [record], [])
        assert not holds and not blocked
        apply(db, changes, [])
        db.commit()
        db.refresh(question)
        assert question.verification_status == "verified"
        assert [(item.answers_json, item.is_current) for item in question.answer_versions] == [(["C"], True)]
        audit = db.scalar(select(QuestionReviewAudit).where(QuestionReviewAudit.question_id == question.id))
        assert audit is not None
        assert audit.disposition == "corrected"
        assert audit.correction_summary == "정답 C는 유지하고 AI 해설을 교정했습니다."


def test_corrected_review_is_visible_to_an_administrator() -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        certification = Certification(
            certification_code="DEA-C01", name_en="AWS DEA", name_ko="AWS 데이터",
            exam_version="DEA-C01", default_question_count=65,
            default_duration_minutes=130, passing_score=720,
        )
        db.add(certification); db.flush()
        domain = Domain(
            certification_id=certification.id, domain_code="DEA-D1", name_en="Ingestion",
            name_ko="수집 및 변환", exam_weight=100, sort_order=1,
        )
        db.add(domain); db.flush()
        question = Question(
            question_uid="AWS-DEA-C01-000011", certification_id=certification.id,
            domain_id=domain.id, question_type="multiple_choice", question_en="Question",
            question_ko="교정된 문제", content_hash="corrected-review", verification_status="verified",
        )
        db.add(question); db.flush()
        db.add(QuestionReviewAudit(
            question_id=question.id, audit_batch="dea-c01-audit-2026-11-09",
            disposition="corrected", audit_status="APPLIED", issue_summary="해설의 자동 반영 표현이 틀렸습니다.",
            correction_summary="정답 B는 유지하고 AI 해설을 교정했습니다.", source_pdf_page=4,
            sources_json=["AWS 공식 문서"], proposed_answers=["B"], content_fingerprint="b" * 64,
        ))
        db.commit()
        listing = admin_question_reviews(db, "DEA-C01")
        assert listing["items"][0]["disposition"] == "corrected"
        detail = admin_question_review_detail(question.id, db, "DEA-C01")
        assert detail["correction_summary"] == "정답 B는 유지하고 AI 해설을 교정했습니다."


def test_audit_preflight_blocks_a_stale_answer_but_resolves_exact_hold_content() -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        certification = Certification(
            certification_code="DEA-C01", name_en="AWS DEA", name_ko="AWS 데이터",
            exam_version="DEA-C01", default_question_count=65,
            default_duration_minutes=130, passing_score=720,
        )
        db.add(certification)
        db.flush()
        domain = Domain(
            certification_id=certification.id, domain_code="DEA-D1", name_en="Ingestion",
            name_ko="수집 및 변환", exam_weight=100, sort_order=1,
        )
        db.add(domain)
        db.flush()
        question = Question(
            question_uid="AWS-DEA-C01-000005", certification_id=certification.id,
            domain_id=domain.id, question_type="multiple_choice", question_en="Question",
            question_ko="동일한 문제", content_hash="audit-preflight", verification_status="verified",
            choices=[QuestionChoice(choice_key="A", text_en="A", text_ko="선택지 A", sort_order=1)],
            answer_versions=[QuestionAnswerVersion(
                answer_source="admin_final", answers_json=["A"], is_current=True,
            )],
        )
        db.add(question)
        db.commit()
        change = {
            "question_id": question.id,
            "question_uid": question.question_uid,
            "source_question_no": 5,
            "preconditions": {
                "original_question_ko": "동일한 문제",
                "original_choices_ko": {"A": "선택지 A"},
                "existing_verified_answers": ["B"],
            },
        }
        hold = {
            "source_question_no": 5,
            "question_uid": question.question_uid,
            "question": {"ko": "동일한 문제"},
            "choices": {"A": {"ko": "선택지 A"}},
        }
        changes, holds, blocked = preflight(db, [change], [hold])
        assert changes == []
        assert [(record["source_question_no"], item.id) for record, item in holds] == [(5, question.id)]
        assert blocked == [{
            "kind": "change", "question_id": question.id,
            "source_question_no": 5, "reason": "current_answer_mismatch",
        }]


def test_quarantine_preflight_refuses_a_question_when_any_choice_differs() -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        certification = Certification(
            certification_code="DEA-C01", name_en="AWS DEA", name_ko="AWS 데이터",
            exam_version="DEA-C01", default_question_count=65,
            default_duration_minutes=130, passing_score=720,
        )
        db.add(certification)
        db.flush()
        domain = Domain(
            certification_id=certification.id, domain_code="DEA-D1", name_en="Ingestion",
            name_ko="수집 및 변환", exam_weight=100, sort_order=1,
        )
        db.add(domain)
        db.flush()
        question = Question(
            question_uid="AWS-DEA-C01-000005", certification_id=certification.id,
            domain_id=domain.id, question_type="multiple_choice", question_en="Question",
            question_ko="동일한 문제", content_hash="quarantine-preflight", verification_status="verified",
            choices=[QuestionChoice(choice_key="A", text_en="A", text_ko="실제 선택지", sort_order=1)],
        )
        db.add(question)
        db.commit()
        record = {
            "db_action": "DO_NOT_APPLY", "status": "HOLD_REVIEW", "question_id": question.id,
            "question_uid": question.question_uid, "source_question_no": 5,
            "question": {"ko": "동일한 문제"}, "choices": {"A": {"ko": "다른 선택지"}},
        }
        matched, blocked, absent, valid = quarantine_preflight(db, [record])
        assert matched == []
        assert blocked == [{"source_question_no": 5, "reason": "id_or_content_mismatch"}]
        assert absent == []
        assert valid == []


def test_quarantine_preflight_allows_only_explicitly_confirmed_manual_match_or_absence() -> None:
    engine = create_engine("sqlite://", poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        certification = Certification(
            certification_code="DEA-C01", name_en="AWS DEA", name_ko="AWS 데이터",
            exam_version="DEA-C01", default_question_count=65,
            default_duration_minutes=130, passing_score=720,
        )
        db.add(certification)
        db.flush()
        domain = Domain(
            certification_id=certification.id, domain_code="DEA-D1", name_en="Ingestion",
            name_ko="수집 및 변환", exam_weight=100, sort_order=1,
        )
        db.add(domain)
        db.flush()
        question = Question(
            question_uid="AWS-DEA-C01-000036", certification_id=certification.id,
            domain_id=domain.id, question_type="multiple_choice", question_en="Question",
            question_ko="동일한 문제", content_hash="quarantine-manual-match", verification_status="verified",
            choices=[QuestionChoice(choice_key="A", text_en="A", text_ko="실제 선택지", sort_order=1)],
        )
        db.add(question)
        db.commit()
        manual = {
            "db_action": "DO_NOT_APPLY", "status": "HOLD_REVIEW", "question_uid": question.question_uid,
            "source_question_no": 36, "question": {"ko": "동일한 문제"},
            "choices": {"A": {"ko": "감사 파일 선택지"}},
        }
        absent_record = {"db_action": "DO_NOT_APPLY", "status": "HOLD_REVIEW", "source_question_no": 147, "question": {"ko": "없음"}, "choices": {}}
        valid_record = {"db_action": "DO_NOT_APPLY", "status": "HOLD_REVIEW", "source_question_no": 177, "question": {"ko": "정상 문항"}, "choices": {}}
        matched, blocked, absent, valid = quarantine_preflight(
            db, [manual, absent_record, valid_record], {36: question.id}, {147}, {177}
        )
        assert [item.id for item in matched] == [question.id]
        assert blocked == []
        assert absent == [147]
        assert valid == [177]


def test_review_history_import_deduplicates_repeated_source_questions() -> None:
    class Item:
        def __init__(self, identifier: int) -> None:
            self.id = identifier

    pairs, duplicates = unique_question_pairs([
        ({"source_question_no": 195}, Item(623)),
        ({"source_question_no": 204}, Item(623)),
        ({"source_question_no": 205}, Item(624)),
    ])

    assert [question.id for _, question in pairs] == [623, 624]
    assert duplicates == [{"question_id": 623, "source_question_nos": [195, 204]}]
