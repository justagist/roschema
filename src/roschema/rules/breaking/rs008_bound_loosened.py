"""RS008: an array or string capacity bound was loosened."""

from __future__ import annotations

from typing import cast

from ...differ import ChangeEvent, ChangeType
from ...ir import Field
from ..model import Rule, Severity


def _message(ev: ChangeEvent) -> str:
    old = cast(Field, ev.old)
    new = cast(Field, ev.new)
    return f"bound loosened {old.type.render()} -> {new.type.render()}"


RULE = Rule(
    id="RS008",
    title="Bound loosened",
    description="A bounded array or string had its capacity increased.",
    rationale=(
        "Newer messages may exceed the old bound, so an older subscriber can "
        "reject them; the reverse direction stays compatible, hence a warning."
    ),
    levels=("wire",),
    default_severity=Severity.WARN,
    handles=(ChangeType.FIELD_BOUND_LOOSENED,),
    message=_message,
    example_before="string<=16 name",
    example_after="string<=64 name",
)
