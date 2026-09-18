"""CodeLoop command-line interface. Commands are added phase by phase (spec Appendix A).

Console output is counts and hashes only: no encounter text is ever printed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer
from pydantic import BaseModel

from codeloop import __version__
from codeloop.config import load_project_config
from codeloop.paths import Paths, find_root

app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    help="CodeLoop: outpatient professional-coding agent + self-improvement harness.",
)


def _paths(root: Path | None) -> Paths:
    return Paths(root or find_root())


def _fail(msg: str, code: int = 1) -> None:
    typer.secho(f"error: {msg}", err=True, fg=typer.colors.RED)
    raise typer.Exit(code)


@app.callback(invoke_without_command=True)
def _root(
    ctx: typer.Context,
    version: bool = typer.Option(False, "--version", help="print the version and exit"),
) -> None:
    if version:
        typer.echo(f"codeloop {__version__}")
        raise typer.Exit()
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())


@app.command()
def seal(
    root: Path | None = typer.Option(None, help="repository root (default: auto-detect)"),
    seed: int | None = typer.Option(None, help="override seal_seed from config/project.yaml (D0)"),
    keep_raw: bool = typer.Option(False, "--keep-raw", help="do not delete data/raw (tests only)"),
) -> None:
    """Phase 0, once: download, draw the 40-encounter holdout, encrypt it, write dev + public labels."""
    from codeloop.ingest.aci_bench import IngestError, load_aci_bench
    from codeloop.ingest.download import DownloadError, download_all
    from codeloop.ingest.labels import LabelIngestError, load_amazon, load_medcoder
    from codeloop.seal.crypto import SealKeyError, passphrase_from_env
    from codeloop.seal.run import SealError, SealInputs, perform_seal

    paths = _paths(root)
    config = load_project_config(paths.project_yaml)
    if paths.holdout_ids.exists():
        _fail(f"{paths.holdout_ids.relative_to(paths.root)} exists; the holdout is drawn once (see ledger.md)")
    try:
        passphrase = passphrase_from_env()
    except SealKeyError as e:
        _fail(str(e))
    paths.ensure_layout()
    try:
        typer.echo("downloading pinned sources into data/raw/ ...")
        downloads = download_all(config, paths.raw, paths.root)
        for d in downloads:
            typer.echo(f"  {d.source}/{d.name}: {d.bytes} bytes sha256={d.sha256[:16]}…")
        encounters, aci_stats = load_aci_bench(paths.raw, "aci_bench", config.sources["aci_bench"])
        amazon_rows = load_amazon(paths.raw, "amazon_labels", config.sources["amazon_labels"])
        medcoder = load_medcoder(paths.raw, "medcoder", config.sources["medcoder"])
        typer.echo(
            f"parsed {len(encounters)} encounters {aci_stats.per_subset}; "
            f"amazon rows={len(amazon_rows)}; medcoder docs={len(medcoder.docs)} "
            f"dx={len(medcoder.diagnoses)} evidence={len(medcoder.evidence)}"
        )
        result = perform_seal(
            paths, config,
            SealInputs(encounters, amazon_rows, medcoder, downloads, aci_stats),
            passphrase=passphrase, seed=seed, delete_raw=not keep_raw,
        )
    except (DownloadError, IngestError, LabelIngestError, SealError, SealKeyError) as e:
        _fail(str(e))
    typer.secho("sealed.", fg=typer.colors.GREEN)
    typer.echo(f"  seed={result.seed} holdout_n={result.holdout_n} allocation={result.allocation}")
    typer.echo(f"  holdout_ids sha256={result.holdout_ids_sha256}")
    typer.echo(f"  content hashes sha256={result.content_hashes_sha256}")
    typer.echo(f"  encrypted holdout sha256={result.enc_sha256}")
    typer.echo(
        f"  dev encounters={result.dev_count}; labels_public amazon={result.amazon_count} "
        f"medcoder={result.medcoder_count}; raw entries deleted={result.raw_entries_deleted}"
    )
    typer.echo("  ledger entry appended; leakage scan passed")


@app.command()
def ingest(
    root: Path | None = typer.Option(None, help="repository root (default: auto-detect)"),
    allow_upstream_drift: bool = typer.Option(False, help="continue if upstream files changed"),
    keep_raw: bool = typer.Option(False, "--keep-raw", help="do not delete data/raw (tests only)"),
) -> None:
    """Rebuild data/dev and data/labels_public from upstream using the committed holdout IDs."""
    from codeloop.ingest.aci_bench import IngestError, load_aci_bench
    from codeloop.ingest.download import DownloadError, download_all
    from codeloop.ingest.labels import LabelIngestError, load_amazon, load_medcoder
    from codeloop.ingest.run import IngestError as IngestRunError
    from codeloop.ingest.run import perform_ingest
    from codeloop.seal.run import SealInputs

    paths = _paths(root)
    config = load_project_config(paths.project_yaml)
    if not paths.holdout_ids.exists():
        _fail("no sealed holdout; run `codeloop seal` first")
    paths.ensure_layout()
    try:
        typer.echo("downloading pinned sources into data/raw/ ...")
        downloads = download_all(config, paths.raw, paths.root)
        encounters, aci_stats = load_aci_bench(paths.raw, "aci_bench", config.sources["aci_bench"])
        amazon_rows = load_amazon(paths.raw, "amazon_labels", config.sources["amazon_labels"])
        medcoder = load_medcoder(paths.raw, "medcoder", config.sources["medcoder"])
        result = perform_ingest(
            paths, config,
            SealInputs(encounters, amazon_rows, medcoder, downloads, aci_stats),
            allow_upstream_drift=allow_upstream_drift, delete_raw=not keep_raw,
        )
    except (DownloadError, IngestError, LabelIngestError, IngestRunError) as e:
        _fail(str(e))
    typer.secho("ingest complete.", fg=typer.colors.GREEN)
    typer.echo(f"  dev encounters={result.dev_count}; amazon={result.amazon_count}; medcoder={result.medcoder_count}")
    typer.echo(
        f"  upstream drift: {result.upstream_drift or 'none'}; "
        f"changed committed outputs: {result.changed_outputs or 'none'}"
    )


@app.command()
def score(
    gold: Path = typer.Option(..., help="gold JSONL (label records or packages)"),
    pred: Path = typer.Option(..., help="prediction JSONL (CodingPackage records)"),
    scope: Path | None = typer.Option(None, help="scope.yaml (default: config/scope.yaml)"),
    out: Path | None = typer.Option(None, help="write the full ScoreReport JSON here"),
    root: Path | None = typer.Option(None, help="repository root"),
) -> None:
    """Score predictions against gold with the canonicalizer and field-level agreement (spec §5)."""
    from codeloop.scoring import Scope, score_files
    from codeloop.util.hashing import sha256_file

    paths = _paths(root)
    scope_path = scope or paths.scope_yaml
    try:
        report = score_files(gold, pred, Scope.load(scope_path), scope_sha256=sha256_file(scope_path))
    except (ValueError, OSError) as e:
        _fail(str(e))
    b = report.batch
    typer.echo(f"scoring {report.scoring_version}; scope {scope_path} sha256={report.scope_sha256[:16]}…")
    typer.echo(
        f"encounters={b.n} fields={b.total_fields} correct={b.total_correct} "
        f"no_in_scope_fields={b.no_in_scope_fields}"
    )
    typer.echo(f"mean agreement={b.mean_agreement:.4f} hierarchical={b.mean_hier_agreement:.4f}")
    for name, t in b.tiers.items():
        typer.echo(f"  {name}: {t.count}/{t.n} = {t.share:.3f} (wilson {t.wilson_low:.3f}–{t.wilson_high:.3f})")
    for t, v in b.per_type.items():
        cells = ", ".join(f"{k}={val:.3f}" if isinstance(val, float) else f"{k}={val}" for k, val in v.items())
        typer.echo(f"  {t}: {cells}")
    if report.missing_pred:
        typer.echo(f"  gold encounters without a prediction (scored as empty): {len(report.missing_pred)}")
    if report.unscored_pred:
        typer.echo(f"  predictions without gold (ignored): {len(report.unscored_pred)}")
    if out:
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(report.model_dump_json(indent=2), encoding="utf-8")
        typer.echo(f"wrote {out}")


class _Ping(BaseModel):
    ok: bool
    echo: str


def _require_provider(client) -> None:
    """One tiny live request (bypassing the cache) so missing credentials fail before any work starts."""
    from codeloop.llm.providers import LLMProviderError

    try:
        resp = client.provider.generate(
            "You are a connectivity check. Reply with the structured result only.",
            'Set ok to true and echo the word "codeloop".', _Ping, client.config.params_for("ping"),
        )
    except (LLMProviderError, Exception) as e:  # noqa: BLE001 - the SDK raises its own class when no credentials resolve
        _fail(
            f"LLM provider unavailable: {type(e).__name__}: {e}\n"
            "Set ANTHROPIC_API_KEY in the shell (or log in with `ant auth login`) and retry."
        )
    if resp.stop_reason == "refusal" or not resp.parsed:
        _fail(f"LLM connectivity check did not return a structured result (stop_reason={resp.stop_reason})")


audit_app = typer.Typer(no_args_is_help=True, help="Phase 2 prevalence audit over the dev encounters.")
app.add_typer(audit_app, name="audit")


def _dev_encounters(paths: Paths):
    from codeloop.schemas.encounter import load_encounters_jsonl

    if not paths.dev_encounters.exists():
        _fail("data/dev/encounters.jsonl missing; run `make data`")
    return load_encounters_jsonl(paths.dev_encounters)


@audit_app.command("run")
def audit_run(
    root: Path | None = typer.Option(None, help="repository root"),
    limit: int | None = typer.Option(None, help="audit only the first N dev encounters (by id)"),
    concurrency: int = typer.Option(4, help="parallel LLM calls"),
    seed: int = typer.Option(1, help="requested seed (cache-key discriminator)"),
    no_cache: bool = typer.Option(False, "--no-cache", help="bypass the LLM cache"),
) -> None:
    """One structured LLM call per dev encounter flagging candidate services (never the holdout)."""
    from codeloop.audit.run import run_audit
    from codeloop.ledger import append_entry
    from codeloop.llm.client import build_client

    paths = _paths(root)
    encounters = _dev_encounters(paths)
    holdout = set(paths.holdout_ids.read_text().split()) if paths.holdout_ids.exists() else set()
    if any(e.id in holdout for e in encounters):
        _fail("dev encounters contain holdout ids; refusing")
    if limit:
        encounters = encounters[:limit]
    client = build_client(paths.root, cache_enabled=not no_cache)
    _require_provider(client)
    typer.echo(
        f"auditing {len(encounters)} dev encounters with {client.config.default.model} (concurrency {concurrency}) ..."
    )
    summary = run_audit(paths, client, encounters, seed=seed, concurrency=concurrency)
    pricing = client.config.pricing.get(summary.model)
    cost = (
        pricing.cost(summary.tokens_in, summary.tokens_out, summary.cache_read_tokens, summary.cache_creation_tokens)
        if pricing
        else None
    )
    typer.echo(
        f"audited {summary.n_encounters} encounters, {summary.n_flags} flags {summary.per_category_flags}; "
        f"tokens in/out {summary.tokens_in}/{summary.tokens_out} (cache read {summary.cache_read_tokens}); "
        f"cache hits {summary.cache_hits}; validation retries {summary.validation_retries}; "
        f"failures {len(summary.failures)}"
        + (f"; est. cost ${cost:.2f}" if cost is not None else "")
    )
    for f in summary.failures[:20]:
        typer.echo(f"  failure: {f}", err=True)
    append_entry(
        paths.ledger, "audit run",
        {"run_id": summary.run_id, "model": summary.model, "prompt_hash": summary.prompt_hash,
         "models_yaml_sha256": client.models_hash, "encounters": summary.n_encounters, "flags": summary.n_flags,
         "per_category_flags": summary.per_category_flags, "tokens_in": summary.tokens_in,
         "tokens_out": summary.tokens_out, "cache_hits": summary.cache_hits, "failures": len(summary.failures),
         "estimated_cost_usd": round(cost, 2) if cost is not None else None},
    )
    if summary.failures:
        raise typer.Exit(1)


@audit_app.command("sample")
def audit_sample(
    n: int = typer.Option(30, help="sample size: half flagged, half random"),
    root: Path | None = typer.Option(None, help="repository root"),
) -> None:
    """Draw the CPC spot-check sample (seeded; recorded in the ledger)."""
    from codeloop.audit.sample import write_spot_check_sample
    from codeloop.ledger import append_entry

    paths = _paths(root)
    config = load_project_config(paths.project_yaml)
    seed = int(config.seeds.get("audit_sample_seed", config.seal_seed))
    try:
        sample = write_spot_check_sample(paths, n=n, seed=seed)
    except (RuntimeError, ValueError) as e:
        _fail(str(e))
    typer.echo(
        f"drew {len(sample['arms']['flagged'])} flagged + {len(sample['arms']['random'])} random encounters "
        f"(seed {seed}) -> runs/audit/spot_check_sample.json"
    )
    append_entry(paths.ledger, "audit sample", {"seed": seed, "n": n, "population": sample["population"],
                 "population_flagged": sample["population_flagged"], "encounter_ids": sample["arms"]})


@audit_app.command("report")
def audit_report(root: Path | None = typer.Option(None, help="repository root")) -> None:
    """Write reports/audit.md with per-category precision, evaluable_n_est and D10 module decisions."""
    from codeloop.audit.report import write_report

    paths = _paths(root)
    config = load_project_config(paths.project_yaml)
    try:
        write_report(paths, config)
    except RuntimeError as e:
        _fail(str(e))
    typer.echo("wrote reports/audit.md, runs/audit/flag_counts.json, runs/audit/module_decisions.json")


@audit_app.command("serve")
def audit_serve(
    reviewer: str = typer.Option(..., help="reviewer id recorded on every response (e.g. cpc1)"),
    port: int = typer.Option(8765, help="port"),
    root: Path | None = typer.Option(None, help="repository root"),
) -> None:
    """Serve the spot-check page for the CPC at http://127.0.0.1:<port>/ ."""
    import uvicorn

    from codeloop.audit.ui import create_app

    paths = _paths(root)
    try:
        ui = create_app(paths, reviewer)
    except RuntimeError as e:
        _fail(str(e))
    typer.echo(f"spot-check UI at http://127.0.0.1:{port}/ (reviewer {reviewer}; basic auth {'on' if ui.state.auth else 'off'}); Ctrl-C to stop")
    uvicorn.run(ui, host="127.0.0.1", port=port, log_level="warning")


