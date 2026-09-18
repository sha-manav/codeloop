import json
import subprocess

import pytest
from fastapi.testclient import TestClient
from typer.testing import CliRunner

from codeloop.cli import app
from codeloop.ledger import read_entries
from codeloop.review_ui.app import ReviewSession, create_review_app
from codeloop.review_ui.store import EventStore
from codeloop.seal.run import perform_seal
from codeloop.versioning import git
from codeloop.versioning.freeze import FREEZE_TAG, FreezeError, perform_freeze
from codeloop.versioning.versions import VersionError, freeze_version
from tests.synthetic import FAKE_KEY, make_inputs, make_repo
from tests.test_review_ui import _repo as _ui_repo
from tests.test_scrubber_compliance import SCOPE

runner = CliRunner()


def _git_repo(tmp_path, monkeypatch):
    paths, config = make_repo(tmp_path)
    perform_seal(paths, config, make_inputs(), passphrase=FAKE_KEY, actor="tests")
    (paths.runs / "audit").mkdir(parents=True, exist_ok=True)
    dev_ids = [line.split('"id": "')[1][:6] for line in paths.dev_encounters.read_text(encoding="utf-8").splitlines() if '"id": "' in line]
    (paths.runs / "audit" / "flag_counts.json").write_text(json.dumps({i: 0 for i in dev_ids}), encoding="utf-8")
    paths.scope_yaml.write_text(SCOPE.model_dump_json(), encoding="utf-8")
    for k, v in {"GIT_AUTHOR_NAME": "t", "GIT_AUTHOR_EMAIL": "t@x", "GIT_COMMITTER_NAME": "t", "GIT_COMMITTER_EMAIL": "t@x"}.items():
        monkeypatch.setenv(k, v)
    subprocess.run(["git", "init", "-q", "-b", "main"], cwd=paths.root, check=True)
    (paths.root / ".gitignore").write_text("*.sqlite\n*.building\ndata/raw/\n", encoding="utf-8")
    git.commit_all(paths.root, "init")
    return paths, config


def test_freeze_and_version_supersede(tmp_path, monkeypatch):
    paths, config = _git_repo(tmp_path, monkeypatch)
    first = perform_freeze(paths, actor="tests")
    assert git.tag_exists(paths.root, FREEZE_TAG)
    with pytest.raises(FreezeError, match="supersede"):
        perform_freeze(paths, actor="tests")
    # a config change after the freeze -> supersede
    paths.scope_yaml.write_text(SCOPE.model_dump_json().replace("73000-73140", "73000-73140"), encoding="utf-8")
    (paths.root / "note.txt").write_text("changed", encoding="utf-8")
    git.commit_all(paths.root, "change")
    second = perform_freeze(paths, actor="tests", supersede=True, reason="scope corrected after CPC spot-check")
    assert git.tag_exists(paths.root, "freeze-provisional") and git.tag_commit(paths.root, "freeze-provisional") == first.commit
    assert git.tag_exists(paths.root, FREEZE_TAG) and git.tag_commit(paths.root, FREEZE_TAG) == second.commit != first.commit
    assert list(paths.splits.glob("dev_split.provisional-*.json")) and paths.dev_split.exists()
    events = [e.event for e in read_entries(paths.ledger)]
    assert events.count("freeze") == 2 and "freeze superseded (correction)" in events
    assert "scope corrected" in paths.ledger.read_text(encoding="utf-8")
    # version freeze, then supersede it: tag, VERSION.md, sealed files and runs are all renamed
    def fake_predict(v):
        (paths.sealed / f"predictions_{v}.enc").write_bytes(b"CLSEAL01fake")
        (paths.sealed / f"predictions_{v}.sha256").write_text("x\n", encoding="utf-8")
        return "x"
    v0 = freeze_version(paths, "v0", sealed_predict=fake_predict, actor="tests")
    (paths.runs / "v0" / "batch1").mkdir(parents=True, exist_ok=True)
    (paths.runs / "v0" / "batch1" / "predictions.jsonl").write_text("", encoding="utf-8")
    git.commit_all(paths.root, "v0 batch1 drafts")
    with pytest.raises(VersionError, match="supersede"):
        freeze_version(paths, "v0", sealed_predict=fake_predict, actor="tests")
    v0b = freeze_version(paths, "v0", sealed_predict=fake_predict, actor="tests", supersede=True, reason="re-frozen after scope fix")
    assert git.tag_commit(paths.root, "v0-provisional") == v0.tag_commit and git.tag_commit(paths.root, "v0") == v0b.tag_commit
    assert (paths.versions / "v0-provisional" / "VERSION.md").exists() and (paths.versions / "v0" / "VERSION.md").exists()
    assert (paths.sealed / "predictions_v0-provisional.enc").exists() and (paths.sealed / "predictions_v0.enc").exists()
    assert (paths.runs / "v0-provisional" / "batch1").exists() and not (paths.runs / "v0" / "batch1").exists()
    assert "version v0 superseded (correction)" in [e.event for e in read_entries(paths.ledger)]
    # a second supersede gets a numbered provisional name
    v0c = freeze_version(paths, "v0", sealed_predict=fake_predict, actor="tests", supersede=True)
    assert git.tag_exists(paths.root, "v0-provisional-2") and v0c.tag_commit != v0b.tag_commit
    # reports and holdout scoring ignore *-provisional artefacts
    from codeloop.reporting.report import _versions

    assert _versions(paths) == [] and (paths.runs / "v0-provisional" / "batch1").exists()  # provisional dirs are ignored


