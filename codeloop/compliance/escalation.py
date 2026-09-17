"""Diff-based escalation gate (spec §9): additions or escalations of billable elements in a candidate
package relative to the base version's package must carry allowed-source evidence and pass the scrubber."""

from __future__ import annotations

from dataclasses import dataclass, field

from codeloop.compliance.static import allowed_sources
from codeloop.schemas.encounter import Encounter
from codeloop.schemas.package import CodingPackage
from codeloop.scoring import Scope
from codeloop.scrubber import scrub
from codeloop.tables import Tables
from codeloop.tools.validators import BYPASS_MODIFIERS


@dataclass
class Escalation:
    kind: str  # new_line | higher_units | bypass_modifier_added | more_specific_dx | new_dx
    field_ref: str
    detail: str
    evidence_ok: bool
    scrubber_ok: bool

    @property
    def passed(self) -> bool:
        return self.evidence_ok and self.scrubber_ok


@dataclass
class EscalationResult:
    encounter_id: str
    passed: bool
    escalations: list[Escalation] = field(default_factory=list)
    scrubber_errors: int = 0


def _more_specific(base_code: str, cand_code: str) -> bool:
    return (
        base_code != cand_code
        and base_code[:3] == cand_code[:3]
        and (len(cand_code) > len(base_code) or cand_code[3:] != base_code[3:])
    )


def check_escalation(
    base: CodingPackage,
    cand: CodingPackage,
    *,
    encounter: Encounter,
    scope: Scope,
    tables: Tables,
    policy: str,
    on_date: str,
) -> EscalationResult:
    allowed = allowed_sources(policy)
    failures = scrub(cand, tables, scope, on_date)
    scrub_errors = sum(1 for f in failures if f.severity == "error")
    scrubber_ok = scrub_errors == 0
    result = EscalationResult(encounter_id=cand.encounter_id, passed=True, scrubber_errors=scrub_errors)

    base_dx = {d.code for d in base.diagnoses}
    cand_dx = {d.code: d for d in cand.diagnoses}
    for code, d in cand_dx.items():
        if code in base_dx:
            continue
        ev_ok = any(s.source in allowed for s in d.evidence)
        specific_of = [b for b in base_dx if _more_specific(b, code) and b not in cand_dx]
        kind = "more_specific_dx" if specific_of else "new_dx"
        detail = f"{code} replaces {specific_of[0]}" if specific_of else f"{code} added"
        result.escalations.append(Escalation(kind, f"dx:{code}", detail, ev_ok, scrubber_ok))

    def key(ln):
        return (ln.code, tuple(ln.modifiers))

    base_lines = {}
    for ln in base.lines:
        k = key(ln)
        base_lines[k] = base_lines.get(k, 0) + ln.units
    base_codes = {ln.code for ln in base.lines}
    for i, ln in enumerate(cand.lines):
        ref = f"line:{ln.code}:{i}"
        ev_ok = any(s.source in allowed for s in ln.evidence)
        if ln.code not in base_codes:
            result.escalations.append(Escalation("new_line", ref, f"{ln.code} added", ev_ok, scrubber_ok))
            continue
        k = key(ln)
        if k in base_lines and ln.units > base_lines[k]:
            result.escalations.append(
                Escalation("higher_units", f"{ref}:units", f"units {base_lines[k]} -> {ln.units}", ev_ok, scrubber_ok)
            )
        base_mods = set()
        for b in base.lines:
            if b.code == ln.code:
                base_mods |= set(b.modifiers)
        added = (set(ln.modifiers) - base_mods) & BYPASS_MODIFIERS
        if added:
            result.escalations.append(
                Escalation("bypass_modifier_added", f"{ref}:modifiers", f"added {sorted(added)}", ev_ok, scrubber_ok)
            )
    result.passed = all(e.passed for e in result.escalations)
    return result
