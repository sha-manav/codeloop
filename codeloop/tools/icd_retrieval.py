"""ICD-10-CM retrieval (spec §7.1) over the pinned code set: FTS5 BM25 with query expansion."""

from __future__ import annotations

import re
from dataclasses import dataclass

from codeloop.tables import Tables

# FIND-DX-0052: a named condition qualified by control, stability, cause or lab findings ("..., under control",
# "... with elevated glucose") retrieves the qualifier's codes (gestational, abnormal-glucose, retinopathy) and not the
# condition's default code, and the mapper, told to choose only from the candidates, leaves the problem uncoded.
# The head term is the description before its first qualifier; the category defaults are the "unspecified" /
# "without complications" members of the categories already retrieved.
_HEAD_CUT = re.compile(r",|;|:| - | with | without | due to | secondary to | status post | s/p ", re.IGNORECASE)
_PARENTHETICAL = re.compile(r"\([^)]*\)")
_DEFAULT_WORDS = re.compile(r"unspecified|without complication", re.IGNORECASE)
_EXTRA_CANDIDATES = 10  # appended after the base candidates, so the base list is unchanged
_HEAD_HITS_KEPT = 5  # the head term's best hits come first; category defaults fill the rest
_DEFAULTS_PER_CATEGORY = 2
_CATEGORIES_CONSIDERED = 5


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

    def category_defaults(self, category: str, limit: int = _DEFAULTS_PER_CATEGORY) -> list[Candidate]:
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

    def candidates_for_problem(
        self, description: str, qualifiers: list[str], laterality: str, status: str, k: int = 12
    ) -> list[Candidate]:
        """Union of several phrasings, best-first, plus laterality siblings of the top hits; then (FIND-DX-0052) the
        head term's hits and the retrieved categories' default codes, appended so the base list is unchanged."""
        base = self._base_candidates(description, qualifiers, laterality, status, k)
        if status == "historical":
            return base
        seen = {c.code for c in base}
        head = head_term(description)
        head_hits: list[Candidate] = []
        if head and head.lower() != description.lower():
            head_hits = [c for c in self.search(head, k=k) if c.code not in seen][:_HEAD_HITS_KEPT]
        extra: dict[str, Candidate] = {c.code: c for c in head_hits}
        categories = list(dict.fromkeys([c.code[:3] for c in base[:6]] + [c.code[:3] for c in head_hits[:3]]))
        for category in categories[:_CATEGORIES_CONSIDERED]:
            for d in self.category_defaults(category):
                if d.code not in seen:
                    extra.setdefault(d.code, d)
        return base + list(extra.values())[:_EXTRA_CANDIDATES]

    def _base_candidates(
        self, description: str, qualifiers: list[str], laterality: str, status: str, k: int
    ) -> list[Candidate]:
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
