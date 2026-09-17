import json

from fastapi.testclient import TestClient

from codeloop.review_ui.app import ReviewSession, create_review_app
from codeloop.review_ui.labels import build_labels
from codeloop.review_ui.replay import replay, review_minutes
from codeloop.review_ui.store import EventStore
from codeloop.schemas.event import Event
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
    # labels build: only approved encounters, with touches/minutes/grades; blind label kept separately
    ui.post("/api/approve", json={"encounter_id": blind_id})
    result = build_labels(paths, batch="spare", version="dev", store=session.store, actor="tests")
    assert result.approved == 2 and len(result.pending) == len(ids) - 2
    labels = {r["encounter_id"]: r for r in read_jsonl(paths.labels_file("spare"))}
    assert labels[review_id]["touches"] == 2 and labels[review_id]["query_grades"] == {"query:0": "warranted"} and labels[review_id]["blind_label"] is None
    assert labels[blind_id]["blind_label"]["diagnoses"][0]["code"] == "E119" and labels[blind_id]["label"]["diagnoses"][0]["code"] == "M1711" and labels[blind_id]["blind_subset"]
    assert (paths.review_dir("dev", "spare") / "events.jsonl").exists()


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
