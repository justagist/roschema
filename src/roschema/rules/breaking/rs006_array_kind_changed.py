"""RS006: an array's kind changed (fixed / bounded / unbounded)."""

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
    description="A field changed between fixed, bounded and unbounded array forms.",
    rationale=(
        "Fixed, bounded and unbounded arrays use different CDR encodings and "
        "generate different container types."
    ),
    levels=("wire", "source"),
    default_severity=Severity.ERROR,
    handles=(ChangeType.FIELD_ARRAY_KIND_CHANGED,),
    message=_message,
    example_before="int32[] data",
    example_after="int32[8] data",
)
