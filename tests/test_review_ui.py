import json
import re

from fastapi.testclient import TestClient

from codeloop.review_ui.app import ReviewSession, create_review_app
from codeloop.review_ui.codeset import parse_billable
from codeloop.review_ui.labels import build_labels
from codeloop.review_ui.replay import ineffective_touch_ids, pointer_problems, replay, review_minutes
from codeloop.review_ui.store import EventStore
from codeloop.schemas.event import Event
from codeloop.schemas.label import LabelPackage
from codeloop.seal.crypto import decrypt_from_file
from codeloop.seal.run import perform_seal
from codeloop.util.jsonl import read_jsonl, write_jsonl
from codeloop.versioning.freeze import perform_freeze
from tests.synthetic import FAKE_KEY, make_inputs, make_repo
from tests.test_scrubber_compliance import SCOPE


def _repo(tmp_path):
    paths, config = make_repo(tmp_path)
    perform_seal(paths, config, make_inputs(), passphrase=FAKE_KEY, actor="tests")
    (paths.runs / "audit").mkdir(parents=True, exist_ok=True)
    dev_ids = [line.split('"id": "')[1][:6] for line in paths.dev_encounters.read_text(encoding="utf-8").splitlines() if '"id": "' in line]
    (paths.runs / "audit" / "flag_counts.json").write_text(json.dumps({i: 0 for i in dev_ids}), encoding="utf-8")
    paths.scope_yaml.write_text(SCOPE.model_dump_json(), encoding="utf-8")
    perform_freeze(paths, actor="tests", do_git=False)
    split = json.loads(paths.dev_split.read_text())
    ids = split["sets"]["spare"]
    preds = []
    for eid in ids:
        preds.append({"encounter_id": eid, "version": "dev", "run_id": "r", "diagnoses": [
            {"code": "M1711", "status": "active", "first_listed": True, "evidence": [{"source": "note", "start": 0, "end": 5, "text": "CHIEF", "sha256": "x"}], "rationale": "r"}],
            "lines": [{"code": "73562", "modifiers": ["RT"], "units": 1, "pointers": ["M1711"], "module": "core_lines", "evidence": [], "rationale": ""}],
            "provider_queries": [{"field_ref": "dx:M1711:laterality", "question": "which side?", "evidence": [], "suggested_value": None}],
            "data_gaps": [], "scrubber": [], "compliance": {"policy": "note_only", "checked": True, "passed": True, "issues": [], "downgraded_fields": []}})
    write_jsonl(paths.runs / "dev" / "spare" / "predictions.jsonl", preds)
    # make two spare encounters blind for the test
    split["blind"]["spare"] = ids[:2]
    paths.dev_split.write_text(json.dumps(split), encoding="utf-8")
    return paths, config, ids


