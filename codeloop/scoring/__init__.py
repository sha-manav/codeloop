"""Canonical representation, scorer and bootstrap (spec §5). FROZEN at Phase 3.

This package is deliberately self-contained: it imports only the standard library, pydantic and
PyYAML, never other `codeloop` modules, so that its tree hash fully determines scoring behaviour.
`tests/test_scoring_self_contained.py` enforces that.
"""

from codeloop.scoring.bootstrap import BootstrapResult, paired_bootstrap_diff, wilson_interval
from codeloop.scoring.canonical import Canonical, CanonicalLine, canonicalize, to_package_like
from codeloop.scoring.io import ScoreReport, load_packages, score_files, score_pairs
from codeloop.scoring.scope import Scope
from codeloop.scoring.scorer import BatchScore, FieldResult, ScoreResult, aggregate, score_encounter

SCORING_VERSION = "1.0"

__all__ = [
    "SCORING_VERSION", "BatchScore", "BootstrapResult", "Canonical", "CanonicalLine", "FieldResult",
    "Scope", "ScoreReport", "ScoreResult", "aggregate", "canonicalize", "load_packages",
    "paired_bootstrap_diff", "score_encounter", "score_files", "score_pairs", "to_package_like",
    "wilson_interval",
]
