"""Diagnosis rules: existence/billability, history-of handling, laterality basis, first-listed."""

from __future__ import annotations

from dataclasses import dataclass, field

from codeloop.rules.sections import assessment_plan_ranges, in_assessment_plan
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


# Diagnoses that are documented but were not assessed (batch1 findings; coder guidelines section 3: a visit is coded for
# what was assessed, managed or affecting care). Each class is one accepted finding, keyed by the ICD-10-CM categories
# the coder removed, so the rule reaches exactly as far as the evidence does; a class is added when a finding is
# accepted. (finding, code prefixes, needs a definitive musculoskeletal or injury diagnosis beside it)
NOT_ASSESSED_CLASSES: tuple[tuple[str, tuple[str, ...], bool], ...] = (
    ("FIND-DX-0020", ("R42",), False),  # a review-of-systems positive coded as a diagnosis
    ("FIND-DX-0023", ("R63",), False),  # weight-change symptoms from the history
    ("FIND-DX-0030", ("Z87",), False),  # personal history that is simply recorded
    ("FIND-DX-0006", ("M253", "M254", "M255", "M256"), True),  # joint symptoms beside the diagnosis that explains them
)
_JOINT_SYMPTOMS = ("M253", "M254", "M255", "M256", "M796")


def _definitive_msk(code: str) -> bool:
    return code[:1] in ("M", "S") and not code.startswith(_JOINT_SYMPTOMS)


def drop_not_assessed(decisions: list[DxDecision], note_text: str, line_pointers: list[list[str]]) -> list[str]:
    """Un-code a diagnosis of a NOT_ASSESSED class when none of its note evidence lies in the assessment and plan.

    Conservative on every side: the note must have recognizable sections and the diagnosis note evidence; another
    diagnosis must remain coded; a diagnosis that is the only thing a billed line points at stays. Returns the dropped
    codes; the caller removes them from line pointers and from queries and gaps."""
    ranges = assessment_plan_ranges(note_text)
    if ranges is None:
        return []
    dropped: list[str] = []
    for d in decisions:
        if not d.code:
            continue
        cls = next((c for c in NOT_ASSESSED_CLASSES if d.code.startswith(c[1])), None)
        if cls is None or not d.evidence or any(in_assessment_plan(ranges, s.start) for s in d.evidence):
            continue
        others = [x.code for x in decisions if x.code and x is not d]
        if not others or (cls[2] and not any(_definitive_msk(c) for c in others)):
            continue
        if any(ptrs and set(ptrs) <= {d.code} for ptrs in line_pointers):
            d.notes.append(f"kept although not in the assessment and plan ({cls[0]}): a billed line points only at it")
            continue
        d.notes.append(f"not coded ({cls[0]}): {d.code} is documented outside the assessment and plan only")
        dropped.append(d.code)
        d.code, d.first_listed, d.queries, d.gaps = None, False, [], []
    return dropped


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
