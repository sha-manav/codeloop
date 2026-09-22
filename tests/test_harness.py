"""Phase 7 acceptance: a synthetic finding flows findings extract -> package -> task folder -> gate check,
plus eval runner, version freeze, sealed holdout prediction and single-shot scoring, and reports."""

import json
import os
import subprocess

import pytest

from codeloop.evals.runner import run_suite
from codeloop.evals.suites import EvalSuite
from codeloop.findings.extract import extract_findings
from codeloop.findings.package import package_finding
from codeloop.gate.check import gate_check
from codeloop.holdout.score import HoldoutError, holdout_score, verify_scorer
from codeloop.holdout.sealed import sealed_predict
from codeloop.llm import FakeProvider, LLMCache, LLMClient, PromptStore, load_models_config
from codeloop.reporting.report import build_reports
from codeloop.review_ui.labels import build_labels
from codeloop.review_ui.store import EventStore
from codeloop.schemas.event import Event
from codeloop.seal.crypto import encrypt_to_file
from codeloop.seal.run import perform_seal
from codeloop.util.hashing import sha256_text
from codeloop.util.jsonl import read_jsonl, write_jsonl
from codeloop.versioning.freeze import perform_freeze
from codeloop.versioning.versions import VersionError, freeze_version
from tests.synthetic import FAKE_KEY, make_inputs, make_repo
from tests.test_scrubber_compliance import SCOPE
from tests.test_tables import synthetic_tables

BATCH = "batch1"


def _extraction_for(eid: str, note: str, right_knee: bool):
    """Deterministic fake extraction: every encounter gets a knee OA problem; 'right_knee' controls laterality."""
    return {
        "problems": [{"description": "osteoarthritis of the knee", "status": "active", "laterality": "right" if right_knee else "unspecified",
                      "qualifiers": [], "note_quotes": ["Knee pain"], "dialogue_quotes": []},
                     {"description": "fever", "status": "active", "laterality": "not_applicable", "qualifiers": [], "note_quotes": ["Denies fever"], "dialogue_quotes": []}],
        "services": [], "administrations": [], "patient": {},
    }


def _provider(good: bool):
    """Base behaviour codes M1710 (unspecified); the 'good' head behaviour codes M1711 (right), matching gold."""

    def fn(system, user, schema, params):
        name = schema.__name__
        if name == "Extraction":
            eid = user.split("Encounter ")[1].split(" ")[0]
            return _extraction_for(eid, "", right_knee=good)
        if name == "DxMapping":
            return {"selections": [
                {"problem_index": 0, "code": "M17.11" if good else "M17.10", "first_listed": True, "laterality_basis": "note", "rationale": "x"},
                {"problem_index": 1, "code": "R50.9", "first_listed": False, "laterality_basis": "none", "rationale": "x"},
            ]}
        return {"selections": []}

    return fn


def _client(root, provider, cache=True):
    return LLMClient(load_models_config(root / "config" / "models.yaml"), PromptStore(root / "prompts"), provider=provider,
                     cache=LLMCache(None) if cache else None, cache_enabled=cache)


def _repo(tmp_path):
    paths, config = make_repo(tmp_path)
    perform_seal(paths, config, make_inputs(), passphrase=FAKE_KEY, actor="tests")
    (paths.runs / "audit").mkdir(parents=True, exist_ok=True)
    dev_ids = [line.split('"id": "')[1][:6] for line in paths.dev_encounters.read_text(encoding="utf-8").splitlines() if '"id": "' in line]
    (paths.runs / "audit" / "flag_counts.json").write_text(json.dumps({i: 0 for i in dev_ids}), encoding="utf-8")
    paths.scope_yaml.write_text(SCOPE.model_dump_json(), encoding="utf-8")
    perform_freeze(paths, actor="tests", do_git=False)
    return paths, config


