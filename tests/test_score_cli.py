import json

import pytest
from typer.testing import CliRunner

from codeloop.cli import app
from codeloop.scoring import load_packages, score_files
from codeloop.util.jsonl import write_jsonl
from tests.scoring_fixtures import TEST_SCOPE, dx, line, pkg

runner = CliRunner()


def _files(tmp_path):
    gold = tmp_path / "gold.jsonl"
    pred = tmp_path / "pred.jsonl"
    write_jsonl(gold, [
        {"encounter_id": "E1", "coder_id": "c", "label": pkg([dx("M1711", True)], [line("96372", pointers=["A"])])},
        {"encounter_id": "E2", "coder_id": "c", "label": pkg([dx("E119", True)])},
        {"encounter_id": "E3", "coder_id": "c", "label": pkg()},
    ])
    write_jsonl(pred, [
        {"encounter_id": "E1", "version": "dev", "run_id": "r", **pkg([dx("M1711", True)], [line("96372", pointers=["M1711"])])},
        {"package": {"encounter_id": "E2", **pkg([dx("E1165", True)])}},
        {"encounter_id": "E9", **pkg([dx("Z000")])},
    ])
    scope = tmp_path / "scope.yaml"
    scope.write_text(json.dumps(TEST_SCOPE.model_dump()), encoding="utf-8")  # JSON is valid YAML
    return gold, pred, scope


def test_score_files_handles_shapes_missing_and_unscored(tmp_path):
    gold, pred, scope = _files(tmp_path)
    assert set(load_packages(pred)) == {"E1", "E2", "E9"}
    report = score_files(gold, pred, TEST_SCOPE)
    by_id = {r.encounter_id: r for r in report.results}
    assert by_id["E1"].agreement == 1.0 and by_id["E3"].no_in_scope_fields
    # E2: dx:E119 wrong, dx:E1165 wrong (each 0.5 hierarchical credit), first_listed E119 != E1165
    assert by_id["E2"].agreement == 0.0 and by_id["E2"].hier_agreement == pytest.approx(1 / 3)
    assert report.missing_pred == ["E3"] and report.unscored_pred == ["E9"] and report.batch.n == 3


def test_cli_score_writes_report(tmp_path):
    gold, pred, scope = _files(tmp_path)
    out = tmp_path / "report.json"
    r = runner.invoke(app, ["score", "--gold", str(gold), "--pred", str(pred), "--scope", str(scope), "--out", str(out)])
    assert r.exit_code == 0, r.output
    assert "mean agreement=" in r.output and "predictions without gold (ignored): 1" in r.output
    data = json.loads(out.read_text(encoding="utf-8"))
    assert data["batch"]["n"] == 3 and data["scoring_version"] == "1.0" and len(data["results"]) == 3
