from codeloop.compliance import apply_evidence_policy, check_escalation, check_package
from codeloop.schemas import CodingPackage, DiagnosisPred, LinePred, Span
from codeloop.schemas.encounter import build_encounter
from codeloop.scoring import Scope
from codeloop.scrubber import rule_fire_counts, scrub
from tests.test_tables import synthetic_tables

SCOPE = Scope.model_validate({
    "modules": {"core_dx": {"on": True}, "core_lines": {"on": True, "code_ranges": ["73000-73140", "73501-73660", "71045-71048", "96372-96372", "20600-20611"]},
                "distinct_59x": {"on": False, "modifiers": ["59", "XE", "XS", "XP", "XU"]}, "qw": {"on": False, "modifiers": ["QW"]}, "jw_jz": {"on": False, "modifiers": ["JW", "JZ"]}},
    "exclusions": {"em_code_ranges": ["99202-99205", "99211-99215"], "modifiers": ["25"]},
})
NOTE = "ASSESSMENT\n\nRight knee osteoarthritis. X-ray of the right knee, 3 views, taken today shows joint space narrowing.\n"
DLG = "[doctor] your right knee looks arthritic .\n[patient] okay ."


def enc():
    return build_encounter(id="D2N001", subset="aci", split_orig="t", dialogue_raw=DLG, note_raw=NOTE)[0]


def note_span(text):
    e = enc()
    i = e.note_text.index(text)
    return Span.from_source("note", e.note_text, i, i + len(text))


def dlg_span(text):
    e = enc()
    i = e.dialogue_text.index(text)
    return Span.from_source("dialogue", e.dialogue_text, i, i + len(text))


def pkg(diagnoses, lines):
    return CodingPackage(encounter_id="D2N001", version="dev", run_id="r", diagnoses=diagnoses, lines=lines)


def dx(code, first=False, evidence=None):
    return DiagnosisPred(code=code, first_listed=first, evidence=evidence if evidence is not None else [note_span("Right knee osteoarthritis")])


def line(code, mods=(), units=1, pointers=("M1711",), evidence=None):
    return LinePred(code=code, modifiers=list(mods), units=units, pointers=list(pointers), evidence=evidence if evidence is not None else [note_span("X-ray of the right knee, 3 views, taken today")])


def test_scrubber_ptp_indicators():
    t = synthetic_tables()
    # 73560 (col1) / 73562 (col2) indicator 1: needs a bypass modifier on the column-2 line
    f = scrub(pkg([dx("M1711", True)], [line("73560"), line("73562")]), t, SCOPE, "20261001")
    assert [x.rule_id for x in f] == ["NCCI_PTP"] and f[0].field_ref == "line:73562:1:modifiers" and f[0].severity == "error"
    # bypass modifier present -> no PTP failure, but 59 is out of scope (module off) -> MODIFIER failure
    f = scrub(pkg([dx("M1711", True)], [line("73560"), line("73562", ["59"])]), t, SCOPE, "20261001")
    assert {x.rule_id for x in f} == {"MODIFIER"}
    # indicator 0 pair 96372/99213 -> error regardless of modifiers
    f = scrub(pkg([dx("M1711", True)], [line("96372"), line("99213", ["59"])]), t, SCOPE, "20261001")
    assert any(x.rule_id == "NCCI_PTP" and "indicator 0" in x.message for x in f)
    # deleted edit (73564/73560 deleted 2019) is ignored on a 2026 date
    f = scrub(pkg([dx("M1711", True)], [line("73564"), line("73560")]), t, SCOPE, "20261001")
    assert not any(x.rule_id == "NCCI_PTP" for x in f)
    assert any(x.rule_id == "NCCI_PTP" for x in scrub(pkg([dx("M1711", True)], [line("73564"), line("73560")]), t, SCOPE, "20180101"))


