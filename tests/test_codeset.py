import sqlite3

import pytest

from codeloop.paths import Paths
from codeloop.review_ui.codeset import BILLABLE_LIST, export_billable, load_billable, parse_billable


def test_lookup_and_header():
    b = parse_billable("# icd10cm.release = FY2027\n# count = 4\nK5900\nG35D\nI10\nK5909\n")
    assert b.release == "FY2027" and b.codes == ("G35D", "I10", "K5900", "K5909")
    assert b.is_billable("k59.00") and b.is_billable("I10") and not b.is_billable("K590") and not b.is_billable("G35")
    assert b.has_more_specific("K59.0") and b.has_more_specific("G35") and not b.has_more_specific("I10") and not b.has_more_specific("Z99")


def test_export_roundtrip(tmp_path):
    db = tmp_path / "tables.sqlite"
    conn = sqlite3.connect(db)
    conn.executescript("CREATE TABLE meta(key TEXT PRIMARY KEY, value TEXT); CREATE TABLE icd10cm(code TEXT, valid INTEGER, short TEXT, long TEXT);")
    conn.executemany("INSERT INTO meta VALUES (?, ?)", [("icd10cm.release", "FY2027"), ("tables_yaml_sha256", "abc"), ("parser_version", "1")])
    conn.executemany("INSERT INTO icd10cm VALUES (?, ?, '', '')", [("K590", 0), ("K5900", 1), ("I10", 1)])
    conn.commit()
    conn.close()
    out = tmp_path / "list.txt"
    assert export_billable(db, out) == 2
    b = load_billable(out)
    assert b.codes == ("I10", "K5900") and b.provenance["tables_yaml_sha256"] == "abc" and load_billable(tmp_path / "missing.txt") is None


def test_committed_list_is_the_pinned_release():
    """The list in the image must be the project's pinned code set; checked against the tables wherever they exist."""
    b = load_billable()
    assert b is not None and b.release == "FY2027" and int(b.provenance["count"]) == len(b.codes) == len(set(b.codes))
    assert b.is_billable("G35D") and not b.is_billable("G35") and b.has_more_specific("G35")
    assert not any("." in c or c != c.upper() or not (3 <= len(c) <= 7) for c in b.codes)
    tables = Paths(BILLABLE_LIST.parents[2]).root / "data" / "tables" / "tables.sqlite"
    if not tables.exists():
        pytest.skip("data/tables/tables.sqlite not built here")
    conn = sqlite3.connect(f"file:{tables}?mode=ro", uri=True)
    meta = dict(conn.execute("SELECT key, value FROM meta").fetchall())
    codes = tuple(r[0] for r in conn.execute("SELECT code FROM icd10cm WHERE valid = 1 ORDER BY code"))
    conn.close()
    assert b.codes == tuple(sorted(codes)) and b.provenance["tables_yaml_sha256"] == meta["tables_yaml_sha256"]
