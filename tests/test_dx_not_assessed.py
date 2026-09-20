"""The not-assessed rule (batch1 findings FIND-DX-0006, -0020, -0023, -0030; merged with PR #1).

tests/ is not writable for the improvement agent, so these came after the merge. Synthetic text only.
"""

from codeloop.agent.pipeline import RunContext, run_encounter
from codeloop.rules import dx_rules
from codeloop.rules.dx_rules import DxDecision, drop_not_assessed
from codeloop.rules.sections import assessment_plan_ranges, in_assessment_plan
from codeloop.schemas.encounter import build_encounter
from codeloop.schemas.package import Span
from tests.synthetic import REAL_ROOT
from tests.test_pipeline import _client
from tests.test_scrubber_compliance import SCOPE
from tests.test_tables import synthetic_tables

NOTE = (
    "CHIEF COMPLAINT\n\nKnee pain.\n\nREVIEW OF SYSTEMS\n\nPositive for dizziness and knee swelling.\n\n"
    "SOCIAL HISTORY\n\nFormer smoker.\n\nPHYSICAL EXAM\n\nEffusion of the right knee.\n\n"
    "ASSESSMENT\n\nRight knee osteoarthritis. Dizziness, will check orthostatics.\n\nPLAN\n\nNaproxen.\n"
)


def _span(text: str) -> Span:
    start = NOTE.index(text)
    return Span.from_source("note", NOTE, start, start + len(text))


def _dx(i: int, code: str, *quotes: str, first: bool = False) -> DxDecision:
    return DxDecision(problem_index=i, code=code, first_listed=first, rationale="", evidence=[_span(q) for q in quotes])


def test_sections_find_the_assessment_and_plan():
    ranges = assessment_plan_ranges(NOTE)
    assert len(ranges) == 2  # ASSESSMENT and PLAN
    assert in_assessment_plan(ranges, NOTE.index("Right knee osteoarthritis")) and in_assessment_plan(ranges, NOTE.index("Naproxen"))
    assert not in_assessment_plan(ranges, NOTE.index("Positive for dizziness")) and not in_assessment_plan(ranges, NOTE.index("Effusion"))
    assert assessment_plan_ranges("no headers here, just a paragraph of text.\nAnd another line.") is None
    assert assessment_plan_ranges("HISTORY OF PRESENT ILLNESS\n\ntext\n") == []  # headers, but no assessment/plan section


def test_a_listed_class_is_uncoded_only_when_its_evidence_is_outside_the_assessment_and_plan():
    oa = _dx(0, "M1711", "Right knee osteoarthritis.", first=True)
    ros_only = _dx(1, "R42", "Positive for dizziness")
    history = _dx(2, "Z87891", "Former smoker.")
    murmur_like = _dx(3, "R011", "Effusion of the right knee.")  # not a listed class (FIND-DX-0010 is ambiguous)
    decisions = [oa, ros_only, history, murmur_like]
    assert drop_not_assessed(decisions, NOTE, []) == {"R42": [], "Z87891": []}
    assert [d.code for d in decisions] == ["M1711", None, None, "R011"]
    assert "FIND-DX-0020" in ros_only.notes[0] and "FIND-DX-0030" in history.notes[0]
    # the same code with evidence in the assessment is what the visit assessed: kept
    assessed = _dx(1, "R42", "Positive for dizziness", "Dizziness, will check orthostatics.")
    assert drop_not_assessed([_dx(0, "M1711", "Right knee osteoarthritis."), assessed], NOTE, []) == {} and assessed.code == "R42"


def test_the_rule_is_conservative():
    # the only diagnosis stays, whatever its class
    alone = _dx(0, "R42", "Positive for dizziness", first=True)
    assert drop_not_assessed([alone], NOTE, []) == {} and alone.code == "R42"
    # no note evidence, or a note without recognizable sections: nothing to decide on
    no_evidence = DxDecision(problem_index=1, code="R42", first_listed=False, rationale="", evidence=[])
    assert drop_not_assessed([_dx(0, "M1711", "Right knee osteoarthritis."), no_evidence], NOTE, []) == {}
    flat = "dizziness noted. osteoarthritis of the knee."
    d = DxDecision(problem_index=1, code="R42", first_listed=False, rationale="", evidence=[Span.from_source("note", flat, 0, 9)])
    other = DxDecision(problem_index=0, code="M1711", first_listed=True, rationale="", evidence=[Span.from_source("note", flat, 17, 31)])
    assert drop_not_assessed([other, d], flat, []) == {} and d.code == "R42"
    # a billed line that points only at it: the diagnosis stays, with a note
    sole = _dx(1, "R42", "Positive for dizziness")
    assert drop_not_assessed([_dx(0, "M1711", "Right knee osteoarthritis."), sole], NOTE, [["R42"]]) == {}
    assert sole.code == "R42" and "a billed line points only at it" in sole.notes[0]


