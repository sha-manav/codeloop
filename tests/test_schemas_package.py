import pytest
from pydantic import ValidationError

from codeloop.schemas import CodingPackage, DiagnosisPred, Event, LinePred, Span, verify_package_spans
from codeloop.schemas.encounter import build_encounter
from codeloop.schemas.field_ref import FieldRef, line_ref, parse_field_ref


def _enc():
    enc, _ = build_encounter(id="D2N001", subset="aci", split_orig="train", dialogue_raw="[doctor] knee hurts ?\n[patient] yes , right knee .", note_raw="ASSESSMENT\n\nRight knee osteoarthritis.\n")
    return enc


def test_span_validation_and_verify():
    enc = _enc()
    s = Span.from_source("note", enc.note_text, 12, 36)
    assert s.text == "Right knee osteoarthriti" and s.verify(enc)
    with pytest.raises(ValidationError):
        Span(source="note", start=0, end=3, text="abcd", sha256=s.sha256)
    with pytest.raises(ValidationError):
        Span(source="note", start=0, end=4, text="abcd", sha256="0" * 64)
    with pytest.raises(ValidationError):
        Span.make("note", 5, 2, "")


def test_package_normalizes_and_verifies_spans():
    enc = _enc()
    good = Span.from_source("note", enc.note_text, 12, 37)
    bad = Span.make("note", 12, 37, "Right knee osteoarthritiX")
    pkg = CodingPackage(
        encounter_id="D2N001", version="dev", run_id="r1",
        diagnoses=[DiagnosisPred(code="m17.11", first_listed=True, evidence=[good])],
        lines=[LinePred(code="96372", modifiers=["rt", "59"], pointers=["M17.11"], evidence=[bad])],
    )
    assert pkg.diagnoses[0].code == "M1711" and pkg.lines[0].modifiers == ["59", "RT"] and pkg.lines[0].pointers == ["M1711"]
    assert pkg.first_listed_code == "M1711"
    problems = verify_package_spans(pkg, enc)
    assert len(problems) == 1 and problems[0].startswith("line:96372:0")
    with pytest.raises(ValidationError):
        LinePred(code="9637", units=1)
    with pytest.raises(ValidationError):
        LinePred(code="96372", units=0)
    assert CodingPackage.model_validate_json(pkg.model_dump_json()) == pkg


def test_event_reason_rules():
    base = dict(ts="t", coder_id="c", encounter_id="D2N001", batch="batch1", version="v0", mode="review")
    with pytest.raises(ValidationError):
        Event(**base, type="edit", field_ref="dx:M1711")
    assert Event(**base, type="edit", field_ref="dx:M1711", reason="specificity").reason == "specificity"
    assert Event(**{**base, "mode": "blind"}, type="add", field_ref="dx:M1711").reason is None
    with pytest.raises(ValidationError):
        Event(**base, type="accept", reason="because")


def test_field_refs_roundtrip():
    for ref in ("dx:M1711", "dx:M1711:status", "first_listed", "line:96372", "line:96372:1", "line:96372:1:units", "line:J1100:pointers", "query:3"):
        assert str(parse_field_ref(ref)) == ref
    assert parse_field_ref("line:96372:1:units") == FieldRef("line", "96372", 1, "units")
    assert parse_field_ref("line:96372:modifiers").field_type == "modifiers"
    assert line_ref("96372", 2, "units") == "line:96372:2:units"
    for bad in ("dx", "line:96372:status", "query", "first_listed:x", "dx:M1711:units"):
        with pytest.raises(ValueError):
            parse_field_ref(bad)
