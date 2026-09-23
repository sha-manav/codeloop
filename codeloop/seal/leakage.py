"""Holdout leakage scanner (spec §2.3, invariant I1).

Walks the working trees that may ever contain derived data and asserts that
(a) no holdout ID string appears in any file, and
(b) no string value in any JSON/JSONL record hashes to a holdout note or dialogue hash, and no
    `*sha256` field carries one.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Iterator
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codeloop.paths import Paths
from codeloop.util.hashing import sha256_text

SCAN_DIRS: tuple[str, ...] = (
    "data/dev",
    "data/labels_public",
    "data/labels",
    "evals",
    "runs",
    "findings",
    "tasks",
    "reports",
)
_SKIP_NAMES = {".gitkeep", ".DS_Store"}
_SKIP_DIRS = {"__pycache__", ".pytest_cache", ".git"}


@dataclass(frozen=True)
class Leak:
    path: str
    kind: str  # "id_string" | "content_hash" | "hash_field"
    detail: str

    def __str__(self) -> str:
        return f"{self.path}: {self.kind}: {self.detail}"


def load_holdout_ids(paths: Paths) -> list[str]:
    if not paths.holdout_ids.exists():
        return []
    return [ln.strip() for ln in paths.holdout_ids.read_text(encoding="utf-8").splitlines() if ln.strip()]


def load_holdout_hashes(paths: Paths) -> dict[str, dict[str, str]]:
    if not paths.holdout_content_hashes.exists():
        return {}
    with open(paths.holdout_content_hashes, encoding="utf-8") as fh:
        return json.load(fh)


def iter_strings(obj: Any) -> Iterator[str]:
    if isinstance(obj, str):
        yield obj
    elif isinstance(obj, dict):
        for v in obj.values():
            yield from iter_strings(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from iter_strings(v)


def iter_hash_fields(obj: Any) -> Iterator[tuple[str, str]]:
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(k, str) and k.lower().endswith("sha256") and isinstance(v, str):
                yield k, v
            else:
                yield from iter_hash_fields(v)
    elif isinstance(obj, (list, tuple)):
        for v in obj:
            yield from iter_hash_fields(v)


def _iter_records(path: Path) -> Iterator[Any]:
    if path.suffix == ".jsonl":
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        yield json.loads(line)
                    except json.JSONDecodeError:
                        continue
    elif path.suffix == ".json":
        try:
            with open(path, encoding="utf-8") as fh:
                yield json.load(fh)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return


# Spec section 15 step 4: `codeloop holdout score` exports the holdout labels and predictions in plaintext alongside
# the results, once, after writing data/sealed/SCORED.lock. Those files are the reveal, not a leak; they are exempt
# only while the lock exists.
_REVEAL_PATHS = ("runs/holdout/", "reports/holdout.json", "reports/holdout.md")


def _is_reveal(rel: str, root: Path) -> bool:
    return (root / "data" / "sealed" / "SCORED.lock").exists() and any(
        rel == r or rel.startswith(r) for r in _REVEAL_PATHS
    )


def _iter_files(root: Path, scan_dirs: Iterable[str]) -> Iterator[Path]:
    for rel in scan_dirs:
        base = root / rel
        if not base.exists():
            continue
        for p in sorted(base.rglob("*")):
            if not p.is_file() or p.name in _SKIP_NAMES:
                continue
            if any(part in _SKIP_DIRS for part in p.relative_to(root).parts):
                continue
            if _is_reveal(p.relative_to(root).as_posix(), root):
                continue
            yield p


def find_leaks(
    root: Path,
    *,
    ids: list[str] | None = None,
    hashes: dict[str, dict[str, str]] | None = None,
    scan_dirs: Iterable[str] = SCAN_DIRS,
) -> list[Leak]:
    paths = Paths(root)
    ids = load_holdout_ids(paths) if ids is None else ids
    hashes = load_holdout_hashes(paths) if hashes is None else hashes
    if not ids and not hashes:
        return []
    id_bytes = [(i, i.encode("utf-8")) for i in ids]
    hash_to_id = {h: eid for eid, hs in hashes.items() for h in hs.values()}
    leaks: list[Leak] = []
    for p in _iter_files(paths.root, scan_dirs):
        rel = p.relative_to(paths.root).as_posix()
        data = p.read_bytes()
        for eid, b in id_bytes:
            if b in data:
                leaks.append(Leak(rel, "id_string", f"holdout id {eid} appears in file"))
        if p.suffix in (".json", ".jsonl"):
            for n, rec in enumerate(_iter_records(p), start=1):
                for s in iter_strings(rec):
                    if len(s) >= 40 and sha256_text(s) in hash_to_id:
                        leaks.append(Leak(rel, "content_hash", f"record {n}: string value hashes to holdout content"))
                        break
                for key, val in iter_hash_fields(rec):
                    if val in hash_to_id:
                        leaks.append(Leak(rel, "hash_field", f"record {n}: field {key} carries a holdout content hash"))
                        break
    return leaks