@app.command()
def freeze(
    root: Path | None = typer.Option(None, help="repository root"),
    supersede: bool = typer.Option(False, "--supersede", help="retire the existing freeze (tag -> freeze-provisional, ledger correction) and freeze afresh"),
    reason: str = typer.Option("superseded by the owner", help="recorded in the ledger correction entry"),
) -> None:
    """Phase 3: validate scope and decisions, compute the difficulty index, write the dev split, lock
    decisions, record hashes, commit and tag `freeze`."""
    from codeloop.versioning.freeze import FreezeError, perform_freeze
    from codeloop.versioning.git import GitError

    paths = _paths(root)
    try:
        result = perform_freeze(paths, supersede=supersede, reason=reason)
    except (FreezeError, GitError) as e:
        _fail(str(e))
    typer.secho(f"frozen at {result.commit[:12]} (tag {result.tag})", fg=typer.colors.GREEN)
    if supersede:
        typer.echo("  previous freeze kept as tag freeze-provisional; push with: git push --force origin --tags")
    typer.echo(f"  scoring tree sha256={result.scoring_tree_sha256}")
    typer.echo(f"  config tree sha256={result.config_tree_sha256}; splits tree sha256={result.splits_tree_sha256}")
    for name, s in result.summary.items():
        typer.echo(f"  {name}: n={s['n']} mean difficulty={s['mean_difficulty']:.3f} subsets={s['subsets']}")


