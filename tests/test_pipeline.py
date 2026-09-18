import json

from codeloop.agent.pipeline import RunContext, run_encounter
from codeloop.agent.runner import RunError, check_version_state, run_batch
from codeloop.llm import FakeProvider, LLMCache, LLMClient, PromptStore, load_models_config
from codeloop.schemas.encounter import build_encounter
from codeloop.scoring import Scope
from codeloop.seal.run import perform_seal
from codeloop.util.jsonl import read_jsonl
from tests.synthetic import FAKE_KEY, REAL_ROOT, make_inputs, make_repo
from tests.test_scrubber_compliance import SCOPE
from tests.test_tables import synthetic_tables

NOTE = ("CHIEF COMPLAINT\n\nRight knee pain.\n\nRESULTS\n\nX-ray of the right knee, 3 views, taken today shows joint space narrowing.\n\n"
        "ASSESSMENT AND PLAN\n\n1. Right knee osteoarthritis.\n2. Fever, resolved.\nHistory of colon polyps.\n")
DLG = "[doctor] your left knee looks arthritic too .\n[patient] okay ."


def responder(system, user, schema, params):
    name = schema.__name__
    if name == "Extraction":
        return {
            "problems": [
                {"description": "osteoarthritis of the knee", "status": "active", "laterality": "right", "qualifiers": ["primary"],
                 "note_quotes": ["Right knee osteoarthritis."], "dialogue_quotes": []},
                {"description": "osteoarthritis of the knee", "status": "active", "laterality": "left", "qualifiers": [],
                 "note_quotes": [], "dialogue_quotes": ["your left knee looks arthritic too"]},
                {"description": "fever", "status": "ruled_out", "laterality": "not_applicable", "qualifiers": [], "note_quotes": ["Fever, resolved."], "dialogue_quotes": []},
                {"description": "colon polyps", "status": "historical", "laterality": "not_applicable", "qualifiers": [], "note_quotes": ["History of colon polyps."], "dialogue_quotes": []},
            ],
            "services": [
                {"category": "in_office_imaging", "description": "right knee radiograph, 3 views", "body_part": "knee", "laterality": "right", "views": 3,
                 "note_quotes": ["X-ray of the right knee, 3 views, taken today"], "dialogue_quotes": []},
                {"category": "ecg", "description": "ecg", "body_part": None, "laterality": "not_applicable", "views": None, "note_quotes": [], "dialogue_quotes": []},
            ],
            "administrations": [{"product_name": "dexamethasone", "kind": "drug", "dose": "8 mg", "route": "IM", "note_quotes": [], "dialogue_quotes": []}],
            "tests": [],
            "patient": {"age_years": 60, "sex": "female"},
        }
    if name == "DxMapping":
        return {"selections": [
            {"problem_index": 0, "code": "M17.11", "first_listed": True, "laterality_basis": "note", "rationale": "documented right knee OA"},
            {"problem_index": 1, "code": "M17.12", "first_listed": False, "laterality_basis": "dialogue", "rationale": "left side only in transcript"},
            {"problem_index": 2, "code": None, "first_listed": False, "laterality_basis": "none", "rationale": "ruled out"},
            {"problem_index": 3, "code": "Z86.01", "first_listed": False, "laterality_basis": "none", "rationale": "history"},
        ]}
    if name == "LineMapping":
        return {"selections": [{"service_index": 0, "code": "73562", "units": 1, "pointer_problem_indices": [0], "rationale": "3 views knee"}]}
    raise AssertionError(name)


def _client(root, provider):
    return LLMClient(load_models_config(root / "config" / "models.yaml"), PromptStore(root / "prompts"), provider=provider, cache=LLMCache(None))


