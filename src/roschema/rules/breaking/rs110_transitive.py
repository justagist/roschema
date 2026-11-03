"""RS110: an embedded type changed transitively (--deep only).

Emitted by the deep-resolution pipeline rather than by event dispatch, so it
handles no change events; its metadata drives severity, level and the docs.
"""

from __future__ import annotations

from ...differ import ChangeEvent
from ..model import Rule, Severity


def _message(ev: ChangeEvent) -> str:  # pragma: no cover - findings built directly
    chain = ev.detail.get("chain", "")
    return f"embedded type changed: {chain}"


RULE = Rule(
    id="RS110",
    title="Transitively broken by an embedded type",
    description=(
        "An interface embeds (directly or through nested types) another interface "
        "whose wire layout changed, so it is broken even though its own definition "
        "did not change. Reported only with --deep, with the severity of the "
        "reported change it traces back to; suppressed changes are not followed."
    ),
    rationale=(
        "CDR inlines nested messages, so a wire-breaking change to an embedded "
        "type breaks every interface that contains it."
    ),
    levels=("wire",),
    default_severity=Severity.ERROR,
    handles=(),
    message=_message,
    example_before="geometry_msgs/Point position  # Point unchanged here",
    example_after="geometry_msgs/Point position  # but Point.x changed type",
)
