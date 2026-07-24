"""RSL010: a field name shared by a service request and response."""

from __future__ import annotations

from ...ir import Field, InterfaceFile, SectionKind
from ..model import LintHit, LintRule, Severity


def _check(iface: InterfaceFile) -> list[LintHit]:
    if iface.kind != "srv":
        return []
    request: dict[str, Field] = {}
    response: dict[str, Field] = {}
    for section in iface.sections:
        target = request if section.kind is SectionKind.REQUEST else response
        for member in section.members:
            if isinstance(member, Field):
                target[member.name] = member

    hits: list[LintHit] = []
    for name in response:
        if name in request:
            field = response[name]
            hits.append(
                LintHit(
                    section=SectionKind.RESPONSE.value,
                    target=name,
                    line=field.line,
                    message=f"field '{name}' appears in both request and response",
                    comment=field.trailing_comment,
                )
            )
    return hits


RULE = LintRule(
    id="RSL010",
    title="Request/response field shadowing",
    description="A field name is used in both the request and response of a service.",
    rationale="Reusing a name across request and response is a common source of confusion.",
    default_severity=Severity.WARN,
    check=_check,
)