tables_app = typer.Typer(no_args_is_help=True, help="Pinned external tables (ICD-10-CM, HCPCS, NCCI, MPFS, ASP, CVX).")
app.add_typer(tables_app, name="tables")


@tables_app.command("fetch")
def tables_fetch(
    root: Path | None = typer.Option(None, help="repository root"),
    only: list[str] = typer.Option([], help="fetch only these table names"),
    update: bool = typer.Option(False, help="re-pin hashes when upstream files changed"),
) -> None:
    """Download every pinned file into data/tables/raw/ and record sha256/bytes/date in config/tables.yaml."""
    from codeloop.tables.fetch import TableFetchError, fetch_tables

    paths = _paths(root)
    try:
        records = fetch_tables(paths.root, paths.tables_yaml, only=set(only) or None, update=update)
    except TableFetchError as e:
        _fail(str(e))
    for r in records:
        typer.echo(f"  {r.table}/{r.name}: {r.bytes} bytes sha256={r.sha256[:16]}… {r.status}")
    typer.echo(f"{len(records)} files; config/tables.yaml updated")


@tables_app.command("build")
def tables_build(root: Path | None = typer.Option(None, help="repository root")) -> None:
    """Parse the fetched files into data/tables/tables.sqlite (FTS5 index over ICD-10-CM)."""
    from codeloop.ledger import append_entry
    from codeloop.tables.build import build_tables
    from codeloop.util.hashing import sha256_file

    paths = _paths(root)
    try:
        stats = build_tables(paths.root, paths.tables_yaml, paths.tables_sqlite)
    except FileNotFoundError as e:
        _fail(str(e))
    typer.echo(f"built {paths.tables_sqlite.relative_to(paths.root)}: {stats.counts}")
    append_entry(
        paths.ledger, "tables build",
        {"tables_yaml_sha256": sha256_file(paths.tables_yaml), "row_counts": stats.counts,
         "tables_sqlite_sha256": sha256_file(paths.tables_sqlite)},
    )


