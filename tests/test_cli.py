from typer.testing import CliRunner

from codeloop.cli import app
from codeloop.seal.run import perform_seal
from tests.synthetic import FAKE_KEY, make_inputs, make_repo

runner = CliRunner()


def test_version():
    r = runner.invoke(app, ["--version"])
    assert r.exit_code == 0 and "codeloop" in r.output


def test_seal_fails_fast_without_key_and_after_sealing(tmp_path, monkeypatch):
    paths, config = make_repo(tmp_path)
    r = runner.invoke(app, ["seal", "--root", str(paths.root)])
    assert r.exit_code == 1 and "CODELOOP_SEAL_KEY" in r.output
    perform_seal(paths, config, make_inputs(), passphrase=FAKE_KEY, actor="tests")
    monkeypatch.setenv("CODELOOP_SEAL_KEY", FAKE_KEY)
    r = runner.invoke(app, ["seal", "--root", str(paths.root)])
    assert r.exit_code == 1 and "drawn once" in r.output


def test_check_leakage_and_render_decisions(tmp_path):
    paths, config = make_repo(tmp_path)
    r = runner.invoke(app, ["check-leakage", "--root", str(paths.root)])
    assert r.exit_code == 0 and "nothing to check" in r.output
    perform_seal(paths, config, make_inputs(), passphrase=FAKE_KEY, actor="tests")
    r = runner.invoke(app, ["check-leakage", "--root", str(paths.root)])
    assert r.exit_code == 0 and "no holdout leakage" in r.output
    holdout = paths.holdout_ids.read_text().split()
    (paths.reports / "oops.md").write_text(holdout[0], encoding="utf-8")
    r = runner.invoke(app, ["check-leakage", "--root", str(paths.root)])
    assert r.exit_code == 1
    r = runner.invoke(app, ["render-decisions", "--root", str(paths.root)])
    assert r.exit_code == 0 and paths.decisions_md.exists()
    assert "| D0 |" in paths.decisions_md.read_text(encoding="utf-8")
