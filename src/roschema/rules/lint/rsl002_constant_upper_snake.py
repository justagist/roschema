"""RSL002: constant names must be UPPER_SNAKE_CASE (rosidl constant rule)."""

from __future__ import annotations

from ...ir import InterfaceFile
from ..model import LintHit, LintRule, Severity
from ._common import CONSTANT_NAME, iter_constants


def _check(iface: InterfaceFile) -> list[LintHit]:
    hits: list[LintHit] = []
    for section, const in iter_constants(iface):
        if not CONSTANT_NAME.match(const.name):
            hits.append(
                LintHit(
                    section=section,
                    target=const.name,
                    line=const.line,
                    message=f"constant name '{const.name}' is not UPPER_SNAKE_CASE",
                    comment=const.trailing_comment,
                )
            )
    return hits


RULE = LintRule(
    id="RSL002",
    title="Constant name not UPPER_SNAKE_CASE",
    description="Constant names must be uppercase with underscores, matching rosidl.",
    rationale="rosidl requires constant names to be uppercase; other forms fail generation.",
    default_severity=Severity.ERROR,
    check=_check,
)
