"""Golden test: check the fixture corpus and compare full JSON output."""

from __future__ import annotations

import json
from pathlib import Path

from typer.testing import CliRunner

from roschema.cli import app
from roschema.config import Config, finalize_findings
from roschema.differ import diff_interfaces
from roschema.discovery import discover
from roschema.loader import load_interfaces
from roschema.report import build_json, coverage
from roschema.rules import evaluate
from roschema.rules.gendocs import docs_url
from roschema.vfs import RealFS

FIXTURES = Path(__file__).parent / "fixtures"
runner = CliRunner()


def _without_help_uris(doc):
    """Drop each finding's ``help_uri``, which names the installed version."""
    for finding in doc["findings"]:
        assert finding.pop("help_uri") == docs_url(finding["rule"])
    return doc


def _load(side: str):
    vfs = RealFS(FIXTURES / side)
    return load_interfaces(vfs, discover(vfs, "."))


def test_golden_pipeline_matches():
    old, new = _load("ws_old"), _load("ws_new")
    findings = finalize_findings(evaluate(diff_interfaces(old, new)), Config(), None)
    doc = build_json(findings, coverage=coverage(old, new))
    golden = json.loads((FIXTURES / "golden_check.json").read_text())
    assert _without_help_uris(doc) == golden


def test_golden_via_cli_json():
    result = runner.invoke(
        app,
        [
            "check",
            str(FIXTURES / "ws_new"),
            "--against",
            str(FIXTURES / "ws_old"),
            "--format",
            "json",
        ],
    )
    assert result.exit_code == 1  # errors present
    doc = json.loads(result.stdout)
    golden = json.loads((FIXTURES / "golden_check.json").read_text())
    assert _without_help_uris(doc) == golden
