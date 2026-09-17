"""`codeloop ingest` — rebuild data/dev and data/labels_public from upstream using the committed
holdout IDs. Never writes holdout content anywhere; verifies upstream has not drifted."""

from __future__ import annotations

import platform
import tempfile
from dataclasses import dataclass
from pathlib import Path

from codeloop import __version__
from codeloop.config import ProjectConfig
from codeloop.ingest.materialize import clear_raw, write_public_outputs
from codeloop.ingest.report import render_ingest_report, write_text
from codeloop.ledger import append_entry, utc_now
from codeloop.paths import Paths
from codeloop.seal.draw import holdout_allocation
from codeloop.seal.leakage import find_leaks, load_holdout_hashes, load_holdout_ids
from codeloop.seal.run import SealInputs
from codeloop.util.hashing import sha256_file
from codeloop.util.jsonl import read_json


class IngestError(RuntimeError):
    pass


@dataclass
class IngestResult:
    dev_count: int
    amazon_count: int
    medcoder_count: int
    upstream_drift: list[str]
    changed_outputs: list[str]
    ledger_entry: str


def _drift(paths: Paths, downloads) -> list[str]:
    if not paths.source_manifest.exists():
        return ["source_manifest.json missing (cannot compare with the sealed downloads)"]
    manifest = read_json(paths.source_manifest)
    sealed = {d["url"]: d["sha256"] for d in manifest.get("downloads", [])}
    drift = []
    for d in downloads:
        if d.url not in sealed:
            drift.append(f"{d.source}/{d.name}: not in sealed manifest")
        elif sealed[d.url] != d.sha256:
            drift.append(f"{d.source}/{d.name}: sha256 differs from the sealed download")
    return drift


def perform_ingest(
    paths: Paths,
    config: ProjectConfig,
    inputs: SealInputs,
    *,
    actor: str | None = None,
    allow_upstream_drift: bool = False,
    delete_raw: bool = True,
) -> IngestResult:
    holdout = load_holdout_ids(paths)
    hashes = load_holdout_hashes(paths)
    if not holdout or not hashes:
        raise IngestError("no sealed holdout found; run `codeloop seal` first (Phase 0)")
    hset = set(holdout)
    encs = inputs.encounters
    if len(encs) != config.expected_encounter_count:
        raise IngestError(f"expected {config.expected_encounter_count} encounters, got {len(encs)}")
    by_id = {e.id: e for e in encs}
    missing = sum(1 for i in holdout if i not in by_id)
    mismatched = sum(
        1
        for i in holdout
        if i in by_id
        and (
            by_id[i].note_sha256 != hashes[i]["note_sha256"]
            or by_id[i].dialogue_sha256 != hashes[i]["dialogue_sha256"]
        )
    )
    if missing or mismatched:
        raise IngestError(
            f"holdout content check failed: {missing} holdout encounter(s) missing upstream, "
            f"{mismatched} with changed content. Upstream data drifted; do not proceed."
        )
    drift = _drift(paths, inputs.downloads)
    if drift and not allow_upstream_drift:
        raise IngestError(
            "upstream drift detected (pass --allow-upstream-drift to record and continue):\n" + "\n".join(drift)
        )

    before = {p: (sha256_file(p) if p.exists() else None) for p in (paths.amazon_labels, paths.medcoder_labels)}
    generated_at = utc_now()
    with tempfile.TemporaryDirectory(prefix="codeloop-ingest-") as tmp:
        stage = Paths(Path(tmp))
        stage.ensure_layout()
        outputs = write_public_outputs(stage, encs, hset, inputs.amazon_rows, inputs.medcoder)
        counts = {}
        for e in encs:
            counts[e.subset] = counts.get(e.subset, 0) + 1
        allocation = holdout_allocation(counts, config.holdout.n)
        report = render_ingest_report(
            command="ingest", generated_at=generated_at, config=config, downloads=inputs.downloads,
            aci_stats=inputs.aci_stats, amazon_stats=outputs.amazon_stats,
            medcoder_stats=outputs.medcoder_stats, holdout_ids=holdout, allocation=allocation,
            seed=config.seal_seed,
        )
        write_text(stage.ingest_report, report)
        leaks = find_leaks(stage.root, ids=holdout, hashes=hashes)
        if leaks:
            raise IngestError("leakage scan failed in staging:\n" + "\n".join(str(x) for x in leaks[:20]))
        for src, dst in (
            (stage.dev_encounters, paths.dev_encounters),
            (stage.amazon_labels, paths.amazon_labels),
            (stage.medcoder_labels, paths.medcoder_labels),
            (stage.ingest_report, paths.ingest_report),
        ):
            dst.parent.mkdir(parents=True, exist_ok=True)
            dst.write_bytes(src.read_bytes())

    changed = [p.relative_to(paths.root).as_posix() for p, h in before.items() if h != sha256_file(p)]
    deleted = clear_raw(paths) if delete_raw else 0
    entry = append_entry(
        paths.ledger,
        "ingest",
        {
            "codeloop_version": __version__,
            "python": platform.python_version(),
            "holdout_content_check": "ok",
            "upstream_drift": drift or "none",
            "dev_encounters_count": outputs.dev_count,
            "dev_encounters_sha256": sha256_file(paths.dev_encounters),
            "labels_public_amazon_sha256": sha256_file(paths.amazon_labels),
            "labels_public_medcoder_sha256": sha256_file(paths.medcoder_labels),
            "changed_committed_outputs": changed or "none",
            "downloads": [
                {"source": d.source, "name": d.name, "url": d.url, "sha256": d.sha256} for d in inputs.downloads
            ],
            "raw_entries_deleted": deleted,
        },
        actor=actor,
    )
    leaks = find_leaks(paths.root)
    if leaks:
        raise IngestError("leakage scan failed after ingest:\n" + "\n".join(str(x) for x in leaks[:20]))
    return IngestResult(outputs.dev_count, outputs.amazon_count, outputs.medcoder_count, drift, changed, entry)
