"""`codeloop tables build`: parse the fetched files into data/tables/tables.sqlite."""

from __future__ import annotations

import sqlite3
from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass, field
from pathlib import Path

from codeloop.ledger import utc_now
from codeloop.tables import parsers
from codeloop.tables.config import load_tables_config
from codeloop.tables.fetch import member_path

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta(key TEXT PRIMARY KEY, value TEXT);
CREATE TABLE IF NOT EXISTS icd10cm(code TEXT PRIMARY KEY, valid INTEGER NOT NULL, short TEXT, long TEXT);
CREATE VIRTUAL TABLE IF NOT EXISTS icd10cm_fts USING fts5(code UNINDEXED, text);
CREATE TABLE IF NOT EXISTS icd10cm_index(term TEXT NOT NULL, code TEXT NOT NULL);
CREATE INDEX IF NOT EXISTS idx_icd_index_code ON icd10cm_index(code);
CREATE TABLE IF NOT EXISTS hcpcs(code TEXT PRIMARY KEY, short TEXT, long TEXT, termination TEXT, action TEXT);
CREATE TABLE IF NOT EXISTS hcpcs_modifiers(modifier TEXT PRIMARY KEY, short TEXT, long TEXT);
CREATE TABLE IF NOT EXISTS ptp(
    col1 TEXT NOT NULL, col2 TEXT NOT NULL, effective TEXT, deletion TEXT, indicator INTEGER, rationale TEXT);
CREATE INDEX IF NOT EXISTS idx_ptp ON ptp(col1, col2);
CREATE TABLE IF NOT EXISTS mue(code TEXT PRIMARY KEY, mue_value INTEGER, mai TEXT, rationale TEXT);
CREATE TABLE IF NOT EXISTS rvu(
    code TEXT NOT NULL, mod TEXT NOT NULL, status TEXT, glob TEXT, bilat TEXT, PRIMARY KEY(code, mod));
CREATE TABLE IF NOT EXISTS asp_ndc(
    hcpcs TEXT, ndc TEXT, labeler TEXT, drug_name TEXT, dosage TEXT, pkg_size REAL, pkg_qty REAL, billunits REAL,
    billunits_pkg REAL);
