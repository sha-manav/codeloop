"""Hashing helpers. Every hash in CodeLoop is a lowercase hex SHA-256 unless named otherwise."""

from __future__ import annotations

import hashlib
from collections.abc import Iterable
from pathlib import Path


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_text(text: str) -> str:
    return sha256_bytes(text.encode("utf-8"))


def _digest_file(path: Path, algo: str, chunk: int = 1 << 20) -> str:
    h = hashlib.new(algo)
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(chunk), b""):
            h.update(block)
    return h.hexdigest()


def sha256_file(path: Path) -> str:
    return _digest_file(Path(path), "sha256")


def md5_file(path: Path) -> str:
    return _digest_file(Path(path), "md5")


def tree_hash(
    root: Path,
    *,
    exclude_dirs: Iterable[str] = ("__pycache__", ".pytest_cache", ".ruff_cache"),
    exclude_suffixes: Iterable[str] = (".pyc",),
) -> str:
    """Deterministic hash of a directory tree: sorted relative paths and per-file SHA-256s.

    Used for the frozen scorer directory (invariant I3) and for freeze records.
    """
    root = Path(root)
    excluded = set(exclude_dirs)
    suffixes = tuple(exclude_suffixes)
    lines: list[str] = []
    for p in sorted(root.rglob("*")):
        if p.is_dir():
            continue
        rel = p.relative_to(root)
        if any(part in excluded for part in rel.parts) or p.suffix in suffixes:
            continue
        lines.append(f"{rel.as_posix()}\t{sha256_file(p)}")
    return sha256_text("\n".join(lines))
