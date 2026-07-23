"""Stable JSON report. Schema documented in the README."""

from __future__ import annotations

from ..rules import Finding
from .summary import summarize

SCHEMA_VERSION = 1


def build_json(findings: list[Finding]) -> dict[str, object]:
    """Build the JSON-serialisable report document."""
    summary = summarize(findings)
    return {
        "version": SCHEMA_VERSION,
        "findings": [_finding_dict(f) for f in findings],
        "summary": {
            "total": summary.total,
            "errors": summary.errors,
            "warnings": summary.warnings,
            "suppressed": summary.suppressed,
            "advisories": {a.package: a.bump for a in summary.advisories},
        },
    }


def _finding_dict(finding: Finding) -> dict[str, object]:
    return {
        "rule": finding.rule,
        "severity": finding.severity,
        "level": finding.level,
        "package": finding.package,
        "interface": finding.interface,
        "section": finding.section,
        "target": finding.target,
        "message": finding.message,
        "old": _loc(finding.old_file, finding.old_line),
        "new": _loc(finding.new_file, finding.new_line),
        "suppressed": finding.suppressed,
    }


def _loc(file: str | None, line: int | None) -> dict[str, object] | None:
    if file is None:
        return None
    return {"file": file, "line": line}
