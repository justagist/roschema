"""RS021: a constant's value changed."""

from __future__ import annotations

from typing import cast

from ...differ import ChangeEvent, ChangeType
from ...ir import Constant
from ..model import Rule, Severity


def _message(ev: ChangeEvent) -> str:
    old = cast(Constant, ev.old)
    new = cast(Constant, ev.new)
    return f"constant value changed {old.value_raw} -> {new.value_raw}"


RULE = Rule(
    id="RS021",
    title="Constant value changed",
    description="A constant kept its type but changed value.",
    rationale=(
        "Callers compiled against the old value silently disagree with new ones, "
        "and the meaning of already-recorded data shifts."
    ),
    levels=("source", "behavior"),
    default_severity=Severity.ERROR,
    handles=(ChangeType.CONSTANT_VALUE_CHANGED,),
    message=_message,
    example_before="int32 TIMEOUT=30",
    example_after="int32 TIMEOUT=60",
)
