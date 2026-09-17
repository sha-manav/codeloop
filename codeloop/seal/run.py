"""`codeloop seal` — Phase 0, run once (spec §2.3).

Everything is produced in a temporary staging directory and verified there (decrypt round-trip,
leakage scan) before any file is placed in the repository, so a failure leaves nothing behind.
"""

from __future__ import annotations

import platform
import shutil
import tempfile
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from codeloop import __version__
from codeloop.config import ProjectConfig
from codeloop.ingest.aci_bench import AciIngestStats
from codeloop.ingest.download import DownloadRecord
from codeloop.ingest.labels import AmazonCodeRow, MedCodERData
from codeloop.ingest.materialize import clear_raw, write_public_outputs
from codeloop.ingest.report import render_ingest_report, write_text
from codeloop.ledger import append_entry, utc_now
from codeloop.paths import Paths
from codeloop.schemas.encounter import Encounter
from codeloop.seal.crypto import (
    MIN_PASSPHRASE_LEN,
    SealKeyError,
    decrypt_from_file,
    encrypt_to_file,
    meta_path_for,
)
from codeloop.seal.draw import draw_holdout, holdout_allocation
from codeloop.seal.leakage import find_leaks
from codeloop.util.hashing import sha256_file, sha256_text
from codeloop.util.jsonl import dumps_record, write_json


class SealError(RuntimeError):
    pass


@dataclass
class SealInputs:
    encounters: list[Encounter]
    amazon_rows: list[AmazonCodeRow]
    medcoder: MedCodERData
    downloads: list[DownloadRecord]
    aci_stats: AciIngestStats


@dataclass
class SealResult:
    seed: int
    holdout_n: int
    allocation: dict[str, int]
    holdout_ids_sha256: str
    content_hashes_sha256: str
    enc_sha256: str
    dev_count: int
    amazon_count: int
    medcoder_count: int
    raw_entries_deleted: int
    ledger_entry: str
    files: list[str] = field(default_factory=list)


def _refuse_if_sealed(paths: Paths) -> None:
    for p in (paths.holdout_ids, paths.holdout_encounters_enc, paths.holdout_content_hashes):
        if p.exists():
            raise SealError(
                f"refusing to seal: {p.relative_to(paths.root)} already exists. "
                "The holdout is drawn exactly once; see ledger.md."
            )


