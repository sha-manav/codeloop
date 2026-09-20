"""Billable ICD-10-CM codes for the review UI's entry check.

The UIs run where data/tables/tables.sqlite (hundreds of MB, not in the image) is absent, and a blind label is final,
so a slip such as a category typed where the release needs a longer code could never be corrected. The list beside
this module is exported from the pinned tables by `codeloop tables export-billable` (ICD-10-CM is public domain;
codes only, no descriptions) and carries its provenance in `#` header lines. tests/test_codeset.py checks it against
the tables whenever they are present. CPT/HCPCS codes are deliberately not shipped: shape check only.
"""

from __future__ import annotations

import bisect
import sqlite3
from dataclasses import dataclass, field
from pathlib import Path

from codeloop.util.codes import normalize_icd10cm

BILLABLE_LIST = Path(__file__).with_name("icd10cm_billable.txt")


@dataclass(frozen=True)
class BillableIcd:
    codes: tuple[str, ...]  # sorted, normalized (no dot)
    provenance: dict[str, str] = field(default_factory=dict)

    def is_billable(self, code: str) -> bool:
        c = normalize_icd10cm(code)
        i = bisect.bisect_left(self.codes, c)
        return i < len(self.codes) and self.codes[i] == c

    def has_more_specific(self, code: str) -> bool:
        """True for a category or subcategory: some billable code extends it."""
        c = normalize_icd10cm(code)
        i = bisect.bisect_right(self.codes, c)
        return i < len(self.codes) and self.codes[i].startswith(c)

    @property
    def release(self) -> str:
        return self.provenance.get("icd10cm.release", "")


def parse_billable(text: str) -> BillableIcd:
    provenance: dict[str, str] = {}
    codes: list[str] = []
    for line in text.splitlines():
        line = line.strip()
        if line.startswith("#"):
            key, sep, value = line[1:].partition("=")
            if sep:
                provenance[key.strip()] = value.strip()
        elif line:
            codes.append(line)
    return BillableIcd(tuple(sorted(codes)), provenance)


def load_billable(path: Path = BILLABLE_LIST) -> BillableIcd | None:
    """None when the list is absent: the UI then falls back to the shape check alone."""
    if not path.exists():
        return None
    return parse_billable(path.read_text(encoding="utf-8"))


def export_billable(tables_sqlite: Path, out: Path = BILLABLE_LIST) -> int:
    """Write the billable codes of the built tables, with the tables' own provenance, and return how many."""
    conn = sqlite3.connect(f"file:{tables_sqlite}?mode=ro", uri=True)
    try:
        meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
        codes = [r[0] for r in conn.execute("SELECT code FROM icd10cm WHERE valid = 1 ORDER BY code")]
    finally:
        conn.close()
    header = [
        "# Billable ICD-10-CM codes (public domain), one per line, no dots. From `codeloop tables export-billable`.",
        f"# icd10cm.release = {meta.get('icd10cm.release', '')}",
        f"# tables_yaml_sha256 = {meta.get('tables_yaml_sha256', '')}",
        f"# parser_version = {meta.get('parser_version', '')}",
        f"# count = {len(codes)}",
    ]
    out.write_text("\n".join(header + codes) + "\n", encoding="utf-8", newline="\n")
    return len(codes)
