"""Invariant I1 (spec §2.3): no holdout ID or holdout content hash in any derived-data tree."""

from pathlib import Path

import pytest

from codeloop.paths import Paths, find_root
from codeloop.seal.leakage import find_leaks, load_holdout_hashes, load_holdout_ids


def test_no_holdout_leakage():
    root = find_root(Path(__file__).resolve().parent)
    paths = Paths(root)
    ids = load_holdout_ids(paths)
    if not ids:
        pytest.skip("holdout not sealed yet (Phase 0 pending)")
    hashes = load_holdout_hashes(paths)
    assert len(ids) == 40 and set(hashes) == set(ids)
    leaks = find_leaks(root)
    assert leaks == [], "\n".join(str(x) for x in leaks)


def test_reveal_exports_are_exempt_only_once_the_holdout_is_scored(tmp_path):
    """Spec section 15 step 4: the plaintext export written by `holdout score` is the reveal, not a leak."""
    (tmp_path / "runs" / "holdout").mkdir(parents=True)
    (tmp_path / "runs" / "holdout" / "labels.jsonl").write_text('{"encounter_id": "D2N999"}\n', encoding="utf-8")
    (tmp_path / "runs" / "other").mkdir()
    (tmp_path / "runs" / "other" / "x.jsonl").write_text('{"encounter_id": "D2N999"}\n', encoding="utf-8")
    (tmp_path / "data" / "sealed").mkdir(parents=True)
    before = find_leaks(tmp_path, ids=["D2N999"], hashes={}, scan_dirs=["runs"])
    assert {leak.path for leak in before} == {"runs/holdout/labels.jsonl", "runs/other/x.jsonl"}
    (tmp_path / "data" / "sealed" / "SCORED.lock").write_text("scored", encoding="utf-8")
    after = find_leaks(tmp_path, ids=["D2N999"], hashes={}, scan_dirs=["runs"])
    assert {leak.path for leak in after} == {"runs/other/x.jsonl"}

