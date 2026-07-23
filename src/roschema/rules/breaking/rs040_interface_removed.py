"""RS040: an entire interface file was removed."""

from __future__ import annotations

from ...differ import ChangeEvent, ChangeType
from ..model import Rule, Severity


def _message(ev: ChangeEvent) -> str:
    return f"interface {ev.interface} removed"


RULE = Rule(
    id="RS040",
    title="Interface removed",
    description="A whole .msg/.srv/.action definition no longer exists.",
    rationale="Every publisher, subscriber and downstream package that referenced it breaks.",
    levels=("wire", "source", "introspection", "behavior"),
    default_severity=Severity.ERROR,
    handles=(ChangeType.INTERFACE_REMOVED,),
    message=_message,
    example_before="my_msgs/msg/State.msg present",
    example_after="my_msgs/msg/State.msg deleted",
)
