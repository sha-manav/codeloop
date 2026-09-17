"""`codeloop eval run --suite <path> --runs N --seeds 1,2,3 [--limit]` (spec §12, decision D4).

Runs the current working tree's pipeline over the suite's encounters once per seed, scores each run
with the frozen scorer, and reports the mean, per-run values and run-to-run variance. Results go to
evals/results/<suite>/<commit>.json with a Markdown summary alongside.
"""

from __future__ import annotations

import statistics
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from codeloop.agent.pipeline import RunContext, run_encounter
from codeloop.compliance import check_escalation
from codeloop.config import ProjectConfig
from codeloop.evals.suites import EvalDataset, EvalSuite, load_gold, load_gold_file
from codeloop.ledger import utc_now
from codeloop.llm.client import LLMClient
from codeloop.paths import Paths
from codeloop.schemas.encounter import Encounter, load_encounters_jsonl
from codeloop.schemas.package import CodingPackage
from codeloop.scoring import Scope, aggregate, canonicalize, score_encounter
from codeloop.tables import Tables
from codeloop.util.hashing import sha256_file
from codeloop.util.jsonl import read_jsonl, write_json
from codeloop.versioning import git


class RunMetrics(BaseModel):
    seed: int
    n: int
    targeted_error_rate: float | None = None
    targeted_fields: int = 0
    targeted_wrong: int = 0
    mean_agreement: float | None = None
    dx_recall: float | None = None
    line_recall: float | None = None
    scrubber_errors: int = 0
    escalation_failures: int = 0
    escalation_checked: int = 0
    failures: list[str] = Field(default_factory=list)


class EvalResult(BaseModel):
    suite: str
    kind: str
    commit: str
    ran_at: str
    seeds: list[int]
    n_encounters: int
    runs: list[RunMetrics]
    mean: dict[str, float | None]
    variance: dict[str, float | None]
    predictions_sha256: dict[str, str] = Field(default_factory=dict)
    notes: list[str] = Field(default_factory=list)