def test_blind_mode_never_serves_predictions_and_reveals_after_submit(tmp_path):
    paths, config, ids = _repo(tmp_path)
    session = ReviewSession(paths, batch="spare", version="dev", coder_id="owner", store_path=None)
    session.store = EventStore(None)
    ui = TestClient(create_review_app(session))
    blind_id, review_id = ids[0], ids[2]
    r = ui.get(f"/api/encounter/{blind_id}").json()
    assert r["mode"] == "blind" and r["draft"] is None and "M1711" not in json.dumps(r) and session.predictions_loaded_for == set()
    # blind-mode adds need no reason; build the blind label then submit
    assert ui.post("/api/event", json={"encounter_id": blind_id, "type": "add", "field_ref": "dx:E119", "after": {"code": "E11.9", "first_listed": True}}).status_code == 200
    assert ui.post("/api/approve", json={"encounter_id": blind_id}).status_code == 400
    r = ui.post("/api/blind_submit", json={"encounter_id": blind_id}).json()
    assert r["blind_label"]["diagnoses"][0]["code"] == "E119" and r["mode"] == "review"
    r = ui.get(f"/api/encounter/{blind_id}").json()
    assert r["mode"] == "review" and r["draft"] is not None and r["label"]["diagnoses"][0]["code"] == "M1711"
    # review encounter: draft served, reasons required, accept/edit/remove/grade/approve flow
    r = ui.get(f"/api/encounter/{review_id}").json()
    assert r["mode"] == "review" and r["draft"]["spans"]["dx:M1711"][0]["text"] == "CHIEF"
    assert ui.post("/api/event", json={"encounter_id": review_id, "type": "edit", "field_ref": "dx:M1711", "after": {"code": "M17.12"}}).status_code == 400
    assert ui.post("/api/event", json={"encounter_id": review_id, "type": "edit", "field_ref": "dx:M1711", "after": {"code": "M17.12"}, "reason": "specificity"}).status_code == 200
    assert ui.post("/api/event", json={"encounter_id": review_id, "type": "accept", "field_ref": "line:73562:0"}).status_code == 200
    assert ui.post("/api/event", json={"encounter_id": review_id, "type": "grade_evidence", "field_ref": "dx:M1712", "span_id": "dx:M1711#0", "grade": "supported"}).status_code == 200
    assert ui.post("/api/event", json={"encounter_id": review_id, "type": "grade_query", "field_ref": "query:0", "grade": "warranted"}).status_code == 200
    assert ui.post("/api/event", json={"encounter_id": review_id, "type": "add", "field_ref": "line:96372", "after": {"code": "96372", "pointers": ["M1712"]}, "reason": "missed"}).status_code == 200
    assert ui.post("/api/approve", json={"encounter_id": review_id}).status_code == 200
    r = ui.get(f"/api/encounter/{review_id}").json()
    assert r["status"] == "approved" and r["touches"] == 2
    assert [d["code"] for d in r["label"]["diagnoses"]] == ["M1712"] and [ln["code"] for ln in r["label"]["lines"]] == ["73562", "96372"]
    assert r["evidence_grades"] == {"dx:M1711#0": "supported"} and r["query_grades"] == {"query:0": "warranted"}
    assert ui.get("/").status_code == 200 and ui.get(f"/encounter/{review_id}").status_code == 200 and ui.get("/encounter/D2N999").status_code == 404
    # approve is refused until every drafted field, passage and query has a decision (guidelines §4)
    r = ui.post("/api/approve", json={"encounter_id": blind_id})
    assert r.status_code == 400 and "not ready to approve" in r.text
    for ev in (
        {"type": "accept", "field_ref": "dx:M1711"}, {"type": "accept", "field_ref": "line:73562:0"},
        {"type": "grade_evidence", "field_ref": "dx:M1711", "span_id": "dx:M1711#0", "grade": "unsupported"},
        {"type": "grade_query", "field_ref": "query:0", "grade": "unwarranted"},
    ):
        assert ui.post("/api/event", json={"encounter_id": blind_id, **ev}).status_code == 200
    assert ui.get(f"/api/encounter/{blind_id}").json()["pending"] == {"fields": [], "spans": [], "queries": [], "pointers": [], "first_listed": []}
    # labels build: only approved encounters, with touches/minutes/grades; blind label kept separately
    assert ui.post("/api/approve", json={"encounter_id": blind_id}).status_code == 200
    result = build_labels(paths, batch="spare", version="dev", store=session.store, actor="tests")
    assert result.approved == 2 and len(result.pending) == len(ids) - 2
    labels = {r["encounter_id"]: r for r in read_jsonl(paths.labels_file("spare"))}
    assert labels[review_id]["touches"] == 2 and labels[review_id]["query_grades"] == {"query:0": "warranted"} and labels[review_id]["blind_label"] is None
    assert labels[blind_id]["blind_label"]["diagnoses"][0]["code"] == "E119" and labels[blind_id]["label"]["diagnoses"][0]["code"] == "M1711" and labels[blind_id]["blind_subset"]
    assert (paths.review_dir("dev", "spare") / "events.jsonl").exists()


