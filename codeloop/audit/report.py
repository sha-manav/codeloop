"""`codeloop audit report`: reports/audit.md with per-category precision, evaluable_n_est and D10 decisions."""

from __future__ import annotations

from collections import defaultdict
from typing import Any

from codeloop.audit.responses import latest_grades, load_events, missed_events
from codeloop.audit.run import audit_dir, load_results
from codeloop.audit.sample import load_spot_check_sample
from codeloop.audit.schema import CATEGORIES, MODULE_CATEGORY, PROCEDURE_CATEGORIES, PROPOSED_RANGES
from codeloop.config import ProjectConfig
from codeloop.ingest.report import write_text
from codeloop.ledger import utc_now
from codeloop.paths import Paths
from codeloop.scoring.bootstrap import wilson_interval
from codeloop.util.jsonl import write_json


def category_stats(results: dict[str, dict[str, Any]], grades: dict[tuple[str, int], Any]) -> dict[str, dict[str, Any]]:
    stats: dict[str, dict[str, Any]] = {c: {"flags": 0, "flagged_encounters": 0, "graded": 0, "confirmed": 0} for c in CATEGORIES}
    for eid, rec in results.items():
        seen: set[str] = set()
        for idx, flag in enumerate(rec["result"]["flags"]):
            c = flag["category"]
            stats[c]["flags"] += 1
            seen.add(c)
            g = grades.get((eid, idx))
            if g is not None:
                stats[c]["graded"] += 1
                stats[c]["confirmed"] += int(g.decision == "confirm")
        for c in seen:
            stats[c]["flagged_encounters"] += 1
    for s in stats.values():
        if s["graded"]:
            p = s["confirmed"] / s["graded"]
            lo, hi = wilson_interval(s["confirmed"], s["graded"])
            s["precision"], s["precision_low"], s["precision_high"] = p, lo, hi
            s["evaluable_n_est"] = s["flagged_encounters"] * p
        else:
            s["precision"] = s["precision_low"] = s["precision_high"] = None
            s["evaluable_n_est"] = None
    return stats


def multi_procedure_stats(results: dict[str, dict[str, Any]], grades: dict[tuple[str, int], Any]) -> dict[str, Any]:
    """Proxy for distinct_59x: encounters with >=2 distinct procedure categories flagged."""
    flagged = 0
    graded = 0
    confirmed = 0
    for eid, rec in results.items():
        procs = [(i, f) for i, f in enumerate(rec["result"]["flags"]) if f["category"] in PROCEDURE_CATEGORIES]
        cats = {f["category"] for _, f in procs}
        if len(cats) < 2:
            continue
        flagged += 1
        g = [grades.get((eid, i)) for i, _ in procs]
        if all(x is not None for x in g):
            graded += 1
            confirmed_cats = {f["category"] for (i, f), x in zip(procs, g, strict=True) if x.decision == "confirm"}
            confirmed += int(len(confirmed_cats) >= 2)
    p = confirmed / graded if graded else None
    return {"flagged_encounters": flagged, "graded": graded, "confirmed": confirmed, "precision": p,
            "evaluable_n_est": flagged * p if p is not None else None}


def decide(stat: dict[str, Any], config: ProjectConfig) -> tuple[bool | None, str]:
    rule = config.decisions["D10"].value
    n_min = float(rule.get("evaluable_n_est_min", 15))
    c_min = int(rule.get("spot_check_confirmed_min", 5))
    if stat.get("flagged_encounters", 0) == 0:
        return False, "no flagged encounters (evaluable_n_est = 0)"
    if stat.get("precision") is None:
        return None, "undecided: no graded flags in the spot-check"
    on = stat["evaluable_n_est"] >= n_min and stat["confirmed"] >= c_min
    return on, f"evaluable_n_est {stat['evaluable_n_est']:.1f} {'>=' if stat['evaluable_n_est'] >= n_min else '<'} {n_min:g} and confirmed {stat['confirmed']} {'>=' if stat['confirmed'] >= c_min else '<'} {c_min}"


