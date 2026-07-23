"""RS005: a field was renamed (type and position unchanged)."""

from __future__ import annotations

from ...differ import ChangeEvent, ChangeType
from ..model import Rule, Severity


def _message(ev: ChangeEvent) -> str:
    old_name = ev.detail.get("old_name", "?")
    return f"field renamed '{old_name}' -> '{ev.target}'"


RULE = Rule(
    id="RS005",
    title="Field renamed",
    description="A field at the same position kept its type but changed name.",
    rationale=(
        "The wire bytes are unchanged, but generated field accessors and every "
        "name-based tool (bags, echo, YAML config) break."
    ),
    levels=("source", "introspection"),
    default_severity=Severity.ERROR,
    handles=(ChangeType.FIELD_RENAMED,),
    message=_message,
    example_before="float32 theta",
    example_after="float32 yaw",
)