def test_scrubber_mue_modifiers_structural():
    t = synthetic_tables()
    f = scrub(pkg([dx("M1711", True)], [line("73560", units=3)]), t, SCOPE, "20261001")
    assert [x.rule_id for x in f] == ["MUE"] and "exceed MUE 2" in f[0].message and f[0].field_ref.endswith(":units")
    f = scrub(pkg([dx("M1711", True)], [line("96372", ["50"]), line("73560", ["RT", "50"]), line("20610", ["59", "XS"])]), t, SCOPE, "20261001")
    msgs = [x.message for x in f if x.rule_id == "MODIFIER"]
    assert any("bilateral indicator" in m for m in msgs) and any("RT/LT cannot be combined" in m for m in msgs)
    assert any("59 and X" in m for m in msgs) and any("out of scope" in m for m in msgs)
    f = scrub(pkg([dx("M1711", True)], [line("73560", ["25"])]), t, SCOPE, "20261001")
    assert any("modifier 25" in x.message for x in f)
    f = scrub(pkg([dx("M17", True)], [line("73560", pointers=[]), line("99999", pointers=["R509"])]), t, SCOPE, "20261001")
    kinds = [x.message for x in f if x.rule_id == "STRUCTURAL"]
    assert any("no diagnosis pointer" in m for m in kinds) and any("does not resolve" in m for m in kinds)
    assert any("not in the pinned code sets" in m for m in kinds) and any("not a valid (billable)" in m for m in kinds)
    assert rule_fire_counts(f)["STRUCTURAL:error"] >= 4
    assert scrub(pkg([dx("M1711", True)], [line("73560")]), t, SCOPE, "20261001") == []


def test_note_only_policy_rejects_dialogue_only_support():
    t = synthetic_tables()
    e = enc()
    p = pkg([dx("M1711", True, [dlg_span("your right knee looks arthritic")])], [line("73560", evidence=[dlg_span("okay")])])
    result = check_package(p, e, SCOPE, t, "note_only")
    assert not result.passed and {i.kind for i in result.issues} == {"no_allowed_evidence"}
    assert check_package(p, e, SCOPE, t, "note_or_dialogue").passed
    downgraded_pkg, refs = apply_evidence_policy(p, "note_only")
    assert refs == ["dx:M1711", "line:73560:0"] and downgraded_pkg.diagnoses == [] and downgraded_pkg.lines == []
    assert len(downgraded_pkg.provider_queries) == 2 and downgraded_pkg.provider_queries[0].evidence[0].source == "dialogue"
    good = pkg([dx("M1711", True)], [line("73560")])
    assert check_package(good, e, SCOPE, t, "note_only").passed and apply_evidence_policy(good, "note_only")[1] == []


def test_span_mismatch_and_unknown_codes_are_compliance_issues():
    t = synthetic_tables()
    e = enc()
    bad_span = Span.make("note", 0, 10, "ASSESSMENT")  # correct text
    tampered = Span.make("note", 0, 10, "ASSESSXXXX")
    p = pkg([dx("M1799", True, [tampered]), dx("R509", evidence=[bad_span])], [line("99999")])
    r = check_package(p, e, SCOPE, t, "note_only")
    kinds = sorted({i.kind for i in r.issues})
    assert kinds == ["out_of_scope_line", "span_mismatch", "unknown_code"] and not r.passed


def test_escalation_gate():
    t = synthetic_tables()
    e = enc()
    base = pkg([dx("M1710", True)], [line("73560", pointers=["M1710"])])
    cand = pkg([dx("M1711", True)], [line("73562", pointers=["M1711"]), line("73560", pointers=["M1711"])])
    r = check_escalation(base, cand, encounter=e, scope=SCOPE, tables=t, policy="note_only", on_date="20261001")
    kinds = {x.kind for x in r.escalations}
    assert "more_specific_dx" in kinds and "new_line" in kinds
    assert not r.passed and r.scrubber_errors == 1  # PTP 73560/73562 without bypass modifier
    clean = pkg([dx("M1711", True)], [line("73562", pointers=["M1711"])])
    r = check_escalation(base, clean, encounter=e, scope=SCOPE, tables=t, policy="note_only", on_date="20261001")
    assert r.passed and {x.kind for x in r.escalations} == {"more_specific_dx", "new_line"}
    no_ev = pkg([dx("M1711", True, [dlg_span("okay")])], [])
    r = check_escalation(base, no_ev, encounter=e, scope=SCOPE, tables=t, policy="note_only", on_date="20261001")
    assert not r.passed and not r.escalations[0].evidence_ok
    higher = pkg([dx("M1710", True)], [line("73560", units=2, pointers=["M1710"])])
    r = check_escalation(base, higher, encounter=e, scope=SCOPE, tables=t, policy="note_only", on_date="20261001")
    assert [x.kind for x in r.escalations] == ["higher_units"] and r.passed
    same = check_escalation(base, base, encounter=e, scope=SCOPE, tables=t, policy="note_only", on_date="20261001")
    assert same.passed and same.escalations == []
