"""Append-only ledger (ledger.md): UTC timestamp, event, hashes, actor.

Entries are Markdown sections so humans can read them and code can parse them back.
"""

from __future__ import annotations

import json
import os
import re
import subprocess
from collections.abc import Mapping
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

HEADER = "# CodeLoop ledger"
_ENTRY_RE = re.compile(r"^## (?P<ts>\S+) — (?P<event>.+)$")
_FIELD_RE = re.compile(r"^- (?P<key>[^:]+): (?P<value>.*)$")


def utc_now() -> str:
    return datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def resolve_actor(root: Path | None = None) -> str:
    env = os.environ.get("CODELOOP_ACTOR")
    if env:
        return env
    name = email = ""
    try:
        cwd = str(root) if root else None
        name = subprocess.run(
            ["git", "config", "user.name"], capture_output=True, text=True, cwd=cwd
        ).stdout.strip()
        email = subprocess.run(
            ["git", "config", "user.email"], capture_output=True, text=True, cwd=cwd
        ).stdout.strip()
    except OSError:
        pass
    if name and email:
        return f"{name} <{email}>"
    return name or email or os.environ.get("USER", "unknown")


def _fmt(value: Any) -> str:
    if isinstance(value, str):
        return value
    return json.dumps(value, ensure_ascii=False, sort_keys=True)


def append_entry(
    ledger_path: Path,
    event: str,
    fields: Mapping[str, Any],
    *,
    actor: str | None = None,
    ts: str | None = None,
) -> str:
    """Append one entry and return its text. Never rewrites existing content."""
    ledger_path = Path(ledger_path)
    ts = ts or utc_now()
    actor = actor or resolve_actor(ledger_path.parent)
    lines = [f"## {ts} — {event}", "", f"- actor: {actor}"]
    for key, value in fields.items():
        lines.append(f"- {key}: {_fmt(value)}")
    text = "\n".join(lines) + "\n"
    if not ledger_path.exists():
        ledger_path.write_text(HEADER + "\n", encoding="utf-8")
    with open(ledger_path, "a", encoding="utf-8", newline="\n") as fh:
        fh.write("\n" + text)
    return text


@dataclass
class LedgerEntry:
    ts: str
    event: str
    fields: dict[str, str] = field(default_factory=dict)

    def json_field(self, key: str) -> Any:
        return json.loads(self.fields[key])


def read_entries(ledger_path: Path) -> list[LedgerEntry]:
    entries: list[LedgerEntry] = []
    current: LedgerEntry | None = None
    for line in Path(ledger_path).read_text(encoding="utf-8").splitlines():
        m = _ENTRY_RE.match(line)
        if m:
            current = LedgerEntry(ts=m.group("ts"), event=m.group("event"))
            entries.append(current)
            continue
        f = _FIELD_RE.match(line)
        if f and current is not None:
            current.fields[f.group("key")] = f.group("value")
    return entries
