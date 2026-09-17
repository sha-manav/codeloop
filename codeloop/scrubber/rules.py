"""Deterministic, table-driven scrubber (spec §8). No LLM.

`ScrubSignal` is the adapter interface: in production, clearinghouse and payer responses (277CA, 835)
could feed the same `ScrubFailure` type through additional signals; those parsers are not implemented.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Protocol

from codeloop.schemas.package import CodingPackage, LinePred, ScrubFailure
from codeloop.scoring import Scope
from codeloop.tables import Tables
from codeloop.tools.validators import BYPASS_MODIFIERS, VALID_MODIFIERS, X_MODIFIERS, is_drug_code


@dataclass
class ScrubContext:
    tables: Tables
    scope: Scope
    on_date: str  # YYYYMMDD used for NCCI effective/deletion dates

    def version(self, table: str) -> str:
        return f"{table}={self.tables.release(table)}; {self.tables.version}"


class ScrubSignal(Protocol):
    rule_id: str

    def failures(self, package: CodingPackage, ctx: ScrubContext) -> list[ScrubFailure]: ...


def _line_ref(line: LinePred, idx: int, sub: str | None = None) -> str:
    ref = f"line:{line.code}:{idx}"
    return f"{ref}:{sub}" if sub else ref


class NcciPtpSignal:
    rule_id = "NCCI_PTP"

    def failures(self, package: CodingPackage, ctx: ScrubContext) -> list[ScrubFailure]:
        out: list[ScrubFailure] = []
        version = ctx.version("ncci_ptp_practitioner")
        lines = list(enumerate(package.lines))
        for i, a in lines:
            for j, b in lines:
                if i == j or a.code == b.code:
                    continue
                edit = ctx.tables.ptp_edit(a.code, b.code, ctx.on_date)  # a = column 1, b = column 2
                if edit is None:
                    continue
                indicator, rationale = edit
                if indicator == 9:
                    continue
                if indicator == 0:
                    out.append(
                        ScrubFailure(
                            rule_id=self.rule_id,
                            field_ref=_line_ref(b, j),
                            severity="error",
                            table_version=version,
                            message=f"NCCI PTP edit {a.code}/{b.code}: modifier not allowed (indicator 0); {rationale}",
                        )
                    )
                elif indicator == 1 and not (set(b.modifiers) & BYPASS_MODIFIERS):
                    out.append(
                        ScrubFailure(
                            rule_id=self.rule_id,
                            field_ref=_line_ref(b, j, "modifiers"),
                            severity="error",
                            table_version=version,
                            message=f"NCCI PTP {a.code}/{b.code}: column-2 line needs a 59/X modifier; {rationale}",
                        )
                    )
        return out


class MueSignal:
    rule_id = "MUE"

    def failures(self, package: CodingPackage, ctx: ScrubContext) -> list[ScrubFailure]:
        out: list[ScrubFailure] = []
        version = ctx.version("ncci_mue_practitioner")
        units_by_code: Counter[str] = Counter()
        for line in package.lines:
            units_by_code[line.code] += line.units
        for idx, line in enumerate(package.lines):
            mue = ctx.tables.mue(line.code)
            if mue is None:
                continue
            value, mai = mue
            if units_by_code[line.code] > value:
                out.append(
                    ScrubFailure(
                        rule_id=self.rule_id,
                        field_ref=_line_ref(line, idx, "units"),
                        severity="error",
                        table_version=version,
                        message=f"units {units_by_code[line.code]} exceed MUE {value} for {line.code} (MAI {mai})",
                    )
                )
        return out


class ModifierSignal:
    rule_id = "MODIFIER"

    def failures(self, package: CodingPackage, ctx: ScrubContext) -> list[ScrubFailure]:
        out: list[ScrubFailure] = []
        version = ctx.version("mpfs_rvu")
        qw_on = ctx.scope.modules.get("qw") is not None and ctx.scope.modules["qw"].on
        jw_on = ctx.scope.modules.get("jw_jz") is not None and ctx.scope.modules["jw_jz"].on
        for idx, line in enumerate(package.lines):
            mods = set(line.modifiers)
            ref = _line_ref(line, idx, "modifiers")

            def fail(msg: str, severity: str = "error", ref: str = ref) -> None:
                out.append(
                    ScrubFailure(
                        rule_id=self.rule_id, field_ref=ref, severity=severity, table_version=version, message=msg
                    )  # type: ignore[arg-type]
                )

            for m in sorted(mods):
                if m not in VALID_MODIFIERS and not ctx.tables.hcpcs_modifier_known(m):
                    fail(f"unknown modifier {m}")
                if not ctx.scope.allowed_modifier(m):
                    fail(f"modifier {m} is out of scope (excluded or owned by an off module)")
            if "25" in mods:
                fail("modifier 25 is never asserted by the agent (E/M is out of scope)")
            if "50" in mods:
                bilat = ctx.tables.bilateral_indicator(line.code)
                if bilat not in ("1", "3"):
                    fail(f"modifier 50 not permitted: bilateral indicator {bilat!r} for {line.code}")
                if mods & {"RT", "LT"}:
                    fail("RT/LT cannot be combined with modifier 50 on the same line")
            if "59" in mods and mods & X_MODIFIERS:
                fail("59 and X{E,S,P,U} modifiers cannot appear on the same line")
            if "QW" in mods and qw_on and not line.code[:1].isdigit():
                fail("QW belongs on CLIA-waived test codes", severity="warn")
            if mods & {"JW", "JZ"} and jw_on and not is_drug_code(line.code):
                fail("JW/JZ belong on drug lines only")
            if {"JW", "JZ"} <= mods:
                fail("JW and JZ are mutually exclusive")
        return out


class StructuralSignal:
    rule_id = "STRUCTURAL"

    def failures(self, package: CodingPackage, ctx: ScrubContext) -> list[ScrubFailure]:
        out: list[ScrubFailure] = []
        version = ctx.tables.version
        dx_codes = {d.code for d in package.diagnoses}
        for idx, line in enumerate(package.lines):
            if not line.pointers:
                out.append(
                    ScrubFailure(
                        rule_id=self.rule_id,
                        field_ref=_line_ref(line, idx, "pointers"),
                        severity="error",
                        table_version=version,
                        message="line has no diagnosis pointer",
                    )
                )
            for p in line.pointers:
                if p not in dx_codes:
                    out.append(
                        ScrubFailure(
                            rule_id=self.rule_id,
                            field_ref=_line_ref(line, idx, "pointers"),
                            severity="error",
                            table_version=version,
                            message=f"pointer {p} does not resolve to a diagnosis in the package",
                        )
                    )
            if line.units < 1:
                out.append(
                    ScrubFailure(
                        rule_id=self.rule_id,
                        field_ref=_line_ref(line, idx, "units"),
                        severity="error",
                        table_version=version,
                        message="units must be at least 1",
                    )
                )
            if not ctx.tables.line_code_exists(line.code):
                out.append(
                    ScrubFailure(
                        rule_id=self.rule_id,
                        field_ref=_line_ref(line, idx),
                        severity="error",
                        table_version=version,
                        message=f"code {line.code} is not in the pinned code sets",
                    )
                )
        for d in package.diagnoses:
            if not ctx.tables.icd_valid(d.code):
                out.append(
                    ScrubFailure(
                        rule_id=self.rule_id,
                        field_ref=f"dx:{d.code}",
                        severity="error",
                        table_version=version,
                        message=f"{d.code} is not a valid (billable) ICD-10-CM code",
                    )
                )
        return out


SIGNALS: tuple[ScrubSignal, ...] = (NcciPtpSignal(), MueSignal(), ModifierSignal(), StructuralSignal())


def scrub(package: CodingPackage, tables: Tables, scope: Scope, on_date: str, *, signals=SIGNALS) -> list[ScrubFailure]:
    ctx = ScrubContext(tables=tables, scope=scope, on_date=on_date)
    out: list[ScrubFailure] = []
    for signal in signals:
        out.extend(signal.failures(package, ctx))
    return out


def rule_fire_counts(failures: list[ScrubFailure]) -> dict[str, int]:
    return dict(sorted(Counter(f"{f.rule_id}:{f.severity}" for f in failures).items()))
