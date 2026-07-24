"""RSL004: field lacks a documentation comment (off by default)."""

from __future__ import annotations

from ...ir import InterfaceFile
from ..model import LintHit, LintRule, Severity
from ._common import iter_fields


def _check(iface: InterfaceFile) -> list[LintHit]:
    hits: list[LintHit] = []
    for section, field in iter_fields(iface):
        if field.trailing_comment is None:
            hits.append(
                LintHit(
                    section=section,
                    target=field.name,
                    line=field.line,
                    message=f"field '{field.name}' has no documentation comment",
                )
            )
    return hits


RULE = LintRule(
    id="RSL004",
    title="Field missing documentation",
    description="A field has no trailing documentation comment.",
    rationale=(
        "Documented fields are easier to consume. Off by default; only trailing "
        "comments are tracked (preceding comments are not retained in the IR)."
    ),
    default_severity=Severity.OFF,
    check=_check,
)