def _seed_labels_and_events(paths, ids, version="v0"):
    """Simulate v0 predictions (M1710 unspecified) and a coder who corrects the first 6 encounters to M1711."""
    preds = []
    for eid in ids:
        preds.append({"encounter_id": eid, "version": version, "run_id": "r", "diagnoses": [
            {"code": "M1710", "status": "active", "first_listed": True, "evidence": [{"source": "note", "start": 0, "end": 5, "text": "CHIEF", "sha256": sha256_text("CHIEF")}], "rationale": "r"},
            {"code": "R509", "status": "active", "first_listed": False, "evidence": [], "rationale": "r"}],
            "lines": [], "provider_queries": [], "data_gaps": [], "scrubber": [],
            "compliance": {"policy": "note_only", "checked": True, "passed": True, "issues": [], "downgraded_fields": []}})
    write_jsonl(paths.runs / version / BATCH / "predictions.jsonl", preds)
    store = EventStore(paths.review_dir(version, BATCH) / "events.sqlite")
    base = dict(coder_id="cpc", batch=BATCH, version=version, mode="review")
    for k, eid in enumerate(ids):
        store.append(Event(ts=f"2026-10-01T10:{k:02d}:00Z", encounter_id=eid, type="open", **base))
        if k < 6:
            store.append(Event(ts=f"2026-10-01T10:{k:02d}:30Z", encounter_id=eid, type="edit", field_ref="dx:M1710", after={"code": "M17.11"}, reason="specificity", **base))
        else:
            store.append(Event(ts=f"2026-10-01T10:{k:02d}:30Z", encounter_id=eid, type="accept", field_ref="dx:M1710", **base))
        if k == 0:
            store.append(Event(ts=f"2026-10-01T10:{k:02d}:40Z", encounter_id=eid, type="remove", field_ref="dx:R509", reason="unsupported", **base))
        store.append(Event(ts=f"2026-10-01T10:{k:02d}:50Z", encounter_id=eid, type="approve", **base))
    return store


def test_findings_package_gate_end_to_end(tmp_path):
    paths, config = _repo(tmp_path)
    ids = json.loads(paths.dev_split.read_text())["sets"][BATCH][:10]
    store = _seed_labels_and_events(paths, ids)
    # an Edit pressed on unchanged values carries a reason but no correction: not a touch, never a finding
    store.append(Event(ts="2026-10-01T10:01:45Z", coder_id="cpc", batch=BATCH, version="v0", mode="review", encounter_id=ids[1], type="edit",
                       field_ref="dx:R509", after={"code": "R50.9", "status": "active", "first_listed": False}, reason="guideline"))
    r = build_labels(paths, BATCH, version="v0", store=store, actor="tests") if False else build_labels(paths, batch=BATCH, version="v0", store=store, actor="tests")
    assert r.approved == 10
    assert {x["encounter_id"]: x["touches"] for x in read_jsonl(paths.labels_file(BATCH))}[ids[1]] == 1
    findings = extract_findings(paths, config, batch=BATCH)
    by_key = {f.grouping_key: f for f in findings}
    assert "guideline|dx|core_dx|R50" not in by_key
    spec = by_key["specificity|dx|core_dx|M17"]
    assert spec.status == "eligible" and spec.count == 6 and spec.id.startswith("FIND-DX-")
    assert by_key["unsupported|dx|core_dx|R50"].status == "candidate"
    # a second extract on the same batch is idempotent (same ids, same counts)
    again = extract_findings(paths, config, batch=BATCH)
    assert {f.id: f.count for f in again} == {f.id: f.count for f in findings}
    # ... and does not promote a same-batch candidate as if the key had been seen in a prior batch
    assert {f.id: f.status for f in again} == {f.id: f.status for f in findings}
    assert {f.grouping_key: f for f in again}["unsupported|dx|core_dx|R50"].status == "candidate"
    out = package_finding(paths, config, spec.id, store=store)
    task_dir = paths.tasks / spec.id
    assert (task_dir / "task.yaml").exists() and (task_dir / "EXEC_PLAN.md").exists() and (task_dir / "RESULTS.md").exists()
    ds = json.dumps(__import__("yaml").safe_load((paths.root / out["dataset"]).read_text()))
    assert "M1711" in ds and "dx:M1711" in ds and (paths.evals / "suites" / f"targeted-{spec.id}.yaml").exists()
    tables = synthetic_tables()
    # head with the improved behaviour: targeted error falls to 0, regression agreement improves -> PASS
    good = gate_check(paths, config, task_dir=task_dir, base="base000", head="head000", llm=_client(paths.root, FakeProvider(_provider(True))),
                      tables=tables, runs=2, seeds=[1, 2], actor="tests")
    assert good.passed, [c.__dict__ for c in good.checks]
    assert (task_dir / "GATE.md").read_text().count("PASS") >= 1 and good.numbers["head_targeted_error"] == 0.0 and good.numbers["base_targeted_error"] == 1.0
    # head identical to base behaviour: targeted error does not fall -> FAIL
    bad = gate_check(paths, config, task_dir=task_dir, base="base000", head="head000", llm=_client(paths.root, FakeProvider(_provider(False))),
                     tables=tables, runs=1, seeds=[1], actor="tests")
    assert not bad.passed and any(c.name == "targeted" and not c.passed for c in bad.checks)
    # eval results were written with per-run and mean/variance
    res = sorted((paths.evals / "results" / f"targeted-{spec.id}").glob("*.json"))
    assert res and "variance" in json.loads(res[0].read_text())


