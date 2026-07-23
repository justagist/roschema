"""RS007: an array or string capacity bound was tightened."""

from __future__ import annotations

from typing import cast

from ...differ import ChangeEvent, ChangeType
from ...ir import Field
from ..model import Rule, Severity


def _message(ev: ChangeEvent) -> str:
    old = cast(Field, ev.old)
    new = cast(Field, ev.new)
    return f"bound tightened {old.type.render()} -> {new.type.render()}"


RULE = Rule(
    id="RS007",
    title="Bound tightened",
    description="A bounded array or string had its capacity reduced.",
    rationale=(
        "A message that was valid before may now exceed the new bound, so a "
        "stricter subscriber rejects previously-valid data."
    ),
    levels=("wire",),
    default_severity=Severity.ERROR,
    handles=(ChangeType.FIELD_BOUND_TIGHTENED,),
    message=_message,
    example_before="string<=64 name",
    example_after="string<=16 name",
)
