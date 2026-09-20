"""Diagnosis rules: existence/billability, history-of handling, laterality basis, first-listed."""

from __future__ import annotations

from dataclasses import dataclass, field

from codeloop.schemas.package import DataGap, ProviderQuery, Span
from codeloop.tools.icd_retrieval import IcdRetriever
from codeloop.util.codes import normalize_icd10cm

HISTORY_PREFIXES = ("Z8", "Z9")
SIDE_WORDS = {"right": "right", "left": "left", "bilateral": "bilateral"}


@dataclass
class DxDecision:
    problem_index: int
    code: str | None
    first_listed: bool
    rationale: str
    evidence: list[Span]
    queries: list[ProviderQuery] = field(default_factory=list)
    gaps: list[DataGap] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def _side_in_description(desc: str) -> str | None:
    d = desc.lower()
    for word in ("bilateral", "right", "left"):
        if f" {word} " in f" {d} " or d.endswith(f" {word}") or f", {word}" in d:
            return word
    return None


def apply_dx_rules(
    *,
    problem_index: int,
    problem_status: str,
    problem_laterality: str,
    problem_basis: str = "assessed",
    selected_code: str | None,
    first_listed: bool,
    rationale: str,
    laterality_basis: str,
    provider_query: str | None,
    note_spans: list[Span],
    dialogue_spans: list[Span],
    retriever: IcdRetriever,
    evidence_policy: str,
) -> DxDecision:
    d = DxDecision(
        problem_index=problem_index,
        code=None,
        first_listed=first_listed,
        rationale=rationale,
        evidence=list(note_spans),
    )
    ref_base = f"problem:{problem_index}"
    if problem_basis == "mentioned_only":
        # Documented, but neither assessed nor affecting care at this visit (an exam finding nobody comments on, a
        # review-of-systems positive, history that is simply recorded): outpatient coding does not report it, so no
        # code, no query, no data gap. Symptoms integral to an assessed problem do not come through here; see
        # drop_integral_symptoms.
        d.notes.append("not coded: documented but neither assessed nor affecting care at this visit")
        return d
    if problem_status == "ruled_out" or not selected_code:
        if provider_query:
            d.queries.append(
                ProviderQuery(field_ref=ref_base, question=provider_query, evidence=dialogue_spans or note_spans)
            )
        return d
    code = normalize_icd10cm(selected_code)
    if not retriever.exists(code):
        d.gaps.append(DataGap(field_ref=f"dx:{code}", missing="selected code is not in the pinned ICD-10-CM release"))
        return d
    if not retriever.is_billable(code):
        children = [c for c, _desc, valid in retriever.tables.icd_children(code) if valid]
        d.gaps.append(
            DataGap(field_ref=f"dx:{code}", missing=f"non-billable category code; {len(children)} billable children")
        )
        return d
    if problem_status == "historical" and not code.startswith(HISTORY_PREFIXES):
        d.gaps.append(
            DataGap(
                field_ref=f"dx:{code}",
                missing="historical problem mapped to an active-condition code; a personal-history Z-code is required",
            )
        )
        return d
    desc = retriever.description(code) or ""
    coded_side = _side_in_description(desc)
    # laterality: documented side must match; dialogue-only side is downgraded under note_only
    if coded_side in ("right", "left") and problem_laterality in ("right", "left") and coded_side != problem_laterality:
        variants = {_side_in_description(v.description): v.code for v in retriever.laterality_variants(code)}
        fixed = variants.get(problem_laterality)
        if fixed:
            d.notes.append(
                f"laterality mismatch: {code} says {coded_side}, documentation says {problem_laterality}; "
                f"replaced with {fixed}"
            )
            code = fixed
        else:
            d.gaps.append(
                DataGap(
                    field_ref=f"dx:{code}",
                    missing=f"code laterality ({coded_side}) contradicts documentation ({problem_laterality})",
                )
            )
            return d
    dialogue_only_side = evidence_policy == "note_only" and laterality_basis == "dialogue"
    if coded_side in ("right", "left", "bilateral") and dialogue_only_side:
        variants = {_side_in_description(v.description): v.code for v in retriever.laterality_variants(code)}
        unspecified = variants.get(None)
        question = provider_query or (
            f"Please document the side ({coded_side}) for the condition coded as {code}; the note does not state it."
        )
        d.queries.append(
            ProviderQuery(
                field_ref=f"dx:{code}:laterality", question=question, evidence=dialogue_spans, suggested_value=code
            )
        )
        if unspecified:
            d.notes.append(
                f"note_only: laterality documented only in the transcript; {code} downgraded to {unspecified}"
            )
            code = unspecified
        else:
            d.gaps.append(
                DataGap(
                    field_ref=f"dx:{code}",
                    missing="laterality supported only by the transcript and no unspecified-side code exists",
                )
            )
            return d
    elif provider_query:
        d.queries.append(
            ProviderQuery(field_ref=f"dx:{code}", question=provider_query, evidence=dialogue_spans or note_spans)
        )
    d.code = code
    return d


def drop_integral_symptoms(decisions: list[DxDecision], integral_to: dict[int, int]) -> None:
    """A symptom or sign is not coded beside the diagnosis that explains it, but only when that diagnosis is coded:
    if it could not be (no fitting candidate, a data gap), the symptom is what the documentation supports, and any
    line the visit billed still has a diagnosis to point at. `integral_to`: symptom problem index -> explaining one."""
    by_index = {d.problem_index: d for d in decisions}
    for i, j in integral_to.items():
        sym, target = by_index.get(i), by_index.get(j)
        if sym is None or not sym.code:
            continue
        if target is not None and target.code and target is not sym:
            sym.notes.append(f"not coded: integral to problem {j}, which is coded {target.code} (was {sym.code})")
            sym.code, sym.first_listed, sym.queries, sym.gaps = None, False, [], []
        else:
            sym.notes.append(f"coded although marked integral to problem {j}: that problem has no code")


def choose_first_listed(decisions: list[DxDecision]) -> None:
    """Exactly one first-listed among coded, non-historical diagnoses; default to the first coded active problem."""
    coded = [x for x in decisions if x.code]
    flagged = [x for x in coded if x.first_listed]
    for x in coded:
        x.first_listed = False
    if flagged:
        flagged[0].first_listed = True
    elif coded:
        active = [x for x in coded if not x.code.startswith(HISTORY_PREFIXES)] or coded
        active[0].first_listed = True
