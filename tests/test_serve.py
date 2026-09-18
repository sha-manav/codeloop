import json

import pytest
from fastapi.testclient import TestClient

from codeloop.review_ui.labels import build_labels
from codeloop.review_ui.serve import ServeConfigError, ServeSettings, build_app
from codeloop.review_ui.store import EventStore
from codeloop.util.jsonl import read_jsonl
from tests.test_review_ui import _repo


def _env(**over):
    base = {"CODELOOP_UI_MODE": "review", "CODELOOP_BATCH": "spare", "CODELOOP_VERSION": "dev", "CODELOOP_CODER_ID": "cpc1",
            "CODELOOP_UI_USER": "cpc", "CODELOOP_UI_PASS": "pw-123456", "CODELOOP_DATA_DIR": "/tmp/x"}
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}


def test_settings_validation():
    s = ServeSettings.from_env(_env())
    assert s.mode == "review" and s.events_path.as_posix() == "/tmp/x/events/dev_spare.sqlite" and s.port == 8080
    for bad in (_env(CODELOOP_UI_MODE="holdout"), _env(CODELOOP_UI_USER=None), _env(CODELOOP_UI_PASS=None),
                _env(CODELOOP_BATCH=None), _env(CODELOOP_BATCH="holdout"), _env(CODELOOP_UI_MODE=None)):
        with pytest.raises(ServeConfigError):
            ServeSettings.from_env(bad)
    a = ServeSettings.from_env(_env(CODELOOP_UI_MODE="audit", CODELOOP_BATCH=None, CODELOOP_VERSION=None, CODELOOP_CODER_ID=None))
    assert a.mode == "audit" and a.coder_id == "cpc" and a.audit_responses_path.as_posix() == "/tmp/x/audit/spot_check_responses.jsonl"
    assert ServeSettings.from_env(_env(CODELOOP_UI_PASS=None, CODELOOP_UI_PASSWORD="legacy-pw")).mode == "review"


def test_review_mode_writes_events_under_data_dir_and_auths_every_route(tmp_path, monkeypatch):
    paths, config, ids = _repo(tmp_path)
    data_dir = tmp_path / "vol"
    env = _env(CODELOOP_DATA_DIR=str(data_dir))
    for k, v in env.items():
        monkeypatch.setenv(k, v)
    monkeypatch.setenv("CODELOOP_SEAL_KEY", "must-not-be-read-0123456789")
    app = build_app(ServeSettings.from_env(), paths.root)
    ui = TestClient(app)
    assert ui.get("/health").status_code == 401 and ui.get("/").status_code == 401
    auth = ("cpc", "pw-123456")
    h = ui.get("/health", auth=auth).json()
    assert h["ok"] and h["mode"] == "review" and h["batch"] == "spare"
    review_id = ids[2]
    assert ui.post("/api/event", auth=auth, json={"encounter_id": review_id, "type": "accept", "field_ref": "dx:M1711"}).status_code == 200
    store_path = data_dir / "events" / "dev_spare.sqlite"
    assert store_path.exists() and EventStore(store_path).for_encounter(review_id)[0].coder_id == "cpc1"
    assert not (paths.review_dir("dev", "spare") / "events.sqlite").exists()
    # `make fly-pull-events` drops the sqlite under runs/<version>/<batch>/; labels build finds it there unchanged
    pulled = paths.runs / "dev" / "spare" / "events.sqlite"
    pulled.parent.mkdir(parents=True, exist_ok=True)
    pulled.write_bytes(store_path.read_bytes())
    result = build_labels(paths, batch="spare", version="dev", actor="tests")
    assert result.approved == 0 and len(result.pending) == len(ids)


def test_audit_mode_seeds_and_writes_under_data_dir(tmp_path, monkeypatch):
    from codeloop.audit.run import run_audit
    from codeloop.audit.sample import write_spot_check_sample
    from codeloop.llm import FakeProvider, LLMCache, LLMClient, PromptStore, load_models_config
    from codeloop.schemas.encounter import load_encounters_jsonl
    from tests.test_audit import _responder

    paths, config, ids = _repo(tmp_path)
    client = LLMClient(load_models_config(paths.models_yaml), PromptStore(paths.root / "prompts"), provider=FakeProvider(_responder), cache=LLMCache(None))
    run_audit(paths, client, load_encounters_jsonl(paths.dev_encounters)[:40], seed=1, run_id="t")
    write_spot_check_sample(paths, n=30, seed=1)
    seed_line = json.dumps({"ts": "t", "reviewer": "seed", "encounter_id": "X", "type": "note", "comment": "repo copy"})
    (paths.runs / "audit" / "spot_check_responses.jsonl").write_text(seed_line + "\n", encoding="utf-8")
    data_dir = tmp_path / "vol"
    for k, v in _env(CODELOOP_UI_MODE="audit", CODELOOP_BATCH=None, CODELOOP_VERSION=None, CODELOOP_CODER_ID="cpc9", CODELOOP_DATA_DIR=str(data_dir)).items():
        monkeypatch.setenv(k, v)
    ui = TestClient(build_app(ServeSettings.from_env(), paths.root))
    auth = ("cpc", "pw-123456")
    assert ui.get("/").status_code == 401 and ui.get("/", auth=auth).status_code == 200
    target = data_dir / "audit" / "spot_check_responses.jsonl"
    assert target.exists() and read_jsonl(target)[0]["comment"] == "repo copy"  # seeded on first start
    sample = json.loads((paths.runs / "audit" / "spot_check_sample.json").read_text())
    eid = sample["arms"]["flagged"][0]
    assert ui.post("/api/event", auth=auth, json={"encounter_id": eid, "type": "grade", "flag_index": 0, "decision": "confirm"}).status_code == 200
    rows = read_jsonl(target)
    assert len(rows) == 2 and rows[1]["reviewer"] == "cpc9"
    assert len(read_jsonl(paths.runs / "audit" / "spot_check_responses.jsonl")) == 1  # repo copy untouched
