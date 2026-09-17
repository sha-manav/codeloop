import dataclasses

import pytest

from codeloop.ingest.run import IngestError, perform_ingest
from codeloop.schemas.encounter import build_encounter
from codeloop.seal.run import perform_seal
from codeloop.util.hashing import sha256_file
from tests.synthetic import FAKE_KEY, make_inputs, make_repo


def test_ingest_reproduces_sealed_outputs(tmp_path):
    paths, config = make_repo(tmp_path)
    perform_seal(paths, config, make_inputs(), passphrase=FAKE_KEY, actor="tests")
    before = {p: sha256_file(p) for p in (paths.dev_encounters, paths.amazon_labels, paths.medcoder_labels)}
    (paths.raw / "again.csv").write_text("x", encoding="utf-8")
    result = perform_ingest(paths, config, make_inputs(), actor="tests")
    assert result.changed_outputs == [] and result.upstream_drift == []
    assert {p: sha256_file(p) for p in before} == before
    assert sorted(p.name for p in paths.raw.iterdir()) == [".gitkeep"]


def test_ingest_refuses_when_holdout_content_changed(tmp_path):
    paths, config = make_repo(tmp_path)
    perform_seal(paths, config, make_inputs(), passphrase=FAKE_KEY, actor="tests")
    holdout = set(paths.holdout_ids.read_text().split())
    inputs = make_inputs()
    tampered = []
    for e in inputs.encounters:
        if e.id in holdout and not tampered:
            e2, _ = build_encounter(id=e.id, subset=e.subset, split_orig=e.split_orig, dialogue_raw=e.dialogue_text, note_raw=e.note_text + " changed")
            tampered.append(e2)
        else:
            tampered.append(e)
    inputs.encounters = tampered
    with pytest.raises(IngestError, match="holdout content check failed"):
        perform_ingest(paths, config, inputs, actor="tests")


def test_ingest_detects_upstream_drift(tmp_path):
    paths, config = make_repo(tmp_path)
    perform_seal(paths, config, make_inputs(), passphrase=FAKE_KEY, actor="tests")
    inputs = make_inputs()
    inputs.downloads[0] = dataclasses.replace(inputs.downloads[0], sha256="9" * 64)
    with pytest.raises(IngestError, match="upstream drift"):
        perform_ingest(paths, config, inputs, actor="tests")
    result = perform_ingest(paths, config, inputs, actor="tests", allow_upstream_drift=True)
    assert len(result.upstream_drift) == 1
