import json

from codeloop.paths import Paths
from codeloop.seal.leakage import find_leaks
from codeloop.util.jsonl import write_json, write_jsonl
from tests.synthetic import synthetic_encounters


def _prepare(tmp_path):
    paths = Paths(tmp_path)
    paths.ensure_layout()
    encs = synthetic_encounters()
    holdout = [e.id for e in encs[:40]]
    paths.holdout_ids.write_text("\n".join(holdout) + "\n", encoding="utf-8")
    write_json(paths.holdout_content_hashes, {e.id: {"note_sha256": e.note_sha256, "dialogue_sha256": e.dialogue_sha256} for e in encs[:40]})
    write_jsonl(paths.dev_encounters, encs[40:])
    (paths.reports / "ingest.md").write_text("counts only\n", encoding="utf-8")
    return paths, encs, holdout


def test_clean_tree_has_no_leaks(tmp_path):
    paths, _, _ = _prepare(tmp_path)
    assert find_leaks(paths.root) == []


def test_detects_id_string_content_hash_and_hash_field(tmp_path):
    paths, encs, holdout = _prepare(tmp_path)
    (paths.reports / "bad.md").write_text(f"mentions {holdout[3]}\n", encoding="utf-8")
    write_jsonl(paths.runs / "pred.jsonl", [{"encounter_id": "X", "note": encs[0].note_text}])
    write_json(paths.tasks / "t.json", {"trace": {"note_sha256": encs[1].note_sha256}})
    kinds = {(leak.path, leak.kind) for leak in find_leaks(paths.root)}
    assert ("reports/bad.md", "id_string") in kinds
    assert ("runs/pred.jsonl", "content_hash") in kinds
    assert ("tasks/t.json", "hash_field") in kinds


def test_sealed_and_splits_dirs_are_not_scanned(tmp_path):
    paths, _, holdout = _prepare(tmp_path)
    (paths.sealed / "notes.txt").write_text(holdout[0], encoding="utf-8")
    assert find_leaks(paths.root) == []


def test_no_holdout_means_nothing_to_check(tmp_path):
    paths = Paths(tmp_path)
    paths.ensure_layout()
    (paths.reports / "x.md").write_text("D2N001", encoding="utf-8")
    assert find_leaks(paths.root) == []
    assert json.loads("[]") == []
