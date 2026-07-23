"""GitHub Actions workflow-command annotations."""

from __future__ import annotations

from ..rules import Finding

_LEVEL = {"error": "error", "warn": "warning"}


def build_github(findings: list[Finding]) -> list[str]:
    """Build ``::error``/``::warning`` annotation lines for non-suppressed findings.

    Uses the new-side file/line so annotations land on the changed code.
    """
    lines: list[str] = []
    for finding in findings:
        if finding.suppressed:
            continue
        command = _LEVEL.get(finding.severity, "notice")
        props = [f"title={finding.rule}"]
        if finding.new_file:
            props.insert(0, f"file={finding.new_file}")
            if finding.new_line is not None:
                props.insert(1, f"line={finding.new_line}")
        message = f"{finding.rule} {finding.qualified_target}: {finding.message}"
        lines.append(f"::{command} {','.join(props)}::{message}")
    return lines