def _mean(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return statistics.fmean(vals) if vals else None


def _var(values: list[float | None]) -> float | None:
    vals = [v for v in values if v is not None]
    return statistics.pvariance(vals) if len(vals) > 1 else (0.0 if vals else None)


def targeted_error(score_fields: list, field_refs: list[str]) -> tuple[int, int]:
    """(wrong, total) over the finding's field refs. A ref absent from the scored fields means neither side
    asserts it, i.e. the prediction agrees with gold on that field, so it counts as correct."""
    by_ref = {f.ref: f.correct for f in score_fields}
    wrong = sum(1 for r in field_refs if not by_ref.get(r, True))
    return wrong, len(field_refs)


def score_packages(packages: dict[str, CodingPackage | dict], gold: dict[str, dict], scope: Scope) -> dict[str, Any]:
    results = []
    for eid in sorted(gold):
        pred = packages.get(eid, {"diagnoses": [], "lines": []})
        results.append(score_encounter(eid, canonicalize(gold[eid], scope), canonicalize(pred, scope)))
    return {"results": results, "batch": aggregate(results)}


def evaluate_packages(
    *,
    suite: EvalSuite,
    dataset: EvalDataset | None,
    packages: dict[str, CodingPackage],
    gold: dict[str, dict],
    scope: Scope,
    tables: Tables,
    encounters: dict[str, Encounter],
    base_packages: dict[str, dict] | None,
    policy: str,
    on_date: str,
    seed: int,
    failures: list[str],
) -> RunMetrics:
    scored = score_packages(packages, gold, scope)
    m = RunMetrics(seed=seed, n=len(gold), failures=failures)
    if suite.kind == "targeted" and dataset is not None:
        wrong = total = 0
        by_id = {r.encounter_id: r for r in scored["results"]}
        for case in dataset.cases:
            if case.encounter_id in by_id:
                w, t = targeted_error(by_id[case.encounter_id].fields, case.field_refs)
                wrong += w
                total += t
        m.targeted_fields, m.targeted_wrong = total, wrong
        m.targeted_error_rate = wrong / total if total else None
    b = scored["batch"]
    m.mean_agreement = b.mean_agreement
    m.dx_recall = b.per_type["dx"]["recall"]
    m.line_recall = b.per_type["line"]["recall"]
    m.scrubber_errors = sum(
        1
        for p in packages.values()
        for f in (p.scrubber if isinstance(p, CodingPackage) else [])
        if f.severity == "error"
    )
    if base_packages:
        for eid, pkg in packages.items():
            base = base_packages.get(eid)
            if base is None or eid not in encounters:
                continue
            r = check_escalation(
                CodingPackage.model_validate(base),
                pkg,
                encounter=encounters[eid],
                scope=scope,
                tables=tables,
                policy=policy,
                on_date=on_date,
            )
            m.escalation_checked += 1
            m.escalation_failures += int(not r.passed)
    return m


def run_suite(
    paths: Paths,
    config: ProjectConfig,
    suite_path: Path,
    *,
    llm: LLMClient,
    tables: Tables,
    runs: int | None = None,
    seeds: list[int] | None = None,
    limit: int | None = None,
    concurrency: int = 4,
) -> EvalResult:
    suite = EvalSuite.load(suite_path)
    seeds = seeds or suite.seeds[: (runs or suite.runs)]
    scope = Scope.load(paths.scope_yaml)
    policy = str(config.decisions["D1"].value)
    on_date = datetime.now(UTC).strftime("%Y%m%d")
    dataset = EvalDataset.load(paths.root / suite.dataset) if suite.kind == "targeted" and suite.dataset else None
    if dataset is not None:
        gold = {c.encounter_id: load_gold(paths, c.gold) for c in dataset.cases}
    else:
        gold = {}
        for f in suite.gold:
            gold.update(load_gold_file(paths, f))
    if limit:
        gold = dict(list(sorted(gold.items()))[:limit])
    holdout = set(paths.holdout_ids.read_text().split()) if paths.holdout_ids.exists() else set()
    if set(gold) & holdout:
        raise RuntimeError("eval gold contains holdout ids; refusing")
    encounters = {e.id: e for e in load_encounters_jsonl(paths.dev_encounters) if e.id in gold}
    base_packages: dict[str, dict] | None = None
    if suite.base_version:
        base_packages = {}
        for p in (paths.runs / suite.base_version).glob("*/predictions.jsonl"):
            base_packages.update({r["encounter_id"]: r for r in read_jsonl(p)})
    commit = git.current_commit(paths.root) if git.is_repo(paths.root) else "nogit"
    run_metrics: list[RunMetrics] = []
    out_dir = paths.evals / "results" / suite.name
    out_dir.mkdir(parents=True, exist_ok=True)
    pred_hashes: dict[str, str] = {}
    for seed in seeds:
        ctx = RunContext(
            paths=paths,
            version="eval",
            run_id=f"eval-{suite.name}-{commit[:8]}-s{seed}",
            llm=llm,
            tables=tables,
            scope=scope,
            scope_hash=sha256_file(paths.scope_yaml),
            evidence_policy=policy,
            on_date=on_date,
            seed=seed,
            prompt_hashes=llm.prompts.hashes(),
        )
        packages: dict[str, CodingPackage] = {}
        failures: list[str] = []
        from concurrent.futures import ThreadPoolExecutor

        def work(enc: Encounter, ctx=ctx):
            try:
                return enc.id, run_encounter(enc, ctx).package, None
            except Exception as e:  # noqa: BLE001
                return enc.id, None, f"{enc.id}: {type(e).__name__}: {e}"

        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            for eid, pkg, err in pool.map(work, [encounters[i] for i in sorted(encounters)]):
                if err:
                    failures.append(err)
                else:
                    packages[eid] = pkg
        m = evaluate_packages(
            suite=suite,
            dataset=dataset,
            packages=packages,
            gold=gold,
            scope=scope,
            tables=tables,
            encounters=encounters,
            base_packages=base_packages,
            policy=policy,
            on_date=on_date,
            seed=seed,
            failures=failures,
        )
        run_metrics.append(m)
        pred_path = out_dir / f"{commit[:12]}.seed{seed}.predictions.jsonl"
        from codeloop.util.jsonl import write_jsonl

        write_jsonl(pred_path, [packages[k] for k in sorted(packages)])
        pred_hashes[str(seed)] = sha256_file(pred_path)
    keys = (
        "targeted_error_rate",
        "mean_agreement",
        "dx_recall",
        "line_recall",
        "scrubber_errors",
        "escalation_failures",
    )
    result = EvalResult(
        suite=suite.name,
        kind=suite.kind,
        commit=commit,
        ran_at=utc_now(),
        seeds=list(seeds),
        n_encounters=len(gold),
        runs=run_metrics,
        mean={k: _mean([getattr(r, k) for r in run_metrics]) for k in keys},
        variance={k: _var([getattr(r, k) for r in run_metrics]) for k in keys},
        predictions_sha256=pred_hashes,
    )
    write_json(out_dir / f"{commit[:12]}.json", result.model_dump(mode="json"))
    (out_dir / f"{commit[:12]}.md").write_text(render_summary(result), encoding="utf-8")
    return result


def render_summary(r: EvalResult) -> str:
    lines = [
        f"# Eval {r.suite} ({r.kind}) @ {r.commit[:12]}",
        "",
        f"Ran {r.ran_at}; encounters {r.n_encounters}; seeds {r.seeds}.",
        "",
        "| seed | targeted error | mean agreement | dx recall | line recall | scrubber errors | escalation failures | failures |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for m in r.runs:
        te = (
            "—"
            if m.targeted_error_rate is None
            else f"{m.targeted_error_rate:.3f} ({m.targeted_wrong}/{m.targeted_fields})"
        )
        lines.append(
            f"| {m.seed} | {te} | {m.mean_agreement:.4f} | {m.dx_recall:.3f} | {m.line_recall:.3f} | {m.scrubber_errors} | {m.escalation_failures}/{m.escalation_checked} | {len(m.failures)} |"
        )
    lines += ["", "| metric | mean | variance |", "|---|---|---|"]
    for k, v in r.mean.items():
        var = r.variance.get(k)
        lines.append(f"| {k} | {'—' if v is None else f'{v:.4f}'} | {'—' if var is None else f'{var:.6f}'} |")
    return "\n".join(lines) + "\n"