@app.command()
def run(
    version: str = typer.Option(..., help="vK (checked out at that tag) or dev (seed/spare only)"),
    batch: str = typer.Option(..., help="seed | batch1 | batch2 | batch3 | spare"),
    limit: int | None = typer.Option(None, help="run only the first N encounters of the batch"),
    seeds: str = typer.Option("1", help="comma-separated requested seeds, e.g. 1,2,3"),
    concurrency: int = typer.Option(4, help="parallel encounters"),
    no_cache: bool = typer.Option(False, "--no-cache", help="bypass the LLM cache"),
    root: Path | None = typer.Option(None, help="repository root"),
) -> None:
    """Run the agent pipeline over a batch; writes runs/<version>/<batch>/predictions.jsonl and traces."""
    from codeloop.agent.runner import RunError, check_version_state, run_batch
    from codeloop.llm.client import build_client
    from codeloop.tables import open_tables

    paths = _paths(root)
    config = load_project_config(paths.project_yaml)
    try:
        commit = check_version_state(paths, version, batch)
        tables = open_tables(paths.tables_sqlite)
    except (RunError, FileNotFoundError) as e:
        _fail(str(e))
    seed_list = [int(x) for x in seeds.split(",") if x.strip()]
    client = build_client(paths.root, cache_enabled=not no_cache)
    _require_provider(client)
    typer.echo(f"running {version} on {batch} (seeds {seed_list}, concurrency {concurrency}) ...")
    try:
        s = run_batch(paths, config, version=version, batch=batch, llm=client, tables=tables, seeds=seed_list,
                      limit=limit, concurrency=concurrency, commit=commit)
    except RunError as e:
        _fail(str(e))
    typer.echo(
        f"run {s.run_id}: {s.n_encounters} encounters x {len(s.seeds)} seed(s); llm calls {s.llm_calls} "
        f"(cache hits {s.cache_hits}); tokens in/out {s.tokens_in}/{s.tokens_out}; failures {len(s.failures)}"
        + (f"; est. cost ${s.estimated_cost_usd:.2f}" if s.estimated_cost_usd is not None else "")
    )
    typer.echo(f"  scrubber rule counts {s.scrubber_rule_counts}; compliance failed {s.compliance_failed}; "
               f"data gaps {s.data_gaps}; provider queries {s.provider_queries}")
    for p in s.predictions.values():
        typer.echo(f"  predictions: {p}")
    for f in s.failures[:20]:
        typer.echo(f"  failure: {f}", err=True)
    if s.failures:
        raise typer.Exit(1)