def test_eval_runner_reports_variance(tmp_path):
    paths, config = _repo(tmp_path)
    ids = json.loads(paths.dev_split.read_text())["sets"][BATCH][:4]
    store = _seed_labels_and_events(paths, ids)
    build_labels(paths, batch=BATCH, version="v0", store=store, actor="tests")
    suite = EvalSuite(name="regression-test", kind="regression", gold=[f"data/labels/{BATCH}.jsonl"], base_version="v0", runs=2, seeds=[1, 2])
    p = paths.evals / "suites" / "regression-test.yaml"
    suite.save(p)
    calls = {"n": 0}

    def flaky(system, user, schema, params):
        calls["n"] += 1
        return _provider(calls["n"] % 3 == 0)(system, user, schema, params)

    r = run_suite(paths, config, p, llm=_client(paths.root, FakeProvider(flaky), cache=False), tables=synthetic_tables())
    assert r.n_encounters == 4 and len(r.runs) == 2 and r.mean["mean_agreement"] is not None and r.variance["mean_agreement"] is not None
    assert r.runs[0].escalation_checked == 4


def test_version_freeze_sealed_predict_and_single_shot_score(tmp_path, monkeypatch):
    paths, config = _repo(tmp_path)
    tables = synthetic_tables()
    # version freeze without git: VERSION.md + ledger (the sealed prediction is stubbed here and run explicitly below)
    r = freeze_version(paths, "v0", sealed_predict=lambda v: None, do_git=False, actor="tests")
    assert (paths.versions / "v0" / "VERSION.md").exists() and r.hashes["scoring_tree"] and "prompt:extract" in r.hashes
    client = _client(paths.root, FakeProvider(_provider(True)), cache=False)
    digest = sealed_predict(paths, config, "v0", llm=client, tables=tables, passphrase=FAKE_KEY, concurrency=2, check_tag=False, actor="tests")
    assert (paths.sealed / "predictions_v0.enc").exists() and (paths.sealed / "predictions_v0.sha256").read_text().startswith(digest)
    assert not list(paths.runs.glob("**/holdout*")) and not list(paths.root.glob("**/traces_v0.json"))
    # cache must be off
    from codeloop.holdout.sealed import SealedPredictError

    with pytest.raises(SealedPredictError):
        sealed_predict(paths, config, "v1", llm=_client(paths.root, FakeProvider(_provider(True)), cache=True), tables=tables, passphrase=FAKE_KEY, check_tag=False)
    with pytest.raises(VersionError):
        freeze_version(paths, "v0", sealed_predict=lambda v: None, do_git=False)  # sealed predictions exist
    with pytest.raises(VersionError):
        freeze_version(paths, "x1", sealed_predict=lambda v: None, do_git=False)
    assert verify_scorer(paths, actor="tests")
    # holdout labels: primary coder labels all 40 with the 'good' answer; second coder labels 5
    holdout_ids = paths.holdout_ids.read_text().split()
    recs = [{"encounter_id": e, "coder_id": "cpc1", "label": {"diagnoses": [{"code": "M1711", "first_listed": True}, {"code": "R509"}], "lines": []}} for e in holdout_ids]
    recs += [{"encounter_id": e, "coder_id": "cpc2", "label": {"diagnoses": [{"code": "M1711", "first_listed": True}], "lines": []}} for e in holdout_ids[:5]]
    encrypt_to_file("".join(json.dumps(x) + "\n" for x in recs).encode(), paths.holdout_labels_enc, FAKE_KEY, label="holdout_labels")
    # a second version with the worse behaviour
    sealed_predict(paths, config, "v1", llm=_client(paths.root, FakeProvider(_provider(False)), cache=False), tables=tables, passphrase=FAKE_KEY, check_tag=False, actor="tests")
    res = holdout_score(paths, config, passphrase=FAKE_KEY, do_git=False, actor="tests")
    assert res["per_version"]["v0"]["mean_agreement"] == 1.0 and res["per_version"]["v1"]["mean_agreement"] < 1.0
    assert "v0->v1" in res["pairwise"] and res["pairwise"]["v0->v1"]["diff"] < 0 and res["human_human"]["n"] == 5
    assert isinstance(res["per_version"]["v0"]["core_lines"], str) and res["per_version"]["v0"]["core_lines"].startswith("insufficient")
    assert (paths.reports / "holdout.md").exists() and (paths.sealed / "SCORED.lock").exists() and (paths.runs / "holdout" / "labels.jsonl").exists()
    with pytest.raises(HoldoutError):
        holdout_score(paths, config, passphrase=FAKE_KEY, do_git=False)


