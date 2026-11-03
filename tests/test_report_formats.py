"""Tests for JSON/GitHub reporters and the semver advisory."""

from __future__ import annotations

from dataclasses import replace

from roschema.report import build_github, build_json, coverage, summarize
from roschema.report.changes import NEW_CONSTANT, NEW_INTERFACE, Change
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
        "help_uri",
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


def test_build_github_escapes_command_text():
    finding = replace(
        _finding("RS021", new_file="a,b:c.msg", new_line=1),
        message='constant value changed "50%" -> "75%\nx"',
    )
    assert build_github([finding]) == [
        "::error file=a%2Cb%3Ac.msg,line=1,title=RS021::"
        'RS021 demo/msg/T.a: constant value changed "50%25" -> "75%25%0Ax"'
    ]


def test_advisory_major():
    s = summarize([_finding("RS001", levels=("wire", "source"))])
    assert s.advisories[0].bump == "MAJOR"


def test_advisory_minor_for_additive_non_error():
    s = summarize([_finding("RS002", severity="warn", levels=("wire", "source"))])
    assert s.advisories[0].bump == "MINOR"


def test_advisory_minor_for_added_interface_or_constant():
    added = [
        Change("other/msg/New", None, "", "interface added", NEW_INTERFACE),
        Change("demo/msg/T", "message", "MODE_X", "constant added: uint8 MODE_X=3", NEW_CONSTANT),
    ]
    s = summarize([_finding("RS030", severity="warn", levels=("behavior",))], added)
    assert [(a.package, a.bump, a.reason) for a in s.advisories] == [
        ("demo", "MINOR", "1 additive change(s)"),
        ("other", "MINOR", "1 additive change(s)"),
    ]


def test_advisory_major_outranks_additions():
    added = [Change("demo/msg/New", None, "", "interface added", NEW_INTERFACE)]
    s = summarize([_finding("RS001", levels=("wire", "source"))], added)
    assert s.advisories[0].bump == "MAJOR"


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


def test_coverage_names_first_new_interfaces():
    new = [f"p/msg/N{i}" for i in range(5)]
    cov = coverage(["p/msg/A"], ["p/msg/A", *new])
    assert cov.describe() == (
        "compared 1 interface(s) in 1 package(s); 5 new (p/msg/N0, p/msg/N1, p/msg/N2 and 2 more)"
    )