@app.command()
def calibration(
    version: str = typer.Option(..., help="run version, e.g. dev or v0"),
    batch: str = typer.Option(..., help="batch name"),
    root: Path | None = typer.Option(None, help="repository root"),
) -> None:
    """Compare a run's diagnoses with the public ICD label sets (reference only) -> reports/calibration_<v>_<b>.md."""
    from codeloop.agent.runner import predictions_path
    from codeloop.ingest.report import write_text
    from codeloop.reporting.calibration import calibration_report

    paths = _paths(root)
    pred = predictions_path(paths, version, batch)
    if not pred.exists():
        _fail(f"{pred.relative_to(paths.root)} missing; run `codeloop run` first")
    text = calibration_report(paths, pred, title=f"{version} on {batch}")
    out = paths.reports / f"calibration_{version}_{batch}.md"
    write_text(out, text)
    typer.echo(f"wrote {out.relative_to(paths.root)}")
    typer.echo("\n".join(line for line in text.splitlines() if line.startswith("- ") or line.startswith("## ")))


review_app_cli = typer.Typer(no_args_is_help=True, help="Coder review UI (review / blind / holdout-labeling modes).")
app.add_typer(review_app_cli, name="review")


@review_app_cli.command("serve")
def review_serve(
    coder_id: str = typer.Option(..., help="coder id recorded on every event"),
    batch: str | None = typer.Option(None, help="batch name (review mode)"),
    version: str | None = typer.Option(None, help="version whose draft is reviewed (review mode)"),
    holdout_labeling: bool = typer.Option(False, "--holdout-labeling", help="blind-label the sealed holdout (Phase 9)"),
    port: int = typer.Option(8766, help="port"),
    root: Path | None = typer.Option(None, help="repository root"),
) -> None:
    """Serve the review UI at http://127.0.0.1:<port>/ for one coder."""
    import uvicorn

    from codeloop.review_ui.app import ReviewSession, create_review_app
    from codeloop.seal.crypto import SealKeyError, passphrase_from_env

    paths = _paths(root)
    try:
        if holdout_labeling:
            session = ReviewSession(paths, batch="holdout", version="holdout", coder_id=coder_id, holdout_labeling=True,
                                    passphrase=passphrase_from_env())
        else:
            if not batch or not version:
                _fail("--batch and --version are required in review mode")
            session = ReviewSession(paths, batch=batch, version=version, coder_id=coder_id)
    except (SealKeyError, RuntimeError) as e:
        _fail(str(e))
    what = "holdout labeling" if holdout_labeling else f"{version}/{batch}"
    ui = create_review_app(session)
    typer.echo(f"review UI at http://127.0.0.1:{port}/ (coder {coder_id}, {what}; basic auth {'on' if ui.state.auth else 'off'}); Ctrl-C to stop")
    uvicorn.run(ui, host="127.0.0.1", port=port, log_level="warning")


labels_app = typer.Typer(no_args_is_help=True, help="CPC labels from review events.")
app.add_typer(labels_app, name="labels")


@labels_app.command("build")
def labels_build(
    batch: str = typer.Option(..., help="batch name"),
    version: str = typer.Option(..., help="version whose review events to replay"),
    root: Path | None = typer.Option(None, help="repository root"),
) -> None:
    """Replay review events into data/labels/<batch>.jsonl (approved encounters only)."""
    from codeloop.review_ui.labels import LabelsError, build_labels

    paths = _paths(root)
    try:
        r = build_labels(paths, batch=batch, version=version)
    except LabelsError as e:
        _fail(str(e))
    typer.echo(f"wrote {r.labels_path} ({r.approved} approved; pending {len(r.pending)}); events -> {r.events_path}")


eval_app = typer.Typer(no_args_is_help=True, help="Eval harness (targeted and regression suites).")
app.add_typer(eval_app, name="eval")


