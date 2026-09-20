"""Where in the note a span sits: inside the assessment and plan, or not.

Notes in this corpus carry upper-case section headers on their own line. Only the generic header vocabulary is used
here; nothing about any one note. A note without recognizable headers yields None, and rules that depend on sections
then do not fire.
"""

from __future__ import annotations

import re

_HEADER = re.compile(r"^\s*([A-Z][A-Z /&\-]{3,60}?)\s*:?\s*$", re.M)
# the clinician's conclusions and decisions: what the visit assessed and what was done about it
ASSESSMENT_PLAN_WORDS = ("ASSESSMENT", "PLAN", "IMPRESSION", "INSTRUCTION")


def assessment_plan_ranges(note_text: str) -> list[tuple[int, int]] | None:
    """Character ranges of the assessment/plan sections; None when the note has no recognizable headers."""
    headers = [(m.start(), m.group(1).upper()) for m in _HEADER.finditer(note_text)]
    if not headers:
        return None
    ranges = []
    for k, (start, name) in enumerate(headers):
        if any(w in name for w in ASSESSMENT_PLAN_WORDS):
            end = headers[k + 1][0] if k + 1 < len(headers) else len(note_text)
            ranges.append((start, end))
    return ranges


def in_assessment_plan(ranges: list[tuple[int, int]], offset: int) -> bool:
    return any(start <= offset < end for start, end in ranges)
