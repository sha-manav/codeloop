"""ICD-10-CM retrieval (spec §7.1) over the pinned code set: FTS5 BM25 with query expansion."""

from __future__ import annotations

import re
from dataclasses import dataclass

from codeloop.tables import Tables

# FIND-DX-0052: a named condition qualified by control, stability, cause or lab findings ("..., under control",
# "... with elevated glucose") retrieves the qualifier's codes (gestational, abnormal-glucose, retinopathy) and not the
# condition's default code, and the mapper, told to choose only from the candidates, leaves the problem uncoded.
# The head term is the description before its first qualifier; the pipeline retries only uncoded problems with it, so
# the first mapping call and every decision it made are unchanged.
_HEAD_CUT = re.compile(r",|;|:| - | with | without | due to | secondary to | status post | s/p ", re.IGNORECASE)
_PARENTHETICAL = re.compile(r"\([^)]*\)")


def head_term(description: str) -> str:
    """The condition named before its first qualifier: 'Diabetes, currently under control' -> 'Diabetes'."""
    d = _PARENTHETICAL.sub(" ", description)
    d = _HEAD_CUT.split(d, maxsplit=1)[0]
    return re.sub(r"\s+", " ", d).strip()


@dataclass(frozen=True)
class Candidate:
    code: str
    description: str
    valid: bool


class IcdRetriever:
    def __init__(self, tables: Tables):
        self.tables = tables

    def exists(self, code: str) -> bool:
        return self.tables.icd_exists(code)

    def is_billable(self, code: str) -> bool:
        return self.tables.icd_valid(code)

    def description(self, code: str) -> str | None:
        return self.tables.icd_description(code)

    def laterality_variants(self, code: str) -> list[Candidate]:
        return [Candidate(c, d, True) for c, d in self.tables.icd_laterality_variants(code)]

    def search(self, query: str, k: int = 10) -> list[Candidate]:
        hits = self.tables.icd_search(query, k=k, valid_only=True)
        return [Candidate(h.code, h.description, h.valid) for h in hits]

    def candidates_for_problem(
        self, description: str, qualifiers: list[str], laterality: str, status: str, k: int = 12
    ) -> list[Candidate]:
        """Union of several phrasings, best-first, plus laterality siblings of the top hits."""
        queries = [description]
        if qualifiers:
            queries.append(" ".join([description, *qualifiers]))
        if laterality in ("right", "left", "bilateral", "unspecified"):
            queries.append(f"{description} {laterality}")
        if status == "historical":
            queries.insert(0, f"personal history of {description}")
        seen: dict[str, Candidate] = {}
        for q in queries:
            for c in self.search(q, k=k):
                seen.setdefault(c.code, c)
        for code in list(seen)[:3]:
            for v in self.laterality_variants(code):
                seen.setdefault(v.code, v)
        return list(seen.values())[: k + 6]

    def retry_candidates(self, description: str, offered: set[str], k: int = 8) -> list[Candidate]:
        """FIND-DX-0052: the head term's best hits that were not offered on the first pass, for a problem the mapper
        left uncoded. Empty when the description has no qualifier to strip, so nothing is retried for it."""
        head = head_term(description)
        if not head or head.lower() == description.lower():
            return []
        return [c for c in self.search(head, k=k + len(offered)) if c.code not in offered][:k]