@eval_app.command("run")
def eval_run(
    suite: Path = typer.Option(..., help="suite yaml"),
    runs: int | None = typer.Option(None, help="number of runs (default: suite.runs, D4 = 3)"),
    seeds: str | None = typer.Option(None, help="comma-separated seeds (default: suite seeds)"),
    limit: int | None = typer.Option(None, help="first N encounters only"),
    concurrency: int = typer.Option(4),
    root: Path | None = typer.Option(None, help="repository root"),
) -> None:
    """Run a suite at the current working tree; results -> evals/results/<suite>/<commit>.json + .md."""
    from codeloop.evals.runner import run_suite
    from codeloop.llm.client import build_client
    from codeloop.tables import open_tables

    paths = _paths(root)
    config = load_project_config(paths.project_yaml)
    client = build_client(paths.root)
    _require_provider(client)
    seed_list = [int(x) for x in seeds.split(",")] if seeds else None
    try:
        r = run_suite(paths, config, suite, llm=client, tables=open_tables(paths.tables_sqlite), runs=runs, seeds=seed_list,
                      limit=limit, concurrency=concurrency)
    except (RuntimeError, FileNotFoundError) as e:
        _fail(str(e))
    typer.echo(f"{r.suite} @ {r.commit[:12]}: n={r.n_encounters} seeds={r.seeds} mean={r.mean} variance={r.variance}")
    for m in r.runs:
        if m.failures:
            typer.echo(f"  seed {m.seed}: {len(m.failures)} failures", err=True)


findings_app = typer.Typer(no_args_is_help=True, help="Findings: extract from coder corrections; package into evals + tasks.")
app.add_typer(findings_app, name="findings")


@findings_app.command("extract")
def findings_extract(batch: str = typer.Option(...), root: Path | None = typer.Option(None)) -> None:
    """Group edit/add/remove events (reason != judgment) into candidate findings (D3 thresholds)."""
    from codeloop.findings.extract import extract_findings
    from codeloop.ledger import append_entry

    paths = _paths(root)
    config = load_project_config(paths.project_yaml)
    try:
        out = extract_findings(paths, config, batch=batch)
    except RuntimeError as e:
        _fail(str(e))
    for f in out:
        typer.echo(f"  {f.id} [{f.status}] count={f.count} key={f.grouping_key}")
    append_entry(paths.ledger, f"findings extract {batch}", {"findings": [(f.id, f.status, f.count) for f in out]})
    typer.echo(f"{len(out)} finding(s) written/updated under findings/")


@findings_app.command("package")
def findings_package(finding: str = typer.Argument(...), root: Path | None = typer.Option(None)) -> None:
    """Create the targeted dataset, targeted + regression suites and the task folder for a finding."""
    from codeloop.findings.package import package_finding
    from codeloop.ledger import append_entry

    paths = _paths(root)
    config = load_project_config(paths.project_yaml)
    try:
        out = package_finding(paths, config, finding)
    except RuntimeError as e:
        _fail(str(e))
    append_entry(paths.ledger, f"findings package {finding}", out)
    for k, v in out.items():
        typer.echo(f"  {k}: {v}")


@findings_app.command("cluster")
def findings_cluster(batch: str = typer.Option(...), root: Path | None = typer.Option(None)) -> None:
    """Optional LLM pass proposing merges/splits of the batch's candidate findings -> findings/proposals/<batch>.md."""
    from codeloop.findings.cluster import cluster_findings
    from codeloop.ledger import append_entry
    from codeloop.llm.client import build_client
    from codeloop.review_ui.store import EventStore
    from codeloop.util.jsonl import read_jsonl

    paths = _paths(root)
    labels = read_jsonl(paths.labels_file(batch)) if paths.labels_file(batch).exists() else []
    if not labels:
        _fail(f"no labels for {batch}")
    store = EventStore.from_jsonl(paths.review_dir(labels[0]["version_reviewed"], batch) / "events.jsonl")
    client = build_client(paths.root)
    _require_provider(client)
    out = cluster_findings(paths, client, batch=batch, store=store)
    append_entry(paths.ledger, f"findings cluster {batch}", {"proposal": out.relative_to(paths.root).as_posix(), "model": client.config.default.model})
    typer.echo(f"wrote {out.relative_to(paths.root)} (a proposal; apply at triage)")


export_app = typer.Typer(no_args_is_help=True, help="Exports.")
app.add_typer(export_app, name="export")


@export_app.command("labels")
def export_labels(release: bool = typer.Option(False, "--release", help="required"), root: Path | None = typer.Option(None)) -> None:
    """Write the ACI-Bench-Claims file (codes and evidence offsets only) after a license check."""
    from codeloop.ledger import append_entry
    from codeloop.reporting.export import ExportError, export_release
    from codeloop.util.hashing import sha256_file

    if not release:
        _fail("pass --release to write the export")
    paths = _paths(root)
    config = load_project_config(paths.project_yaml)
    try:
        out, n = export_release(paths, config)
    except ExportError as e:
        _fail(str(e))
    append_entry(paths.ledger, "export labels --release", {"records": n, "sha256": sha256_file(out)})
    typer.echo(f"wrote {out.relative_to(paths.root)} ({n} records)")


gate_app = typer.Typer(no_args_is_help=True, help="Merge gate (D5).")
app.add_typer(gate_app, name="gate")


