"""`codeloop gate check --task tasks/FIND-… --base <commit> --head <commit>` (spec §13.2, decision D5)."""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

import yaml

from codeloop.config import ProjectConfig
from codeloop.evals.runner import EvalResult, RunMetrics, run_suite, score_packages, targeted_error
from codeloop.evals.suites import EvalDataset, EvalSuite, load_gold, load_gold_file
from codeloop.ledger import append_entry, utc_now
from codeloop.llm.client import LLMClient
from codeloop.paths import Paths
from codeloop.scoring import Scope
from codeloop.tables import Tables
from codeloop.util.jsonl import read_jsonl, write_json
from codeloop.versioning import git


@dataclass
class Check:
    name: str
    passed: bool
    detail: str


@dataclass
class GateReport:
    task: str
    base: str
    head: str
    checks: list[Check] = field(default_factory=list)
    grader_changed: bool = False
    changed_paths: list[str] = field(default_factory=list)
    base_targeted: list[float] = field(default_factory=list)
    head_targeted: list[float] = field(default_factory=list)
    numbers: dict[str, float | int | None] = field(default_factory=dict)

    @property
    def passed(self) -> bool:
        return all(c.passed for c in self.checks) and not self.grader_changed

    @property
    def route_to_human(self) -> bool:
        return self.grader_changed


def _under(path: str, prefixes: list[str]) -> bool:
    return any(path.startswith(p) for p in prefixes)


def stored_base_metrics(
    paths: Paths, *, base_version: str, targeted: EvalSuite, regression: EvalSuite, scope: Scope
) -> tuple[list[RunMetrics], list[RunMetrics]]:
    """Base metrics from the base version's stored predictions (every stored seed is one run)."""
    dataset = EvalDataset.load(paths.root / targeted.dataset) if targeted.dataset else None
    t_gold = {c.encounter_id: load_gold(paths, c.gold) for c in dataset.cases} if dataset else {}
    r_gold: dict[str, dict] = {}
    for f in regression.gold:
        r_gold.update(load_gold_file(paths, f))
    per_seed: dict[int, dict[str, dict]] = {}
    for p in sorted((paths.runs / base_version).glob("*/predictions*.jsonl")):
        seed = 1 if p.name == "predictions.jsonl" else int(p.name.split("seed")[1].split(".")[0])
        per_seed.setdefault(seed, {}).update({r["encounter_id"]: r for r in read_jsonl(p)})
    t_runs, r_runs = [], []
    for seed, preds in sorted(per_seed.items()):
        if dataset:
            scored = score_packages(preds, t_gold, scope)
            wrong = total = 0
            by_id = {r.encounter_id: r for r in scored["results"]}
            for case in dataset.cases:
                if case.encounter_id in by_id:
                    w, t = targeted_error(by_id[case.encounter_id].fields, case.field_refs)
                    wrong, total = wrong + w, total + t
            t_runs.append(
                RunMetrics(
                    seed=seed,
                    n=len(t_gold),
                    targeted_error_rate=(wrong / total if total else None),
                    targeted_fields=total,
                    targeted_wrong=wrong,
                )
            )
        scored = score_packages({k: v for k, v in preds.items() if k in r_gold}, r_gold, scope)
        b = scored["batch"]
        errors = sum(
            1
            for eid, v in preds.items()
            if eid in r_gold
            for f in v.get("scrubber", [])
            if f.get("severity") == "error"
        )
        r_runs.append(
            RunMetrics(
                seed=seed,
                n=len(r_gold),
                mean_agreement=b.mean_agreement,
                dx_recall=b.per_type["dx"]["recall"],
                line_recall=b.per_type["line"]["recall"],
                scrubber_errors=errors,
            )
        )
    return t_runs, r_runs


def _mean(vals: list[float | None]) -> float | None:
    xs = [v for v in vals if v is not None]
    return sum(xs) / len(xs) if xs else None


