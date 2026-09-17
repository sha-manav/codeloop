"""Code-string normalization shared by ingest and (later, as its own frozen copy) scoring."""

from __future__ import annotations

import re

_ICD_RE = re.compile(r"^[A-Z][0-9][0-9A-Z](?:[0-9A-Z]{1,4})?$")


def normalize_icd10cm(code: str) -> str:
    """Uppercase, strip whitespace and the dot: 'm17.11' -> 'M1711'. Does not validate."""
    return code.strip().upper().replace(".", "")


def looks_like_icd10cm(code: str) -> bool:
    """Shape check only (no code-set lookup): letter, digit, alnum, then up to four alnums."""
    return bool(_ICD_RE.match(normalize_icd10cm(code)))