@gate_app.command("check")
def gate_check_cmd(
    task: Path = typer.Option(..., help="tasks/FIND-…"),
    base: str = typer.Option(..., help="base commit"),
    head: str = typer.Option(..., help="head commit (must be checked out)"),
    runs: int | None = typer.Option(None),
    seeds: str | None = typer.Option(None),
    concurrency: int = typer.Option(4),
    root: Path | None = typer.Option(None),
) -> None:
    """Run targeted + regression suites at HEAD, compare with the base version's stored outputs, write GATE.md."""
    from codeloop.gate.check import gate_check
    from codeloop.llm.client import build_client
    from codeloop.tables import open_tables

    paths = _paths(root)
    config = load_project_config(paths.project_yaml)
    client = build_client(paths.root)
    _require_provider(client)
    seed_list = [int(x) for x in seeds.split(",")] if seeds else None
    try:
        r = gate_check(paths, config, task_dir=task, base=base, head=head, llm=client, tables=open_tables(paths.tables_sqlite),
                       runs=runs, seeds=seed_list, concurrency=concurrency)
    except (RuntimeError, FileNotFoundError) as e:
        _fail(str(e))
    for c in r.checks:
        typer.echo(f"  {'pass' if c.passed else 'FAIL'} {c.name}: {c.detail}")
    typer.secho(f"GATE {'PASS' if r.passed else 'FAIL'}{' (route to human)' if r.route_to_human else ''} -> {task}/GATE.md",
                fg=typer.colors.GREEN if r.passed else typer.colors.RED)
    if not r.passed:
        raise typer.Exit(1)


version_app = typer.Typer(no_args_is_help=True, help="Version freezes (VERSION.md, tag, sealed holdout predictions).")
app.add_typer(version_app, name="version")


@version_app.command("freeze")
def version_freeze(
    version: str = typer.Argument(..., help="v0, v1, …"),
    concurrency: int = typer.Option(4),
    skip_holdout: bool = typer.Option(False, "--skip-holdout", help="do not run the sealed holdout prediction (tests only)"),
    supersede: bool = typer.Option(False, "--supersede", help="retire the existing vK (tag -> vK-provisional, artefacts renamed, ledger correction) and freeze afresh"),
    reason: str = typer.Option("superseded by the owner", help="recorded in the ledger correction entry"),
    root: Path | None = typer.Option(None),
) -> None:
    """Freeze vK on a clean main: VERSION.md, tag, then sealed holdout predictions (D7)."""
    from codeloop.holdout.sealed import SealedPredictError, sealed_predict
    from codeloop.llm.client import build_client
    from codeloop.seal.crypto import SealKeyError, passphrase_from_env
    from codeloop.tables import open_tables
    from codeloop.versioning.versions import VersionError, freeze_version

    paths = _paths(root)
    config = load_project_config(paths.project_yaml)
    try:
        passphrase = None if skip_holdout else passphrase_from_env()
        tables = None if skip_holdout else open_tables(paths.tables_sqlite)
    except (SealKeyError, FileNotFoundError) as e:
        _fail(str(e))

    def do_predict(v: str) -> str | None:
        if skip_holdout:
            return None
        client = build_client(paths.root, cache_enabled=False)
        _require_provider(client)
        return sealed_predict(paths, config, v, llm=client, tables=tables, passphrase=passphrase, concurrency=concurrency)

    try:
        r = freeze_version(paths, version, sealed_predict=do_predict, supersede=supersede, reason=reason)
    except (VersionError, SealedPredictError) as e:
        _fail(str(e))
    typer.secho(f"{version} frozen at {r.tag_commit[:12]}; sealed predictions sha256={r.sealed_predictions_sha256}", fg=typer.colors.GREEN)
    if supersede:
        typer.echo(f"  previous {version} kept as tag {version}-provisional; push with: git push --force origin --tags")


holdout_app = typer.Typer(no_args_is_help=True, help="Holdout protocol (spec §15).")
app.add_typer(holdout_app, name="holdout")


@holdout_app.command("predict")
def holdout_predict(
    version: str = typer.Option(...), sealed: bool = typer.Option(False, "--sealed", help="required"),
    concurrency: int = typer.Option(4), root: Path | None = typer.Option(None),
) -> None:
    """Sealed prediction for a frozen version (normally run by `version freeze`)."""
    from codeloop.holdout.sealed import SealedPredictError, sealed_predict
    from codeloop.llm.client import build_client
    from codeloop.seal.crypto import SealKeyError, passphrase_from_env
    from codeloop.tables import open_tables

    if not sealed:
        _fail("holdout predictions are only produced sealed (--sealed)")
    paths = _paths(root)
    config = load_project_config(paths.project_yaml)
    try:
        client = build_client(paths.root, cache_enabled=False)
        _require_provider(client)
        digest = sealed_predict(paths, config, version, llm=client, tables=open_tables(paths.tables_sqlite),
                                passphrase=passphrase_from_env(), concurrency=concurrency)
    except (SealKeyError, SealedPredictError, FileNotFoundError) as e:
        _fail(str(e))
    typer.echo(f"sealed predictions written; sha256={digest}")


