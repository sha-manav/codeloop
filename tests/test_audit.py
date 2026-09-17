import json

from fastapi.testclient import TestClient

from codeloop.audit.report import build_report, category_stats
from codeloop.audit.responses import SpotCheckEvent, append_event, latest_grades, load_events
from codeloop.audit.run import load_results, run_audit
from codeloop.audit.sample import draw_spot_check, write_spot_check_sample
from codeloop.audit.schema import AuditResult
from codeloop.audit.ui import create_app
from codeloop.llm import FakeProvider, LLMCache, LLMClient, PromptStore, load_models_config
from codeloop.util.jsonl import write_jsonl
from tests.synthetic import make_repo, synthetic_encounters


def _responder(system, user, schema, params):
    eid = user.split("Encounter ")[1].split(" ")[0]
    n = int(eid[3:])
    flags = []
    if n % 3 == 0:
        flags.append({"category": "in_office_injection", "description": "injection", "evidence_quote": f"Knee pain, visit number {n}.", "evidence_source": "note", "confidence": "high", "facts": {"product": "synthetic", "route": "IM"}})
    if n % 5 == 0:
        flags.append({"category": "immunization", "description": "flu shot", "evidence_quote": "Denies fever", "evidence_source": "note", "confidence": "medium", "facts": {"product": "flu", "counseling_documented": True}})
    if n % 7 == 0:
        flags.append({"category": "waived_in_office_test", "description": "strep", "evidence_quote": "not in the note at all", "evidence_source": "note", "confidence": "low", "facts": {}})
    return {"flags": flags, "patient": {"age_years": 40 + n % 30, "age_evidence": None, "sex": "female" if n % 2 else "male", "sex_evidence": None}}


def _setup(tmp_path, n_dev=60):
    paths, config = make_repo(tmp_path)
    encs = synthetic_encounters()[:n_dev]
    write_jsonl(paths.dev_encounters, encs)
    provider = FakeProvider(_responder)
    client = LLMClient(load_models_config(paths.models_yaml), PromptStore(paths.root / "prompts"), provider=provider, cache=LLMCache(None))
    return paths, config, encs, client, provider


def test_run_audit_locates_spans_and_is_idempotent_via_cache(tmp_path):
    paths, config, encs, client, provider = _setup(tmp_path)
    summary = run_audit(paths, client, encs, seed=1, concurrency=3, run_id="audit-test")
    assert summary.n_encounters == 60 and summary.failures == [] and summary.model == "claude-opus-5"
    results = load_results(paths)
    assert len(results) == 60
    r = results["D2N015"]  # 15: injection (3) + immunization (5)
    assert [f["category"] for f in r["result"]["flags"]] == ["in_office_injection", "immunization"]
    assert r["flag_spans"][0]["text"] == "Knee pain, visit number 15." and r["flag_spans"][1]["text"] == "Denies fever"
    assert results["D2N021"]["flag_spans"][1] is None  # 21: injection + unlocatable waived test quote
    assert AuditResult.model_validate(r["result"]).patient.sex == "female"
    again = run_audit(paths, client, encs[:10], seed=1, run_id="audit-test-2")
    assert again.cache_hits == 10 and len(provider.calls) == 60 and len(load_results(paths)) == 60


def test_sample_draws_flagged_and_random_arms_deterministically(tmp_path):
    paths, config, encs, client, _ = _setup(tmp_path)
    run_audit(paths, client, encs, seed=1, run_id="t")
    results = load_results(paths)
    s1 = draw_spot_check(results, n=30, seed=7)
    s2 = draw_spot_check(results, n=30, seed=7)
    assert s1["arms"] == s2["arms"] and len(s1["arms"]["flagged"]) == 15 and len(s1["arms"]["random"]) == 15
    assert all(results[i]["result"]["flags"] for i in s1["arms"]["flagged"])
    assert not set(s1["arms"]["flagged"]) & set(s1["arms"]["random"])
    assert draw_spot_check(results, n=30, seed=8)["arms"] != s1["arms"]
    written = write_spot_check_sample(paths, n=30, seed=7)
    assert written["arms"] == s1["arms"] and (paths.runs / "audit" / "spot_check_sample.json").exists()