def test_ledger_note_cli(tmp_path):
    paths, _ = make_repo(tmp_path)
    r = runner.invoke(app, ["ledger", "note", "CPC onboarded on 2026-10-01", "--root", str(paths.root)])
    assert r.exit_code == 0
    entries = read_entries(paths.ledger)
    assert entries[-1].event == "note" and entries[-1].fields["text"] == "CPC onboarded on 2026-10-01"


def test_basic_auth_on_review_and_audit_ui(tmp_path, monkeypatch):
    paths, config, ids = _ui_repo(tmp_path)
    monkeypatch.setenv("CODELOOP_UI_USER", "cpc")
    monkeypatch.setenv("CODELOOP_UI_PASS", "s3cret-password")
    session = ReviewSession(paths, batch="spare", version="dev", coder_id="cpc", store_path=None)
    session.store = EventStore(None)
    ui = TestClient(create_review_app(session))
    assert ui.get("/").status_code == 401 and ui.get("/").headers["www-authenticate"].startswith("Basic")
    assert ui.get("/", auth=("cpc", "wrong")).status_code == 401
    assert ui.get("/", auth=("cpc", "s3cret-password")).status_code == 200
    assert ui.get(f"/api/encounter/{ids[2]}", auth=("cpc", "s3cret-password")).status_code == 200
    # audit UI shares the middleware
    from codeloop.audit.run import run_audit
    from codeloop.audit.sample import write_spot_check_sample
    from codeloop.audit.ui import create_app
    from codeloop.llm import FakeProvider, LLMCache, LLMClient, PromptStore, load_models_config
    from codeloop.schemas.encounter import load_encounters_jsonl
    from tests.test_audit import _responder

    client = LLMClient(load_models_config(paths.models_yaml), PromptStore(paths.root / "prompts"), provider=FakeProvider(_responder), cache=LLMCache(None))
    run_audit(paths, client, load_encounters_jsonl(paths.dev_encounters)[:40], seed=1, run_id="t")
    write_spot_check_sample(paths, n=30, seed=1)
    audit_ui = TestClient(create_app(paths, reviewer="cpc"))
    assert audit_ui.get("/").status_code == 401 and audit_ui.get("/", auth=("cpc", "s3cret-password")).status_code == 200
    # misconfiguration: only one variable set
    monkeypatch.delenv("CODELOOP_UI_PASS")
    with pytest.raises(RuntimeError):
        create_review_app(session)
    # no variables: open access
    monkeypatch.delenv("CODELOOP_UI_USER")
    assert TestClient(create_review_app(session)).get("/").status_code == 200
