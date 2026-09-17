"""Scope filter (spec §3), applied symmetrically to gold and predicted packages.

Lines are kept only if their code falls in an *on* module's allowlist and not in an excluded E/M
range. Excluded modifiers and modifiers owned by an *off* module are stripped. Diagnoses are
always kept. Code ranges are inclusive and compared as fixed-width five-character strings, which
orders CPT ("99202"–"99205") and HCPCS ("J0120"–"J9999") correctly.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from pathlib import Path

import yaml
from pydantic import BaseModel, ConfigDict, Field

_CODE5 = re.compile(r"^[0-9A-Z]{5}$")


class ModuleScope(BaseModel):
    model_config = ConfigDict(extra="allow")
    on: bool = False
    code_ranges: list[str] = Field(default_factory=list)
    modifiers: list[str] = Field(default_factory=list)
    threshold: int | None = None
    evaluable_n_est: int | None = None


class Exclusions(BaseModel):
    em_code_ranges: list[str] = Field(default_factory=list)
    modifiers: list[str] = Field(default_factory=list)


class Scope(BaseModel):
    model_config = ConfigDict(extra="allow")
    icd10cm_release: str | None = None
    modules: dict[str, ModuleScope] = Field(default_factory=dict)
    exclusions: Exclusions = Field(default_factory=Exclusions)
    holdout_module_min_n: int = 10

    @classmethod
    def load(cls, path: Path) -> Scope:
        with open(path, encoding="utf-8") as fh:
            raw = yaml.safe_load(fh) or {}
        return cls.model_validate(_fix_yaml_bool_keys(raw))

    def in_scope_line(self, code: str) -> bool:
        code = code.strip().upper()
        if code_in_ranges(code, self.exclusions.em_code_ranges):
            return False
        return any(m.on and code_in_ranges(code, m.code_ranges) for m in self.modules.values())

    def module_for_line(self, code: str) -> str | None:
        code = code.strip().upper()
        if code_in_ranges(code, self.exclusions.em_code_ranges):
            return None
        for name, m in self.modules.items():
            if m.on and code_in_ranges(code, m.code_ranges):
                return name
        return None

    def allowed_modifier(self, modifier: str) -> bool:
        modifier = modifier.strip().upper()
        if modifier in {m.upper() for m in self.exclusions.modifiers}:
            return False
        for m in self.modules.values():
            if not m.on and modifier in {x.upper() for x in m.modifiers}:
                return False
        return True

    def filter_modifiers(self, modifiers: Iterable[str]) -> tuple[str, ...]:
        kept = {m.strip().upper() for m in modifiers if m and m.strip() and self.allowed_modifier(m)}
        return tuple(sorted(kept))


def _fix_yaml_bool_keys(obj):
    """YAML 1.1 reads the bare keys `on`/`off`/`yes`/`no` as booleans; the spec's module shape uses `on:`.
    Restore those keys as strings so `{on: true}` means what it says."""
    if isinstance(obj, dict):
        return {("on" if k is True else "off" if k is False else k): _fix_yaml_bool_keys(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_fix_yaml_bool_keys(v) for v in obj]
    return obj


def parse_range(spec: str) -> tuple[str, str]:
    s = spec.strip().upper()
    lo, _, hi = s.partition("-")
    hi = hi or lo
    lo, hi = lo.strip(), hi.strip()
    if not (_CODE5.match(lo) and _CODE5.match(hi)):
        raise ValueError(f"code range endpoints must be five-character codes: {spec!r}")
    if lo > hi:
        raise ValueError(f"code range is reversed: {spec!r}")
    return lo, hi


def code_in_ranges(code: str, ranges: Iterable[str]) -> bool:
    return any(lo <= code <= hi for lo, hi in (parse_range(r) for r in ranges))
