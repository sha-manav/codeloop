"""Interval statistics for decision D9: Wilson intervals for tier shares and paired bootstrap
95% CIs (10,000 resamples over encounters) for differences in mean per-encounter agreement."""

from __future__ import annotations

import random
from collections.abc import Mapping, Sequence

from pydantic import BaseModel

Z95 = 1.959963984540054


def wilson_interval(successes: int, n: int, z: float = Z95) -> tuple[float, float]:
    if n <= 0:
        return 0.0, 0.0
    p = successes / n
    denom = 1 + z * z / n
    centre = (p + z * z / (2 * n)) / denom
    half = z * ((p * (1 - p) / n + z * z / (4 * n * n)) ** 0.5) / denom
    return max(0.0, centre - half), min(1.0, centre + half)


class BootstrapResult(BaseModel):
    n: int
    n_resamples: int
    seed: int
    mean_a: float
    mean_b: float
    diff: float  # mean_b - mean_a
    ci_low: float
    ci_high: float
    level: float = 0.95


def _percentile(sorted_values: Sequence[float], q: float) -> float:
    if not sorted_values:
        return 0.0
    pos = q * (len(sorted_values) - 1)
    lo = int(pos)
    hi = min(lo + 1, len(sorted_values) - 1)
    frac = pos - lo
    return sorted_values[lo] * (1 - frac) + sorted_values[hi] * frac


def paired_bootstrap_diff(
    a: Sequence[float], b: Sequence[float], *, n_resamples: int = 10_000, seed: int = 0, level: float = 0.95
) -> BootstrapResult:
    """Paired bootstrap of mean(b) - mean(a) over encounters (same index = same encounter)."""
    if len(a) != len(b):
        raise ValueError("paired bootstrap requires equal-length, aligned sequences")
    n = len(a)
    if n == 0:
        return BootstrapResult(n=0, n_resamples=n_resamples, seed=seed, mean_a=0.0, mean_b=0.0,
                               diff=0.0, ci_low=0.0, ci_high=0.0, level=level)
    diffs = [float(y) - float(x) for x, y in zip(a, b, strict=True)]
    rng = random.Random(seed)
    resampled: list[float] = []
    for _ in range(n_resamples):
        total = 0.0
        for _k in range(n):
            total += diffs[rng.randrange(n)]
        resampled.append(total / n)
    resampled.sort()
    alpha = (1 - level) / 2
    mean_a = sum(map(float, a)) / n
    mean_b = sum(map(float, b)) / n
    return BootstrapResult(
        n=n, n_resamples=n_resamples, seed=seed, mean_a=mean_a, mean_b=mean_b, diff=mean_b - mean_a,
        ci_low=_percentile(resampled, alpha), ci_high=_percentile(resampled, 1 - alpha), level=level,
    )


def pairwise_version_differences(
    agreements: Mapping[str, Mapping[str, float]], *, n_resamples: int = 10_000, seed: int = 0
) -> dict[str, BootstrapResult]:
    """For every ordered version pair (earlier, later) compute the paired bootstrap of the difference
    over the encounters both versions scored. Keys look like 'v0->v1'."""
    versions = list(agreements)
    out: dict[str, BootstrapResult] = {}
    for i, va in enumerate(versions):
        for vb in versions[i + 1 :]:
            common = sorted(set(agreements[va]) & set(agreements[vb]))
            a = [agreements[va][e] for e in common]
            b = [agreements[vb][e] for e in common]
            out[f"{va}->{vb}"] = paired_bootstrap_diff(a, b, n_resamples=n_resamples, seed=seed)
    return out
