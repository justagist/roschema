"""Stable JSON report. Schema documented in the README."""

from __future__ import annotations

from collections.abc import Sequence

from ..rules import Finding
from ..rules.gendocs import docs_url
from .changes import Change, suppressed_changes
from .summary import Coverage, summarize

SCHEMA_VERSION = 1


def build_json(
    findings: list[Finding],
    *,
    advisories: bool = True,
    coverage: Coverage | None = None,
    changes: Sequence[Change] = (),
    verbose: bool = False,
) -> dict[str, object]:
    """Build the JSON-serialisable report document.

    ``advisories`` adds per-package semver advice and ``coverage`` the interface
    counts; both only mean something for a comparison against a baseline (not
    for lint). Additions among ``changes`` count towards the advice, and
    ``verbose`` lists ``changes`` and suppressed findings, with their reasons.
    """
    summary = summarize(findings, changes)
    counts: dict[str, object] = {
        "total": summary.total,
        "errors": summary.errors,
        "warnings": summary.warnings,
        "suppressed": summary.suppressed,
    }
    if advisories:
        counts["advisories"] = {a.package: a.bump for a in summary.advisories}
    doc: dict[str, object] = {
        "version": SCHEMA_VERSION,
        "findings": [_finding_dict(f) for f in findings],
        "summary": counts,
    }
    if verbose:
        doc["changes"] = [
            {
                "rule": c.rule,
                "package": c.package,
                "interface": c.interface,
                "section": c.section,
                "target": c.target,
                "message": c.message,
                "reason": c.reason,
            }
            for c in [*changes, *suppressed_changes(findings)]
        ]
    if coverage is not None:
        doc["coverage"] = {
            "packages": coverage.packages,
            "compared": coverage.compared,
            "target_only": coverage.target_only,
            "baseline_only": coverage.baseline_only,
        }
    return doc


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
        "help_uri": docs_url(finding.rule),
    }


def _loc(file: str | None, line: int | None) -> dict[str, object] | None:
    if file is None:
        return None
    return {"file": file, "line": line}
