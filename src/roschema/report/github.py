"""GitHub Actions workflow-command annotations."""

from __future__ import annotations

from ..rules import Finding

_LEVEL = {"error": "error", "warn": "warning"}


def build_github(findings: list[Finding], display_prefix: str = "") -> list[str]:
    """Build ``::error``/``::warning`` annotation lines for non-suppressed findings.

    Uses the new-side file/line so annotations land on the changed code.
    ``display_prefix`` is prepended to file paths so they are repo-root-relative
    (GitHub resolves annotation paths from the repo root, not the check target).
    """
    lines: list[str] = []
    for finding in findings:
        if finding.suppressed:
            continue
        command = _LEVEL.get(finding.severity, "notice")
        props = [f"title={_escape_property(finding.rule)}"]
        if finding.new_file:
            path = f"{display_prefix}/{finding.new_file}" if display_prefix else finding.new_file
            props.insert(0, f"file={_escape_property(path)}")
            if finding.new_line is not None:
                props.insert(1, f"line={finding.new_line}")
        message = f"{finding.rule} {finding.qualified_target}: {finding.message}"
        lines.append(f"::{command} {','.join(props)}::{_escape_data(message)}")
    return lines


def _escape_data(value: str) -> str:
    """Escape a workflow-command message as ``@actions/core`` does."""
    return value.replace("%", "%25").replace("\r", "%0D").replace("\n", "%0A")


def _escape_property(value: str) -> str:
    """Escape a workflow-command property, where ``:`` and ``,`` are delimiters."""
    return _escape_data(value).replace(":", "%3A").replace(",", "%2C")
