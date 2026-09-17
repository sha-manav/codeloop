"""Repository root discovery and the canonical paths every command uses."""

from __future__ import annotations

import os
from pathlib import Path


class RepoNotFound(RuntimeError):
    pass


def find_root(start: Path | None = None) -> Path:
    env = os.environ.get("CODELOOP_ROOT")
    if env:
        return Path(env).resolve()
    here = (start or Path.cwd()).resolve()
    for cand in (here, *here.parents):
        if (
            (cand / "pyproject.toml").is_file()
            and (cand / "codeloop").is_dir()
            and (cand / "config" / "project.yaml").is_file()
        ):
            return cand
    raise RepoNotFound(
        "CodeLoop repository root not found: run from inside the repo or set CODELOOP_ROOT"
    )


class Paths:
    """All standard locations, derived from the repo root. Keep in sync with the spec layout."""

    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    # --- top level
    @property
    def ledger(self) -> Path:
        return self.root / "ledger.md"

    @property
    def decisions_md(self) -> Path:
        return self.root / "DECISIONS.md"

    # --- config
    @property
    def config(self) -> Path:
        return self.root / "config"

    @property
    def project_yaml(self) -> Path:
        return self.config / "project.yaml"

    @property
    def scope_yaml(self) -> Path:
        return self.config / "scope.yaml"

    @property
    def models_yaml(self) -> Path:
        return self.config / "models.yaml"

    @property
    def tables_yaml(self) -> Path:
        return self.config / "tables.yaml"

    # --- data
    @property
    def data(self) -> Path:
        return self.root / "data"

    @property
    def raw(self) -> Path:
        return self.data / "raw"

    @property
    def dev(self) -> Path:
        return self.data / "dev"

    @property
    def dev_encounters(self) -> Path:
        return self.dev / "encounters.jsonl"

    @property
    def labels_public(self) -> Path:
        return self.data / "labels_public"

    @property
    def amazon_labels(self) -> Path:
        return self.labels_public / "amazon.jsonl"

    @property
    def medcoder_labels(self) -> Path:
        return self.labels_public / "medcoder.jsonl"

    @property
    def labels(self) -> Path:
        return self.data / "labels"

    @property
    def splits(self) -> Path:
        return self.data / "splits"

    @property
    def holdout_ids(self) -> Path:
        return self.splits / "holdout_ids.txt"

    @property
    def holdout_ids_sha256(self) -> Path:
        return self.splits / "holdout_ids.sha256"

    @property
    def dev_split(self) -> Path:
        return self.splits / "dev_split.json"

    @property
    def source_manifest(self) -> Path:
        return self.splits / "source_manifest.json"

    @property
    def sealed(self) -> Path:
        return self.data / "sealed"

    @property
    def holdout_content_hashes(self) -> Path:
        return self.sealed / "holdout_content_hashes.json"

    @property
    def holdout_encounters_enc(self) -> Path:
        return self.sealed / "holdout_encounters.enc"

    @property
    def tables(self) -> Path:
        return self.data / "tables"

    @property
    def tables_sqlite(self) -> Path:
        return self.tables / "tables.sqlite"

    @property
    def tables_raw(self) -> Path:
        return self.tables / "raw"

    # --- other trees
    @property
    def reports(self) -> Path:
        return self.root / "reports"

    @property
    def ingest_report(self) -> Path:
        return self.reports / "ingest.md"

    @property
    def scoring_pkg(self) -> Path:
        return self.root / "codeloop" / "scoring"

    @property
    def runs(self) -> Path:
        return self.root / "runs"

    @property
    def evals(self) -> Path:
        return self.root / "evals"

    @property
    def findings(self) -> Path:
        return self.root / "findings"

    @property
    def tasks(self) -> Path:
        return self.root / "tasks"

    @property
    def versions(self) -> Path:
        return self.root / "versions"

    def ensure_layout(self) -> None:
        for d in (
            self.config, self.raw, self.dev, self.labels_public, self.labels, self.splits,
            self.sealed, self.tables, self.reports, self.runs, self.evals, self.findings,
            self.tasks, self.versions,
        ):
            d.mkdir(parents=True, exist_ok=True)
