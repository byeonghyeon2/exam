from dataclasses import dataclass

import pytest

from app.services.allocation import allocate_by_domain


@dataclass
class Item:
    id: int
    domain_id: int


def test_allocation_is_reproducible_and_weighted() -> None:
    items = [Item(i, 1 if i < 8 else 2) for i in range(10)]
    first = allocate_by_domain(items, {1: 0.75, 2: 0.25}, 4, seed=7)
    second = allocate_by_domain(items, {1: 0.75, 2: 0.25}, 4, seed=7)
    assert [x.id for x in first.questions] == [x.id for x in second.questions]
    assert [x.domain_id for x in first.questions].count(1) == 3


def test_domain_shortage_falls_back_or_fails() -> None:
    items = [Item(1, 1), Item(2, 2), Item(3, 2)]
    assert allocate_by_domain(items, {1: 0.9, 2: 0.1}, 2, seed=1).used_fallback
    with pytest.raises(ValueError):
        allocate_by_domain(items, {1: 0.9, 2: 0.1}, 2, seed=1, allow_fallback=False)

