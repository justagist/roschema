"""Tests for JSON/GitHub reporters and the semver advisory."""

from __future__ import annotations

from roschema.report import build_github, build_json, summarize
from roschema.rules import Finding


def _finding(
    rule, severity="error", levels=("wire",), suppressed=False, new_file=None, new_line=None
):
    return Finding(
        rule=rule,
        severity=severity,
        level=levels[0],
        interface="demo/msg/T",
        section="message",
        target="a",
        message="m",
        old_file="demo/msg/T.msg",
        old_line=1,
        new_file=new_file,
        new_line=new_line,
        suppressed=suppressed,
        levels=levels,
    )


def test_build_json_schema():
    doc = build_json([_finding("RS001")])
    assert doc["version"] == 1
    assert set(doc["findings"][0]) == {
        "rule",
        "severity",
        "level",
        "package",
        "interface",
        "section",
        "target",
        "message",
        "old",
        "new",
        "suppressed",
    }
    assert set(doc["summary"]) == {"total", "errors", "warnings", "suppressed", "advisories"}


def test_build_json_null_new_location():
    doc = build_json([_finding("RS040")])
    assert doc["findings"][0]["new"] is None
    assert doc["findings"][0]["old"] == {"file": "demo/msg/T.msg", "line": 1}


def test_build_github_error_line():
    lines = build_github([_finding("RS003", new_file="demo/msg/T.msg", new_line=3)])
    assert lines[0].startswith("::error ")
    assert "file=demo/msg/T.msg" in lines[0]
    assert "line=3" in lines[0]
    assert "title=RS003" in lines[0]


def test_build_github_warning_and_skips_suppressed():
    lines = build_github(
        [
            _finding("RS008", severity="warn", new_file="x.msg", new_line=1),
            _finding("RS001", suppressed=True, new_file="y.msg", new_line=1),
        ]
    )
    assert len(lines) == 1
    assert lines[0].startswith("::warning ")


def test_advisory_major():
    s = summarize([_finding("RS001", levels=("wire", "source"))])
    assert s.advisories[0].bump == "MAJOR"


def test_advisory_minor_for_additive_non_error():
    s = summarize([_finding("RS002", severity="warn", levels=("wire", "source"))])
    assert s.advisories[0].bump == "MINOR"


def test_advisory_patch():
    s = summarize([_finding("RS030", severity="warn", levels=("behavior",))])
    assert s.advisories[0].bump == "PATCH"


def test_summary_counts_and_suppressed():
    s = summarize(
        [
            _finding("RS001"),
            _finding("RS008", severity="warn"),
            _finding("RS003", suppressed=True),
        ]
    )
    assert (s.total, s.errors, s.warnings, s.suppressed) == (2, 1, 1, 1)
