import pytest

from codeloop.scoring import paired_bootstrap_diff, wilson_interval
from codeloop.scoring.bootstrap import pairwise_version_differences


def test_wilson_known_values():
    lo, hi = wilson_interval(0, 40)
    assert lo == 0.0 and hi == pytest.approx(0.0881, abs=1e-3)
    lo, hi = wilson_interval(20, 40)
    assert lo == pytest.approx(0.3512, abs=1e-3) and hi == pytest.approx(0.6488, abs=1e-3)
    assert wilson_interval(40, 40)[1] == 1.0 and wilson_interval(0, 0) == (0.0, 0.0)


def test_paired_bootstrap_identical_and_shifted():
    a = [0.5, 0.75, 1.0, 0.25] * 10
    r = paired_bootstrap_diff(a, a, n_resamples=500, seed=1)
    assert r.diff == 0.0 and r.ci_low == 0.0 and r.ci_high == 0.0
    b = [x + 0.1 for x in a]
    r = paired_bootstrap_diff(a, b, n_resamples=500, seed=1)
    assert r.diff == pytest.approx(0.1) and r.ci_low == pytest.approx(0.1) and r.ci_high == pytest.approx(0.1)


def test_paired_bootstrap_is_seeded_and_brackets_the_mean():
    a = [i / 40 for i in range(40)]
    b = [min(1.0, x + (0.2 if i % 2 else -0.05)) for i, x in enumerate(a)]
    r1 = paired_bootstrap_diff(a, b, n_resamples=2000, seed=7)
    r2 = paired_bootstrap_diff(a, b, n_resamples=2000, seed=7)
    assert r1 == r2 and r1.ci_low < r1.diff < r1.ci_high and r1.n == 40
    with pytest.raises(ValueError):
        paired_bootstrap_diff([1.0], [1.0, 0.5])


def test_pairwise_versions_use_common_encounters():
    agreements = {"v0": {"a": 0.5, "b": 0.5, "c": 0.5}, "v1": {"a": 1.0, "b": 0.5}, "v2": {"a": 1.0, "b": 1.0, "c": 1.0}}
    out = pairwise_version_differences(agreements, n_resamples=200, seed=3)
    assert set(out) == {"v0->v1", "v0->v2", "v1->v2"}
    assert out["v0->v1"].n == 2 and out["v0->v2"].n == 3 and out["v0->v2"].diff == pytest.approx(0.5)
