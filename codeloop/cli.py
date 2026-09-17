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
    typer.echo(f"spot-check UI at http://127.0.0.1:{port}/ (reviewer {reviewer}); Ctrl-C to stop")
    uvicorn.run(ui, host="127.0.0.1", port=port, log_level="warning")


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
