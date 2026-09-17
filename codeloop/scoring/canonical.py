"""Canonical representation (spec §5.1).

Rules: codes uppercased, ICD dots removed; modifiers sorted; pointer letters resolved to codes;
lines with identical (code, modifiers) merged with units summed (pointers unioned); scope filter
applied; ordering discarded. The same function canonicalizes predictions and labels, which may be
`CodingPackage`-shaped or label-shaped mappings (only `diagnoses`, `first_listed` and `lines` are read).
"""

from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict

from codeloop.scoring.scope import Scope


class CanonicalLine(BaseModel):
    model_config = ConfigDict(frozen=True)
    code: str
    modifiers: tuple[str, ...]
    units: int
    pointers: frozenset[str]


class Canonical(BaseModel):
    model_config = ConfigDict(frozen=True)
    diagnoses: frozenset[str]
    first_listed: str | None
    lines: list[CanonicalLine]

    @property
    def is_empty(self) -> bool:
        return not self.diagnoses and not self.lines and self.first_listed is None


def normalize_icd(code: Any) -> str:
    return str(code).strip().upper().replace(".", "")


def normalize_line_code(code: Any) -> str:
    return str(code).strip().upper()


def _as_mapping(item: Any) -> Mapping[str, Any]:
    if isinstance(item, Mapping):
        return item
    if hasattr(item, "model_dump"):
        return item.model_dump()
    raise TypeError(f"cannot canonicalize {type(item).__name__}")


def _resolve_pointer(raw: Any, order: list[str]) -> str:
    s = str(raw).strip().upper()
    if len(s) == 1 and "A" <= s <= "Z":
        idx = ord(s) - ord("A")
        if idx < len(order):
            return order[idx]
    if s.isdigit():  # 1-based numeric pointers
        idx = int(s) - 1
        if 0 <= idx < len(order):
            return order[idx]
    return normalize_icd(s)


def canonicalize(package: Any, scope: Scope) -> Canonical:
    pkg = _as_mapping(package)
    dx_items = [_as_mapping(d) for d in (pkg.get("diagnoses") or [])]
    order: list[str] = []
    for d in dx_items:
        code = normalize_icd(d.get("code") or "")
        if code and code not in order:
            order.append(code)
    diagnoses = frozenset(order)

    first_listed: str | None = None
    for d in dx_items:
        if d.get("first_listed"):
            first_listed = normalize_icd(d.get("code") or "") or None
            break
    if first_listed is None and pkg.get("first_listed"):
        first_listed = normalize_icd(pkg["first_listed"]) or None

    merged: dict[tuple[str, tuple[str, ...]], tuple[int, set[str]]] = {}
    for raw_line in pkg.get("lines") or []:
        ln = _as_mapping(raw_line)
        code = normalize_line_code(ln.get("code") or "")
        if not code or not scope.in_scope_line(code):
            continue
        modifiers = scope.filter_modifiers(ln.get("modifiers") or [])
        units = int(ln.get("units") if ln.get("units") is not None else 1)
        pointers = {_resolve_pointer(p, order) for p in (ln.get("pointers") or []) if str(p).strip()}
        key = (code, modifiers)
        if key in merged:
            prev_units, prev_pointers = merged[key]
            merged[key] = (prev_units + units, prev_pointers | pointers)
        else:
            merged[key] = (units, pointers)
    lines = [
        CanonicalLine(code=code, modifiers=mods, units=units, pointers=frozenset(pointers))
        for (code, mods), (units, pointers) in sorted(merged.items())
    ]
    return Canonical(diagnoses=diagnoses, first_listed=first_listed, lines=lines)


def to_package_like(c: Canonical) -> dict[str, Any]:
    """A plain mapping that canonicalizes back to `c` (used for idempotence checks and exports)."""
    return {
        "diagnoses": [{"code": code, "first_listed": code == c.first_listed} for code in sorted(c.diagnoses)],
        "first_listed": c.first_listed,
        "lines": [
            {"code": ln.code, "modifiers": list(ln.modifiers), "units": ln.units, "pointers": sorted(ln.pointers)}
            for ln in c.lines
        ],
    }
