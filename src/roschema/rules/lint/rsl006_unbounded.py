"""RSL006: unbounded string or array (off by default; RT-minded guidance)."""

from __future__ import annotations

from ...ir import ArrayKind, InterfaceFile
from ..model import LintHit, LintRule, Severity
from ._common import iter_fields


def _check(iface: InterfaceFile) -> list[LintHit]:
    hits: list[LintHit] = []
    for section, field in iter_fields(iface):
        t = field.type
        unbounded_array = t.array_kind is ArrayKind.UNBOUNDED
        unbounded_string = t.base in ("string", "wstring") and t.string_bound is None
        if unbounded_array or unbounded_string:
            hits.append(
                LintHit(
                    section=section,
                    target=field.name,
                    line=field.line,
                    message=f"field '{field.name}' is unbounded ('{field.type.render()}')",
                    comment=field.trailing_comment,
                )
            )
    return hits


RULE = LintRule(
    id="RSL006",
    title="Unbounded string or array",
    description="A field is an unbounded array or contains unbounded strings.",
    rationale=(
        "Unbounded fields allocate dynamically, which real-time users often avoid. "
        "Off by default; informational."
    ),
    default_severity=Severity.OFF,
    check=_check,
)
