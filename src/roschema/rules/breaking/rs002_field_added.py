"""RS002: a field was added."""

from __future__ import annotations

from ...differ import ChangeEvent, ChangeType
from ..model import Rule, Severity


def _message(ev: ChangeEvent) -> str:
    return f"field '{ev.target}' added"


RULE = Rule(
    id="RS002",
    title="Field added",
    description="A field was added to an interface section.",
    rationale=(
        "Appending a field is source-compatible but still changes the CDR wire "
        "layout, so a new publisher and an old subscriber cannot interoperate."
    ),
    levels=("wire", "source"),
    default_severity=Severity.ERROR,
    handles=(ChangeType.FIELD_ADDED,),
    message=_message,
    example_before="int32 a",
    example_after="int32 a\nint32 b",
)
