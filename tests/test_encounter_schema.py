import pytest
from pydantic import ValidationError

from codeloop.schemas.encounter import (
    Encounter,
    build_encounter,
    flatten_dialogue,
    load_encounters_jsonl,
    normalize_newlines,
    parse_dialogue,
)
from codeloop.util.hashing import sha256_text
from codeloop.util.jsonl import write_jsonl


def test_parse_dialogue_tags_blanks_and_continuations():
    raw = "[doctor] hello there .\n[patient] hi .\n\nthis line continues the patient turn .\n[ inaudible 00:09:25 ] also continuation\n[patient_guest] i am here too .\n"
    turns, stats = parse_dialogue(raw)
    assert [t.speaker for t in turns] == ["doctor", "patient", "patient_guest"]
    assert turns[1].text == "hi .\nthis line continues the patient turn .\n[ inaudible 00:09:25 ] also continuation"
    assert stats.turns == 3 and stats.continuation_lines == 2 and stats.blank_lines == 2
    assert stats.speakers == {"doctor": 1, "patient": 1, "patient_guest": 1}


def test_leading_untagged_line_becomes_unknown_speaker():
    turns, stats = parse_dialogue("no tag here\n[doctor] ok\n")
    assert turns[0].speaker == "unknown" and stats.leading_untagged_lines == 1


def test_flatten_is_identity_for_well_formed_dialogue():
    raw = "[doctor] hi , how are you ?\n[patient] fine .\n[doctor] good ."
    turns, _ = parse_dialogue(raw)
    assert flatten_dialogue(turns) == raw


def test_normalize_newlines_handles_crlf_and_bom():
    assert normalize_newlines("﻿a\r\nb\rc\n") == "a\nb\nc\n"


def test_build_encounter_hashes_and_validator():
    enc, _ = build_encounter(id="D2N001", subset="aci", split_orig="train", dialogue_raw="[doctor] hi\r\n[patient] hey", note_raw="NOTE\r\nline")
    assert enc.note_text == "NOTE\nline" and enc.dialogue_text == "[doctor] hi\n[patient] hey"
    assert enc.note_sha256 == sha256_text("NOTE\nline")
    bad = enc.model_dump()
    bad["note_sha256"] = "0" * 64
    with pytest.raises(ValidationError):
        Encounter.model_validate(bad)
    bad = enc.model_dump()
    bad["dialogue_text"] = "[doctor] tampered"
    with pytest.raises(ValidationError):
        Encounter.model_validate(bad)
    with pytest.raises(ValidationError):
        build_encounter(id="x", subset="nope", split_orig="t", dialogue_raw="", note_raw="")


def test_jsonl_roundtrip_reverifies(tmp_path):
    enc, _ = build_encounter(id="D2N002", subset="virtscribe", split_orig="valid", dialogue_raw="[doctor] a\n[patient] b", note_raw="n")
    p = tmp_path / "e.jsonl"
    write_jsonl(p, [enc])
    assert load_encounters_jsonl(p) == [enc]
    text = p.read_text(encoding="utf-8").replace('"note_text": "n"', '"note_text": "m"')
    p.write_text(text, encoding="utf-8")
    with pytest.raises(ValidationError):
        load_encounters_jsonl(p)
