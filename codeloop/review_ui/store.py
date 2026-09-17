"""Append-only SQLite event store for the review UI (spec §10.2) plus a JSONL export for git."""

from __future__ import annotations

import json
import sqlite3
import threading
from pathlib import Path

from codeloop.schemas.event import Event

_SCHEMA = """
CREATE TABLE IF NOT EXISTS events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ts TEXT NOT NULL, coder_id TEXT NOT NULL, encounter_id TEXT NOT NULL, batch TEXT NOT NULL,
    version TEXT NOT NULL,
    mode TEXT NOT NULL, type TEXT NOT NULL, field_ref TEXT, before TEXT, after TEXT, reason TEXT, span_id TEXT,
    grade TEXT
);
CREATE INDEX IF NOT EXISTS idx_events_enc ON events(encounter_id, id);
"""


class EventStore:
    def __init__(self, path: Path | None):
        self.path = Path(path) if path else None
        if self.path:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(str(self.path) if self.path else ":memory:", check_same_thread=False)
        self._conn.executescript(_SCHEMA)
        self._lock = threading.Lock()

    def append(self, event: Event) -> int:
        with self._lock:
            cur = self._conn.execute(
                "INSERT INTO events (ts, coder_id, encounter_id, batch, version, mode, type, field_ref, before, after,"
                " reason, span_id, grade) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
                (
                    event.ts, event.coder_id, event.encounter_id, event.batch, event.version, event.mode, event.type,
                    event.field_ref, json.dumps(event.before, sort_keys=True) if event.before is not None else None,
                    json.dumps(event.after, sort_keys=True) if event.after is not None else None, event.reason,
                    event.span_id, event.grade,
                ),
            )
            self._conn.commit()
            return int(cur.lastrowid)

    def _rows(self, where: str = "", params: tuple = ()) -> list[tuple[int, Event]]:
        with self._lock:
            rows = self._conn.execute(f"SELECT * FROM events {where} ORDER BY id", params).fetchall()  # noqa: S608
        out = []
        for r in rows:
            (rid, ts, coder, enc, batch, version, mode, typ, ref, before, after, reason, span_id, grade) = r
            event = Event(
                ts=ts, coder_id=coder, encounter_id=enc, batch=batch, version=version, mode=mode, type=typ,
                field_ref=ref, before=json.loads(before) if before else None,
                after=json.loads(after) if after else None, reason=reason, span_id=span_id, grade=grade,
            )
            out.append((rid, event))
        return out

    def for_encounter(self, encounter_id: str) -> list[Event]:
        return [e for _, e in self._rows("WHERE encounter_id = ?", (encounter_id,))]

    def all(self) -> list[tuple[int, Event]]:
        return self._rows()

    def export_jsonl(self, path: Path) -> int:
        path.parent.mkdir(parents=True, exist_ok=True)
        n = 0
        with open(path, "w", encoding="utf-8", newline="\n") as fh:
            for rid, e in self.all():
                record = {"id": rid, **e.model_dump(mode="json")}
                fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")
                n += 1
        return n

    @classmethod
    def from_jsonl(cls, path: Path) -> EventStore:
        store = cls(None)
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    d = json.loads(line)
                    d.pop("id", None)
                    store.append(Event.model_validate(d))
        return store

    def close(self) -> None:
        self._conn.close()
