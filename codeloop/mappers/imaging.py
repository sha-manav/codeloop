"""Imaging mapper: in-office radiographs -> CPT code numbers within the core_lines allowlist."""

from __future__ import annotations

from dataclasses import dataclass, field

from codeloop.agent.schemas import LineSelection, Service
from codeloop.rules.line_rules import imaging_modifiers
from codeloop.schemas.package import DataGap, Span
from codeloop.scoring import Scope
from codeloop.tables import Tables
from codeloop.util.codes import normalize_icd10cm

MODULE = "core_lines"
CATEGORIES = ("in_office_imaging",)


@dataclass
class LineDecision:
    service_index: int
    code: str | None
    modifiers: list[str]
    units: int
    pointers: list[str]
    module: str
    rationale: str
    evidence: list[Span]
    gaps: list[DataGap] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def allowed_ranges(scope: Scope) -> list[str]:
    m = scope.modules.get(MODULE)
    return list(m.code_ranges) if m and m.on else []


def apply_line_rules(
    *,
    service: Service,
    selection: LineSelection | None,
    note_spans: list[Span],
    scope: Scope,
    tables: Tables,
    problem_codes: dict[int, str],
) -> LineDecision:
    d = LineDecision(
        service_index=selection.service_index if selection else -1,
        code=None,
        modifiers=[],
        units=1,
        pointers=[],
        module=MODULE,
        rationale=selection.rationale if selection else "",
        evidence=list(note_spans),
    )
    ref = f"service:{d.service_index}"
    if selection is None or not selection.code:
        if selection and selection.data_gap:
            d.gaps.append(DataGap(field_ref=ref, missing=selection.data_gap))
        return d
    code = selection.code.strip().upper()
    if not tables.line_code_exists(code):
        d.gaps.append(DataGap(field_ref=f"line:{code}", missing="selected code is not in the pinned code sets"))
        return d
    if scope.module_for_line(code) != MODULE:
        d.gaps.append(DataGap(field_ref=f"line:{code}", missing=f"selected code is outside the {MODULE} allowlist"))
        return d
    d.code = code
    d.units = max(1, int(selection.units or 1))
    d.modifiers = imaging_modifiers(service.body_part, service.laterality)
    pointers = [problem_codes[i] for i in selection.pointer_problem_indices if i in problem_codes]
    d.pointers = sorted({normalize_icd10cm(p) for p in pointers})
    return d
