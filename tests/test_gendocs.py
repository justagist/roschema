"""Assert the committed rule reference stays in sync with the rule metadata."""

from __future__ import annotations

from pathlib import Path

from roschema.rules.gendocs import render_docs

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
