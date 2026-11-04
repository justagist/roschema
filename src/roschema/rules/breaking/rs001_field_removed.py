"""RS001: a field was removed."""

from __future__ import annotations

from ...differ import ChangeEvent, ChangeType
from ..model import Rule, Severity


def _message(ev: ChangeEvent) -> str:
    return f"field '{ev.target}' removed"


RULE = Rule(
    id="RS001",
    title="Field removed",
    description="A field was removed from an interface section.",
    rationale=(
        "CDR is positional, so removing a field shifts every following field and "
        "breaks the wire layout, the generated API and name-based tooling."
    ),
    levels=("wire", "introspection", "source"),
    default_severity=Severity.ERROR,
    handles=(ChangeType.FIELD_REMOVED,),
    message=_message,
    example_before="int32 a\nint32 b",
    example_after="int32 a",
)
