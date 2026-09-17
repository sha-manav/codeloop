from codeloop.ingest.labels import crosswalk_amazon, crosswalk_medcoder, locate
from tests.synthetic import synthetic_amazon, synthetic_encounters, synthetic_medcoder


def test_amazon_crosswalk_by_id_normalizes_codes():
    encs = synthetic_encounters()
    records, stats = crosswalk_amazon(synthetic_amazon(encs), encs)
    assert stats.matched_documents == len(encs) and stats.unmatched_documents == 1 and stats.unmatched_rows == 1
    assert stats.encounters_without_record == []
    first = records[0]
    assert first["encounter_id"] == "D2N001" and first["match"] == "id"
    assert [c["code"] for c in first["codes"]] == ["M1711", "R509"]
    assert all(c["valid_shape"] for r in records for c in r["codes"])


def test_medcoder_crosswalk_tiers_offsets_and_unmatched():
    encs = synthetic_encounters()
    records, stats = crosswalk_medcoder(synthetic_medcoder(encs), encs)
    n_docs = len(encs) - 3
    assert stats.matched_documents == n_docs and stats.unmatched_documents == 2 and stats.unmatched_rows == 2
    assert set(stats.matched_by) == {"exact", "rstrip", "collapsed_ws"} and sum(stats.matched_by.values()) == n_docs
    assert stats.matched_by["exact"] > 0 and stats.matched_by["rstrip"] > 0 and stats.matched_by["collapsed_ws"] > 0
    assert len(stats.encounters_without_record) == 3
    by_id = {e.id: e for e in encs}
    for r in records:
        note = by_id[r["encounter_id"]].note_text
        for d in r["diagnoses"]:
            assert d["code"] == "M1711" and d["medcoder_offsets_verified"] is True
            assert " ".join(note[d["note_start"] : d["note_end"]].split()) == d["diagnosis"]
        for ev in r["evidence"]:
            assert ev["medcoder_offsets_verified"] is False  # deliberately shifted, like the real file
            assert note[ev["note_start"] : ev["note_end"]] == ev["text"]
    assert stats.extra["diagnoses_located_in_note"] == n_docs and stats.extra["diagnoses_not_located"] == 0
    assert stats.extra["medcoder_evidence_offsets_verified"] == 0
    assert stats.extra["docs_partition_holdout"] == 20


def test_locate_requires_uniqueness_and_tolerates_whitespace():
    text = "alpha beta  gamma\nbeta delta"
    assert locate(text, "beta gamma") == (6, 17)
    assert locate(text, "beta") is None  # ambiguous
    assert locate(text, "omega") is None
    assert locate(text, "   ") is None