def test_page_js_sends_the_encounter_id_with_every_post(tmp_path):
    """The API tests above post hand-written bodies; this pins what the page itself sends. Every POST once went out
    without encounter_id, so nothing a coder did could be saved. tests/test_review_ui_browser.py runs the real thing."""
    paths, config, ids = _repo(tmp_path)
    session = ReviewSession(paths, batch="spare", version="dev", coder_id="owner", store_path=None)
    session.store = EventStore(None)
    page = TestClient(create_review_app(session)).get(f"/encounter/{ids[2]}").text
    assert f"const EID = {json.dumps(ids[2])};" in page
    js = page.split("<script>")[-1]
    assert "function send(path, body){ return api(path, {encounter_id: EID, ...body}); }" in js
    posts = re.findall(r"\b(api|send)\('(/api/(?:event|approve|blind_submit))'", js)
    assert {path for _, path in posts} == {"/api/event", "/api/approve", "/api/blind_submit"}
    assert all(fn == "send" for fn, _ in posts), posts
    # passage text is never inlined into a handler attribute: an apostrophe in it would end the attribute
    assert "onclick='" not in js and "JSON.stringify(spans)" not in js


def test_guards_refuse_what_the_append_only_store_could_never_take_back(tmp_path):
    """Refused before anything is written: an empty blind submit, an Edit that changes nothing, blank or misshapen
    codes, values replay could not load, fields that are not there, duplicates. Each once reached the production
    store (or could have) where the only remedy is a ledger note."""
    paths, config, ids = _repo(tmp_path)
    session = ReviewSession(paths, batch="spare", version="dev", coder_id="owner", store_path=None)
    session.store = EventStore(None)
    ui = TestClient(create_review_app(session))
    blind_id, review_id = ids[0], ids[2]

    def refused(eid, needle, **ev):
        r = ui.post("/api/event", json={"encounter_id": eid, **ev})
        assert r.status_code == 400 and needle in r.json()["detail"], (ev, r.text)

    # blind: an empty label is never submitted, the encounter stays blind and the draft stays unread
    r = ui.post("/api/blind_submit", json={"encounter_id": blind_id})
    assert r.status_code == 400 and "no diagnoses" in r.json()["detail"]
    assert session.mode(blind_id) == "blind" and session.events(blind_id) == [] and session.predictions_loaded_for == set()
    refused(blind_id, "code box is empty", type="add", field_ref="dx:", after={"code": " "})
    refused(blind_id, "not shaped like an ICD-10-CM", type="add", field_ref="dx:5K90", after={"code": "5K9.0"})
    refused(blind_id, "not shaped like a CPT", type="add", field_ref="line:7356", after={"code": "7356"})
    refused(blind_id, "cannot be saved", type="add", field_ref="line:73562", after={"code": "73562", "units": 0})
    refused(blind_id, "cannot be saved", type="add", field_ref="line:73562", after={"code": "73562", "units": None})
    assert ui.post("/api/event", json={"encounter_id": blind_id, "type": "add", "field_ref": "dx:J069", "after": {"code": "J06.9", "first_listed": True}}).status_code == 200
    refused(blind_id, "already on the package", type="add", field_ref="dx:J069", after={"code": "j06.9"})
    refused(blind_id, "code box is empty", type="edit", field_ref="dx:J069", after={"code": "", "status": "active", "first_listed": True})
    refused(blind_id, "Nothing changed", type="edit", field_ref="dx:J069", after={"code": "J06.9", "status": "active", "first_listed": True})
    assert [e.type for e in session.events(blind_id)] == ["add"]
    assert ui.post("/api/blind_submit", json={"encounter_id": blind_id}).status_code == 200

    # review: the draft is dx M1711 (first-listed) and line 73562 RT x1 -> M1711
    as_drafted = {"code": "M17.11", "status": "active", "first_listed": True}
    refused(review_id, "Nothing changed", type="edit", field_ref="dx:M1711", after=as_drafted, reason="guideline")
    refused(review_id, "Nothing changed", type="edit", field_ref="line:73562:0", reason="query_needed",
            after={"code": "73562", "modifiers": ["rt"], "units": 1, "pointers": ["M1711"]})
    refused(review_id, "not on the package", type="edit", field_ref="dx:Z999", after={"code": "Z99.9"}, reason="wrong_value")
    refused(review_id, "not on the package", type="remove", field_ref="line:99999:0", reason="unsupported")
    refused(review_id, "cannot be first-listed", type="edit", field_ref="first_listed", after={"code": "E11.9"}, reason="guideline")
    refused(review_id, "cannot be saved", type="edit", field_ref="line:73562:0", after={"units": "many"}, reason="wrong_value")
    refused(review_id, "Unknown field", type="edit", field_ref="query:0", after={"code": "M17.11"}, reason="judgment")
    assert session.events(review_id) == []
    ok = ui.post("/api/event", json={"encounter_id": review_id, "type": "edit", "field_ref": "dx:M1711", "after": {**as_drafted, "code": "M17.12"}, "reason": "specificity"})
    assert ok.status_code == 200 and ui.get(f"/api/encounter/{review_id}").json()["touches"] == 1


