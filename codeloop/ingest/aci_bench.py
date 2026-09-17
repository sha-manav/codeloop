"""ACI-Bench challenge CSVs -> Encounter records (spec §2.2)."""

from __future__ import annotations

import csv
from collections import Counter, defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from codeloop.config import Source
from codeloop.schemas.encounter import DialogueParseStats, Encounter, build_encounter

REQUIRED_COLUMNS = {"dataset", "encounter_id", "dialogue", "note"}


class IngestError(RuntimeError):
    pass


@dataclass
class AciIngestStats:
    files: list[str] = field(default_factory=list)
    per_split: dict[str, int] = field(default_factory=dict)
    per_subset: dict[str, int] = field(default_factory=dict)
    per_split_subset: dict[str, dict[str, int]] = field(default_factory=dict)
    dialogue: DialogueParseStats = field(default_factory=DialogueParseStats)
    notes_with_trailing_ws: int = 0
    texts_with_cr: int = 0
    note_len_min: int = 0
    note_len_max: int = 0
    note_len_mean: float = 0.0

    def to_dict(self) -> dict:
        return {
            "files": self.files,
            "per_split": self.per_split,
            "per_subset": self.per_subset,
            "per_split_subset": self.per_split_subset,
            "dialogue": {
                "turns": self.dialogue.turns,
                "continuation_lines": self.dialogue.continuation_lines,
                "leading_untagged_lines": self.dialogue.leading_untagged_lines,
                "blank_lines": self.dialogue.blank_lines,
                "speakers": dict(sorted(self.dialogue.speakers.items())),
            },
            "notes_with_trailing_ws": self.notes_with_trailing_ws,
            "texts_with_cr": self.texts_with_cr,
            "note_len": {"min": self.note_len_min, "mean": round(self.note_len_mean), "max": self.note_len_max},
        }


def parse_challenge_csv(path: Path, split_orig: str) -> tuple[list[Encounter], AciIngestStats]:
    path = Path(path)
    stats = AciIngestStats(files=[path.name])
    encounters: list[Encounter] = []
    lengths: list[int] = []
    with open(path, newline="", encoding="utf-8-sig") as fh:
        reader = csv.DictReader(fh)
        missing = REQUIRED_COLUMNS - set(reader.fieldnames or [])
        if missing:
            raise IngestError(
                f"{path.name}: missing columns {sorted(missing)}; found {reader.fieldnames}"
            )
        for row in reader:
            raw_note = row["note"] or ""
            raw_dialogue = row["dialogue"] or ""
            if "\r" in raw_note or "\r" in raw_dialogue:
                stats.texts_with_cr += 1
            enc, dstats = build_encounter(
                id=(row["encounter_id"] or "").strip(),
                subset=(row["dataset"] or "").strip(),
                split_orig=split_orig,
                dialogue_raw=raw_dialogue,
                note_raw=raw_note,
            )
            if not enc.id:
                raise IngestError(f"{path.name}: row with empty encounter_id")
            encounters.append(enc)
            stats.dialogue.merge(dstats)
            if enc.note_text != enc.note_text.rstrip():
                stats.notes_with_trailing_ws += 1
            lengths.append(len(enc.note_text))
    stats.per_split = {split_orig: len(encounters)}
    subset_counts = Counter(e.subset for e in encounters)
    stats.per_subset = dict(sorted(subset_counts.items()))
    stats.per_split_subset = {split_orig: dict(sorted(subset_counts.items()))}
    if lengths:
        stats.note_len_min, stats.note_len_max = min(lengths), max(lengths)
        stats.note_len_mean = sum(lengths) / len(lengths)
    return encounters, stats


def merge_stats(parts: list[AciIngestStats], lengths_by_part: list[list[int]] | None = None) -> AciIngestStats:
    total = AciIngestStats()
    for p in parts:
        total.files.extend(p.files)
        for k, v in p.per_split.items():
            total.per_split[k] = total.per_split.get(k, 0) + v
        for k, v in p.per_subset.items():
            total.per_subset[k] = total.per_subset.get(k, 0) + v
        for k, v in p.per_split_subset.items():
            total.per_split_subset[k] = dict(v)
        total.dialogue.merge(p.dialogue)
        total.notes_with_trailing_ws += p.notes_with_trailing_ws
        total.texts_with_cr += p.texts_with_cr
    total.per_subset = dict(sorted(total.per_subset.items()))
    return total


def load_aci_bench(raw_dir: Path, source_id: str, source: Source) -> tuple[list[Encounter], AciIngestStats]:
    """Parse every configured member/file of the ACI-Bench source and validate the corpus."""
    sdir = Path(raw_dir) / source_id
    encounters: list[Encounter] = []
    parts: list[AciIngestStats] = []
    for f in source.files:
        if f.kind == "zip":
            for m in f.members:
                encs, st = parse_challenge_csv(sdir / Path(m.member).name, m.split_orig)
                encounters.extend(encs)
                parts.append(st)
        else:
            encs, st = parse_challenge_csv(sdir / f.name, f.split_orig or "unknown")
            encounters.extend(encs)
            parts.append(st)
    stats = merge_stats(parts)
    lengths = [len(e.note_text) for e in encounters]
    if lengths:
        stats.note_len_min, stats.note_len_max = min(lengths), max(lengths)
        stats.note_len_mean = sum(lengths) / len(lengths)
    dupes = [i for i, c in Counter(e.id for e in encounters).items() if c > 1]
    if dupes:
        raise IngestError(f"duplicate encounter ids in ACI-Bench download: {len(dupes)}")
    by_subset: dict[str, list[str]] = defaultdict(list)
    for e in encounters:
        by_subset[e.subset].append(e.id)
    return sorted(encounters, key=lambda e: e.id), stats
