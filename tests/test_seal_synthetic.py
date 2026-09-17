import pytest

from codeloop.ledger import read_entries
from codeloop.schemas.encounter import Encounter
from codeloop.seal.crypto import SealKeyError, decrypt_from_file
from codeloop.seal.leakage import find_leaks
from codeloop.seal.run import SealError, perform_seal
from codeloop.util.hashing import sha256_text
from codeloop.util.jsonl import read_json, read_jsonl
from tests.synthetic import FAKE_KEY, make_inputs, make_repo, synthetic_encounters


def test_seal_end_to_end_on_synthetic_corpus(tmp_path):
    paths, config = make_repo(tmp_path)
    inputs = make_inputs()
    result = perform_seal(paths, config, inputs, passphrase=FAKE_KEY, actor="tests")

    ids = paths.holdout_ids.read_text(encoding="utf-8").split()
    assert len(ids) == 40 and ids == sorted(ids) and len(set(ids)) == 40
    assert paths.holdout_ids_sha256.read_text(encoding="utf-8").split()[0] == sha256_text("\n".join(ids) + "\n") == result.holdout_ids_sha256
    assert result.allocation == {"aci": 21, "virtassist": 11, "virtscribe": 8}

    hashes = read_json(paths.holdout_content_hashes)
    assert set(hashes) == set(ids)
    by_id = {e.id: e for e in inputs.encounters}
    assert all(hashes[i]["note_sha256"] == by_id[i].note_sha256 for i in ids)

    plaintext = decrypt_from_file(paths.holdout_encounters_enc, FAKE_KEY).decode("utf-8")
    sealed = [Encounter.model_validate_json(ln) for ln in plaintext.splitlines() if ln]
    assert [e.id for e in sealed] == ids and all(by_id[e.id] == e for e in sealed)

    dev = read_jsonl(paths.dev_encounters)
    assert len(dev) == 167 and not ({d["id"] for d in dev} & set(ids))
    amazon = read_jsonl(paths.amazon_labels)
    medcoder = read_jsonl(paths.medcoder_labels)
    assert amazon and medcoder
    assert not ({r["encounter_id"] for r in amazon} & set(ids))
    assert not ({r["encounter_id"] for r in medcoder} & set(ids))
    assert len(amazon) == 167
    assert len(medcoder) == len([e for e in inputs.encounters[:204] if e.id not in ids])

    report = paths.ingest_report.read_text(encoding="utf-8")
    assert "Ingest report" in report and not any(i in report for i in ids)
    manifest = read_json(paths.source_manifest)
    assert manifest["command"] == "seal" and len(manifest["downloads"]) == 3

    remaining = sorted(p.name for p in paths.raw.iterdir())
    assert remaining == [".gitkeep"] and result.raw_entries_deleted == 2

    entries = read_entries(paths.ledger)
    assert entries[-1].event == "seal" and entries[-1].fields["seal_seed"] == str(config.seal_seed)
    assert entries[-1].json_field("allocation") == result.allocation
    assert find_leaks(paths.root) == []

    with pytest.raises(SealError):
        perform_seal(paths, config, inputs, passphrase=FAKE_KEY, actor="tests")


def test_seal_is_deterministic_for_a_given_seed(tmp_path):
    a, ca = make_repo(tmp_path / "a")
    b, cb = make_repo(tmp_path / "b")
    perform_seal(a, ca, make_inputs(), passphrase=FAKE_KEY, actor="tests")
    perform_seal(b, cb, make_inputs(), passphrase=FAKE_KEY, actor="tests")
    assert a.holdout_ids.read_text() == b.holdout_ids.read_text()
    assert a.dev_encounters.read_bytes() == b.dev_encounters.read_bytes()
    assert a.holdout_encounters_enc.read_bytes() != b.holdout_encounters_enc.read_bytes()  # fresh salt/nonce


def test_seal_refuses_partial_corpus_and_weak_key(tmp_path):
    paths, config = make_repo(tmp_path)
    with pytest.raises(SealError):
        perform_seal(paths, config, make_inputs(synthetic_encounters({"aci": 111, "virtassist": 55, "virtscribe": 40})), passphrase=FAKE_KEY, actor="tests")
    with pytest.raises(SealKeyError):
        perform_seal(paths, config, make_inputs(), passphrase="short", actor="tests")
    assert not paths.holdout_ids.exists() and not paths.holdout_encounters_enc.exists()