def test_run_encounter_end_to_end():
    enc, _ = build_encounter(id="D2N001", subset="aci", split_orig="t", dialogue_raw=DLG, note_raw=NOTE)
    provider = FakeProvider(responder)
    ctx = RunContext(paths=None, version="dev", run_id="r1", llm=_client(REAL_ROOT, provider), tables=synthetic_tables(), scope=SCOPE,
                     scope_hash="s", evidence_policy="note_only", on_date="20261001", seed=1, prompt_hashes={})
    trace = run_encounter(enc, ctx)
    pkg = trace.package
    assert [s.name for s in trace.stages] == ["ingest", "extract", "map_dx", "map_lines", "assemble", "validate"]
    codes = {d.code: d for d in pkg.diagnoses}
    assert set(codes) == {"M1711", "Z8601"} and codes["M1711"].first_listed and codes["Z8601"].status == "historical"
    # left-knee OA supported only by the transcript: downgraded under note_only -> provider query, no dx
    q = [x for x in pkg.provider_queries if "laterality" in x.field_ref or x.field_ref.startswith("dx:M171")]
    assert q and any(s.source == "dialogue" for s in q[0].evidence)
    assert [(ln.code, ln.modifiers, ln.units, ln.pointers) for ln in pkg.lines] == [("73562", ["26", "RT"], 1, ["M1711"])]
    assert pkg.lines[0].evidence[0].source == "note" and pkg.compliance.passed and pkg.compliance.checked
    assert pkg.scrubber == [] and any("dexamethasone" in g.missing.lower() or "J1100" in g.missing for g in pkg.data_gaps) is False
    assert any("administration" in g.field_ref for g in pkg.data_gaps) is False  # dexamethasone resolves via the synthetic ASP row
    assert trace.stages[3].output["administrations"][0]["hcpcs"] == "J1100" and trace.stages[3].output["administrations"][0]["units"] == 8
    assert len(provider.calls) == 3
    dumped = json.loads(pkg.model_dump_json())
    assert dumped["diagnoses"][0]["evidence"][0]["text"] == "Right knee osteoarthritis."


def test_run_batch_writes_predictions_and_manifest(tmp_path):
    paths, config = make_repo(tmp_path)
    perform_seal(paths, config, make_inputs(), passphrase=FAKE_KEY, actor="tests")
    from codeloop.versioning.freeze import perform_freeze

    (paths.runs / "audit").mkdir(parents=True, exist_ok=True)
    dev_ids = [line.split('"id": "')[1][:6] for line in paths.dev_encounters.read_text(encoding="utf-8").splitlines() if '"id": "' in line]
    (paths.runs / "audit" / "flag_counts.json").write_text(json.dumps({i: 0 for i in dev_ids}), encoding="utf-8")
    paths.scope_yaml.write_text(SCOPE.model_dump_json(), encoding="utf-8")
    perform_freeze(paths, actor="tests", do_git=False)
    provider = FakeProvider(lambda s, u, schema, p: {"problems": [], "services": [], "administrations": [], "tests": [], "patient": {}} if schema.__name__ == "Extraction" else {"selections": []})
    summary = run_batch(paths, config, version="dev", batch="seed", llm=_client(paths.root, provider), tables=synthetic_tables(),
                        seeds=[1, 2], limit=4, concurrency=2, commit="abc")
    assert summary.n_encounters == 4 and summary.failures == [] and summary.llm_calls == 8
    preds = read_jsonl(paths.root / summary.predictions[1])
    assert len(preds) == 4 and all(p["diagnoses"] == [] for p in preds)
    assert (paths.runs / "dev" / "seed" / "predictions.seed2.jsonl").exists() and (paths.runs / "dev" / "seed" / "run.json").exists()
    manifest = json.loads((paths.runs / "dev" / "seed" / "run.json").read_text())
    assert manifest["seeds"] == [1, 2] and manifest["evidence_policy"] == "note_only" and "extract" in manifest["prompt_hashes"]
    assert (paths.runs / "dev" / "seed" / "traces" / "seed1").exists()
    assert "— run dev seed" in paths.ledger.read_text(encoding="utf-8")


def test_version_state_rules(tmp_path):
    paths, _ = make_repo(tmp_path)
    try:
        check_version_state(paths, "dev", "batch1")
        raise AssertionError("dev on batch1 should be refused")
    except RunError:
        pass
    try:
        check_version_state(paths, "v0", "batch1")
        raise AssertionError("v0 without a tag should be refused")
    except RunError:
        pass


def test_scope_from_test_module():
    assert Scope.model_validate(SCOPE.model_dump()).in_scope_line("73562")
