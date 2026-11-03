"""RSL001: field names must be snake_case (rosidl field-name rule)."""

from __future__ import annotations

from ...ir import InterfaceFile
from ..model import LintHit, LintRule, Severity
from ._common import FIELD_NAME, iter_fields


def _check(iface: InterfaceFile) -> list[LintHit]:
    hits: list[LintHit] = []
    for section, field in iter_fields(iface):
        if not FIELD_NAME.match(field.name):
            hits.append(
                LintHit(
                    section=section,
                    target=field.name,
                    line=field.line,
                    message=f"field name '{field.name}' is not snake_case",
                    comment=field.trailing_comment,
                )
            )
    return hits


RULE = LintRule(
    id="RSL001",
    title="Field name not snake_case",
    description="Field names must be lowercase snake_case, matching rosidl.",
    rationale=(
        "rosidl requires field names to be lowercase with single underscores and "
        "no leading digit or trailing underscore; other forms fail generation."
    ),
    default_severity=Severity.ERROR,
    check=_check,
    example_flagged="float64 MaxSpeed",
    example_preferred="float64 max_speed",
)
