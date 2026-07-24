"""RS022: a constant's type changed."""

from __future__ import annotations

from typing import cast

from ...differ import ChangeEvent, ChangeType
from ...ir import Constant
from ..model import Rule, Severity


def _message(ev: ChangeEvent) -> str:
    old = cast(Constant, ev.old)
    new = cast(Constant, ev.new)
    return f"constant type changed {old.type.render()} -> {new.type.render()}"


RULE = Rule(
    id="RS022",
    title="Constant type changed",
    description="A constant kept its name but changed type.",
    rationale="The generated constant's type changes, breaking code that used the old type.",
    levels=("source",),
    default_severity=Severity.ERROR,
    handles=(ChangeType.CONSTANT_TYPE_CHANGED,),
    message=_message,
    example_before="int32 LIMIT=100",
    example_after="float32 LIMIT=100.0",
)
