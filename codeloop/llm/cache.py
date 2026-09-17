"""SQLite cache for LLM completions, keyed on (model, params, rendered prompt hash, seed, schema)."""

from __future__ import annotations

import json
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from codeloop.ledger import utc_now
from codeloop.util.hashing import sha256_text

_SCHEMA = """
CREATE TABLE IF NOT EXISTS llm_cache (
    key TEXT PRIMARY KEY,
    model TEXT NOT NULL,
    params_json TEXT NOT NULL,
    prompt_sha256 TEXT NOT NULL,
    seed INTEGER,
    schema_name TEXT,
    response_json TEXT NOT NULL,
    created_at TEXT NOT NULL
);
"""


def cache_key(model: str, params: dict[str, Any], rendered_sha256: str, seed: int | None, schema_sha256: str) -> str:
    payload = json.dumps(
        {"model": model, "params": params, "prompt": rendered_sha256, "seed": seed, "schema": schema_sha256},
        sort_keys=True,
    )
    return sha256_text(payload)


@dataclass
class CacheRecord:
    key: str
    response: dict[str, Any]
    created_at: str


class LLMCache:
    def __init__(self, path: Path | None):
        """`path=None` gives an in-memory cache (tests). Thread-safe via a single lock."""
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path) if self.path else ":memory:", check_same_thread=False)
        self._conn.execute(_SCHEMA)
        self._conn.commit()
        self._lock = threading.Lock()
        self.hits = 0
        self.misses = 0

    def get(self, key: str) -> CacheRecord | None:
        with self._lock:
            row = self._conn.execute("SELECT response_json, created_at FROM llm_cache WHERE key = ?", (key,)).fetchone()
        if row is None:
            self.misses += 1
            return None
        self.hits += 1
        return CacheRecord(key=key, response=json.loads(row[0]), created_at=row[1])

    def put(
        self, key: str, *, model: str, params: dict[str, Any], prompt_sha256: str, seed: int | None,
        schema_name: str, response: dict[str, Any],
    ) -> None:
        with self._lock:
            self._conn.execute(
                "INSERT OR REPLACE INTO llm_cache VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                (key, model, json.dumps(params, sort_keys=True), prompt_sha256, seed, schema_name,
                 json.dumps(response, ensure_ascii=False, sort_keys=True), utc_now()),
            )
            self._conn.commit()

    def __len__(self) -> int:
        with self._lock:
            return int(self._conn.execute("SELECT COUNT(*) FROM llm_cache").fetchone()[0])

    def close(self) -> None:
        self._conn.close()
