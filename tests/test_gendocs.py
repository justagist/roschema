"""Assert the committed rule reference stays in sync with the rule metadata."""

from __future__ import annotations

from pathlib import Path

from roschema.rules.gendocs import main, render_docs

RULES_MD = Path(__file__).parent.parent / "docs" / "rules.md"


def test_rules_doc_is_in_sync():
    assert RULES_MD.is_file(), "run: python -m roschema.rules.gendocs"
    assert RULES_MD.read_text() == render_docs(), (
        "docs/rules.md is stale; regenerate with `python -m roschema.rules.gendocs`"
    )


def test_every_rule_is_documented():
    text = render_docs()
    for rule_id in ("RS001", "RS040", "RS060", "RS110", "RSL001", "RSL010"):
        assert f"### {rule_id} " in text


def test_gendocs_main_writes(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main([]) == 0
    assert (tmp_path / "docs" / "rules.md").read_text() == render_docs()


def test_gendocs_main_check_fresh(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    main([])
    assert main(["--check"]) == 0


def test_gendocs_main_check_stale(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "rules.md").write_text("stale")
    assert main(["--check"]) == 1


def test_gendocs_main_unknown_arg(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    assert main(["--bogus"]) == 2
