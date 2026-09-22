"""ICD-10-CM retrieval (spec §7.1) over the pinned code set: FTS5 BM25 with query expansion."""

from __future__ import annotations

import re
from dataclasses import dataclass

from codeloop.tables import Tables

# FIND-DX-0052: a named condition qualified by control, stability, cause or lab findings ("..., under control",
# "... with elevated glucose") retrieves the qualifier's codes (gestational, abnormal-glucose, retinopathy) and not the
# condition's default code, and the mapper, told to choose only from the candidates, leaves the problem uncoded.
# The head term is the description before its first qualifier; the pipeline retries only uncoded problems with it, so
# the first mapping call and every decision it made are unchanged. A problem that a billed line points at gets a wider
# retry (more hits, the head term, and the "unspecified" / "without complications" members of the retrieved
# categories), because a line without a coded indication is structurally invalid (spec section 8).
_HEAD_CUT = re.compile(r",|;|:| - | with | without | due to | secondary to | status post | s/p ", re.IGNORECASE)
_PARENTHETICAL = re.compile(r"\([^)]*\)")
_DEFAULT_WORDS = re.compile(r"unspecified|without complication", re.IGNORECASE)


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

    def category_defaults(self, category: str, limit: int = 2) -> list[Candidate]:
        """The billable default members of a 3-character category: the category itself when billable (I10), then the
        nearest descendants whose description says unspecified or without complications (E119, I509)."""
        out: list[Candidate] = []
        if self.is_billable(category):
            out.append(Candidate(category, self.description(category) or "", True))
        frontier = [category]
        for _ in range(4):
            if not frontier or len(out) >= limit:
                break
            next_frontier: list[str] = []
            for parent in frontier:
                for code, desc, valid in self.tables.icd_children(parent):
                    if valid and _DEFAULT_WORDS.search(desc):
                        out.append(Candidate(code, desc, True))
                    next_frontier.append(code)
            frontier = next_frontier
        return out[:limit]

    def wide_candidates(
        self, description: str, qualifiers: list[str], offered: set[str], k: int = 30, cap: int = 24
    ) -> list[Candidate]:
        """A wider net for an uncoded problem that a billed line depends on: deeper hits for the description with and
        without its qualifiers, the head term's hits, and the retrieved categories' default codes; nothing already
        offered on the first pass."""
        found: dict[str, Candidate] = {}
        queries = [description, head_term(description)]
        if qualifiers:
            queries.append(" ".join([description, *qualifiers]))
        for q in dict.fromkeys(q for q in queries if q):
            for c in self.search(q, k=k):
                if c.code not in offered:
                    found.setdefault(c.code, c)
        for category in list(dict.fromkeys(c[:3] for c in list(found)[:8]))[:5]:
            for d in self.category_defaults(category):
                if d.code not in offered:
                    found.setdefault(d.code, d)
        return list(found.values())[:cap]
