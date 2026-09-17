"""Prompt files under prompts/: one per LLM call site, hashed into every trace.

Format: an optional `=== SYSTEM ===` section (stable instructions, cached by the provider) followed
by a `=== USER ===` section (per-encounter template). Placeholders are `{{name}}`; substituted values
are never re-scanned, so encounter text containing braces is safe.
"""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from codeloop.util.hashing import sha256_file, sha256_text

_PLACEHOLDER = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")
_SYSTEM_MARK = "=== SYSTEM ==="
_USER_MARK = "=== USER ==="


class PromptError(RuntimeError):
    pass


@dataclass(frozen=True)
class PromptTemplate:
    name: str
    path: str
    file_sha256: str
    system: str
    user: str

    def variables(self) -> set[str]:
        return set(_PLACEHOLDER.findall(self.system)) | set(_PLACEHOLDER.findall(self.user))

    def render(self, variables: Mapping[str, object]) -> tuple[str, str]:
        missing = self.variables() - set(variables)
        if missing:
            raise PromptError(f"prompt {self.name}: missing variables {sorted(missing)}")

        def sub(m: re.Match[str]) -> str:
            return str(variables[m.group(1)])

        return _PLACEHOLDER.sub(sub, self.system).strip(), _PLACEHOLDER.sub(sub, self.user).strip()


def parse_prompt_file(name: str, path: Path) -> PromptTemplate:
    text = path.read_text(encoding="utf-8")
    if _USER_MARK in text:
        head, _, user = text.partition(_USER_MARK)
        system = head.replace(_SYSTEM_MARK, "", 1)
    else:
        system, user = "", text
    if not user.strip():
        raise PromptError(f"prompt {name}: empty USER section")
    return PromptTemplate(
        name=name, path=str(path), file_sha256=sha256_file(path), system=system.strip(), user=user.strip()
    )


class PromptStore:
    def __init__(self, directory: Path):
        self.directory = Path(directory)
        self._cache: dict[str, PromptTemplate] = {}

    def load(self, name: str) -> PromptTemplate:
        path = self.directory / f"{name}.txt"
        if not path.is_file():
            raise PromptError(f"prompt file not found: {path}")
        current = sha256_file(path)
        cached = self._cache.get(name)
        if cached is None or cached.file_sha256 != current:
            cached = parse_prompt_file(name, path)
            self._cache[name] = cached
        return cached

    def hashes(self) -> dict[str, str]:
        """{prompt_name: file sha256} for every prompt file (recorded in traces and VERSION.md)."""
        return {p.stem: sha256_file(p) for p in sorted(self.directory.glob("*.txt"))}


def rendered_sha256(system: str, user: str) -> str:
    return sha256_text(system + "\x00" + user)
