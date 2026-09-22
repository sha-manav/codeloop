"""`codeloop serve-holdout`: the Phase 9 labeling UI as a container; the seal key is required, labels land on the volume."""

import pytest
from fastapi.testclient import TestClient

from codeloop.review_ui.serve_holdout import HoldoutServeConfigError, HoldoutServeSettings, build_app
from codeloop.review_ui.store import EventStore
from codeloop.seal.crypto import decrypt_from_file
from tests.synthetic import FAKE_KEY
from tests.test_review_ui import _repo


def _env(**over):
    base = {
        "CODELOOP_SEAL_KEY": FAKE_KEY,
        "CODELOOP_CODER_ID": "cpc1",
        "CODELOOP_UI_USER": "cpc",
        "CODELOOP_UI_PASS": "pw-123456",
        "CODELOOP_DATA_DIR": "/tmp/x",
        "CODELOOP_HOLDOUT_SRC": "/tmp/src",
    }
    base.update(over)
    return {k: v for k, v in base.items() if v is not None}


def test_settings_validation():
    s = HoldoutServeSettings.from_env(_env())
    assert s.coder_id == "cpc1" and s.sealed_dir.as_posix() == "/tmp/x/sealed" and s.port == 8080
    for bad in (
        _env(CODELOOP_SEAL_KEY=None),
        _env(CODELOOP_SEAL_KEY=" "),
        _env(CODELOOP_CODER_ID=None),
        _env(CODELOOP_UI_USER=None),
        _env(CODELOOP_UI_PASS=None),
    ):
        with pytest.raises(HoldoutServeConfigError):
            HoldoutServeSettings.from_env(bad)


def test_holdout_app_stages_ciphertext_labels_on_the_volume_and_never_loads_predictions(tmp_path, monkeypatch):
    paths, config, ids = _repo(tmp_path)
    monkeypatch.setenv("CODELOOP_UI_USER", "cpc")
    monkeypatch.setenv("CODELOOP_UI_PASS", "pw-123456")
    src = tmp_path / "image-src"
    src.mkdir()
    for name in ("holdout_encounters.enc", "holdout_encounters.enc.meta.json"):
        (src / name).write_bytes((paths.sealed / name).read_bytes())
    vol = tmp_path / "vol"
    settings = HoldoutServeSettings.from_env(_env(CODELOOP_DATA_DIR=str(vol), CODELOOP_HOLDOUT_SRC=str(src)))
    app = build_app(settings, paths.root, FAKE_KEY)
    ui = TestClient(app)
    assert ui.get("/health").status_code == 401 and ui.get("/").status_code == 401
    auth = ("cpc", "pw-123456")
    h = ui.get("/health", auth=auth).json()
    assert h["mode"] == "holdout" and h["encounters"] == 40 and h["labeled"] == 0
    assert (vol / "sealed" / "holdout_encounters.enc").exists()
    holdout_ids = set(paths.holdout_ids.read_text().split())
    hid = sorted(holdout_ids)[0]
    r = ui.get(f"/api/encounter/{hid}", auth=auth).json()
    assert r["mode"] == "holdout" and r["draft"] is None
    ev = {"encounter_id": hid, "type": "add", "field_ref": "dx:J069", "after": {"code": "J06.9", "first_listed": True}}
    assert ui.post("/api/event", auth=auth, json=ev).status_code == 200
    assert ui.post("/api/blind_submit", auth=auth, json={"encounter_id": hid}).status_code == 200
    assert ui.get("/health", auth=auth).json()["labeled"] == 1
    # every sealed artefact is on the volume, encrypted; nothing under the repo's data/sealed or data/labels changed
    enc = vol / "sealed" / "holdout_labels.enc"
    assert enc.read_bytes().startswith(b"CLSEAL01") and not paths.holdout_labels_enc.exists()
    rows = decrypt_from_file(enc, FAKE_KEY).decode("utf-8").splitlines()
    assert len(rows) == 1 and '"coder_id": "cpc1"' in rows[0]
    assert EventStore(vol / "sealed" / "holdout_events.sqlite").for_encounter(hid)[-1].type == "blind_submit"
    assert not list(paths.labels.glob("holdout*")) and not (paths.runs / "holdout").exists()


def test_missing_ciphertext_refuses_to_start(tmp_path, monkeypatch):
    paths, config, ids = _repo(tmp_path)
    monkeypatch.setenv("CODELOOP_UI_USER", "cpc")
    monkeypatch.setenv("CODELOOP_UI_PASS", "pw-123456")
    settings = HoldoutServeSettings.from_env(
        _env(CODELOOP_DATA_DIR=str(tmp_path / "vol"), CODELOOP_HOLDOUT_SRC=str(tmp_path / "nowhere"))
    )
    with pytest.raises(HoldoutServeConfigError):
        build_app(settings, paths.root, FAKE_KEY)