def test_lines_must_point_at_diagnoses_that_are_on_the_package(tmp_path):
    """Spec §8 structural rule, applied to the coder's label: removing or replacing a diagnosis used to leave the
    X-ray line pointing at it, and the scorer compares pointer sets as they stand."""
    pkg = LabelPackage.model_validate({"diagnoses": [{"code": "M17.11"}, {"code": "E11.9"}], "lines": [
        {"code": "73562", "pointers": ["M17.11", "B", "2"]}, {"code": "73564", "pointers": []}, {"code": "73560", "pointers": ["C", "3", "I10"]}]})
    assert pointer_problems(pkg) == [
        "line 73564 has no diagnosis pointer",
        "line 73560 points at C, which is not a diagnosis on the package",
        "line 73560 points at 3, which is not a diagnosis on the package",
        "line 73560 points at I10, which is not a diagnosis on the package",
    ]
    paths, config, ids = _repo(tmp_path)
    session = ReviewSession(paths, batch="spare", version="dev", coder_id="owner", store_path=None)
    session.store = EventStore(None)
    ui = TestClient(create_review_app(session))
    blind_id, review_id, recode_id = ids[0], ids[2], ids[3]

    def post(eid, **ev):
        return ui.post("/api/event", json={"encounter_id": eid, **ev})

    # replace the drafted diagnosis (remove + add): the line is left pointing at the removed code until it is fixed
    assert post(review_id, type="remove", field_ref="dx:M1711", reason="guideline").status_code == 200
    assert post(review_id, type="add", field_ref="dx:S86912A", after={"code": "S86.912A", "first_listed": True}, reason="missed").status_code == 200
    for ev in ({"type": "accept", "field_ref": "line:73562:0"}, {"type": "grade_query", "field_ref": "query:0", "grade": "warranted"},
               {"type": "grade_evidence", "field_ref": "dx:M1711", "span_id": "dx:M1711#0", "grade": "supported"}):
        assert post(review_id, **ev).status_code == 200
    state = ui.get(f"/api/encounter/{review_id}").json()
    assert state["pending"] == {"fields": [], "spans": [], "queries": [], "first_listed": [],
                                "pointers": ["line 73562 points at M1711, which is not a diagnosis on the package"]}
    r = ui.post("/api/approve", json={"encounter_id": review_id})
    assert r.status_code == 400 and "line 73562 points at M1711" in r.json()["detail"] and "pointer box" in r.json()["detail"]
    assert post(review_id, type="edit", field_ref="line:73562:0", after={"pointers": ["S86.912A"]}, reason="wrong_value").status_code == 200
    assert ui.post("/api/approve", json={"encounter_id": review_id}).status_code == 200
    # a recode is different: the line still points at the same diagnosis, so its pointer follows the new code
    assert post(recode_id, type="edit", field_ref="dx:M1711", after={"code": "M17.12"}, reason="specificity").status_code == 200
    state = ui.get(f"/api/encounter/{recode_id}").json()
    assert state["label"]["lines"][0]["pointers"] == ["M1712"] and state["pending"]["pointers"] == [] and state["touches"] == 1
    # blind: not submitted while a line has no pointer or points at nothing
    assert post(blind_id, type="add", field_ref="dx:J069", after={"code": "J06.9", "first_listed": True}).status_code == 200
    assert post(blind_id, type="add", field_ref="line:71046", after={"code": "71046", "modifiers": ["26"]}).status_code == 200
    r = ui.post("/api/blind_submit", json={"encounter_id": blind_id})
    assert r.status_code == 400 and "line 71046 has no diagnosis pointer" in r.json()["detail"] and session.mode(blind_id) == "blind"
    assert ui.get(f"/api/encounter/{blind_id}").json()["pending"]["pointers"] == ["line 71046 has no diagnosis pointer"]
    assert post(blind_id, type="edit", field_ref="line:71046:0", after={"pointers": ["J06.9"]}).status_code == 200
    assert ui.post("/api/blind_submit", json={"encounter_id": blind_id}).status_code == 200


