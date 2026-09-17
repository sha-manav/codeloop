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
