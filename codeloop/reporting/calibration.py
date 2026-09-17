"""Calibration of a run's diagnoses against the public ICD label sets (reference only, spec Phase 4)."""

from __future__ import annotations

from pathlib import Path

from codeloop.paths import Paths
from codeloop.scoring.bootstrap import wilson_interval
from codeloop.util.jsonl import read_jsonl


def _prf(pred: set[str], gold: set[str]) -> tuple[float, float, float]:
    tp = len(pred & gold)
    p = tp / len(pred) if pred else (1.0 if not gold else 0.0)
    r = tp / len(gold) if gold else (1.0 if not pred else 0.0)
    f = 2 * p * r / (p + r) if p + r else 0.0
    return p, r, f


def calibration_report(paths: Paths, predictions_path: Path, *, title: str) -> str:
    preds = {r["encounter_id"]: r for r in read_jsonl(predictions_path)}
    amazon = (
        {r["encounter_id"]: {c["code"] for c in r["codes"]} for r in read_jsonl(paths.amazon_labels)}
        if paths.amazon_labels.exists()
        else {}
    )
    medcoder = (
        {r["encounter_id"]: {d["code"] for d in r["diagnoses"]} for r in read_jsonl(paths.medcoder_labels)}
        if paths.medcoder_labels.exists()
        else {}
    )
    lines = [
        f"# Calibration: {title}",
        "",
        "Reference only: public label sets were produced under other scopes and guidelines; they are not the project's gold.",
        "",
    ]
    for name, labels in (("Amazon", amazon), ("MedCodER", medcoder)):
        rows = []
        exact = cat = []
        exact, cat, first = [], [], []
        for eid, p in sorted(preds.items()):
            if eid not in labels:
                continue
            pred = {d["code"] for d in p["diagnoses"]}
            gold = labels[eid]
            exact.append(_prf(pred, gold))
            cat.append(_prf({c[:3] for c in pred}, {c[:3] for c in gold}))
            fl = next((d["code"] for d in p["diagnoses"] if d.get("first_listed")), None)
            first.append(int(fl in gold) if fl else 0)
            rows.append((eid, len(pred), len(gold), len(pred & gold)))
        if not rows:
            lines += [f"## vs {name}", "", "no overlapping encounters", ""]
            continue
        n = len(rows)
        mp, mr, mf = (sum(x[i] for x in exact) / n for i in range(3))
        cp, cr, cf = (sum(x[i] for x in cat) / n for i in range(3))
        fl_ok = sum(first)
        lo, hi = wilson_interval(fl_ok, n)
        lines += [
            f"## vs {name} (n = {n})",
            "",
            f"- exact-code diagnosis precision/recall/F1 (mean per encounter): {mp:.3f} / {mr:.3f} / {mf:.3f}",
            f"- category (first three characters) precision/recall/F1: {cp:.3f} / {cr:.3f} / {cf:.3f}",
            f"- first-listed code present in the reference set: {fl_ok}/{n} = {fl_ok / n:.3f} "
            f"(Wilson {lo:.3f}–{hi:.3f})",
            f"- predicted codes per encounter: {sum(r[1] for r in rows) / n:.2f}; "
            f"reference codes per encounter: {sum(r[2] for r in rows) / n:.2f}",
            "",
            "| Encounter | predicted | reference | exact matches |",
            "|---|---|---|---|",
        ]
        lines += [f"| {eid} | {np} | {ng} | {tp} |" for eid, np, ng, tp in rows]
        lines.append("")
    return "\n".join(lines)
