"""Finding record (spec §11): findings/FIND-<MODULE>-<NNNN>.yaml."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field


class Occurrence(BaseModel):
    encounter_id: str
    event_ids: list[Any] = Field(default_factory=list)


class Resolution(BaseModel):
    version: str | None = None
    pr: str | None = None
    before_error_rate: float | None = None
    after_error_rate: float | None = None
    batch_next_error_rate: float | None = None


class Finding(BaseModel):
    id: str
    title: str
    batch_discovered: str
    status: Literal["candidate", "eligible", "accepted", "ambiguous", "rejected", "resolved"] = "candidate"
    pattern: str = ""
    reasons: list[str] = Field(default_factory=list)
    field_types: list[str] = Field(default_factory=list)
    module: str = "core"
    code_category: str = ""
    grouping_key: str = ""
    occurrences: list[Occurrence] = Field(default_factory=list)
    count: int = 0
    hypothesis: str = ""
    pipeline_cause: str | None = None  # filled by the improvement agent
    targeted_eval: str | None = None
    task: str | None = None
    resolution: Resolution = Field(default_factory=Resolution)
    triage_notes: str = ""
    triage_assisted_by: str | None = None  # "owner" | "owner+llm:<model>"