def _fmt(x: float | None, digits: int = 2) -> str:
    return "—" if x is None else f"{x:.{digits}f}"


def build_report(paths: Paths, config: ProjectConfig) -> str:
    results = load_results(paths)
    if not results:
        raise RuntimeError("no audit results; run `codeloop audit run` first")
    events = load_events(paths)
    grades = latest_grades(events)
    sample = load_spot_check_sample(paths)
    stats = category_stats(results, grades)
    multi = multi_procedure_stats(results, grades)

    models = {r["llm"]["model"] for r in results.values()}
    prompt_hashes = {r["llm"]["prompt_hash"] for r in results.values()}
    tokens_in = sum(r["llm"]["tokens_in"] for r in results.values())
    tokens_out = sum(r["llm"]["tokens_out"] for r in results.values())
    n_flags = sum(len(r["result"]["flags"]) for r in results.values())
    located = sum(1 for r in results.values() for s in r["flag_spans"] if s)
    age = sum(1 for r in results.values() if r["result"]["patient"]["age_years"] is not None)
    sex = sum(1 for r in results.values() if r["result"]["patient"]["sex"] is not None)
    by_subset: dict[str, list[int]] = defaultdict(list)
    for r in results.values():
        by_subset[r["subset"]].append(len(r["result"]["flags"]))

    lines = [
        "# Prevalence audit (Phase 2)",
        "",
        f"Generated {utc_now()}. Dev encounters audited: {len(results)} (the 40 holdout encounters are never audited).",
        f"Model(s): {', '.join(sorted(models))}; prompt hash(es): {', '.join(h[:16] + '…' for h in sorted(prompt_hashes))};",
        f"tokens in/out: {tokens_in}/{tokens_out}. Flags: {n_flags} ({located} with a located evidence span).",
        f"Patient facts documented: age {age}/{len(results)}, sex {sex}/{len(results)}.",
        "",
        "Flags per encounter by subset: " + "; ".join(f"{s}: mean {sum(v)/len(v):.2f} over {len(v)}" for s, v in sorted(by_subset.items())),
        "",
        "## Spot-check",
        "",
    ]
    if sample:
        lines.append(f"Sample drawn {sample['drawn_at']} with seed {sample['seed']}: {len(sample['arms']['flagged'])} flagged-arm + {len(sample['arms']['random'])} random-arm encounters out of {sample['population']} ({sample['population_flagged']} with ≥1 flag).")
    else:
        lines.append("No spot-check sample drawn yet (`codeloop audit sample --n 30`).")
    reviewers: dict[str, int] = defaultdict(int)
    for g in grades.values():
        reviewers[g.reviewer] += 1
    provisional = [r for r in reviewers if r.startswith("provisional")]
    lines += [
        f"Grades recorded: {len(grades)} flags graded ({sum(1 for g in grades.values() if g.decision == 'confirm')} confirmed); "
        f"missed services reported: {len(missed_events(events))}.",
        f"Graders (latest grade per flag): {dict(sorted(reviewers.items())) or 'none'}.",
    ]
    if provisional:
        lines += [
            "",
            f"**Provisional:** grades from {', '.join(provisional)} are a machine stand-in, not a CPC judgment. "
            "The CPC's grades replace them automatically (latest grade per flag wins); the module decisions below are provisional until then.",
        ]
    lines += [
        "",
        "## Per-category prevalence and precision",
        "",
        "`evaluable_n_est = flagged_encounters × precision` (precision from graded flags in the spot-check; Wilson 95% interval).",
        "",
        "| Category | Flags | Flagged encounters | Graded | Confirmed | Precision (95% CI) | evaluable_n_est |",
        "|---|---|---|---|---|---|---|",
    ]
    for c in CATEGORIES:
        s = stats[c]
        ci = "—" if s["precision"] is None else f"{s['precision']:.2f} ({s['precision_low']:.2f}–{s['precision_high']:.2f})"
        lines.append(f"| {c} | {s['flags']} | {s['flagged_encounters']} | {s['graded']} | {s['confirmed']} | {ci} | {_fmt(s['evaluable_n_est'], 1)} |")
    lines += [
        "",
        "## Module decisions (decision D10)",
        "",
        f"Rule: on iff `evaluable_n_est >= {config.decisions['D10'].value.get('evaluable_n_est_min', 15)}` and `confirmed >= {config.decisions['D10'].value.get('spot_check_confirmed_min', 5)}`.",
        "",
        "| Module | Signal | Flagged encounters | Confirmed | evaluable_n_est | Decision | Arithmetic |",
        "|---|---|---|---|---|---|---|",
    ]
    decisions: dict[str, Any] = {}
    for module, category in MODULE_CATEGORY.items():
        s = stats[category]
        on, why = decide(s, config)
        decisions[module] = {"on": on, "category": category, "evaluable_n_est": s["evaluable_n_est"], "confirmed": s["confirmed"]}
        lines.append(f"| {module} | {category} | {s['flagged_encounters']} | {s['confirmed']} | {_fmt(s['evaluable_n_est'], 1)} | {'on' if on else 'off' if on is not None else 'undecided'} | {why} |")
    on, why = decide(multi, config)
    decisions["distinct_59x"] = {"on": on, "category": "≥2 distinct procedure categories", "evaluable_n_est": multi["evaluable_n_est"], "confirmed": multi["confirmed"]}
    lines.append(f"| distinct_59x | ≥2 distinct procedure categories in one encounter | {multi['flagged_encounters']} | {multi['confirmed']} | {_fmt(multi['evaluable_n_est'], 1)} | {'on' if on else 'off' if on is not None else 'undecided'} | {why} |")
    lines += [
        "",
        "## core_lines allowlist proposal (owner fills `config/scope.yaml`)",
        "",
        "Code numbers only. A category is proposed for the allowlist when at least one flag was confirmed; the owner decides the final ranges.",
        "",
        "| Category | Confirmed | evaluable_n_est | Proposed ranges |",
        "|---|---|---|---|",
    ]
    for c in CATEGORIES:
        s = stats[c]
        proposed = ", ".join(PROPOSED_RANGES.get(c, [])) or "(none: define per finding)"
        mark = "propose" if s["confirmed"] > 0 else "hold"
        lines.append(f"| {c} | {s['confirmed']} | {_fmt(s['evaluable_n_est'], 1)} | {mark}: {proposed} |")
    missed = missed_events(events)
    if missed:
        counts: dict[str, int] = defaultdict(int)
        for m in missed:
            counts[m.category or "?"] += 1
        lines += ["", "## Services the CPC reported as missed by the audit", "", "| Category | Count |", "|---|---|"]
        lines += [f"| {c} | {n} |" for c, n in sorted(counts.items())]
    lines += [
        "",
        "## Notes",
        "",
        "- Flags are candidates from one structured LLM call per encounter; only the spot-check grades are human judgments.",
        "- Speaker tags in some subsets are swapped by ASR, so `counseling_by` from the transcript is unreliable evidence.",
        "- Per-encounter flag counts for the Phase 3 difficulty index are in `runs/audit/flag_counts.json`.",
        "",
    ]
    write_json(audit_dir(paths) / "flag_counts.json", {eid: len(r["result"]["flags"]) for eid, r in sorted(results.items())})
    write_json(audit_dir(paths) / "module_decisions.json", {"generated_at": utc_now(), "decisions": decisions, "stats": stats, "multi_procedure": multi})
    return "\n".join(lines)


def write_report(paths: Paths, config: ProjectConfig) -> str:
    text = build_report(paths, config)
    write_text(paths.reports / "audit.md", text)
    return text