def test_a_package_with_diagnoses_has_exactly_one_first_listed(tmp_path):
    """Removing or un-ticking the first-listed diagnosis left a label with none (a scored field); one batch1
    encounter was approved that way."""
    paths, config, ids = _repo(tmp_path)
    session = ReviewSession(paths, batch="spare", version="dev", coder_id="owner", store_path=None)
    session.store = EventStore(None)
    ui = TestClient(create_review_app(session))
    blind_id, review_id = ids[0], ids[2]

    def post(eid, **ev):
        return ui.post("/api/event", json={"encounter_id": eid, **ev})

    # review: replace the drafted first-listed diagnosis without choosing a new one
    assert post(review_id, type="add", field_ref="dx:E119", after={"code": "E11.9"}, reason="missed").status_code == 200
    assert post(review_id, type="remove", field_ref="dx:M1711", reason="guideline").status_code == 200
    assert post(review_id, type="edit", field_ref="line:73562:0", after={"pointers": ["E11.9"]}, reason="wrong_value").status_code == 200
    for ev in ({"type": "accept", "field_ref": "line:73562:0"}, {"type": "grade_query", "field_ref": "query:0", "grade": "unwarranted"},
               {"type": "grade_evidence", "field_ref": "dx:M1711", "span_id": "dx:M1711#0", "grade": "supported"}):
        assert post(review_id, **ev).status_code == 200
    assert ui.get(f"/api/encounter/{review_id}").json()["pending"]["first_listed"] == ["no diagnosis is marked first-listed"]
    r = ui.post("/api/approve", json={"encounter_id": review_id})
    assert r.status_code == 400 and "no diagnosis is marked first-listed" in r.json()["detail"] and "tick first-listed" in r.json()["detail"]
    assert post(review_id, type="edit", field_ref="dx:E119", after={"code": "E11.9", "first_listed": True}, reason="judgment").status_code == 200
    assert ui.post("/api/approve", json={"encounter_id": review_id}).status_code == 200
    # blind: a label built without ticking first-listed is not submitted
    assert post(blind_id, type="add", field_ref="dx:J069", after={"code": "J06.9"}).status_code == 200
    r = ui.post("/api/blind_submit", json={"encounter_id": blind_id})
    assert r.status_code == 400 and "no diagnosis is marked first-listed" in r.json()["detail"] and session.mode(blind_id) == "blind"
    assert post(blind_id, type="edit", field_ref="dx:J069", after={"code": "J06.9", "first_listed": True}).status_code == 200
    assert ui.post("/api/blind_submit", json={"encounter_id": blind_id}).status_code == 200