def test_joint_symptoms_need_a_definitive_diagnosis_and_the_line_follows_to_it():
    # beside a definitive musculoskeletal diagnosis: both symptom codes go, and a line that pointed only at them
    # is told to point at that diagnosis (what the coder does when replacing a symptom code)
    oa = _dx(0, "M1711", "Right knee osteoarthritis.", first=False)
    pain = _dx(1, "M25561", "Knee pain.", first=True)
    effusion = _dx(2, "M25461", "Effusion of the right knee.")
    htn = _dx(3, "I10", "Naproxen.")
    dropped = drop_not_assessed([oa, pain, effusion, htn], NOTE, [["M25461", "M25561"]])
    assert dropped == {"M25561": ["M1711"], "M25461": ["M1711"]} and pain.code is None and not pain.first_listed
    # without one, the symptom is what the documentation supports
    pain2, effusion2 = _dx(0, "M25561", "Knee pain.", first=True), _dx(1, "M25461", "Effusion of the right knee.")
    assert drop_not_assessed([pain2, effusion2, _dx(2, "I10", "Naproxen.")], NOTE, [["M25561"]]) == {}
    assert pain2.code == "M25561" and effusion2.code == "M25461"


def _responder(pointer_index):
    def fn(system, user, schema, params):
        name = schema.__name__
        if name == "Extraction":
            return {
                "problems": [
                    {"description": "fever", "status": "active", "laterality": "not_applicable", "qualifiers": [],
                     "note_quotes": ["Positive for fever."], "dialogue_quotes": []},
                    {"description": "osteoarthritis of the knee", "status": "active", "laterality": "right", "qualifiers": ["primary"],
                     "note_quotes": ["Right knee osteoarthritis."], "dialogue_quotes": []},
                ],
                "services": [{"category": "in_office_imaging", "description": "right knee radiograph, 3 views", "body_part": "knee",
                              "laterality": "right", "views": 3, "note_quotes": ["X-ray of the right knee, 3 views, taken today"], "dialogue_quotes": []}],
                "administrations": [], "patient": {},
            }
        if name == "DxMapping":
            return {"selections": [
                {"problem_index": 0, "code": "R50.9", "first_listed": True, "laterality_basis": "none", "rationale": "x",
                 "provider_query": "is the fever being worked up?"},
                {"problem_index": 1, "code": "M17.11", "first_listed": False, "laterality_basis": "note", "rationale": "x"},
            ]}
        if name == "LineMapping":
            return {"selections": [{"service_index": 0, "code": "73562", "units": 1, "pointer_problem_indices": pointer_index, "rationale": "x"}]}
        raise AssertionError(name)

    return fn


def _run(monkeypatch, pointer_index):
    from codeloop.llm import FakeProvider

    # the synthetic code tables hold R509 but none of the production classes
    monkeypatch.setattr(dx_rules, "NOT_ASSESSED_CLASSES", (("TEST-CLASS", ("R50",), False),))
    note = ("REVIEW OF SYSTEMS\n\nPositive for fever.\n\nRESULTS\n\nX-ray of the right knee, 3 views, taken today shows narrowing.\n\n"
            "ASSESSMENT AND PLAN\n\nRight knee osteoarthritis.\n")
    enc, _ = build_encounter(id="D2N001", subset="aci", split_orig="t", dialogue_raw="[doctor] hello .", note_raw=note)
    ctx = RunContext(paths=None, version="dev", run_id="r1", llm=_client(REAL_ROOT, FakeProvider(_responder(pointer_index))),
                     tables=synthetic_tables(), scope=SCOPE, scope_hash="s", evidence_policy="note_only", on_date="20261001", seed=1, prompt_hashes={})
    return run_encounter(enc, ctx).package


def test_pipeline_drops_the_code_its_query_and_its_pointer_and_rechooses_first_listed(monkeypatch):
    pkg = _run(monkeypatch, [0, 1])
    assert [(d.code, d.first_listed) for d in pkg.diagnoses] == [("M1711", True)]
    assert [(ln.code, ln.pointers) for ln in pkg.lines] == [("73562", ["M1711"])]
    assert not [q for q in pkg.provider_queries if q.field_ref.startswith("dx:R509")] and pkg.scrubber == []


def test_pipeline_never_orphans_a_billed_line(monkeypatch):
    pkg = _run(monkeypatch, [0])  # the X-ray points only at the review-of-systems fever
    assert sorted(d.code for d in pkg.diagnoses) == ["M1711", "R509"]
    assert [(ln.code, ln.pointers) for ln in pkg.lines] == [("73562", ["R509"])] and pkg.scrubber == []
