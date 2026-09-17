"""Field-level agreement (spec §5.2) and batch aggregation.

Per encounter, fields are enumerated from gold G and prediction P (both canonical, scope-filtered):
  1. dx:<code> for every code in G ∪ P, correct iff in both.
  2. first_listed, present whenever either side has any diagnosis; correct iff equal (None == None).
  3. Lines matched by code; within a code, G-lines and P-lines are paired greedily by the number of
     agreeing sub-fields. Each unmatched line is one wrong field line:<code>; each matched pair is
     line:<code> (correct) plus :modifiers, :units, :pointers, each correct iff equal.
Agreement = correct / total; both sides empty → 1.0 and flagged no_in_scope_fields.
Hierarchical (secondary): an unmatched diagnosis earns 0.5 credit if an unmatched code on the other
side shares its first three characters (greedy, one-to-one).
Field refs carry an index (line:<code>:<idx>) only when a code has more than one line on either side.
"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

from pydantic import BaseModel

from codeloop.scoring.bootstrap import wilson_interval
from codeloop.scoring.canonical import Canonical, CanonicalLine

EPS = 1e-9
LINE_SUBFIELDS: tuple[str, ...] = ("modifiers", "units", "pointers")
FIELD_TYPES: tuple[str, ...] = ("dx", "first_listed", "line", "modifiers", "units", "pointers")
TIERS: dict[str, float] = {"t75": 0.75, "t90": 0.90, "t100": 1.0}


class FieldResult(BaseModel):
    ref: str
    type: str
    correct: bool
    credit: float  # 1.0 if correct, else hierarchical partial credit (0.5) or 0.0
    gold: Any = None
    pred: Any = None


class TypeCounts(BaseModel):
    tp: int = 0
    fp: int = 0
    fn: int = 0
    n: int = 0
    correct: int = 0


class ScoreResult(BaseModel):
    encounter_id: str
    fields: list[FieldResult]
    n_fields: int
    n_correct: int
    agreement: float
    tiers: dict[str, bool]
    hier_credit: float
    hier_agreement: float
    per_type: dict[str, TypeCounts]
    no_in_scope_fields: bool = False


def _serialize_line(ln: CanonicalLine) -> dict[str, Any]:
    return {"code": ln.code, "modifiers": list(ln.modifiers), "units": ln.units, "pointers": sorted(ln.pointers)}


def _sub_value(ln: CanonicalLine, sub: str) -> Any:
    v = getattr(ln, sub)
    if isinstance(v, tuple):
        return list(v)
    if isinstance(v, frozenset):
        return sorted(v)
    return v


def pair_lines(
    gold: Sequence[CanonicalLine], pred: Sequence[CanonicalLine]
) -> tuple[list[tuple[CanonicalLine, CanonicalLine]], list[CanonicalLine], list[CanonicalLine]]:
    """Greedy one-to-one pairing by number of agreeing sub-fields; deterministic tie-break by order."""
    candidates: list[tuple[int, int, int]] = []
    for i, g in enumerate(gold):
        for j, p in enumerate(pred):
            score = sum(1 for sub in LINE_SUBFIELDS if getattr(g, sub) == getattr(p, sub))
            candidates.append((-score, i, j))
    candidates.sort()
    used_g: set[int] = set()
    used_p: set[int] = set()
    pairs: list[tuple[CanonicalLine, CanonicalLine]] = []
    for _, i, j in candidates:
        if i in used_g or j in used_p:
            continue
        pairs.append((gold[i], pred[j]))
        used_g.add(i)
        used_p.add(j)
    return (
        pairs,
        [g for i, g in enumerate(gold) if i not in used_g],
        [p for j, p in enumerate(pred) if j not in used_p],
    )


def _hierarchical_pairs(gold_dx: frozenset[str], pred_dx: frozenset[str]) -> set[str]:
    """Codes (from both sides) that receive 0.5 hierarchical credit."""
    unmatched_g = sorted(gold_dx - pred_dx)
    unmatched_p = sorted(pred_dx - gold_dx)
    used_p: set[str] = set()
    credited: set[str] = set()
    for g in unmatched_g:
        for p in unmatched_p:
            if p in used_p:
                continue
            if g[:3] == p[:3]:
                used_p.add(p)
                credited.update((g, p))
                break
    return credited


def score_encounter(encounter_id: str, gold: Canonical, pred: Canonical) -> ScoreResult:
    fields: list[FieldResult] = []
    per_type = {t: TypeCounts() for t in FIELD_TYPES}

    credited = _hierarchical_pairs(gold.diagnoses, pred.diagnoses)
    for code in sorted(gold.diagnoses | pred.diagnoses):
        in_g, in_p = code in gold.diagnoses, code in pred.diagnoses
        correct = in_g and in_p
        credit = 1.0 if correct else (0.5 if code in credited else 0.0)
        fields.append(
            FieldResult(ref=f"dx:{code}", type="dx", correct=correct, credit=credit,
                        gold=code if in_g else None, pred=code if in_p else None)
        )
        if correct:
            per_type["dx"].tp += 1
        elif in_g:
            per_type["dx"].fn += 1
        else:
            per_type["dx"].fp += 1

    if gold.diagnoses or pred.diagnoses:
        correct = gold.first_listed == pred.first_listed
        fields.append(
            FieldResult(ref="first_listed", type="first_listed", correct=correct, credit=float(correct),
                        gold=gold.first_listed, pred=pred.first_listed)
        )
        per_type["first_listed"].n += 1
        per_type["first_listed"].correct += int(correct)

    codes = sorted({ln.code for ln in gold.lines} | {ln.code for ln in pred.lines})
    for code in codes:
        g_lines = [ln for ln in gold.lines if ln.code == code]
        p_lines = [ln for ln in pred.lines if ln.code == code]
        pairs, unmatched_g, unmatched_p = pair_lines(g_lines, p_lines)
        multi = len(g_lines) > 1 or len(p_lines) > 1
        idx = 0

        def ref_for(i: int, code: str = code, multi: bool = multi) -> str:
            return f"line:{code}:{i}" if multi else f"line:{code}"

        for gl, pl in pairs:
            base = ref_for(idx)
            fields.append(FieldResult(ref=base, type="line", correct=True, credit=1.0,
                                      gold=_serialize_line(gl), pred=_serialize_line(pl)))
            per_type["line"].tp += 1
            for sub in LINE_SUBFIELDS:
                ok = getattr(gl, sub) == getattr(pl, sub)
                fields.append(FieldResult(ref=f"{base}:{sub}", type=sub, correct=ok, credit=float(ok),
                                          gold=_sub_value(gl, sub), pred=_sub_value(pl, sub)))
                per_type[sub].n += 1
                per_type[sub].correct += int(ok)
            idx += 1
        for gl in unmatched_g:
            fields.append(FieldResult(ref=ref_for(idx), type="line", correct=False, credit=0.0,
                                      gold=_serialize_line(gl), pred=None))
            per_type["line"].fn += 1
            idx += 1
        for pl in unmatched_p:
            fields.append(FieldResult(ref=ref_for(idx), type="line", correct=False, credit=0.0,
                                      gold=None, pred=_serialize_line(pl)))
            per_type["line"].fp += 1
            idx += 1

    n_fields = len(fields)
    n_correct = sum(1 for f in fields if f.correct)
    hier_credit = sum(f.credit for f in fields)
    if n_fields == 0:
        agreement, hier_agreement, empty = 1.0, 1.0, True
    else:
        agreement, hier_agreement, empty = n_correct / n_fields, hier_credit / n_fields, False
    tiers = {name: agreement >= threshold - EPS for name, threshold in TIERS.items()}
    return ScoreResult(
        encounter_id=encounter_id, fields=fields, n_fields=n_fields, n_correct=n_correct,
        agreement=agreement, tiers=tiers, hier_credit=hier_credit, hier_agreement=hier_agreement,
        per_type=per_type, no_in_scope_fields=empty,
    )


class TierShare(BaseModel):
    count: int
    n: int
    share: float
    wilson_low: float
    wilson_high: float


class BatchScore(BaseModel):
    n: int
    encounter_ids: list[str]
    mean_agreement: float
    mean_hier_agreement: float
    tiers: dict[str, TierShare]
    per_type: dict[str, dict[str, float | int]]
    no_in_scope_fields: int
    total_fields: int
    total_correct: int


def _safe_div(a: float, b: float) -> float:
    return a / b if b else 0.0


def aggregate(results: Sequence[ScoreResult]) -> BatchScore:
    n = len(results)
    ids = [r.encounter_id for r in results]
    mean_agreement = _safe_div(sum(r.agreement for r in results), n)
    mean_hier = _safe_div(sum(r.hier_agreement for r in results), n)
    tiers: dict[str, TierShare] = {}
    for name in TIERS:
        count = sum(1 for r in results if r.tiers.get(name))
        low, high = wilson_interval(count, n) if n else (0.0, 0.0)
        tiers[name] = TierShare(count=count, n=n, share=_safe_div(count, n), wilson_low=low, wilson_high=high)
    per_type: dict[str, dict[str, float | int]] = {}
    for t in ("dx", "line"):
        tp = sum(r.per_type[t].tp for r in results)
        fp = sum(r.per_type[t].fp for r in results)
        fn = sum(r.per_type[t].fn for r in results)
        per_type[t] = {
            "tp": tp, "fp": fp, "fn": fn,
            "precision": _safe_div(tp, tp + fp), "recall": _safe_div(tp, tp + fn),
        }
    for t in ("first_listed", "modifiers", "units", "pointers"):
        total = sum(r.per_type[t].n for r in results)
        correct = sum(r.per_type[t].correct for r in results)
        per_type[t] = {"n": total, "correct": correct, "accuracy": _safe_div(correct, total)}
    return BatchScore(
        n=n, encounter_ids=ids, mean_agreement=mean_agreement, mean_hier_agreement=mean_hier,
        tiers=tiers, per_type=per_type, no_in_scope_fields=sum(1 for r in results if r.no_in_scope_fields),
        total_fields=sum(r.n_fields for r in results), total_correct=sum(r.n_correct for r in results),
    )
