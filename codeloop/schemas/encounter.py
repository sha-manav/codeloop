"""Encounter and Turn: the ingest contract (spec §2.2).

Spans elsewhere in the system are character offsets into `note_text` or `dialogue_text`.
These strings are never re-normalized after ingest; the SHA-256 fields are the guard and are
re-verified every time an Encounter is loaded.
"""

from __future__ import annotations

import re
from collections.abc import Iterable
from dataclasses import dataclass, field
from typing import Literal

from pydantic import BaseModel, ConfigDict, model_validator

from codeloop.util.hashing import sha256_text

Subset = Literal["aci", "virtassist", "virtscribe"]
SUBSETS: tuple[str, ...] = ("aci", "virtassist", "virtscribe")

# A dialogue turn starts with an identifier-like speaker tag: "[doctor] ...", "[patient_guest] ...".
# Bracketed ASR annotations such as "[ inaudible 00:09:25 ]" are not speaker tags.
TURN_RE = re.compile(r"^\[([a-z][a-z0-9_]*)\]\s?(.*)$")
UNKNOWN_SPEAKER = "unknown"


class Turn(BaseModel):
    model_config = ConfigDict(frozen=True)
    speaker: str  # as given, e.g. "doctor", "patient"; swapped ASR tags are not corrected
    text: str


def normalize_newlines(s: str) -> str:
    """The only normalization applied to released text: BOM removal and '\\n'-only newlines."""
    if s.startswith("﻿"):
        s = s[1:]
    return s.replace("\r\n", "\n").replace("\r", "\n")


def flatten_dialogue(turns: Iterable[Turn]) -> str:
    """Canonical flattening from the spec: '\\n'.join(f'[{speaker}] {text}')."""
    return "\n".join(f"[{t.speaker}] {t.text}" for t in turns)


@dataclass
class DialogueParseStats:
    turns: int = 0
    continuation_lines: int = 0  # untagged lines appended to the previous turn
    leading_untagged_lines: int = 0  # untagged lines before any tag (speaker 'unknown')
    blank_lines: int = 0
    speakers: dict[str, int] = field(default_factory=dict)

    def merge(self, other: DialogueParseStats) -> None:
        self.turns += other.turns
        self.continuation_lines += other.continuation_lines
        self.leading_untagged_lines += other.leading_untagged_lines
        self.blank_lines += other.blank_lines
        for k, v in other.speakers.items():
            self.speakers[k] = self.speakers.get(k, 0) + v


def parse_dialogue(raw: str) -> tuple[list[Turn], DialogueParseStats]:
    """Split a released dialogue into turns.

    Rules: a line matching TURN_RE starts a turn; blank lines are dropped; any other line is a
    continuation of the current turn (joined with '\\n') so the released wording is preserved.
    """
    stats = DialogueParseStats()
    turns: list[Turn] = []
    speaker: str | None = None
    lines: list[str] = []

    def flush() -> None:
        if speaker is not None:
            turns.append(Turn(speaker=speaker, text="\n".join(lines)))

    for line in normalize_newlines(raw).split("\n"):
        if not line.strip():
            stats.blank_lines += 1
            continue
        m = TURN_RE.match(line)
        if m:
            flush()
            speaker, lines = m.group(1), [m.group(2)]
            stats.turns += 1
            stats.speakers[speaker] = stats.speakers.get(speaker, 0) + 1
        elif speaker is None:
            speaker, lines = UNKNOWN_SPEAKER, [line]
            stats.turns += 1
            stats.leading_untagged_lines += 1
            stats.speakers[speaker] = stats.speakers.get(speaker, 0) + 1
        else:
            lines.append(line)
            stats.continuation_lines += 1
    flush()
    return turns, stats


class Encounter(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    subset: Subset
    split_orig: str  # train/valid/test1/test2/test3 — provenance only
    dialogue: list[Turn]
    dialogue_text: str
    note_text: str
    dialogue_sha256: str
    note_sha256: str

    @model_validator(mode="after")
    def _verify_integrity(self) -> Encounter:
        if flatten_dialogue(self.dialogue) != self.dialogue_text:
            raise ValueError(f"{self.id}: dialogue_text is not the canonical flattening of dialogue")
        if sha256_text(self.dialogue_text) != self.dialogue_sha256:
            raise ValueError(f"{self.id}: dialogue_sha256 does not match dialogue_text")
        if sha256_text(self.note_text) != self.note_sha256:
            raise ValueError(f"{self.id}: note_sha256 does not match note_text")
        if "\r" in self.note_text or "\r" in self.dialogue_text:
            raise ValueError(f"{self.id}: text contains carriage returns; newlines must be '\\n'")
        return self


def build_encounter(
    *, id: str, subset: str, split_orig: str, dialogue_raw: str, note_raw: str
) -> tuple[Encounter, DialogueParseStats]:
    turns, stats = parse_dialogue(dialogue_raw)
    dialogue_text = flatten_dialogue(turns)
    note_text = normalize_newlines(note_raw)
    enc = Encounter(
        id=id,
        subset=subset,  # type: ignore[arg-type]
        split_orig=split_orig,
        dialogue=turns,
        dialogue_text=dialogue_text,
        note_text=note_text,
        dialogue_sha256=sha256_text(dialogue_text),
        note_sha256=sha256_text(note_text),
    )
    return enc, stats


def load_encounters_jsonl(path) -> list[Encounter]:
    """Load and re-verify every record (hash mismatch raises)."""
    out: list[Encounter] = []
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if line:
                out.append(Encounter.model_validate_json(line))
    return out