def gate_check(
    paths: Paths,
    config: ProjectConfig,
    *,
    task_dir: Path,
    base: str,
    head: str,
    llm: LLMClient,
    tables: Tables,
    runs: int | None = None,
    seeds: list[int] | None = None,
    concurrency: int = 4,
    actor: str | None = None,
) -> GateReport:
    with open(task_dir / "task.yaml", encoding="utf-8") as fh:
        task = yaml.safe_load(fh)
    report = GateReport(task=task["finding"], base=base, head=head)
    if git.is_repo(paths.root):
        current = git.current_commit(paths.root)
        if not current.startswith(head) and not head.startswith(current):
            raise RuntimeError(f"HEAD is {current[:12]}, not the head commit {head[:12]}")
        report.changed_paths = [
            p for p in git._git(paths.root, "diff", "--name-only", f"{base}..{head}").splitlines() if p
        ]
    writable = list(task["writable"])
    sign_off = list(task.get("writable_with_sign_off", []))
    bad = [p for p in report.changed_paths if not _under(p, writable + sign_off)]
    report.grader_changed = any(_under(p, sign_off) for p in report.changed_paths)
    report.checks.append(
        Check("paths", not bad, "only permitted paths changed" if not bad else f"forbidden paths changed: {bad[:10]}")
    )
    if report.grader_changed:
        report.checks.append(
            Check("grader", False, "evals/graders changed: routed to human review (grader_changed: true)")
        )

    d5 = config.decisions["D5"].value
    scope = Scope.load(paths.scope_yaml)
    t_suite = EvalSuite.load(paths.root / task["targeted_suite"])
    r_suite = EvalSuite.load(paths.root / task["regression_suite"])
    base_t, base_r = stored_base_metrics(
        paths, base_version=task["base_version"], targeted=t_suite, regression=r_suite, scope=scope
    )
    head_t: EvalResult = run_suite(
        paths,
        config,
        paths.root / task["targeted_suite"],
        llm=llm,
        tables=tables,
        runs=runs,
        seeds=seeds,
        concurrency=concurrency,
    )
    head_r: EvalResult = run_suite(
        paths,
        config,
        paths.root / task["regression_suite"],
        llm=llm,
        tables=tables,
        runs=runs,
        seeds=seeds,
        concurrency=concurrency,
    )

    base_err = _mean([m.targeted_error_rate for m in base_t])
    head_errs = [m.targeted_error_rate for m in head_t.runs if m.targeted_error_rate is not None]
    head_err = _mean(head_errs)
    report.base_targeted = [m.targeted_error_rate for m in base_t if m.targeted_error_rate is not None]
    report.head_targeted = head_errs
    min_rel = float(d5.get("targeted_relative_error_reduction_min", 0.25))
    if base_err is None or head_err is None:
        report.checks.append(
            Check("targeted", False, "targeted error rate unavailable (no base predictions or no head runs)")
        )
    else:
        falls = head_err <= base_err * (1 - min_rel) + 1e-12
        no_rise = all(e <= base_err + 1e-12 for e in head_errs) if d5.get("targeted_no_run_may_rise", True) else True
        report.checks.append(
            Check(
                "targeted",
                falls and no_rise,
                f"error rate base {base_err:.3f} -> head {head_err:.3f} (need <= {base_err * (1 - min_rel):.3f}); runs {[round(e, 3) for e in head_errs]}",
            )
        )
    base_agree, head_agree = _mean([m.mean_agreement for m in base_r]), head_r.mean.get("mean_agreement")
    max_drop = float(d5.get("regression_mean_agreement_drop_max_pp", 1.0)) / 100
    ok = base_agree is not None and head_agree is not None and head_agree >= base_agree - max_drop - 1e-12
    report.checks.append(
        Check(
            "regression_agreement",
            ok,
            f"mean agreement base {base_agree} -> head {head_agree} (max drop {max_drop:.3f})",
        )
    )
    max_recall_drop = float(d5.get("regression_per_type_recall_drop_max_pp", 2.0)) / 100
    for t in ("dx_recall", "line_recall"):
        b, h = _mean([getattr(m, t) for m in base_r]), head_r.mean.get(t)
        ok = b is not None and h is not None and h >= b - max_recall_drop - 1e-12
        report.checks.append(Check(f"regression_{t}", ok, f"{t} base {b} -> head {h} (max drop {max_recall_drop:.3f})"))
    b_scrub, h_scrub = _mean([m.scrubber_errors for m in base_r]), head_r.mean.get("scrubber_errors")
    ok = b_scrub is not None and h_scrub is not None and h_scrub <= b_scrub + 1e-12
    report.checks.append(
        Check("scrubber", ok, f"error-severity failures base {b_scrub} -> head {h_scrub} (non-increasing)")
    )
    esc = sum(m.escalation_failures for m in head_r.runs)
    report.checks.append(Check("compliance_escalation", esc == 0, f"escalation failures across runs: {esc}"))
    report.numbers = {
        "base_targeted_error": base_err,
        "head_targeted_error": head_err,
        "base_agreement": base_agree,
        "head_agreement": head_agree,
        "base_scrubber_errors": b_scrub,
        "head_scrubber_errors": h_scrub,
        "escalation_failures": esc,
        "base_runs": len(base_r),
        "head_runs": len(head_r.runs),
    }
    text = render_gate(report)
    (task_dir / "GATE.md").write_text(text, encoding="utf-8")
    write_json(
        task_dir / "GATE.json",
        {
            "task": report.task,
            "base": base,
            "head": head,
            "passed": report.passed,
            "route_to_human": report.route_to_human,
            "checks": [c.__dict__ for c in report.checks],
            "numbers": report.numbers,
            "changed_paths": report.changed_paths,
            "ran_at": utc_now(),
        },
    )
    append_entry(
        paths.ledger,
        f"gate {report.task}",
        {
            "base": base,
            "head": head,
            "result": "PASS" if report.passed else "FAIL",
            "route_to_human": report.route_to_human,
            "numbers": report.numbers,
        },
        actor=actor,
    )
    return report


def render_gate(r: GateReport) -> str:
    lines = [
        f"# GATE — {r.task}",
        "",
        f"base `{r.base[:12]}` → head `{r.head[:12]}` · **{'PASS' if r.passed else 'FAIL'}**"
        + (" · routed to human review (grader changed)" if r.route_to_human else ""),
        "",
        "| check | result | detail |",
        "|---|---|---|",
    ]
    lines += [f"| {c.name} | {'pass' if c.passed else 'FAIL'} | {c.detail} |" for c in r.checks]
    lines += [
        "",
        f"changed paths: {', '.join(r.changed_paths) or '(none)'}",
        "",
        f"targeted error per run — base: {[round(x, 3) for x in r.base_targeted]}; head: {[round(x, 3) for x in r.head_targeted]}",
        "",
    ]
    return "\n".join(lines)
