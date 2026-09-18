"""`codeloop report` (spec §16): regenerate everything under reports/ from committed data."""

from __future__ import annotations

import json
import re
from collections import defaultdict
from typing import Any

import yaml

from codeloop.ingest.report import write_text
from codeloop.ledger import utc_now
from codeloop.paths import Paths
from codeloop.scoring import Scope, aggregate, canonicalize, score_encounter
from codeloop.util.jsonl import read_json, read_jsonl

BATCHES = ("batch1", "batch2", "batch3")


def _versions(paths: Paths) -> list[str]:
    return sorted(p.name for p in paths.runs.glob("v*") if p.is_dir() and re.fullmatch(r"v\d+", p.name))


def cell_tag(version: str, batch: str) -> str:
    k = int(version[1:])
    b = int(batch[-1])
    if b == k + 1:
        return "live"
    if b <= k:
        return "in-sample"
    return f"unseen (labels anchored to v{b - 1})"


def score_version_batch(paths: Paths, scope: Scope, version: str, batch: str) -> dict[str, Any] | None:
    pred_path = paths.runs / version / batch / "predictions.jsonl"
    label_path = paths.labels_file(batch)
    if not pred_path.exists() or not label_path.exists():
        return None
    preds = {r["encounter_id"]: r for r in read_jsonl(pred_path)}
    labels = {r["encounter_id"]: r for r in read_jsonl(label_path)}
    results = [
        score_encounter(
            eid,
            canonicalize(labels[eid]["label"], scope),
            canonicalize(preds.get(eid, {"diagnoses": [], "lines": []}), scope),
        )
        for eid in sorted(labels)
    ]
    b = aggregate(results)
    touches = [labels[e]["touches"] for e in labels]
    minutes = [labels[e]["review_minutes"] for e in labels]
    blind = [e for e in labels if labels[e].get("blind_label")]
    anchoring = None
    if blind:
        bv = [
            score_encounter(
                e, canonicalize(labels[e]["blind_label"], scope), canonicalize(labels[e]["label"], scope)
            ).agreement
            for e in blind
        ]
        ab = [
            score_encounter(
                e,
                canonicalize(labels[e]["blind_label"], scope),
                canonicalize(preds.get(e, {"diagnoses": [], "lines": []}), scope),
            ).agreement
            for e in blind
        ]
        ar = [
            score_encounter(
                e,
                canonicalize(labels[e]["label"], scope),
                canonicalize(preds.get(e, {"diagnoses": [], "lines": []}), scope),
            ).agreement
            for e in blind
        ]
        anchoring = {
            "n": len(blind),
            "blind_vs_reviewed": sum(bv) / len(bv),
            "agent_vs_blind": sum(ab) / len(ab),
            "agent_vs_reviewed": sum(ar) / len(ar),
        }
    ev_grades = [g for e in labels for g in labels[e].get("evidence_grades", {}).values()]
    q_grades = [g for e in labels for g in labels[e].get("query_grades", {}).values()]
    scrub_ok = sum(
        1 for e in labels if e in preds and not any(f.get("severity") == "error" for f in preds[e].get("scrubber", []))
    )
    rule_counts: dict[str, int] = defaultdict(int)
    for e in labels:
        for f in preds.get(e, {}).get("scrubber", []):
            rule_counts[f"{f['rule_id']}:{f['severity']}"] += 1
    return {
        "version": version,
        "batch": batch,
        "tag": cell_tag(version, batch),
        "n": b.n,
        "mean_agreement": b.mean_agreement,
        "tiers": {k: t.share for k, t in b.tiers.items()},
        "per_type": b.per_type,
        "touches_mean": sum(touches) / len(touches) if touches else None,
        "minutes_mean": sum(minutes) / len(minutes) if minutes else None,
        "anchoring": anchoring,
        "evidence_support_rate": (sum(1 for g in ev_grades if g == "supported") / len(ev_grades))
        if ev_grades
        else None,
        "evidence_graded": len(ev_grades),
        "query_precision": (sum(1 for g in q_grades if g == "warranted") / len(q_grades)) if q_grades else None,
        "queries_graded": len(q_grades),
        "scrubber_acceptance": scrub_ok / b.n if b.n else None,
        "scrubber_rule_counts": dict(sorted(rule_counts.items())),
    }


