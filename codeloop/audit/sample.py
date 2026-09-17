"""`codeloop audit sample --n 30`: 15 flagged + 15 random encounters (seeded) for the CPC spot-check."""

from __future__ import annotations

import random
from pathlib import Path
from typing import Any

from codeloop.audit.run import audit_dir, load_results
from codeloop.ledger import utc_now
from codeloop.paths import Paths
from codeloop.util.jsonl import read_json, write_json


def sample_path(paths: Paths) -> Path:
    return audit_dir(paths) / "spot_check_sample.json"


def draw_spot_check(results: dict[str, dict[str, Any]], *, n: int = 30, seed: int = 0) -> dict[str, Any]:
    if n % 2:
        raise ValueError("n must be even: half flagged, half random")
    half = n // 2
    ids = sorted(results)
    flagged = [i for i in ids if results[i]["result"]["flags"]]
    rng = random.Random(seed)
    flagged_pick = sorted(rng.sample(flagged, min(half, len(flagged))))
    rest = [i for i in ids if i not in set(flagged_pick)]
    random_pick = sorted(rng.sample(rest, min(half, len(rest))))
    return {
        "drawn_at": utc_now(),
        "seed": seed,
        "n_requested": n,
        "population": len(ids),
        "population_flagged": len(flagged),
        "arms": {"flagged": flagged_pick, "random": random_pick},
        "encounters": [{"encounter_id": i, "arm": "flagged"} for i in flagged_pick]
        + [{"encounter_id": i, "arm": "random"} for i in random_pick],
    }


def write_spot_check_sample(paths: Paths, *, n: int = 30, seed: int = 0) -> dict[str, Any]:
    results = load_results(paths)
    if not results:
        raise RuntimeError("no audit results; run `codeloop audit run` first")
    sample = draw_spot_check(results, n=n, seed=seed)
    write_json(sample_path(paths), sample)
    return sample


def load_spot_check_sample(paths: Paths) -> dict[str, Any] | None:
    p = sample_path(paths)
    return read_json(p) if p.exists() else None
