"""RS003: a field's type changed."""

from __future__ import annotations

from typing import cast

from ...differ import ChangeEvent, ChangeType
from ...ir import Field
from ..model import Rule, Severity


def _message(ev: ChangeEvent) -> str:
    old = cast(Field, ev.old)
    new = cast(Field, ev.new)
    return f"type changed {old.type.render()} -> {new.type.render()}"


RULE = Rule(
    id="RS003",
    title="Field type changed",
    description="A field kept its name but changed type (including fixed-array size).",
    rationale=(
        "A different type serialises to different bytes and changes the generated "
        "API. A fixed array's size is part of its type and wire layout."
    ),
    levels=("wire", "source"),
    default_severity=Severity.ERROR,
    handles=(ChangeType.FIELD_TYPE_CHANGED,),
    message=_message,
    example_before="float32 theta",
    example_after="float64 theta",
)
