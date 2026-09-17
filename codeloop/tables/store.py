"""Read-only query layer over data/tables/tables.sqlite used by tools, rules and the scrubber."""

from __future__ import annotations

import re
import sqlite3
import threading
from dataclasses import dataclass
from pathlib import Path

_STOP = {"the", "of", "and", "or", "with", "without", "in", "on", "to", "a", "an", "for", "due", "by", "at", "is", "as"}
_TOKEN = re.compile(r"[A-Za-z0-9]+")


@dataclass(frozen=True)
class IcdHit:
    code: str
    description: str
    valid: bool
    score: float


class Tables:
    """Thread-safe: one connection guarded by a lock (the pipeline runs encounters in threads)."""

    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.conn.row_factory = sqlite3.Row
        self._lock = threading.RLock()

    def _all(self, sql: str, params: tuple = ()) -> list[sqlite3.Row]:
        with self._lock:
            return self.conn.execute(sql, params).fetchall()

    def _one(self, sql: str, params: tuple = ()) -> sqlite3.Row | None:
        with self._lock:
            return self.conn.execute(sql, params).fetchone()

    # ---------------------------------------------------------------- meta
    def meta(self, key: str) -> str | None:
        row = self._one("SELECT value FROM meta WHERE key = ?", (key,))
        return row[0] if row else None

    @property
    def version(self) -> str:
        return f"tables.yaml:{(self.meta('tables_yaml_sha256') or '')[:16]}/parser:{self.meta('parser_version') or '?'}"

    def release(self, table: str) -> str:
        return self.meta(f"{table}.release") or "unknown"

    def count(self, table: str) -> int:
        return int(self._one(f"SELECT COUNT(*) FROM {table}")[0])  # noqa: S608 - fixed names

    # ---------------------------------------------------------------- ICD-10-CM
    def icd_exists(self, code: str) -> bool:
        return self._one("SELECT 1 FROM icd10cm WHERE code = ?", (code,)) is not None

    def icd_valid(self, code: str) -> bool:
        row = self._one("SELECT valid FROM icd10cm WHERE code = ?", (code,))
        return bool(row and row[0])

    def icd_description(self, code: str) -> str | None:
        row = self._one("SELECT long FROM icd10cm WHERE code = ?", (code,))
        return row[0] if row else None

    def icd_search(self, query: str, k: int = 10, *, valid_only: bool = False) -> list[IcdHit]:
        tokens = [t.lower() for t in _TOKEN.findall(query) if len(t) > 1 and t.lower() not in _STOP]
        if not tokens:
            return []
        match = " OR ".join(f'"{t}"' for t in dict.fromkeys(tokens))
        sql = (
            "SELECT f.code, c.long, c.valid, bm25(icd10cm_fts) AS score FROM icd10cm_fts f "
            "JOIN icd10cm c ON c.code = f.code WHERE icd10cm_fts MATCH ? "
            + ("AND c.valid = 1 " if valid_only else "")
            + "ORDER BY score LIMIT ?"
        )
        rows = self._all(sql, (match, k))
        return [IcdHit(code=r[0], description=r[1], valid=bool(r[2]), score=float(r[3])) for r in rows]

    def icd_children(self, code: str) -> list[tuple[str, str, bool]]:
        rows = self._all(
            "SELECT code, long, valid FROM icd10cm WHERE code LIKE ? AND length(code) = ? ORDER BY code",
            (code + "_", len(code) + 1),
        )
        return [(r[0], r[1], bool(r[2])) for r in rows]

    def icd_laterality_variants(self, code: str) -> list[tuple[str, str]]:
        """Sibling codes that differ only in the final character and mention a side."""
        if len(code) < 4:
            return []
        rows = self._all(
            "SELECT code, long FROM icd10cm WHERE code LIKE ? AND length(code) = ? AND valid = 1 ORDER BY code",
            (code[:-1] + "_", len(code)),
        )
        return [(r[0], r[1]) for r in rows if re.search(r"\b(right|left|bilateral|unspecified)\b", r[1], re.I)]

    # ---------------------------------------------------------------- line codes
    def hcpcs_exists(self, code: str) -> bool:
        return self._one("SELECT 1 FROM hcpcs WHERE code = ?", (code,)) is not None

    def rvu_exists(self, code: str) -> bool:
        return self._one("SELECT 1 FROM rvu WHERE code = ?", (code,)) is not None

    def line_code_exists(self, code: str) -> bool:
        """CPT codes are known only through the MPFS RVU file (no descriptors); HCPCS II through its file."""
        return self.hcpcs_exists(code) or self.rvu_exists(code)

    def hcpcs_modifier_known(self, modifier: str) -> bool:
        return self._one("SELECT 1 FROM hcpcs_modifiers WHERE modifier = ?", (modifier,)) is not None

    def bilateral_indicator(self, code: str) -> str | None:
        sql = "SELECT bilat FROM rvu WHERE code = ? AND (mod = '' OR mod IS NULL)"
        row = self._one(sql, (code,))
        if row is None:
            row = self._one("SELECT bilat FROM rvu WHERE code = ? ORDER BY mod LIMIT 1", (code,))
        return row[0] if row else None

    def global_days(self, code: str) -> str | None:
        row = self._one("SELECT glob FROM rvu WHERE code = ? ORDER BY mod LIMIT 1", (code,))
        return row[0] if row else None

    # ---------------------------------------------------------------- NCCI
    def ptp_edit(self, col1: str, col2: str, on_date: str) -> tuple[int, str] | None:
        """Active PTP edit for the ordered pair on YYYYMMDD `on_date`: (modifier indicator, rationale)."""
        rows = self._all(
            "SELECT effective, deletion, indicator, rationale FROM ptp WHERE col1 = ? AND col2 = ?", (col1, col2)
        )
        for eff, deletion, indicator, rationale in rows:
            if eff and eff > on_date:
                continue
            if deletion and deletion != "*" and deletion < on_date:
                continue
            return int(indicator), rationale
        return None

    def mue(self, code: str) -> tuple[int, str] | None:
        row = self._one("SELECT mue_value, mai FROM mue WHERE code = ?", (code,))
        return (int(row[0]), row[1]) if row else None

    # ---------------------------------------------------------------- products
    def drug_lookup(self, name: str, limit: int = 20) -> list[sqlite3.Row]:
        tokens = [t for t in _TOKEN.findall(name.lower()) if len(t) > 2][:3]
        if not tokens:
            return []
        where = " AND ".join("lower(drug_name) LIKE ?" for _ in tokens)
        return self._all(
            f"SELECT hcpcs, ndc, labeler, drug_name, dosage, billunits FROM asp_ndc WHERE {where} LIMIT ?",  # noqa: S608
            (*[f"%{t}%" for t in tokens], limit),
        )

    def cvx_lookup(self, name: str, limit: int = 10) -> list[sqlite3.Row]:
        tokens = [t for t in _TOKEN.findall(name.lower()) if len(t) > 2][:3]
        if not tokens:
            return []
        where = " AND ".join("(lower(short) LIKE ? OR lower(full) LIKE ?)" for _ in tokens)
        params: list[str | int] = []
        for t in tokens:
            params += [f"%{t}%", f"%{t}%"]
        params.append(limit)
        return self._all(f"SELECT cvx, short, full, status FROM cvx WHERE {where} LIMIT ?", params)  # noqa: S608

    def close(self) -> None:
        self.conn.close()


def open_tables(path: Path) -> Tables:
    if not Path(path).exists():
        raise FileNotFoundError(f"{path} missing; run `codeloop tables fetch` and `codeloop tables build`")
    conn = sqlite3.connect(f"file:{path}?mode=ro", uri=True, check_same_thread=False)
    return Tables(conn)
