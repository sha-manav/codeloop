"""Thin git helpers (subprocess). Every call is content-free."""

from __future__ import annotations

import subprocess
from pathlib import Path


class GitError(RuntimeError):
    pass


def _git(root: Path, *args: str, check: bool = True) -> str:
    proc = subprocess.run(["git", *args], cwd=str(root), capture_output=True, text=True)
    if check and proc.returncode != 0:
        raise GitError(f"git {' '.join(args)} failed: {proc.stderr.strip()}")
    return proc.stdout.strip()


def is_repo(root: Path) -> bool:
    try:
        return _git(root, "rev-parse", "--is-inside-work-tree") == "true"
    except GitError:
        return False


def current_commit(root: Path) -> str:
    return _git(root, "rev-parse", "HEAD")


def current_branch(root: Path) -> str:
    return _git(root, "rev-parse", "--abbrev-ref", "HEAD")


def is_clean(root: Path) -> bool:
    return _git(root, "status", "--porcelain") == ""


def dirty_paths(root: Path) -> list[str]:
    out = _git(root, "status", "--porcelain")
    return [line[3:] for line in out.splitlines() if line.strip()]


def tag_exists(root: Path, tag: str) -> bool:
    return _git(root, "tag", "-l", tag) == tag


def create_tag(root: Path, tag: str, message: str) -> None:
    _git(root, "tag", "-a", tag, "-m", message)


def describe_exact_tag(root: Path) -> str | None:
    try:
        return _git(root, "describe", "--tags", "--exact-match")
    except GitError:
        return None


def tags_at_head(root: Path) -> list[str]:
    out = _git(root, "tag", "--points-at", "HEAD")
    return [t for t in out.splitlines() if t]


def commit_all(root: Path, message: str) -> str:
    _git(root, "add", "-A")
    _git(root, "commit", "-q", "-m", message)
    return current_commit(root)


def tag_commit(root: Path, tag: str) -> str:
    return _git(root, "rev-list", "-n", "1", tag)


CODE_DIRS: tuple[str, ...] = ("codeloop", "prompts", "config")


def tree_id(root: Path, rev: str, path: str) -> str | None:
    try:
        return _git(root, "rev-parse", f"{rev}:{path}")
    except GitError:
        return None


def code_matches_tag(root: Path, tag: str, dirs: tuple[str, ...] = CODE_DIRS) -> bool:
    """True when HEAD's committed code directories are identical to the tag's (run outputs may differ)."""
    if not tag_exists(root, tag):
        return False
    return all(tree_id(root, "HEAD", d) == tree_id(root, tag, d) for d in dirs)


def rename_tag(root: Path, old: str, new_base: str) -> str:
    """Move tag `old` to `new_base` (or new_base-2, -3, … if taken) at the same commit; returns the new name."""
    if not tag_exists(root, old):
        raise GitError(f"tag {old!r} does not exist")
    new = new_base
    n = 1
    while tag_exists(root, new):
        n += 1
        new = f"{new_base}-{n}"
    commit = tag_commit(root, old)
    _git(root, "tag", "-a", new, commit, "-m", f"superseded {old}")
    _git(root, "tag", "-d", old)
    return new
