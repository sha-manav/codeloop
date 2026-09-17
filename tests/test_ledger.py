from codeloop.ledger import append_entry, read_entries


def test_append_and_read_roundtrip(tmp_path):
    p = tmp_path / "ledger.md"
    append_entry(p, "seal", {"seed": 1, "alloc": {"a": 2}}, actor="tests", ts="2026-09-17T00:00:00Z")
    append_entry(p, "ingest", {"ok": "yes"}, actor="tests", ts="2026-09-17T00:01:00Z")
    entries = read_entries(p)
    assert [e.event for e in entries] == ["seal", "ingest"]
    assert entries[0].ts == "2026-09-17T00:00:00Z" and entries[0].fields["actor"] == "tests"
    assert entries[0].json_field("alloc") == {"a": 2} and entries[0].fields["seed"] == "1"
    text = p.read_text(encoding="utf-8")
    assert text.startswith("# CodeLoop ledger") and text.count("## ") == 2
