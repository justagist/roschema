"""RS060: structure changed but the MESSAGE_VERSION constant was not bumped.

Off by default (severity ``off``); enable per the PX4 convention with
``[check.rules]`` ``RS060 = "error"``.
"""

from __future__ import annotations

from ...differ import ChangeEvent, ChangeType
from ..model import Rule, Severity


def _message(ev: ChangeEvent) -> str:
    old = ev.detail.get("old_version")
    new = ev.detail.get("new_version")
    return (
        f"structure changed but MESSAGE_VERSION not bumped "
        f"(was {old}, now {new})"
    )


RULE = Rule(
    id="RS060",
    title="MESSAGE_VERSION not bumped",
    description=(
        "A structural change was made to an interface that defines a "
        "MESSAGE_VERSION constant, but the constant was not increased."
    ),
    rationale=(
        "Projects following the PX4 MESSAGE_VERSION convention rely on the "
        "constant tracking every structural change for runtime translation."
    ),
    levels=("behavior",),
    default_severity=Severity.OFF,
    handles=(ChangeType.MESSAGE_VERSION_NOT_BUMPED,),
    message=_message,
    example_before="uint32 MESSAGE_VERSION=1\nint32 a",
    example_after="uint32 MESSAGE_VERSION=1\nint32 a\nint32 b",
)