def test_reports_regenerate(tmp_path):
    paths, config = _repo(tmp_path)
    ids = json.loads(paths.dev_split.read_text())["sets"][BATCH][:8]
    store = _seed_labels_and_events(paths, ids)
    build_labels(paths, batch=BATCH, version="v0", store=store, actor="tests")
    summary = build_reports(paths)
    assert summary["cells"] and summary["cells"][0]["tag"] == "live" and summary["cells"][0]["touches_mean"] > 0
    index = (paths.reports / "index.md").read_text()
    assert "| v0 | batch1 | live |" in index and (paths.reports / "curve.svg").exists() and "not scored yet" in index


def test_run_version_state_uses_code_tree_match(tmp_path, monkeypatch):
    from codeloop.agent.runner import RunError, check_version_state
    from codeloop.versioning import git

    paths, config = _repo(tmp_path)
    for k, v in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}.items():
        monkeypatch.setenv(k, v)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=paths.root, check=True)
    (paths.root / ".gitignore").write_text("*.sqlite\n.building\n", encoding="utf-8")
    git.commit_all(paths.root, "init")
    git.create_tag(paths.root, "freeze", "f")
    git.create_tag(paths.root, "v0", "v0")
    assert check_version_state(paths, "v0", BATCH)
    (paths.runs / "v0").mkdir(parents=True, exist_ok=True)
    (paths.runs / "v0" / "note.txt").write_text("run output", encoding="utf-8")
    git.commit_all(paths.root, "outputs")
    assert check_version_state(paths, "v0", BATCH)  # code unchanged -> allowed off the tag
    (paths.root / "prompts" / "extract.txt").write_text("changed", encoding="utf-8")
    git.commit_all(paths.root, "prompt change")
    with pytest.raises(RunError):
        check_version_state(paths, "v0", BATCH)
    (paths.root / "prompts" / "extract.txt").write_text("dirty", encoding="utf-8")
    with pytest.raises(RunError):
        check_version_state(paths, "v0", BATCH)
    assert os.environ["GIT_AUTHOR_NAME"] == "t"
