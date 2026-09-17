"""Holdout draw (spec §2.3 step 3): stratified on subset, seeded, reproducible.

n_s = round(n_total * N_s / N); the largest subset absorbs the rounding remainder; then, for each
subset in sorted order, `random.Random(seed).sample(sorted_ids_in_subset, n_s)`.
"""

from __future__ import annotations

import random
from collections.abc import Mapping


def holdout_allocation(counts: Mapping[str, int], n_total: int) -> dict[str, int]:
    total = sum(counts.values())
    if total <= 0 or n_total <= 0 or n_total > total:
        raise ValueError(f"cannot allocate {n_total} of {total}")
    alloc = {s: round(n_total * c / total) for s, c in counts.items()}
    remainder = n_total - sum(alloc.values())
    if remainder:
        largest = sorted(counts, key=lambda s: (-counts[s], s))[0]
        alloc[largest] += remainder
    for s, n in alloc.items():
        if n < 0 or n > counts[s]:
            raise ValueError(f"allocation {n} for subset {s!r} out of range")
    return alloc


def draw_holdout(ids_by_subset: Mapping[str, list[str]], n_total: int, seed: int) -> list[str]:
    counts = {s: len(ids) for s, ids in ids_by_subset.items()}
    alloc = holdout_allocation(counts, n_total)
    chosen: list[str] = []
    for subset in sorted(ids_by_subset):
        population = sorted(set(ids_by_subset[subset]))
        chosen.extend(random.Random(seed).sample(population, alloc[subset]))
    if len(set(chosen)) != n_total:
        raise RuntimeError("holdout draw produced duplicate IDs")
    return sorted(chosen)
