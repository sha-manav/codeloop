"""CodeLoop command-line interface. Commands are added phase by phase (spec Appendix A).

Console output is counts and hashes only: no encounter text is ever printed.
"""

from __future__ import annotations

import sys
from pathlib import Path

import typer

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
