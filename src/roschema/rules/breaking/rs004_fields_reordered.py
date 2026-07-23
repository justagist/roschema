"""RS004: the relative order of fields changed."""

from __future__ import annotations

from typing import cast

from ...differ import ChangeEvent, ChangeType
from ..model import Rule, Severity


def _message(ev: ChangeEvent) -> str:
    old_order = cast("list[str]", ev.detail.get("old_order", []))
    new_order = cast("list[str]", ev.detail.get("new_order", []))
    return f"fields reordered: {', '.join(old_order)} -> {', '.join(new_order)}"


RULE = Rule(
    id="RS004",
    title="Fields reordered",
    description="Fields that exist on both sides appear in a different order.",
    rationale="CDR encodes fields by position, so reordering silently corrupts the wire stream.",
    levels=("wire",),
    default_severity=Severity.ERROR,
    handles=(ChangeType.FIELD_REORDERED,),
    message=_message,
    example_before="int32 a\nint32 b",
    example_after="int32 b\nint32 a",
)
