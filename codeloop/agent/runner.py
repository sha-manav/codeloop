"""`codeloop run`: run the pipeline over a batch of dev encounters and write predictions + traces."""

from __future__ import annotations

import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path

from codeloop import __version__
from codeloop.agent.pipeline import RunContext, run_encounter
from codeloop.config import ProjectConfig
from codeloop.ledger import append_entry, utc_now
from codeloop.llm.client import LLMClient
from codeloop.paths import Paths
from codeloop.schemas.encounter import Encounter, load_encounters_jsonl
from codeloop.scoring import Scope
from codeloop.scrubber import rule_fire_counts
from codeloop.tables import Tables
from codeloop.util.hashing import sha256_file
from codeloop.util.jsonl import write_json, write_jsonl
from codeloop.versioning import git
from codeloop.versioning.freeze import batch_ids


class RunError(RuntimeError):
    pass


@dataclass
class RunSummary:
    run_id: str
    version: str
    batch: str
    seeds: list[int]
    n_encounters: int
    predictions: dict[int, str] = field(default_factory=dict)
    tokens_in: int = 0
    tokens_out: int = 0
    cache_hits: int = 0
    llm_calls: int = 0
    failures: list[str] = field(default_factory=list)
    scrubber_rule_counts: dict[str, int] = field(default_factory=dict)
    compliance_failed: int = 0
    data_gaps: int = 0
    provider_queries: int = 0
    estimated_cost_usd: float | None = None


def run_dir(paths: Paths, version: str, batch: str) -> Path:
    return paths.runs / version / batch


def predictions_path(paths: Paths, version: str, batch: str, seed: int = 1) -> Path:
    name = "predictions.jsonl" if seed == 1 else f"predictions.seed{seed}.jsonl"
    return run_dir(paths, version, batch) / name


def check_version_state(paths: Paths, version: str, batch: str) -> str:
    """`dev` runs only on seed/spare; a version tag must be checked out exactly for vK runs."""
    if version == "dev":
        if batch not in ("seed", "spare"):
            raise RunError("--version dev may only run on the seed or spare split")
        return git.current_commit(paths.root) if git.is_repo(paths.root) else ""
    if not git.is_repo(paths.root):
        raise RunError("not a git repository; versioned runs require the version tag")
    tag = git.describe_exact_tag(paths.root)
    if tag == version:
        return git.current_commit(paths.root)
    if not git.tag_exists(paths.root, version):
        raise RunError(f"tag {version!r} does not exist; freeze the version first")
    if not git.is_clean(paths.root):
        raise RunError("working tree is not clean; commit or stash before running a versioned batch")
    if not git.code_matches_tag(paths.root, version):
        raise RunError(f"committed code (codeloop/, prompts/, config/) differs from tag {version!r}; check out the tag")
    return git.current_commit(paths.root)


def load_batch_encounters(paths: Paths, batch: str, limit: int | None = None) -> list[Encounter]:
    ids = batch_ids(paths, batch)
    holdout = set(paths.holdout_ids.read_text().split()) if paths.holdout_ids.exists() else set()
    if set(ids) & holdout:
        raise RunError("batch contains holdout ids; refusing")
    wanted = set(ids)
    encs = [e for e in load_encounters_jsonl(paths.dev_encounters) if e.id in wanted]
    encs.sort(key=lambda e: e.id)
    return encs[:limit] if limit else encs


