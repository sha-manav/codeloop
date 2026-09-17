import pytest

from codeloop.ingest.aci_bench import IngestError, parse_challenge_csv


def test_parse_challenge_csv_with_multiline_quoted_fields(tmp_path):
    p = tmp_path / "train.csv"
    p.write_text(
        'dataset,encounter_id,dialogue,note\n'
        'aci,D2N001,"[doctor] hi .\n[patient] hello .","CHIEF COMPLAINT\n\nSynthetic."\n'
        'virtassist,D2N002,"[doctor] one .\n\n[patient] two .","NOTE TWO  "\n',
        encoding="utf-8",
    )
    encs, stats = parse_challenge_csv(p, "train")
    assert [e.id for e in encs] == ["D2N001", "D2N002"]
    assert encs[0].subset == "aci" and encs[1].subset == "virtassist"
    assert encs[1].note_text == "NOTE TWO  " and stats.notes_with_trailing_ws == 1
    assert stats.per_split == {"train": 2} and stats.dialogue.blank_lines == 1
    assert stats.per_subset == {"aci": 1, "virtassist": 1}


def test_missing_columns_raise(tmp_path):
    p = tmp_path / "bad.csv"
    p.write_text("id,text\n1,x\n", encoding="utf-8")
    with pytest.raises(IngestError):
        parse_challenge_csv(p, "train")
