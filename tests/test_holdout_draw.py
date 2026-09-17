import random

import pytest

from codeloop.seal.draw import draw_holdout, holdout_allocation
from tests.synthetic import SUBSET_COUNTS, synthetic_encounters


def test_allocation_matches_spec_arithmetic_on_real_subset_sizes():
    # round(40*112/207)=22, round(40*55/207)=11, round(40*40/207)=8 -> 41; largest (aci) absorbs -1
    assert holdout_allocation(SUBSET_COUNTS, 40) == {"aci": 21, "virtassist": 11, "virtscribe": 8}


def test_allocation_sums_to_total_and_stays_in_range():
    for counts in ({"a": 10, "b": 10, "c": 10}, {"a": 1, "b": 200}, {"x": 207}):
        alloc = holdout_allocation(counts, 40 if sum(counts.values()) >= 40 else 5)
        assert sum(alloc.values()) in (40, 5)
        assert all(0 <= alloc[s] <= counts[s] for s in counts)


def test_allocation_rejects_impossible_requests():
    with pytest.raises(ValueError):
        holdout_allocation({"a": 10}, 11)


def test_draw_is_deterministic_and_follows_the_literal_formula():
    encs = synthetic_encounters()
    by_subset: dict[str, list[str]] = {}
    for e in encs:
        by_subset.setdefault(e.subset, []).append(e.id)
    seed = 20260917
    drawn = draw_holdout(by_subset, 40, seed)
    assert drawn == draw_holdout(by_subset, 40, seed)
    assert drawn == sorted(drawn) and len(set(drawn)) == 40
    alloc = holdout_allocation({s: len(v) for s, v in by_subset.items()}, 40)
    expected = []
    for s in sorted(by_subset):
        expected.extend(random.Random(seed).sample(sorted(by_subset[s]), alloc[s]))
    assert drawn == sorted(expected)
    id_to_subset = {e.id: e.subset for e in encs}
    per_subset = {}
    for i in drawn:
        per_subset[id_to_subset[i]] = per_subset.get(id_to_subset[i], 0) + 1
    assert per_subset == alloc


def test_different_seed_gives_different_draw():
    by_subset = {"aci": [f"D2N{i:03d}" for i in range(1, 113)], "virtassist": [f"D2N{i:03d}" for i in range(113, 168)], "virtscribe": [f"D2N{i:03d}" for i in range(168, 208)]}
    assert draw_holdout(by_subset, 40, 1) != draw_holdout(by_subset, 40, 2)
