import pytest
from pydantic import ValidationError

from app.schemas.api import DatasetQuestion


def base_question() -> dict:
    return {"question_id": "Q1", "certification_code": "C", "domain_code": "D", "question_type": "multiple_response", "question_en": "Question", "choices": [{"id": "A", "text_en": "A"}, {"id": "B", "text_en": "B"}], "final_answers": ["A", "B"], "required_answer_count": 2}


def test_dataset_question_validates_answer_references() -> None:
    assert DatasetQuestion.model_validate(base_question()).final_answers == ["A", "B"]
    invalid = base_question(); invalid["final_answers"] = ["A", "C"]
    with pytest.raises(ValidationError): DatasetQuestion.model_validate(invalid)

