import random
from collections import defaultdict
from dataclasses import dataclass
from math import floor
from typing import Protocol


class WeightedQuestion(Protocol):
    id: int
    domain_id: int


@dataclass(frozen=True)
class AllocationResult:
    questions: list[WeightedQuestion]
    used_fallback: bool


def allocate_by_domain(questions: list[WeightedQuestion], weights: dict[int, float], count: int, seed: int | None = None, allow_fallback: bool = True) -> AllocationResult:
    if count < 1:
        raise ValueError("count must be positive")
    pools: dict[int, list[WeightedQuestion]] = defaultdict(list)
    rng = random.Random(seed)
    for question in questions:
        pools[question.domain_id].append(question)
    for pool in pools.values():
        rng.shuffle(pool)
    total_weight = sum(weights.values())
    if total_weight <= 0:
        raise ValueError("domain weights must be positive")
    exact = {key: count * value / total_weight for key, value in weights.items()}
    targets = {key: floor(value) for key, value in exact.items()}
    for key in sorted(weights, key=lambda k: (exact[k] - targets[k], weights[k]), reverse=True)[: count - sum(targets.values())]:
        targets[key] += 1
    selected: list[WeightedQuestion] = []
    used_fallback = False
    for domain_id, target in targets.items():
        selected.extend(pools.get(domain_id, [])[:target])
    if len(selected) < count:
        if not allow_fallback:
            raise ValueError("insufficient verified questions for domain allocation")
        used_fallback = True
        selected_ids = {item.id for item in selected}
        remaining = [item for item in questions if item.id not in selected_ids]
        rng.shuffle(remaining)
        selected.extend(remaining[: count - len(selected)])
    if len(selected) < count:
        raise ValueError("insufficient verified questions")
    rng.shuffle(selected)
    return AllocationResult(selected[:count], used_fallback)

