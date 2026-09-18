"""Append-only spot-check responses (runs/audit/spot_check_responses.jsonl)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from codeloop.audit.run import audit_dir
from codeloop.audit.schema import CATEGORIES
from codeloop.ledger import utc_now
from codeloop.paths import Paths
from codeloop.util.jsonl import read_jsonl


class SpotCheckEvent(BaseModel):
    ts: str = Field(default_factory=utc_now)
    reviewer: str
    encounter_id: str
    type: str  # grade | missed | done | note
    flag_index: int | None = None
    decision: str | None = None  # confirm | deny
    comment: str | None = None
    category: str | None = None
    description: str | None = None
    evidence_quote: str | None = None

    def validate_shape(self) -> None:
        if self.type == "grade":
            if self.flag_index is None or self.decision not in ("confirm", "deny"):
                raise ValueError("grade needs flag_index and decision confirm|deny")
        elif self.type == "missed":
            if self.category not in CATEGORIES:
                raise ValueError(f"missed needs a category from {CATEGORIES}")
        elif self.type not in ("done", "note"):
            raise ValueError(f"unknown event type {self.type!r}")


def responses_path(paths: Paths) -> Path:
    return audit_dir(paths) / "spot_check_responses.jsonl"


def append_event(paths: Paths, event: SpotCheckEvent, path: Path | None = None) -> None:
    event.validate_shape()
    p = path or responses_path(paths)
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(event.model_dump(mode="json"), ensure_ascii=False, sort_keys=True) + "\n")


def load_events(paths: Paths, path: Path | None = None) -> list[SpotCheckEvent]:
    p = path or responses_path(paths)
    if not p.exists():
        return []
    return [SpotCheckEvent.model_validate(r) for r in read_jsonl(p)]


def latest_grades(events: list[SpotCheckEvent]) -> dict[tuple[str, int], SpotCheckEvent]:
    """Latest grade per (encounter, flag_index)."""
    out: dict[tuple[str, int], SpotCheckEvent] = {}
    for e in events:
        if e.type == "grade" and e.flag_index is not None:
            out[(e.encounter_id, e.flag_index)] = e
    return out


def done_encounters(events: list[SpotCheckEvent]) -> set[str]:
    return {e.encounter_id for e in events if e.type == "done"}


def missed_events(events: list[SpotCheckEvent]) -> list[SpotCheckEvent]:
    return [e for e in events if e.type == "missed"]


def summary(events: list[SpotCheckEvent]) -> dict[str, Any]:
    grades = latest_grades(events)
    return {
        "events": len(events),
        "graded_flags": len(grades),
        "confirmed": sum(1 for g in grades.values() if g.decision == "confirm"),
        "denied": sum(1 for g in grades.values() if g.decision == "deny"),
        "missed": len(missed_events(events)),
        "done": len(done_encounters(events)),
    }
