"""Deterministic replay of review events into a label record (spec §10.2, §5.3)."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from codeloop.schemas.event import Event
from codeloop.schemas.label import LabelDiagnosis, LabelLine, LabelPackage, LabelRecord

IDLE_CAP_S = 120.0
TOUCH_TYPES = ("edit", "add", "remove")
BLIND_MODES = ("blind", "holdout")


def _ts(s: str) -> datetime:
    return datetime.fromisoformat(s.replace("Z", "+00:00"))


def draft_to_label(draft: dict[str, Any] | None) -> LabelPackage:
    if not draft:
        return LabelPackage()
    return LabelPackage(
        diagnoses=[
            LabelDiagnosis(code=d["code"], status=d.get("status", "active"), first_listed=bool(d.get("first_listed")))
            for d in draft.get("diagnoses", [])
        ],
        lines=[
            LabelLine(
                code=ln["code"], modifiers=ln.get("modifiers", []), units=ln.get("units", 1),
                pointers=ln.get("pointers", []),
            )
            for ln in draft.get("lines", [])
        ],
    )


def _line_index(label: LabelPackage, ref: str) -> int | None:
    parts = ref.split(":")
    if len(parts) < 2 or parts[0] != "line":
        return None
    code = parts[1]
    idx = int(parts[2]) if len(parts) > 2 and parts[2].isdigit() else 0
    matches = [i for i, ln in enumerate(label.lines) if ln.code == code]
    return matches[idx] if idx < len(matches) else None


def apply_event(label: LabelPackage, e: Event) -> LabelPackage:
    ref = e.field_ref or ""
    if e.type == "add" and e.after:
        if ref.startswith("dx"):
            new = LabelDiagnosis.model_validate(e.after)
            if new.first_listed:
                for d in label.diagnoses:
                    d.first_listed = False
            label.diagnoses.append(new)
        elif ref.startswith("line"):
            label.lines.append(LabelLine.model_validate(e.after))
    elif e.type == "remove":
        if ref.startswith("dx:"):
            code = ref.split(":")[1]
            label.diagnoses = [d for d in label.diagnoses if d.code != code]
        elif ref.startswith("line"):
            i = _line_index(label, ref)
            if i is not None:
                del label.lines[i]
    elif e.type == "edit" and e.after:
        if ref == "first_listed":
            code = str(e.after.get("code", "")).upper().replace(".", "")
            for d in label.diagnoses:
                d.first_listed = d.code == code
        elif ref.startswith("dx:"):
            code = ref.split(":")[1]
            for k, d in enumerate(label.diagnoses):
                if d.code == code:
                    updated = LabelDiagnosis.model_validate({**d.model_dump(), **e.after})
                    if updated.first_listed and not d.first_listed:
                        for other in label.diagnoses:
                            other.first_listed = False
                    label.diagnoses[k] = updated
                    break
        elif ref.startswith("line"):
            i = _line_index(label, ref)
            if i is not None:
                label.lines[i] = LabelLine.model_validate({**label.lines[i].model_dump(), **e.after})
    return label


def review_minutes(events: list[Event]) -> float:
    """Sum of gaps between consecutive events from `open` to `approve`, each gap capped at the idle cap."""
    seq = [e for e in events if e.mode in ("review", "blind", "holdout")]
    if not seq:
        return 0.0
    start = next((i for i, e in enumerate(seq) if e.type == "open"), 0)
    end = next((i for i, e in enumerate(seq) if e.type == "approve"), len(seq) - 1)
    total = 0.0
    for a, b in zip(seq[start:end], seq[start + 1 : end + 1], strict=False):
        gap = (_ts(b.ts) - _ts(a.ts)).total_seconds()
        total += max(0.0, min(gap, IDLE_CAP_S))
    return round(total / 60.0, 3)


def replay(encounter_id: str, coder_id: str, draft: dict[str, Any] | None, events: list[Event]) -> LabelRecord:
    label = draft_to_label(draft)
    blind: LabelPackage | None = None
    evidence_grades: dict[str, str] = {}
    query_grades: dict[str, str] = {}
    touches = 0
    for e in events:
        if e.type == "blind_submit":
            blind = LabelPackage.model_validate(e.after or {})
            continue
        if e.mode in BLIND_MODES:
            continue  # blind-mode field events only shape the blind label, which arrives as blind_submit
        if e.type in TOUCH_TYPES:
            touches += 1
            label = apply_event(label, e)
        elif e.type == "grade_evidence" and e.span_id and e.grade:
            evidence_grades[e.span_id] = e.grade
        elif e.type == "grade_query" and e.field_ref and e.grade:
            query_grades[e.field_ref] = e.grade
    return LabelRecord(
        encounter_id=encounter_id, coder_id=coder_id, label=label, blind_label=blind, touches=touches,
        review_minutes=review_minutes(events), evidence_grades=evidence_grades, query_grades=query_grades,
    )


def build_blind_label(events: list[Event]) -> LabelPackage:
    """The blind label is built purely from blind-mode add/edit/remove events, starting empty."""
    label = LabelPackage()
    for e in events:
        if e.mode in BLIND_MODES and e.type in TOUCH_TYPES:
            label = apply_event(label, e)
    return label


def status_of(events: list[Event]) -> str:
    if any(e.type == "approve" for e in events):
        return "approved"
    if events:
        return "in_progress"
    return "unopened"
