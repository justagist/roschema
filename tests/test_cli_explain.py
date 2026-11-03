"""Tests for `roschema explain`."""

from __future__ import annotations

from typer.testing import CliRunner

from roschema.cli import app

runner = CliRunner()


def test_explain_describes_rule_case_insensitively():
    result = runner.invoke(app, ["explain", "rs004"])
    assert result.exit_code == 0
    assert "RS004 -- Fields reordered" in result.stdout
    assert "CDR encodes fields by position" in result.stdout
    assert result.stdout.rstrip().endswith("docs/rules.md#rs004----fields-reordered")


def test_explain_unknown_rule_suggests_closest():
    result = runner.invoke(app, ["explain", "RSL04"])
    assert result.exit_code == 2
    assert "unknown rule 'RSL04'; did you mean RSL004?" in result.output
