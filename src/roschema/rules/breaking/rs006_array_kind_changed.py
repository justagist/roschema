"""RS006: a field changed between scalar, fixed-size array and sequence forms."""

from __future__ import annotations

from typing import cast

from ...differ import ChangeEvent, ChangeType
from ...ir import Field
from ..model import Rule, Severity


def _message(ev: ChangeEvent) -> str:
    old = cast(Field, ev.old)
    new = cast(Field, ev.new)
    return f"array kind changed {old.type.render()} -> {new.type.render()}"


RULE = Rule(
    id="RS006",
    title="Array kind changed",
    description="A field changed between scalar, fixed-size array and sequence forms.",
    rationale=(
        "A sequence carries a length prefix that a fixed-size array and a scalar do "
        "not, so the CDR layout and the generated container type both change. "
        "Adding or removing a sequence bound is reported as RS007 or RS008 instead."
    ),
    levels=("wire", "source"),
    default_severity=Severity.ERROR,
    handles=(ChangeType.FIELD_ARRAY_KIND_CHANGED,),
    message=_message,
    example_before="int32[] data",
    example_after="int32[8] data",
)
