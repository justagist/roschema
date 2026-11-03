"""Tests for the Markdown job-summary report."""

from __future__ import annotations

from roschema.report import build_markdown, coverage
from roschema.report.changes import NEW_INTERFACE, Change
from roschema.rules import Finding
from roschema.rules.gendocs import docs_url


def _finding(rule, message, suppressed=False):
    return Finding(
        rule=rule,
        severity="error",
        level="wire",
        interface="demo/msg/T",
        section="message",
        target="a",
        message=message,
        old_file="demo/msg/T.msg",
        old_line=2,
        new_file=None,
        new_line=None,
        suppressed=suppressed,
        levels=("wire", "source"),
        suppressed_reason="an inline ignore" if suppressed else "",
    )


def test_markdown_lists_findings_advice_and_unreported_changes():
    report = build_markdown(
        [_finding("RS001", "field 'a' removed"), _finding("RS004", "x", suppressed=True)],
        "workspace:/ws",
        "git:main",
        coverage(["demo/msg/T"], ["demo/msg/T", "demo/msg/U"]),
        [Change("demo/msg/U", None, "", "interface added", NEW_INTERFACE)],
    )
    assert (
        f"| [RS001]({docs_url('RS001')}) | error | `demo/msg/T.a` | field 'a' removed | "
        "`demo/msg/T.msg:2` |"
    ) in report
    assert "- demo: MAJOR (1 wire/source-breaking change(s))" in report
    assert "<details><summary>2 change(s) not reported</summary>" in report
    assert "|  | `demo/msg/U` | interface added | a new interface breaks nothing |" in report
    assert "| suppressed by an inline ignore |" in report


def test_markdown_escapes_table_cells():
    report = build_markdown(
        [_finding("RS021", 'constant value changed "a|b" -> "c\nd"')],
        "workspace:/ws",
        "git:main",
        coverage(["demo/msg/T"], ["demo/msg/T"]),
    )
    assert '| constant value changed "a\\|b" -> "c d" |' in report


def test_markdown_without_findings():
    report = build_markdown([], "workspace:/ws", "git:main", coverage(["p/msg/A"], ["p/msg/A"]))
    assert "**No breaking changes found.**" in report
    assert "<details>" not in report