def perform_seal(
    paths: Paths,
    config: ProjectConfig,
    inputs: SealInputs,
    *,
    passphrase: str,
    seed: int | None = None,
    actor: str | None = None,
    delete_raw: bool = True,
) -> SealResult:
    _refuse_if_sealed(paths)
    if len(passphrase) < MIN_PASSPHRASE_LEN:
        raise SealKeyError(f"seal key must be at least {MIN_PASSPHRASE_LEN} characters")
    seed = config.seal_seed if seed is None else int(seed)
    encs = inputs.encounters
    expected = config.expected_encounter_count
    if len(encs) != expected:
        raise SealError(f"expected {expected} encounters, got {len(encs)}; refusing to seal a partial corpus")
    ids = [e.id for e in encs]
    if len(set(ids)) != len(ids):
        raise SealError("duplicate encounter ids; refusing to seal")

    generated_at = utc_now()
    with tempfile.TemporaryDirectory(prefix="codeloop-seal-") as tmp:
        stage = Paths(Path(tmp))
        stage.ensure_layout()

        # 3. draw
        ids_by_subset: dict[str, list[str]] = defaultdict(list)
        for e in encs:
            ids_by_subset[e.subset].append(e.id)
        allocation = holdout_allocation({s: len(v) for s, v in ids_by_subset.items()}, config.holdout.n)
        holdout = draw_holdout(ids_by_subset, config.holdout.n, seed)
        hset = set(holdout)

        # 4. ID list + hash
        ids_text = "\n".join(holdout) + "\n"
        write_text(stage.holdout_ids, ids_text)
        ids_hash = sha256_text(ids_text)
        write_text(stage.holdout_ids_sha256, f"{ids_hash}  holdout_ids.txt\n")

        # 5. content hashes
        content_hashes = {
            e.id: {"note_sha256": e.note_sha256, "dialogue_sha256": e.dialogue_sha256}
            for e in encs
            if e.id in hset
        }
        write_json(stage.holdout_content_hashes, content_hashes)

        # 6. encrypt the 40 records
        holdout_encs = sorted((e for e in encs if e.id in hset), key=lambda e: e.id)
        plaintext = "".join(dumps_record(e) + "\n" for e in holdout_encs).encode("utf-8")
        encrypt_to_file(plaintext, stage.holdout_encounters_enc, passphrase, label="holdout_encounters")
        if decrypt_from_file(stage.holdout_encounters_enc, passphrase) != plaintext:
            raise SealError("decrypt round-trip failed in staging")

        # 7–8. dev encounters and filtered public labels
        outputs = write_public_outputs(stage, encs, hset, inputs.amazon_rows, inputs.medcoder)
        if outputs.dev_count != expected - config.holdout.n:
            raise SealError(f"dev count {outputs.dev_count} != {expected - config.holdout.n}")

        # report + manifest
        report = render_ingest_report(
            command="seal", generated_at=generated_at, config=config, downloads=inputs.downloads,
            aci_stats=inputs.aci_stats, amazon_stats=outputs.amazon_stats,
            medcoder_stats=outputs.medcoder_stats, holdout_ids=holdout, allocation=allocation, seed=seed,
        )
        write_text(stage.ingest_report, report)
        manifest = {
            "generated_at": generated_at,
            "command": "seal",
            "codeloop_version": __version__,
            "python": platform.python_version(),
            "sources": {
                sid: {"title": s.title, "license": s.license, "landing_url": s.landing_url,
                      "pinned_commit": s.pinned_commit, "citation": s.citation}
                for sid, s in config.sources.items()
            },
            "downloads": [d.to_dict() for d in inputs.downloads],
        }
        write_json(stage.source_manifest, manifest)

        # staged leakage scan with the freshly drawn ids/hashes
        leaks = find_leaks(stage.root, ids=holdout, hashes=content_hashes)
        if leaks:
            raise SealError("leakage scan failed in staging:\n" + "\n".join(str(x) for x in leaks[:20]))

        # move into place
        pairs = [
            (stage.holdout_ids, paths.holdout_ids),
            (stage.holdout_ids_sha256, paths.holdout_ids_sha256),
            (stage.holdout_content_hashes, paths.holdout_content_hashes),
            (stage.holdout_encounters_enc, paths.holdout_encounters_enc),
            (meta_path_for(stage.holdout_encounters_enc), meta_path_for(paths.holdout_encounters_enc)),
            (stage.dev_encounters, paths.dev_encounters),
            (stage.amazon_labels, paths.amazon_labels),
            (stage.medcoder_labels, paths.medcoder_labels),
            (stage.ingest_report, paths.ingest_report),
            (stage.source_manifest, paths.source_manifest),
        ]
        for src, dst in pairs:
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(src, dst)
        files = [dst.relative_to(paths.root).as_posix() for _, dst in pairs]

    # 9. delete raw downloads (all three contain holdout rows)
    deleted = clear_raw(paths) if delete_raw else 0

    # 10. ledger
    enc_hash = sha256_file(paths.holdout_encounters_enc)
    content_hashes_hash = sha256_file(paths.holdout_content_hashes)
    fields = {
        "spec_version": config.spec_version,
        "codeloop_version": __version__,
        "python": platform.python_version(),
        "seal_seed": seed,
        "holdout_n": config.holdout.n,
        "stratify_on": config.holdout.stratify_on,
        "subset_counts": {s: len(v) for s, v in sorted(ids_by_subset.items())},
        "allocation": dict(sorted(allocation.items())),
        "holdout_ids_sha256": ids_hash,
        "holdout_content_hashes_sha256": content_hashes_hash,
        "holdout_encounters_enc_sha256": enc_hash,
        "holdout_encounters_enc_meta_sha256": sha256_file(meta_path_for(paths.holdout_encounters_enc)),
        "dev_encounters_count": outputs.dev_count,
        "dev_encounters_sha256": sha256_file(paths.dev_encounters),
        "labels_public_amazon_count": outputs.amazon_count,
        "labels_public_amazon_sha256": sha256_file(paths.amazon_labels),
        "labels_public_medcoder_count": outputs.medcoder_count,
        "labels_public_medcoder_sha256": sha256_file(paths.medcoder_labels),
        "source_manifest_sha256": sha256_file(paths.source_manifest),
        "downloads": [
            {"source": d.source, "name": d.name, "url": d.url, "bytes": d.bytes, "sha256": d.sha256, "md5": d.md5}
            for d in inputs.downloads
        ],
        "raw_entries_deleted": deleted,
    }
    entry = append_entry(paths.ledger, "seal", fields, actor=actor)

    leaks = find_leaks(paths.root)
    if leaks:
        raise SealError("leakage scan failed after seal:\n" + "\n".join(str(x) for x in leaks[:20]))

    return SealResult(
        seed=seed, holdout_n=config.holdout.n, allocation=allocation, holdout_ids_sha256=ids_hash,
        content_hashes_sha256=content_hashes_hash, enc_sha256=enc_hash, dev_count=outputs.dev_count,
        amazon_count=outputs.amazon_count, medcoder_count=outputs.medcoder_count,
        raw_entries_deleted=deleted, ledger_entry=entry, files=files,
    )