def run_batch(
    paths: Paths,
    config: ProjectConfig,
    *,
    version: str,
    batch: str,
    llm: LLMClient,
    tables: Tables,
    seeds: list[int],
    limit: int | None = None,
    concurrency: int = 4,
    commit: str = "",
    actor: str | None = None,
) -> RunSummary:
    encounters = load_batch_encounters(paths, batch, limit)
    scope = Scope.load(paths.scope_yaml)
    run_id = f"{version}-{batch}-{utc_now().replace(':', '').replace('-', '')}-{uuid.uuid4().hex[:6]}"
    on_date = datetime.now(UTC).strftime("%Y%m%d")
    policy = str(config.decisions["D1"].value)
    summary = RunSummary(run_id=run_id, version=version, batch=batch, seeds=list(seeds), n_encounters=len(encounters))
    out_dir = run_dir(paths, version, batch)
    out_dir.mkdir(parents=True, exist_ok=True)
    rule_counts: dict[str, int] = {}
    for seed in seeds:
        ctx = RunContext(
            paths=paths,
            version=version,
            run_id=run_id,
            llm=llm,
            tables=tables,
            scope=scope,
            scope_hash=sha256_file(paths.scope_yaml),
            evidence_policy=policy,
            on_date=on_date,
            seed=seed,
            prompt_hashes=llm.prompts.hashes(),
        )

        def work(enc: Encounter, ctx=ctx):
            try:
                return enc.id, run_encounter(enc, ctx), None
            except Exception as e:  # noqa: BLE001 - recorded, never content
                return enc.id, None, f"{enc.id} seed {ctx.seed}: {type(e).__name__}: {e}"

        traces = []
        with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
            for _eid, trace, err in pool.map(work, encounters):
                if err:
                    summary.failures.append(err)
                    continue
                traces.append(trace)
        traces.sort(key=lambda t: t.encounter_id)
        pred_path = predictions_path(paths, version, batch, seed)
        write_jsonl(pred_path, [t.package for t in traces])
        trace_dir = out_dir / "traces" / f"seed{seed}"
        trace_dir.mkdir(parents=True, exist_ok=True)
        for t in traces:
            (trace_dir / f"{t.encounter_id}.json").write_text(t.model_dump_json(indent=1), encoding="utf-8")
        summary.predictions[seed] = pred_path.relative_to(paths.root).as_posix()
        for t in traces:
            for st in t.stages:
                for call in st.llm_calls:
                    summary.llm_calls += 1
                    summary.tokens_in += call.tokens_in
                    summary.tokens_out += call.tokens_out
                    summary.cache_hits += int(call.cache_hit)
            for k, v in rule_fire_counts(t.package.scrubber).items():
                rule_counts[k] = rule_counts.get(k, 0) + v
            summary.compliance_failed += int(not t.package.compliance.passed)
            summary.data_gaps += len(t.package.data_gaps)
            summary.provider_queries += len(t.package.provider_queries)
    summary.scrubber_rule_counts = dict(sorted(rule_counts.items()))
    pricing = llm.config.pricing.get(llm.config.default.model)
    if pricing:
        summary.estimated_cost_usd = round(pricing.cost(summary.tokens_in, summary.tokens_out), 2)
    manifest = {
        "run_id": run_id,
        "version": version,
        "batch": batch,
        "commit": commit,
        "seeds": seeds,
        "encounters": [e.id for e in encounters],
        "n_encounters": len(encounters),
        "on_date": on_date,
        "evidence_policy": policy,
        "models_yaml_sha256": llm.models_hash,
        "prompt_hashes": llm.prompts.hashes(),
        "scope_sha256": sha256_file(paths.scope_yaml),
        "tables_version": tables.version,
        "codeloop_version": __version__,
        "llm_calls": summary.llm_calls,
        "tokens_in": summary.tokens_in,
        "tokens_out": summary.tokens_out,
        "cache_hits": summary.cache_hits,
        "failures": summary.failures,
        "scrubber_rule_counts": summary.scrubber_rule_counts,
        "compliance_failed": summary.compliance_failed,
        "data_gaps": summary.data_gaps,
        "provider_queries": summary.provider_queries,
        "estimated_cost_usd": summary.estimated_cost_usd,
        "predictions": summary.predictions,
        "finished_at": utc_now(),
    }
    write_json(out_dir / "run.json", manifest)
    append_entry(
        paths.ledger,
        f"run {version} {batch}",
        {
            "run_id": run_id,
            "commit": commit,
            "seeds": seeds,
            "encounters": len(encounters),
            "llm_calls": summary.llm_calls,
            "tokens_in": summary.tokens_in,
            "tokens_out": summary.tokens_out,
            "cache_hits": summary.cache_hits,
            "failures": len(summary.failures),
            "scrubber_rule_counts": summary.scrubber_rule_counts,
            "compliance_failed": summary.compliance_failed,
            "predictions_sha256": {str(s): sha256_file(paths.root / p) for s, p in summary.predictions.items()},
            "models_yaml_sha256": llm.models_hash,
            "scope_sha256": manifest["scope_sha256"],
            "tables_version": tables.version,
            "estimated_cost_usd": summary.estimated_cost_usd,
        },
        actor=actor,
    )
    return summary
