"""RS020: a constant was removed."""

from __future__ import annotations

from ...differ import ChangeEvent, ChangeType
from ..model import Rule, Severity


def _message(ev: ChangeEvent) -> str:
    return f"constant '{ev.target}' removed"


RULE = Rule(
    id="RS020",
    title="Constant removed",
    description="A named constant was removed from an interface.",
    rationale="Code referencing the constant fails to compile; the wire format is unaffected.",
    levels=("source",),
    default_severity=Severity.ERROR,
    handles=(ChangeType.CONSTANT_REMOVED,),
    message=_message,
    example_before="int32 MODE_A=0\nint32 MODE_B=1",
    example_after="int32 MODE_A=0",
)