@holdout_app.command("verify-scorer")
def holdout_verify_scorer(root: Path | None = typer.Option(None)) -> None:
    """Confirm codeloop/scoring hashes to the freeze hash and record it again."""
    from codeloop.holdout.score import HoldoutError, verify_scorer

    paths = _paths(root)
    try:
        h = verify_scorer(paths)
    except HoldoutError as e:
        _fail(str(e))
    typer.secho(f"scorer verified: {h}", fg=typer.colors.GREEN)


@holdout_app.command("score")
def holdout_score_cmd(root: Path | None = typer.Option(None)) -> None:
    """Reveal and score the holdout exactly once (writes data/sealed/SCORED.lock)."""
    from codeloop.holdout.score import HoldoutError, holdout_score
    from codeloop.seal.crypto import SealKeyError, passphrase_from_env

    paths = _paths(root)
    config = load_project_config(paths.project_yaml)
    try:
        r = holdout_score(paths, config, passphrase=passphrase_from_env())
    except (HoldoutError, SealKeyError) as e:
        _fail(str(e))
    typer.secho(f"holdout scored: {[(v, round(pv['mean_agreement'], 4)) for v, pv in r['per_version'].items()]} -> reports/holdout.md", fg=typer.colors.GREEN)


@app.command()
def report(root: Path | None = typer.Option(None)) -> None:
    """Regenerate reports/ (curve, version × batch table, anchoring, findings log, index)."""
    from codeloop.reporting.report import build_reports

    paths = _paths(root)
    summary = build_reports(paths)
    typer.echo(f"reports regenerated: {len(summary['cells'])} version×batch cells; see reports/index.md")


ledger_app = typer.Typer(no_args_is_help=True, help="Append-only ledger.")
app.add_typer(ledger_app, name="ledger")


@ledger_app.command("note")
def ledger_note(text: str = typer.Argument(..., help="free-text note"), root: Path | None = typer.Option(None)) -> None:
    """Append a free-text entry to ledger.md (timestamp and actor are recorded)."""
    from codeloop.ledger import append_entry

    paths = _paths(root)
    append_entry(paths.ledger, "note", {"text": text})
    typer.echo("ledger entry appended")


@app.command()
def serve(root: Path | None = typer.Option(None, help="repository root")) -> None:
    """Container entrypoint: audit or review UI from env vars (CODELOOP_UI_MODE, CODELOOP_BATCH, CODELOOP_VERSION,
    CODELOOP_CODER_ID, CODELOOP_DATA_DIR, CODELOOP_UI_USER/PASS); binds 0.0.0.0:$PORT (8080); basic auth on every route."""
    from codeloop.review_ui.serve import ServeConfigError
    from codeloop.review_ui.serve import main as serve_main

    paths = _paths(root)
    try:
        serve_main(paths.root)
    except (ServeConfigError, RuntimeError) as e:
        _fail(str(e))


llm_app = typer.Typer(no_args_is_help=True, help="LLM client utilities.")
app.add_typer(llm_app, name="llm")


@llm_app.command("ping")
def llm_ping(root: Path | None = typer.Option(None, help="repository root")) -> None:
    """Send one tiny structured request with the pinned model to verify credentials and settings."""
    from codeloop.llm.client import LLMError, build_client
    from codeloop.llm.providers import LLMProviderError

    paths = _paths(root)
    client = build_client(paths.root, cache_enabled=False)
    try:
        c = client.complete("ping", {"word": "codeloop"}, _Ping, seed=0)
    except (LLMError, LLMProviderError) as e:
        _fail(str(e))
    t = c.trace
    typer.echo(
        f"ok={c.parsed.ok} echo={c.parsed.echo!r} model={t.served_model} "
        f"tokens in/out={t.tokens_in}/{t.tokens_out} latency={t.latency_ms}ms stop={t.stop_reason}"
    )


@app.command("check-leakage")
def check_leakage(root: Path | None = typer.Option(None, help="repository root")) -> None:
    """Scan derived-data trees for holdout IDs or holdout content hashes (invariant I1)."""
    from codeloop.seal.leakage import find_leaks, load_holdout_ids

    paths = _paths(root)
    if not load_holdout_ids(paths):
        typer.echo("no holdout sealed yet; nothing to check")
        return
    leaks = find_leaks(paths.root)
    if leaks:
        for leak in leaks:
            typer.echo(str(leak), err=True)
        _fail(f"{len(leaks)} leak(s) found")
    typer.secho("no holdout leakage found", fg=typer.colors.GREEN)


@app.command("render-decisions")
def render_decisions_cmd(root: Path | None = typer.Option(None, help="repository root")) -> None:
    """Re-render DECISIONS.md from config/project.yaml."""
    from codeloop.decisions import render_decisions

    paths = _paths(root)
    config = load_project_config(paths.project_yaml)
    paths.decisions_md.write_text(render_decisions(config), encoding="utf-8", newline="\n")
    typer.echo(f"wrote {paths.decisions_md.relative_to(paths.root)}")


def main() -> None:
    try:
        app()
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    main()
