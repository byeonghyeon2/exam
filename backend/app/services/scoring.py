from collections.abc import Iterable


def normalize_answers(values: Iterable[str]) -> frozenset[str]:
    return frozenset(value.strip().upper() for value in values if value.strip())


def score_answer(selected: Iterable[str], correct: Iterable[str]) -> bool:
    """Exact-set scoring: partial, extra, and unanswered responses are incorrect."""
    selected_set = normalize_answers(selected)
    correct_set = normalize_answers(correct)
    return bool(correct_set) and selected_set == correct_set


def percentage(correct_count: int, total: int) -> float:
    return round(correct_count * 100 / total, 2) if total else 0.0


def scaled_score(correct_count: int, total: int, maximum: int = 1000) -> float:
    return round(correct_count * maximum / total, 2) if total else 0.0

