"""RSL003: interface (file) names must be PascalCase (rosidl message-name rule)."""

from __future__ import annotations

from ...ir import InterfaceFile
from ..model import LintHit, LintRule, Severity
from ._common import MESSAGE_NAME


def _check(iface: InterfaceFile) -> list[LintHit]:
    if MESSAGE_NAME.match(iface.name):
        return []
    return [
        LintHit(
            section=None,
            target="",
            line=None,
            message=f"interface name '{iface.name}' is not PascalCase",
        )
    ]


RULE = LintRule(
    id="RSL003",
    title="Interface name not PascalCase",
    description="Message/service/action file names must be PascalCase, matching rosidl.",
    rationale="rosidl requires message type names to start with a capital and be alphanumeric.",
    default_severity=Severity.ERROR,
    check=_check,
)
