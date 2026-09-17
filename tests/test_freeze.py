import json

import pytest

from codeloop.schemas.encounter import build_encounter
from codeloop.seal.run import perform_seal
from codeloop.versioning.freeze import (
    FreezeError,
    difficulty_index,
    perform_freeze,
    stratified_split,
    validate_scope,
)
from tests.synthetic import FAKE_KEY, make_inputs, make_repo, synthetic_encounters


def _dev(paths):
    from codeloop.schemas.encounter import load_encounters_jsonl

    return load_encounters_jsonl(paths.dev_encounters)


def test_difficulty_index_is_zscored_sum():
    encs = [build_encounter(id=f"D2N{i:03d}", subset="aci", split_orig="t", dialogue_raw="[doctor] hi", note_raw="x" * (100 * i))[0] for i in range(1, 5)]
    d = difficulty_index(encs, {"D2N001": 1, "D2N002": 2, "D2N003": 3, "D2N004": 4}, {"D2N004": 5})
    assert d["D2N001"]["difficulty"] < d["D2N004"]["difficulty"]
    assert abs(sum(v["z_note_len"] for v in d.values())) < 1e-9
    assert d["D2N004"]["n_audit_flags"] == 5 and d["D2N001"]["n_audit_flags"] == 0


def test_stratified_split_sizes_strata_and_determinism():
    encs = synthetic_encounters()[:167]
    diff = difficulty_index(encs, {e.id: (i % 4) for i, e in enumerate(encs)}, {e.id: (i % 3) for i, e in enumerate(encs)})
    sizes = {"seed": 20, "batch1": 45, "batch2": 45, "batch3": 45, "spare": 12}
    s1 = stratified_split(encs, diff, sizes=sizes, blind_per_batch=5, seed=3)
    s2 = stratified_split(encs, diff, sizes=sizes, blind_per_batch=5, seed=3)
    assert s1["sets"] == s2["sets"] and s1["blind"] == s2["blind"]
    assert {k: len(v) for k, v in s1["sets"].items()} == sizes
    all_ids = sorted(i for v in s1["sets"].values() for i in v)
    assert all_ids == sorted(e.id for e in encs)
    for b in ("batch1", "batch2", "batch3"):
        assert len(s1["blind"][b]) == 5 and set(s1["blind"][b]) <= set(s1["sets"][b])
    # subset proportions roughly preserved in every batch (aci 112/167 of the synthetic corpus)
    for b in ("batch1", "batch2", "batch3"):
        assert 25 <= s1["summary"][b]["subsets"]["aci"] <= 36
    assert stratified_split(encs, diff, sizes=sizes, blind_per_batch=5, seed=4)["sets"] != s1["sets"]
    with pytest.raises(FreezeError):
        stratified_split(encs, diff, sizes={**sizes, "spare": 11}, blind_per_batch=5, seed=3)


def test_validate_scope(tmp_path):
    p = tmp_path / "scope.yaml"
    p.write_text("modules:\n  core_dx: {on: true}\n  core_lines: {on: true, code_ranges: []}\n", encoding="utf-8")
    with pytest.raises(FreezeError):
        validate_scope(p)
    p.write_text("modules:\n  core_dx: {on: true}\n  core_lines: {on: true, code_ranges: ['73000-73140']}\n", encoding="utf-8")
    assert validate_scope(p).in_scope_line("73100")


def test_perform_freeze_without_git(tmp_path):
    paths, config = make_repo(tmp_path)
    perform_seal(paths, config, make_inputs(), passphrase=FAKE_KEY, actor="tests")
    (paths.runs / "audit").mkdir(parents=True, exist_ok=True)
    dev = _dev(paths)
    (paths.runs / "audit" / "flag_counts.json").write_text(json.dumps({e.id: k % 3 for k, e in enumerate(dev)}), encoding="utf-8")
    paths.scope_yaml.write_text(
        "modules:\n  core_dx: {on: true}\n  core_lines: {on: true, code_ranges: ['73000-73140']}\n"
        "exclusions: {em_code_ranges: ['99202-99205'], modifiers: ['25']}\naudit_provenance: {status: provisional}\n",
        encoding="utf-8",
    )
    result = perform_freeze(paths, actor="tests", do_git=False)
    split = json.loads(paths.dev_split.read_text(encoding="utf-8"))
    assert {k: len(v) for k, v in split["sets"].items()} == {"seed": 20, "batch1": 45, "batch2": 45, "batch3": 45, "spare": 12}
    holdout = set(paths.holdout_ids.read_text().split())
    assert not holdout & {i for v in split["sets"].values() for i in v}
    assert len(result.scoring_tree_sha256) == 64 and result.summary["batch1"]["n"] == 45
    assert "status: locked" in paths.project_yaml.read_text(encoding="utf-8")
    assert "status: default" not in paths.project_yaml.read_text(encoding="utf-8")
    assert paths.decisions_md.exists() and "locked" in paths.decisions_md.read_text(encoding="utf-8")
    ledger = paths.ledger.read_text(encoding="utf-8")
    assert "— freeze" in ledger and "scope_status: provisional" in ledger
    with pytest.raises(FreezeError):
        perform_freeze(paths, actor="tests", do_git=False)


def test_freeze_requires_audit_flags_and_scope(tmp_path):
    paths, config = make_repo(tmp_path)
    perform_seal(paths, config, make_inputs(), passphrase=FAKE_KEY, actor="tests")
    paths.scope_yaml.write_text("modules:\n  core_dx: {on: true}\n  core_lines: {on: true, code_ranges: []}\n", encoding="utf-8")
    with pytest.raises(FreezeError, match="core_lines"):
        perform_freeze(paths, actor="tests", do_git=False)
    paths.scope_yaml.write_text("modules:\n  core_dx: {on: true}\n  core_lines: {on: true, code_ranges: ['73000-73140']}\n", encoding="utf-8")
    with pytest.raises(FreezeError, match="flag_counts"):
        perform_freeze(paths, actor="tests", do_git=False)
