"""Eval datasets and suites (spec §12)."""

from __future__ import annotations

from pathlib import Path
from typing import Literal

import yaml
from pydantic import BaseModel, Field

from codeloop.paths import Paths
from codeloop.util.jsonl import read_jsonl


class EvalCase(BaseModel):
    encounter_id: str
    gold: str  # "data/labels/batch1.jsonl#D2N0xx"
    field_refs: list[str] = Field(default_factory=list)


class EvalDataset(BaseModel):
    finding: str
    cases: list[EvalCase]

    @classmethod
    def load(cls, path: Path) -> EvalDataset:
        with open(path, encoding="utf-8") as fh:
            return cls.model_validate(yaml.safe_load(fh))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(yaml.safe_dump(self.model_dump(mode="json"), sort_keys=False), encoding="utf-8")


class EvalSuite(BaseModel):
    name: str
    kind: Literal["targeted", "regression"]
    dataset: str | None = None  # targeted: path to the FIND dataset
    gold: list[str] = Field(default_factory=list)  # regression: label files
    base_version: str | None = None  # regression: version whose stored outputs anchor the escalation check
    runs: int = 3
    seeds: list[int] = Field(default_factory=lambda: [1, 2, 3])
    finding: str | None = None

    @classmethod
    def load(cls, path: Path) -> EvalSuite:
        with open(path, encoding="utf-8") as fh:
            return cls.model_validate(yaml.safe_load(fh))

    def save(self, path: Path) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(
            yaml.safe_dump(self.model_dump(mode="json", exclude_none=True), sort_keys=False), encoding="utf-8"
        )


def load_gold(paths: Paths, spec: str) -> dict:
    """Resolve 'data/labels/batch1.jsonl#D2N0xx' to that encounter's label package (dict)."""
    file, _, eid = spec.partition("#")
    for r in read_jsonl(paths.root / file):
        if r["encounter_id"] == eid:
            return r["label"]
    raise KeyError(f"{eid} not in {file}")


def load_gold_file(paths: Paths, file: str) -> dict[str, dict]:
    return {r["encounter_id"]: r["label"] for r in read_jsonl(paths.root / file)}
