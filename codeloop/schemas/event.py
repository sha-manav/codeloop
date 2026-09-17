"""Review-UI event store record (spec §10.2)."""

from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, model_validator

REASONS: tuple[str, ...] = (  # decision D2
    "missed", "unsupported", "specificity", "wrong_value", "guideline", "query_needed", "judgment",
)
PIPELINE_CAUSES: tuple[str, ...] = (
    "extraction_miss", "mapper_gap", "tool_data_gap", "rule_bug", "grader_bug", "model_reasoning",
)
EventType = Literal[
    "open", "accept", "edit", "add", "remove", "grade_evidence", "grade_query", "approve", "blind_submit"
]


class Event(BaseModel):
    ts: str
    coder_id: str
    encounter_id: str
    batch: str
    version: str
    mode: Literal["review", "blind", "holdout"]
    type: EventType
    field_ref: str | None = None
    before: dict[str, Any] | None = None
    after: dict[str, Any] | None = None
    reason: str | None = None  # required for edit/add/remove in review mode
    span_id: str | None = None
    grade: str | None = None

    @model_validator(mode="after")
    def _reason_rules(self) -> Event:
        if self.mode == "review" and self.type in ("edit", "add", "remove"):
            if self.reason not in REASONS:
                raise ValueError(f"{self.type} in review mode requires exactly one reason from {REASONS}")
        if self.reason is not None and self.reason not in REASONS:
            raise ValueError(f"unknown reason {self.reason!r}")
        return self