def curve_svg(cells: list[dict[str, Any]], difficulty: dict[str, float]) -> str:
    live = [c for c in cells if c["tag"] == "live"]
    live.sort(key=lambda c: c["batch"])
    w, h, pad = 640, 300, 40
    xs = list(range(len(live)))
    if not live:
        return "<svg xmlns='http://www.w3.org/2000/svg' width='640' height='120'><text x='20' y='60'>No live cells yet (no labeled batches).</text></svg>"

    def x(i):
        return pad + (i * (w - 2 * pad) / max(1, len(live) - 1))

    def y(v):
        return h - pad - v * (h - 2 * pad)

    series = {"≥75%": ("t75", "#1d4ed8"), "≥90%": ("t90", "#15803d"), "100%": ("t100", "#b91c1c")}
    parts = [
        f"<svg xmlns='http://www.w3.org/2000/svg' width='{w}' height='{h}' font-family='system-ui' font-size='12'>",
        f"<line x1='{pad}' y1='{h - pad}' x2='{w - pad}' y2='{h - pad}' stroke='#999'/>",
        f"<line x1='{pad}' y1='{pad}' x2='{pad}' y2='{h - pad}' stroke='#999'/>",
    ]
    for _label, (key, color) in series.items():
        pts = " ".join(f"{x(i):.1f},{y(c['tiers'][key]):.1f}" for i, c in zip(xs, live, strict=True))
        parts.append(f"<polyline fill='none' stroke='{color}' stroke-width='2' points='{pts}'/>")
    for i, c in zip(xs, live, strict=True):
        d = difficulty.get(c["batch"])
        parts.append(
            f"<text x='{x(i):.1f}' y='{h - pad + 16}' text-anchor='middle'>{c['version']} on {c['batch']}</text>"
        )
        parts.append(
            f"<text x='{x(i):.1f}' y='{h - pad + 30}' text-anchor='middle' fill='#666'>difficulty {d:+.2f}</text>"
            if d is not None
            else ""
        )
    for k, (label, (_key, color)) in enumerate(series.items()):
        parts.append(
            f"<rect x='{w - 150}' y='{pad + 14 * k}' width='10' height='10' fill='{color}'/><text x='{w - 135}' y='{pad + 14 * k + 9}'>{label} agreement</text>"
        )
    parts.append("</svg>")
    return "".join(parts)


def findings_log(paths: Paths) -> list[dict[str, Any]]:
    out = []
    for p in sorted(paths.findings.glob("FIND-*.yaml")):
        with open(p, encoding="utf-8") as fh:
            f = yaml.safe_load(fh)
        out.append(
            {
                "id": f["id"],
                "title": f["title"],
                "status": f["status"],
                "batch": f["batch_discovered"],
                "count": f["count"],
                "resolution": f.get("resolution") or {},
            }
        )
    return out


