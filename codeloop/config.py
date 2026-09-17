"""Typed access to config/project.yaml (decisions, seeds, sources)."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field


class ZipMember(BaseModel):
    member: str
    split_orig: str


class SourceFile(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    url: str
    kind: Literal["file", "zip"] = "file"
    expected_md5: str | None = None
    expected_sha256: str | None = None
    split_orig: str | None = None
    role: str | None = None
    partition: str | None = None
    members: list[ZipMember] = Field(default_factory=list)


class Source(BaseModel):
    model_config = ConfigDict(extra="allow")
    title: str
    citation: str = ""
    license: str = ""
    landing_url: str = ""
    code_url: str | None = None
    pinned_commit: str | None = None
    files: list[SourceFile]


class Decision(BaseModel):
    model_config = ConfigDict(extra="allow")
    name: str
    value: Any
    change_before: str
    status: Literal["default", "confirmed", "changed", "locked"] = "default"
    rationale: str = ""


class HoldoutConfig(BaseModel):
    n: int = 40
    stratify_on: str = "subset"


class DevSplitConfig(BaseModel):
    seed: int = 20
    batches: int = 3
    batch_size: int = 45
    spare: int = 12
    blind_per_batch: int = 5


class ProjectConfig(BaseModel):
    model_config = ConfigDict(extra="allow")
    project: str
    spec_version: str
    expected_encounter_count: int = 207
    holdout: HoldoutConfig = Field(default_factory=HoldoutConfig)
    dev_split: DevSplitConfig = Field(default_factory=DevSplitConfig)
    seeds: dict[str, int]
    decisions: dict[str, Decision]
    sources: dict[str, Source]

    @property
    def seal_seed(self) -> int:
        return int(self.seeds["seal_seed"])


def load_project_config(path: Path) -> ProjectConfig:
    with open(path, encoding="utf-8") as fh:
        raw = yaml.safe_load(fh)
    return ProjectConfig.model_validate(raw)
