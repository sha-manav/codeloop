"""Spec §17: every span in every committed prediction equals its source substring (dev encounters only)."""

from pathlib import Path

import pytest

from codeloop.paths import Paths, find_root
from codeloop.schemas.encounter import load_encounters_jsonl
from codeloop.util.jsonl import read_jsonl


def test_committed_prediction_spans_match_sources():
    root = find_root(Path(__file__).resolve().parent)
    paths = Paths(root)
    files = sorted(p for p in paths.runs.glob("*/*/predictions*.jsonl") if "holdout" not in p.parts)
    if not files or not paths.dev_encounters.exists():
        pytest.skip("no committed predictions or no data/dev (run `make data`)")
    encounters = {e.id: e for e in load_encounters_jsonl(paths.dev_encounters)}
    checked = bad = 0
    for f in files:
        for pkg in read_jsonl(f):
            enc = encounters.get(pkg["encounter_id"])
            assert enc is not None, f"{f}: {pkg['encounter_id']} is not a dev encounter"
            fields = [*pkg.get("diagnoses", []), *pkg.get("lines", []), *pkg.get("provider_queries", [])]
            for field in fields:
                for s in field.get("evidence", []):
                    text = enc.note_text if s["source"] == "note" else enc.dialogue_text
                    checked += 1
                    if text[s["start"] : s["end"]] != s["text"]:
                        bad += 1
    assert checked > 0 and bad == 0, f"{bad} of {checked} spans do not match their sources"
