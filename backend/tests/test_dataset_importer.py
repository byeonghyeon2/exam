import json
from pathlib import Path

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import Session

from app.db.base import Base
from app.importers.dataset_importer import import_dataset
from app.models.entities import Question, QuestionAnswerVersion, QuestionChoice


def write_package(root: Path) -> None:
    (root / "manifest.json").write_text(json.dumps({"question_count": 1}), encoding="utf-8")
    (root / "verification_report.json").write_text(json.dumps({"status": "valid"}), encoding="utf-8")
    (root / "certifications.json").write_text(json.dumps([{
        "certification_code": "DEA-C01", "name_en": "AWS DEA", "name_ko": "AWS DEA",
        "exam_version": "DEA-C01", "default_question_count": 65,
        "default_duration_minutes": 130, "passing_score": 720, "score_type": "scaled",
        "is_active": True,
    }]), encoding="utf-8")
    (root / "domains.json").write_text(json.dumps([{
        "certification_code": "DEA-C01", "domain_code": "DEA-D1", "name_en": "Ingestion",
        "name_ko": "수집", "exam_weight": 34, "sort_order": 1, "is_active": True,
    }]), encoding="utf-8")
    question = {
        "question_id": "DEA-1", "certification_code": "DEA-C01", "domain_code": "DEA-D1",
        "question_type": "multiple_choice", "question_en": "Question", "question_ko": "문제",
        "choices": [{"id": "A", "text_en": "A"}, {"id": "B", "text_en": "B"}],
        "provided_answers": ["A"], "verified_answers": ["A"], "final_answers": ["A"],
        "required_answer_count": 1, "verification_status": "verified", "is_active": True,
    }
    (root / "questions.jsonl").write_text(json.dumps(question) + "\n", encoding="utf-8")


def test_import_is_idempotent_and_preserves_answer_sources(tmp_path: Path) -> None:
    write_package(tmp_path)
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        first = import_dataset(db, tmp_path, "strict")
        second = import_dataset(db, tmp_path, "strict")
        assert (first.added, first.failed) == (1, 0)
        assert (second.unchanged, second.added, second.failed) == (1, 0, 0)
        assert db.scalar(select(func.count(Question.id))) == 1
        assert db.scalar(select(func.count(QuestionChoice.id))) == 2
        assert set(db.scalars(select(QuestionAnswerVersion.answer_source))) == {
            "provided", "ai_verified", "admin_final"
        }
