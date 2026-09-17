import pytest

from codeloop.llm.prompts import PromptError, PromptStore, parse_prompt_file, rendered_sha256


def test_parse_render_and_hash(tmp_path):
    p = tmp_path / "x.txt"
    p.write_text("=== SYSTEM ===\nBe brief about {{topic}}.\n=== USER ===\nNote:\n{{note}}\n", encoding="utf-8")
    t = parse_prompt_file("x", p)
    assert t.variables() == {"topic", "note"}
    system, user = t.render({"topic": "knees", "note": "text with {{braces}} and $dollars"})
    assert system == "Be brief about knees." and user == "Note:\ntext with {{braces}} and $dollars"
    assert len(t.file_sha256) == 64 and rendered_sha256(system, user) != rendered_sha256(system, user + "x")
    with pytest.raises(PromptError):
        t.render({"topic": "knees"})


def test_store_reloads_on_change_and_lists_hashes(tmp_path):
    (tmp_path / "a.txt").write_text("hello {{name}}", encoding="utf-8")
    store = PromptStore(tmp_path)
    first = store.load("a")
    assert first.system == "" and first.user == "hello {{name}}"
    (tmp_path / "a.txt").write_text("hello again {{name}}", encoding="utf-8")
    assert store.load("a").user == "hello again {{name}}" and store.load("a").file_sha256 != first.file_sha256
    assert set(store.hashes()) == {"a"}
    with pytest.raises(PromptError):
        store.load("missing")
    (tmp_path / "empty.txt").write_text("=== SYSTEM ===\nonly system\n=== USER ===\n  \n", encoding="utf-8")
    with pytest.raises(PromptError):
        store.load("empty")
