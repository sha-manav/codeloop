"""Field references (spec §4): the strings shared by the scorer, UI events, findings and evals.

    dx:<code>            dx:<code>:status      first_listed
    line:<code>[:<idx>]  line:<code>[:<idx>]:modifiers | :units | :pointers
    query:<n>
"""

from __future__ import annotations

import re
from dataclasses import dataclass

LINE_SUBFIELDS = ("modifiers", "units", "pointers")
_RE = re.compile(
    r"^(?P<kind>dx|line|query|first_listed)"
    r"(?::(?P<code>[A-Z0-9]+))?"
    r"(?::(?P<idx>\d+))?"
    r"(?::(?P<sub>status|modifiers|units|pointers))?$"
)


@dataclass(frozen=True)
class FieldRef:
    kind: str  # dx | line | query | first_listed
    code: str | None = None
    idx: int | None = None
    sub: str | None = None

    def __str__(self) -> str:
        parts = [self.kind]
        if self.code is not None:
            parts.append(self.code)
        if self.idx is not None:
            parts.append(str(self.idx))
        if self.sub is not None:
            parts.append(self.sub)
        return ":".join(parts)

    @property
    def field_type(self) -> str:
        """The scorer's field type for this reference."""
        if self.kind == "line" and self.sub:
            return self.sub
        return self.kind


def dx_ref(code: str, sub: str | None = None) -> str:
    return str(FieldRef("dx", code, None, sub))


def line_ref(code: str, idx: int | None = None, sub: str | None = None) -> str:
    return str(FieldRef("line", code, idx, sub))


def query_ref(n: int) -> str:
    return f"query:{n}"


def parse_field_ref(ref: str) -> FieldRef:
    m = _RE.match(ref)
    if not m:
        raise ValueError(f"malformed field reference: {ref!r}")
    kind = m.group("kind")
    code, idx, sub = m.group("code"), m.group("idx"), m.group("sub")
    if kind == "query":
        if code is None or not code.isdigit() or idx is not None or sub is not None:
            raise ValueError(f"malformed query reference: {ref!r}")
        return FieldRef("query", None, int(code), None)
    if kind == "first_listed":
        if code or idx or sub:
            raise ValueError(f"malformed first_listed reference: {ref!r}")
        return FieldRef("first_listed")
    if code is None:
        raise ValueError(f"{kind} reference needs a code: {ref!r}")
    if kind == "dx" and (idx is not None or sub not in (None, "status")):
        raise ValueError(f"malformed dx reference: {ref!r}")
    if kind == "line" and sub == "status":
        raise ValueError(f"malformed line reference: {ref!r}")
    return FieldRef(kind, code, int(idx) if idx is not None else None, sub)