def test_typed_codes_must_be_billable_and_modifiers_two_characters(tmp_path):
    """Two of the first four blind labels held a category where the release needs a longer code, and a blind label
    is final. Only a code the coder types is checked, never a drafted code that is merely kept."""
    paths, config, ids = _repo(tmp_path)
    session = ReviewSession(paths, batch="spare", version="dev", coder_id="owner", store_path=None)
    session.store = EventStore(None)
    assert session.codeset is not None and session.codeset.release == "FY2027" and len(session.codeset.codes) > 70000
    ui = TestClient(create_review_app(session))
    blind_id, review_id = ids[0], ids[2]

    def post(eid, **ev):
        return ui.post("/api/event", json={"encounter_id": eid, **ev})

    for code in ("G35", "K95.0", "k59.0"):
        r = post(blind_id, type="add", field_ref="dx:X", after={"code": code})
        assert r.status_code == 400 and "more specific codes exist under it" in r.json()["detail"] and "FY2027" in r.json()["detail"], code
    r = post(blind_id, type="add", field_ref="dx:X", after={"code": "K95.99"})
    assert r.status_code == 400 and "is not in the FY2027 ICD-10-CM code set" in r.json()["detail"]
    assert post(blind_id, type="add", field_ref="dx:K5900", after={"code": "K59.00", "first_listed": True}).status_code == 200
    r = post(blind_id, type="edit", field_ref="dx:K5900", after={"code": "K59.0"})
    assert r.status_code == 400 and "more specific" in r.json()["detail"]
    r = post(blind_id, type="add", field_ref="line:73564", after={"code": "73564", "modifiers": ["26LT"], "pointers": ["K59.00"]})
    assert r.status_code == 400 and "two characters each" in r.json()["detail"]
    assert [e.type for e in session.events(blind_id)] == ["add"]
    # a drafted code that is not in the list can still have its status changed or be accepted: it was not typed here
    session.codeset = parse_billable("# icd10cm.release = FY2027\nE119\n")
    assert post(review_id, type="edit", field_ref="dx:M1711", after={"code": "M17.11", "status": "historical", "first_listed": True}, reason="specificity").status_code == 200
    assert post(review_id, type="edit", field_ref="dx:M1711", after={"code": "M17.12"}, reason="specificity").status_code == 400
    session.codeset = None  # list absent (never the case in the image): shape check only
    assert post(review_id, type="edit", field_ref="dx:M1711", after={"code": "M17.12"}, reason="specificity").status_code == 200


def test_an_empty_blind_submit_in_the_store_is_not_a_blind_label():
    """One reached the batch1 store before the UI refused it (a smoke test, seconds after opening). Reports score every
    blind_label they find against the reviewed label, so it must not pass for the coder's blind coding."""
    base = dict(coder_id="c", encounter_id="E", batch="b", version="v")
    draft = {"diagnoses": [{"code": "E291", "first_listed": True}], "lines": []}
    events = [
        Event(ts="2026-09-19T21:15:28Z", type="open", mode="blind", **base),
        Event(ts="2026-09-19T21:15:35Z", type="blind_submit", mode="blind", after={"diagnoses": [], "lines": []}, **base),
        Event(ts="2026-09-19T21:51:46Z", type="accept", mode="review", field_ref="dx:E291", **base),
        Event(ts="2026-09-19T21:52:42Z", type="approve", mode="review", **base),
    ]
    rec = replay("E", "c", draft, events)
    assert rec.blind_label is None and [d.code for d in rec.label.diagnoses] == ["E291"]
    events[1] = Event(ts="2026-09-19T21:15:35Z", type="blind_submit", mode="blind", after={"diagnoses": [{"code": "E29.1", "first_listed": True}], "lines": []}, **base)
    assert [d.code for d in replay("E", "c", draft, events).blind_label.diagnoses] == ["E291"]


def test_an_edit_that_changes_nothing_is_not_a_touch():
    """Such events are in the batch1 store from before the guard existed; replay and findings must not count them."""
    base = dict(coder_id="c", encounter_id="E", batch="b", version="v", mode="review")
    draft = {"diagnoses": [{"code": "R1033", "first_listed": True}], "lines": [{"code": "74018", "modifiers": ["26"], "units": 1, "pointers": ["R1033"]}]}
    events = [
        (1, Event(ts="2026-09-19T10:00:00Z", type="open", **base)),
        (2, Event(ts="2026-09-19T10:01:00Z", type="edit", field_ref="dx:R1033", after={"code": "R1033", "status": "active", "first_listed": True}, reason="guideline", **base)),
        (3, Event(ts="2026-09-19T10:02:00Z", type="edit", field_ref="line:74018:0", after={"code": "74018", "modifiers": ["26"], "units": 1, "pointers": ["R1033"]}, reason="query_needed", **base)),
        (4, Event(ts="2026-09-19T10:03:00Z", type="edit", field_ref="dx:R1033", after={"code": "R10.30", "status": "active", "first_listed": True}, reason="query_needed", **base)),
        (5, Event(ts="2026-09-19T10:04:00Z", type="remove", field_ref="dx:Z999", reason="unsupported", **base)),
        (6, Event(ts="2026-09-19T10:05:00Z", type="approve", **base)),
    ]
    rec = replay("E", "c", draft, [e for _, e in events])
    assert rec.touches == 1 and [d.code for d in rec.label.diagnoses] == ["R1030"] and [ln.code for ln in rec.label.lines] == ["74018"]
    assert ineffective_touch_ids(draft, events) == {2, 3, 5}


