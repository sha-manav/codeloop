"""Shared output step for `seal` and `ingest`: dev encounters + filtered public labels."""

from __future__ import annotations

import shutil
from dataclasses import dataclass

from codeloop.ingest.labels import (
    AmazonCodeRow,
    CrosswalkStats,
    MedCodERData,
    crosswalk_amazon,
    crosswalk_medcoder,
)
from codeloop.paths import Paths
from codeloop.schemas.encounter import Encounter
from codeloop.util.jsonl import write_jsonl


@dataclass
class PublicOutputs:
    dev_count: int
    amazon_count: int
    medcoder_count: int
    amazon_stats: CrosswalkStats
    medcoder_stats: CrosswalkStats


def write_public_outputs(
    paths: Paths,
    encounters: list[Encounter],
    holdout_ids: set[str],
    amazon_rows: list[AmazonCodeRow],
    medcoder: MedCodERData,
) -> PublicOutputs:
    dev = sorted((e for e in encounters if e.id not in holdout_ids), key=lambda e: e.id)
    dev_count = write_jsonl(paths.dev_encounters, dev)
    amazon_records, amazon_stats = crosswalk_amazon(amazon_rows, encounters)
    medcoder_records, medcoder_stats = crosswalk_medcoder(medcoder, encounters)
    amazon_count = write_jsonl(
        paths.amazon_labels, [r for r in amazon_records if r["encounter_id"] not in holdout_ids]
    )
    medcoder_count = write_jsonl(
        paths.medcoder_labels, [r for r in medcoder_records if r["encounter_id"] not in holdout_ids]
    )
    return PublicOutputs(dev_count, amazon_count, medcoder_count, amazon_stats, medcoder_stats)


def clear_raw(paths: Paths) -> int:
    """Delete everything under data/raw except .gitkeep. Returns the number of entries removed."""
    n = 0
    if not paths.raw.exists():
        return 0
    for child in paths.raw.iterdir():
        if child.name == ".gitkeep":
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()
        n += 1
    return n
