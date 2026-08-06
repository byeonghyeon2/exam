from app.services.scoring import percentage, score_answer


def test_single_choice_is_exact_and_case_normalized() -> None:
    assert score_answer([" b "], ["B"])


def test_multiple_response_requires_complete_exact_set() -> None:
    assert score_answer(["B", "A"], ["A", "B"])
    assert not score_answer(["A"], ["A", "B"])
    assert not score_answer(["A", "B", "C"], ["A", "B"])


def test_unanswered_is_incorrect() -> None:
    assert not score_answer([], ["A"])
    assert percentage(2, 3) == 66.67