def test_replay_is_deterministic_and_minutes_capped():
    base = dict(coder_id="c", encounter_id="E", batch="b", version="v", mode="review")
    events = [
        Event(ts="2026-09-17T10:00:00Z", type="open", **base),
        Event(ts="2026-09-17T10:00:30Z", type="edit", field_ref="dx:M1711", after={"code": "M1712"}, reason="specificity", **base),
        Event(ts="2026-09-17T10:10:30Z", type="remove", field_ref="line:73562:0", reason="unsupported", **base),  # 10 min gap capped at 2 min
        Event(ts="2026-09-17T10:11:00Z", type="add", field_ref="dx:E119", after={"code": "E11.9"}, reason="missed", **base),
        Event(ts="2026-09-17T10:11:20Z", type="approve", **base),
    ]
    draft = {"diagnoses": [{"code": "M1711", "first_listed": True}], "lines": [{"code": "73562", "modifiers": ["RT"], "units": 1, "pointers": ["M1711"]}]}
    a = replay("E", "c", draft, events)
    b = replay("E", "c", draft, events)
    assert a == b and a.touches == 3 and [d.code for d in a.label.diagnoses] == ["M1712", "E119"] and a.label.lines == []
    assert a.label.diagnoses[0].first_listed and review_minutes(events) == round((30 + 120 + 30 + 20) / 60, 3)


def test_event_store_roundtrip(tmp_path):
    store = EventStore(tmp_path / "events.sqlite")
    e = Event(ts="t", coder_id="c", encounter_id="E", batch="b", version="v", mode="review", type="edit", field_ref="dx:X", after={"code": "Y"}, reason="wrong_value")
    store.append(e)
    assert store.for_encounter("E") == [e]
    store.export_jsonl(tmp_path / "events.jsonl")
    again = EventStore.from_jsonl(tmp_path / "events.jsonl")
    assert again.for_encounter("E") == [e]


def test_holdout_labeling_mode_never_opens_predictions_and_seals_labels(tmp_path):
    paths, config, ids = _repo(tmp_path)
    session = ReviewSession(paths, batch="holdout", version="holdout", coder_id="cpc1", holdout_labeling=True, passphrase=FAKE_KEY, store_path=None)
    session.store = EventStore(None)
    ui = TestClient(create_review_app(session))
    hid = sorted(session.encounters)[0]
    assert len(session.encounters) == 40 and hid in set(paths.holdout_ids.read_text().split())
    r = ui.get(f"/api/encounter/{hid}").json()
    assert r["mode"] == "holdout" and r["draft"] is None
    ui.post("/api/event", json={"encounter_id": hid, "type": "add", "field_ref": "dx:J069", "after": {"code": "J06.9", "first_listed": True}})
    assert ui.post("/api/blind_submit", json={"encounter_id": hid}).status_code == 200
    assert session._predictions is None and not (paths.runs / "holdout").exists()
    sealed = decrypt_from_file(paths.holdout_labels_enc, FAKE_KEY).decode("utf-8").splitlines()
    assert len(sealed) == 1 and json.loads(sealed[0])["label"]["diagnoses"][0]["code"] == "J069"
    # the holdout label file is encrypted and no plaintext label was written under data/labels or runs
    assert not list(paths.labels.glob("holdout*")) and paths.holdout_labels_enc.read_bytes().startswith(b"CLSEAL01")
