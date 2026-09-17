"""File-level entry point used by `codeloop score` and by the holdout scoring step.

Gold and prediction files are JSONL. Each record is either package-shaped ({"encounter_id", "diagnoses",
"lines", ...}), label-shaped ({"encounter_id", "label": {...}}) or trace-shaped ({"package": {...}}).
Every gold encounter is scored; a gold encounter with no prediction is scored against an empty
package (every gold field wrong) and listed in `missing_pred`. Predictions without gold are ignored
and listed in `unscored_pred`.
"""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from codeloop.scoring.canonical import canonicalize
from codeloop.scoring.scope import Scope
from codeloop.scoring.scorer import BatchScore, ScoreResult, aggregate, score_encounter


class ScoreReport(BaseModel):
    scoring_version: str
    scope_sha256: str | None = None
    gold_path: str | None = None
    pred_path: str | None = None
    batch: BatchScore
    results: list[ScoreResult]
    missing_pred: list[str] = Field(default_factory=list)
    unscored_pred: list[str] = Field(default_factory=list)


def _unwrap(record: Mapping[str, Any]) -> tuple[str, Mapping[str, Any]]:
    eid = record.get("encounter_id") or record.get("id")
    if "label" in record and isinstance(record["label"], Mapping):
        pkg = record["label"]
    elif "package" in record and isinstance(record["package"], Mapping):
        pkg = record["package"]
        eid = eid or pkg.get("encounter_id")
    else:
        pkg = record
    if not eid:
        raise ValueError("record without encounter_id")
    return str(eid), pkg


def load_packages(path: Path) -> dict[str, Mapping[str, Any]]:
    out: dict[str, Mapping[str, Any]] = {}
    with open(path, encoding="utf-8") as fh:
        for n, line in enumerate(fh, start=1):
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
            except json.JSONDecodeError as e:
                raise ValueError(f"{path}:{n}: invalid JSON") from e
            eid, pkg = _unwrap(record)
            if eid in out:
                raise ValueError(f"{path}: duplicate encounter_id {eid}")
            out[eid] = pkg
    return out


def score_pairs(
    gold: Mapping[str, Mapping[str, Any]], pred: Mapping[str, Mapping[str, Any]], scope: Scope
) -> tuple[list[ScoreResult], list[str], list[str]]:
    results: list[ScoreResult] = []
    missing: list[str] = []
    empty: Mapping[str, Any] = {"diagnoses": [], "lines": []}
    for eid in sorted(gold):
        if eid not in pred:
            missing.append(eid)
        results.append(score_encounter(eid, canonicalize(gold[eid], scope), canonicalize(pred.get(eid, empty), scope)))
    unscored = sorted(set(pred) - set(gold))
    return results, missing, unscored


def score_files(gold_path: Path, pred_path: Path, scope: Scope, *, scope_sha256: str | None = None) -> ScoreReport:
    from codeloop.scoring import SCORING_VERSION  # local import avoids a cycle at package import time

    gold = load_packages(Path(gold_path))
    pred = load_packages(Path(pred_path))
    results, missing, unscored = score_pairs(gold, pred, scope)
    return ScoreReport(
        scoring_version=SCORING_VERSION, scope_sha256=scope_sha256, gold_path=str(gold_path),
        pred_path=str(pred_path), batch=aggregate(results), results=results,
        missing_pred=missing, unscored_pred=unscored,
    )