def test_responses_report_and_module_decisions(tmp_path):
    paths, config, encs, client, _ = _setup(tmp_path)
    run_audit(paths, client, encs, seed=1, run_id="t")
    write_spot_check_sample(paths, n=30, seed=7)
    results = load_results(paths)
    # grade every flag of every sampled encounter: injections confirmed, immunizations 1-in-2, waived tests denied
    sample = json.loads((paths.runs / "audit" / "spot_check_sample.json").read_text())
    k = 0
    for eid in sample["arms"]["flagged"] + sample["arms"]["random"]:
        for i, f in enumerate(results[eid]["result"]["flags"]):
            if f["category"] == "in_office_injection":
                decision = "confirm"
            elif f["category"] == "immunization":
                decision = "confirm" if k % 2 == 0 else "deny"
                k += 1
            else:
                decision = "deny"
            append_event(paths, SpotCheckEvent(reviewer="cpc", encounter_id=eid, type="grade", flag_index=i, decision=decision))
        append_event(paths, SpotCheckEvent(reviewer="cpc", encounter_id=eid, type="done"))
    append_event(paths, SpotCheckEvent(reviewer="cpc", encounter_id=sample["arms"]["random"][0], type="missed", category="ecg", description="ecg done"))
    # a re-grade overrides the earlier decision
    first = next(e for e in sample["arms"]["flagged"] if results[e]["result"]["flags"][0]["category"] == "in_office_injection")
    append_event(paths, SpotCheckEvent(reviewer="cpc", encounter_id=first, type="grade", flag_index=0, decision="deny", comment="changed my mind"))
    events = load_events(paths)
    grades = latest_grades(events)
    assert grades[(first, 0)].decision == "deny"
    stats = category_stats(results, grades)
    inj = stats["in_office_injection"]
    assert inj["graded"] > 0 and inj["confirmed"] == inj["graded"] - 1 and 0 < inj["precision"] < 1
    assert inj["evaluable_n_est"] == inj["flagged_encounters"] * inj["precision"]
    assert stats["waived_in_office_test"]["precision"] == 0.0 and stats["ecg"]["precision"] is None
    text = build_report(paths, config)
    assert "## Module decisions" in text and "| qw |" in text and "| vaccine_admin |" in text and "ecg done" not in text
    assert "| qw | waived_in_office_test |" in text and "off" in text
    decisions = json.loads((paths.runs / "audit" / "module_decisions.json").read_text())["decisions"]
    assert decisions["qw"]["on"] is False
    counts = json.loads((paths.runs / "audit" / "flag_counts.json").read_text())
    assert counts["D2N015"] == 2 and counts["D2N001"] == 0


def test_ui_serves_sample_and_records_events(tmp_path):
    paths, config, encs, client, _ = _setup(tmp_path)
    run_audit(paths, client, encs, seed=1, run_id="t")
    write_spot_check_sample(paths, n=30, seed=7)
    ui = TestClient(create_app(paths, reviewer="cpc1"))
    home = ui.get("/")
    assert home.status_code == 200 and "Spot-check queue" in home.text and "0/30 done" in home.text
    sample = json.loads((paths.runs / "audit" / "spot_check_sample.json").read_text())
    eid = sample["arms"]["flagged"][0]
    page = ui.get(f"/encounter/{eid}")
    assert page.status_code == 200 and "Audit flags" in page.text and "Confirm" in page.text
    assert ui.get("/encounter/D2N999").status_code == 404
    r = ui.post("/api/event", json={"encounter_id": eid, "type": "grade", "flag_index": 0, "decision": "confirm", "comment": "yes"})
    assert r.status_code == 200
    assert ui.post("/api/event", json={"encounter_id": eid, "type": "grade", "flag_index": 0, "decision": "maybe"}).status_code == 400
    assert ui.post("/api/event", json={"encounter_id": "D2N999", "type": "done"}).status_code == 400
    assert ui.post("/api/event", json={"encounter_id": eid, "type": "done"}).status_code == 200
    events = load_events(paths)
    assert [e.type for e in events] == ["grade", "done"] and events[0].reviewer == "cpc1" and events[0].comment == "yes"
    assert "1/30 done" in ui.get("/").text