def build_reports(paths: Paths) -> dict[str, Any]:
    scope = Scope.load(paths.scope_yaml)
    cells = []
    for v in _versions(paths):
        for b in BATCHES:
            c = score_version_batch(paths, scope, v, b)
            if c:
                cells.append(c)
    difficulty = {}
    if paths.dev_split.exists():
        split = read_json(paths.dev_split)
        difficulty = {b: split["summary"][b]["mean_difficulty"] for b in BATCHES if b in split.get("summary", {})}
    (paths.reports / "curve.svg").write_text(curve_svg(cells, difficulty), encoding="utf-8")
    lines = [
        "# CodeLoop reports",
        "",
        f"Regenerated {utc_now()} from committed data. In-scope fields: diagnoses, first-listed, and lines in the scope allowlist; E/M is excluded.",
        "",
        "![curve](curve.svg)",
        "",
        "## Headline: live and holdout cells",
        "",
        "| version | batch | tag | n | mean agreement | ≥75% | ≥90% | 100% | touches | minutes |",
        "|---|---|---|---|---|---|---|---|---|---|",
    ]
    for c in cells:
        if c["tag"] == "live":
            lines.append(
                f"| {c['version']} | {c['batch']} | {c['tag']} | {c['n']} | {c['mean_agreement']:.4f} | {c['tiers']['t75']:.2f} | {c['tiers']['t90']:.2f} | {c['tiers']['t100']:.2f} | {c['touches_mean']:.2f} | {c['minutes_mean']:.2f} |"
            )
    holdout = paths.reports / "holdout.json"
    if holdout.exists():
        h = read_json(holdout)
        for v, pv in h["per_version"].items():
            lines.append(
                f"| {v} | holdout | holdout | {h['n']} | {pv['mean_agreement']:.4f} | {pv['tiers']['t75']['share']:.2f} | {pv['tiers']['t90']['share']:.2f} | {pv['tiers']['t100']['share']:.2f} | — | — |"
            )
    else:
        lines.append("| — | holdout | not scored yet | | | | | | | |")
    lines += [
        "",
        "## Appendix: version × batch (all cells, tagged)",
        "",
        "| version | batch | tag | mean agreement | dx recall | line recall | scrubber acceptance | evidence support | query precision |",
        "|---|---|---|---|---|---|---|---|---|",
    ]
    for c in cells:
        es = "—" if c["evidence_support_rate"] is None else f"{c['evidence_support_rate']:.2f} ({c['evidence_graded']})"
        qp = "—" if c["query_precision"] is None else f"{c['query_precision']:.2f} ({c['queries_graded']})"
        lines.append(
            f"| {c['version']} | {c['batch']} | {c['tag']} | {c['mean_agreement']:.4f} | {c['per_type']['dx']['recall']:.3f} | {c['per_type']['line']['recall']:.3f} | {c['scrubber_acceptance']:.2f} | {es} | {qp} |"
        )
    lines += [
        "",
        "## Anchoring (blind subset)",
        "",
        "| version | batch | n | blind vs reviewed | agent vs blind | agent vs reviewed |",
        "|---|---|---|---|---|---|",
    ]
    for c in cells:
        a = c["anchoring"]
        if a:
            lines.append(
                f"| {c['version']} | {c['batch']} | {a['n']} | {a['blind_vs_reviewed']:.3f} | {a['agent_vs_blind']:.3f} | {a['agent_vs_reviewed']:.3f} |"
            )
    lines += ["", "## Scrubber rule-fire counts per cell", ""]
    lines += [f"- {c['version']} on {c['batch']}: {c['scrubber_rule_counts'] or 'none'}" for c in cells]
    lines += [
        "",
        "## Findings log",
        "",
        "| id | status | batch | count | before | after | next-batch error rate |",
        "|---|---|---|---|---|---|---|",
    ]
    for f in findings_log(paths):
        r = f["resolution"]
        lines.append(
            f"| {f['id']} | {f['status']} | {f['batch']} | {f['count']} | {r.get('before_error_rate', '—')} | {r.get('after_error_rate', '—')} | {r.get('batch_next_error_rate', '—')} |"
        )
    lines += [
        "",
        "## Other reports",
        "",
        "- [Audit](audit.md)",
        "- [Ingest](ingest.md)",
        "- [Holdout](holdout.md)" if holdout.exists() else "- Holdout: not scored yet",
        *[f"- [{p.stem}]({p.name})" for p in sorted(paths.reports.glob("calibration_*.md"))],
        "",
    ]
    write_text(paths.reports / "index.md", "\n".join(lines))
    summary = {"generated_at": utc_now(), "cells": cells, "difficulty": difficulty, "findings": findings_log(paths)}
    (paths.reports / "summary.json").write_text(json.dumps(summary, indent=2, sort_keys=True), encoding="utf-8")
    return summary
