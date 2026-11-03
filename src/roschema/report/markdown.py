"""Markdown report for a GitHub job summary."""

from __future__ import annotations

import html
import re
from collections.abc import Sequence

from ..rules import Finding
from ..rules.gendocs import docs_url
from .changes import Change, by_location, suppressed_changes
from .summary import Coverage, summarize


def build_markdown(
    findings: list[Finding],
    new_source: str,
    old_source: str,
    coverage: Coverage,
    changes: Sequence[Change] = (),
) -> str:
    """Render a check as Markdown: coverage, findings, semver advice and unreported changes.

    GitHub shows only the first few annotations of a step, so the summary is
    where every finding and the semver advice can be read. Unreported changes
    go in a collapsed section.
    """
    summary = summarize(findings, changes)
    lines = [
        "## roschema",
        "",
        f"Checked `{new_source}` against `{old_source}`: {coverage.describe()}.",
        "",
    ]
    reported = [f for f in findings if not f.suppressed]
    if reported:
        lines += [
            f"**{summary.total} finding(s): {summary.errors} error(s), "
            f"{summary.warnings} warning(s)**",
            "",
            "| Rule | Severity | Target | Change | Location |",
            "|---|---|---|---|---|",
        ]
        for f in reported:
            location = f.new_file or f.old_file or ""
            line = f.new_line if f.new_file else f.old_line
            if location and line is not None:
                location = f"{location}:{line}"
            lines.append(
                f"| {_rule_link(f.rule)} | {f.severity} | `{_cell(f.qualified_target)}` | "
                f"{_text(f.message)} | {f'`{_cell(location)}`' if location else ''} |"
            )
    else:
        lines.append("**No breaking changes found.**")
    if summary.suppressed:
        lines += ["", f"{summary.suppressed} finding(s) suppressed."]
    if summary.advisories:
        lines += ["", "**Suggested version bumps**", ""]
        lines += [f"- {a.package}: {a.bump} ({a.reason})" for a in summary.advisories]

    unreported = by_location([*changes, *suppressed_changes(findings)])
    if unreported:
        lines += [
            "",
            f"<details><summary>{len(unreported)} change(s) not reported</summary>",
            "",
            "| Rule | Target | Change | Why |",
            "|---|---|---|---|",
        ]
        for c in unreported:
            rule = _rule_link(c.rule) if c.rule else ""
            lines.append(
                f"| {rule} | `{_cell(c.qualified_target)}` | {_text(c.message)} | "
                f"{_text(c.reason)} |"
            )
        lines += ["", "</details>"]
    return "\n".join(lines) + "\n"


def _rule_link(rule_id: str) -> str:
    url = docs_url(rule_id)
    return f"[{rule_id}]({url})" if url else rule_id


def _cell(text: str) -> str:
    """Make ``text`` safe inside a Markdown table cell, e.g. within a code span."""
    return text.replace("|", "\\|").replace("\n", " ")


def _text(text: str) -> str:
    """Show free ``text`` literally in a table cell: no Markdown, HTML or links."""
    return _cell(re.sub(r"([\\`*_\[\]~#])", r"\\\1", html.escape(text, quote=False)))
