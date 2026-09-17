"""Invariant I3: after the `freeze` tag exists, codeloop/scoring/ must hash to the ledger's frozen hash."""

from pathlib import Path

import pytest

from codeloop.paths import Paths, find_root
from codeloop.util.hashing import tree_hash
from codeloop.versioning import git
from codeloop.versioning.freeze import FREEZE_TAG, frozen_scoring_hash


def test_scoring_frozen():
    root = find_root(Path(__file__).resolve().parent)
    paths = Paths(root)
    if not git.is_repo(root) or not git.tag_exists(root, FREEZE_TAG):
        pytest.skip("freeze tag not present yet (Phase 3 pending)")
    expected = frozen_scoring_hash(paths)
    assert expected, "freeze tag exists but the ledger has no freeze entry with scoring_tree_sha256"
    assert tree_hash(paths.scoring_pkg) == expected, "codeloop/scoring changed after the freeze (invariant I3)"