CREATE INDEX IF NOT EXISTS idx_asp_name ON asp_ndc(drug_name);
CREATE TABLE IF NOT EXISTS cvx(cvx TEXT PRIMARY KEY, short TEXT, full TEXT, status TEXT, nonvaccine INTEGER);
"""


@dataclass
class BuildSources:
    icd10cm: Iterable[tuple[str, bool, str, str]] = ()
    icd10cm_index: Iterable[tuple[str, str]] = ()
    hcpcs: Iterable[tuple[str, str, str, str, str, str]] = ()
    ptp: Iterable[tuple[str, str, str, str, int, str]] = ()
    mue: Iterable[tuple[str, int, str, str]] = ()
    rvu: Iterable[tuple[str, str, str, str, str]] = ()
    asp: Iterable[tuple] = ()
    cvx: Iterable[tuple[str, str, str, str, bool]] = ()
    meta: dict[str, str] = field(default_factory=dict)


@dataclass
class BuildStats:
    counts: dict[str, int] = field(default_factory=dict)


def build_sqlite(conn: sqlite3.Connection, sources: BuildSources) -> BuildStats:
    conn.executescript(SCHEMA)
    stats = BuildStats()
    cur = conn.cursor()
    # index terms first so the FTS text can include them
    terms: dict[str, list[str]] = defaultdict(list)
    n = 0
    for term, code in sources.icd10cm_index:
        cur.execute("INSERT INTO icd10cm_index VALUES (?, ?)", (term, code))
        terms[code].append(term)
        n += 1
    stats.counts["icd10cm_index"] = n
    n = 0
    for code, valid, short, long in sources.icd10cm:
        cur.execute("INSERT OR REPLACE INTO icd10cm VALUES (?, ?, ?, ?)", (code, int(valid), short, long))
        text = " ".join([long, short, *terms.get(code, [])[:25]])
        cur.execute("INSERT INTO icd10cm_fts VALUES (?, ?)", (code, text))
        n += 1
    stats.counts["icd10cm"] = n
    n = m = 0
    for code, modifier, long, short, term, action in sources.hcpcs:
        if code:
            cur.execute("INSERT OR REPLACE INTO hcpcs VALUES (?, ?, ?, ?, ?)", (code, short, long, term, action))
            n += 1
        else:
            cur.execute("INSERT OR REPLACE INTO hcpcs_modifiers VALUES (?, ?, ?)", (modifier, short, long))
            m += 1
    stats.counts["hcpcs"], stats.counts["hcpcs_modifiers"] = n, m
    n = 0
    cur.executemany("INSERT INTO ptp VALUES (?, ?, ?, ?, ?, ?)", _count(sources.ptp, stats, "ptp"))
    cur.executemany("INSERT OR REPLACE INTO mue VALUES (?, ?, ?, ?)", _count(sources.mue, stats, "mue"))
    cur.executemany("INSERT OR REPLACE INTO rvu VALUES (?, ?, ?, ?, ?)", _count(sources.rvu, stats, "rvu"))
    cur.executemany("INSERT INTO asp_ndc VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", _count(sources.asp, stats, "asp_ndc"))
    cur.executemany(
        "INSERT OR REPLACE INTO cvx VALUES (?, ?, ?, ?, ?)",
        ((c, s, f, st, int(nv)) for c, s, f, st, nv in _count(sources.cvx, stats, "cvx")),
    )
    for k, v in {"built_at": utc_now(), **sources.meta}.items():
        cur.execute("INSERT OR REPLACE INTO meta VALUES (?, ?)", (k, v))
    conn.commit()
    return stats


def _count(rows: Iterable, stats: BuildStats, key: str):
    n = 0
    for r in rows:
        n += 1
        yield r
    stats.counts[key] = n


def sources_from_raw(root: Path, tables_yaml: Path) -> BuildSources:
    cfg = load_tables_config(tables_yaml)
    t = cfg.tables

    def member(table: str, idx: int = 0, file_idx: int = 0) -> Path:
        spec = t[table]
        f = spec.files[file_idx]
        p = member_path(root, table, f.members[idx]) if f.members else root / "data" / "tables" / "raw" / table / f.name
        if not p.exists():
            raise FileNotFoundError(f"{p} missing; run `codeloop tables fetch`")
        return p

    def chain_ptp():
        for i in range(len(t["ncci_ptp_practitioner"].files)):
            yield from parsers.parse_ncci_ptp(member("ncci_ptp_practitioner", 0, i))

    layout = parsers.parse_hcpcs_layout(member("hcpcs", 1))
    return BuildSources(
        icd10cm=parsers.parse_icd10cm_order(member("icd10cm")),
        icd10cm_index=parsers.parse_icd10cm_index(member("icd10cm_index")),
        hcpcs=parsers.parse_hcpcs(member("hcpcs", 0), layout),
        ptp=chain_ptp(),
        mue=parsers.parse_ncci_mue(member("ncci_mue_practitioner")),
        rvu=parsers.parse_mpfs_rvu(member("mpfs_rvu")),
        asp=parsers.parse_asp_crosswalk(member("asp_ndc_hcpcs")),
        cvx=parsers.parse_cvx(member("cvx")),
        meta={
            "tables_yaml_sha256": cfg.source_sha256 or "",
            "parser_version": cfg.parser_version,
            **{f"{name}.release": spec.release for name, spec in t.items()},
        },
    )


def build_tables(root: Path, tables_yaml: Path, sqlite_path: Path) -> BuildStats:
    sqlite_path.parent.mkdir(parents=True, exist_ok=True)
    tmp = sqlite_path.with_suffix(".building")
    if tmp.exists():
        tmp.unlink()
    conn = sqlite3.connect(str(tmp))
    try:
        conn.execute("PRAGMA journal_mode=OFF")
        conn.execute("PRAGMA synchronous=OFF")
        stats = build_sqlite(conn, sources_from_raw(root, tables_yaml))
    finally:
        conn.close()
    if sqlite_path.exists():
        sqlite_path.unlink()
    tmp.rename(sqlite_path)
    return stats
