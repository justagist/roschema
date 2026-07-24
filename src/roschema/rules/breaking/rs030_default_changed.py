"""RS030: a field's default value was added, removed or changed."""

from __future__ import annotations

from typing import cast

from ...differ import ChangeEvent, ChangeType
from ...ir import Field
from ..model import Rule, Severity


def _message(ev: ChangeEvent) -> str:
    old = cast(Field, ev.old)
    new = cast(Field, ev.new)
    if old.default is None and new.default is not None:
        return f"default added: {new.default.raw}"
    if old.default is not None and new.default is None:
        return f"default removed (was {old.default.raw})"
    old_raw = old.default.raw if old.default else ""
    new_raw = new.default.raw if new.default else ""
    return f"default changed {old_raw} -> {new_raw}"


RULE = Rule(
    id="RS030",
    title="Field default changed",
    description="A field's default value was added, removed or changed.",
    rationale=(
        "The wire format and API are unchanged, but unset fields deserialise to a "
        "different value, altering behaviour."
    ),
    levels=("behavior",),
    default_severity=Severity.WARN,
    handles=(ChangeType.FIELD_DEFAULT_CHANGED,),
    message=_message,
    example_before="int32 timeout 30",
    example_after="int32 timeout 60",
)
