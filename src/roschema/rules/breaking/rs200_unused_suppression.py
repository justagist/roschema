"""RS200: an allowlist entry or inline ignore suppresses nothing (check only).

Emitted by comparing suppressions with the findings of a check rather than by
event dispatch, so it handles no change events. It has no levels: a stale
suppression is reported whatever level is checked.
"""

from __future__ import annotations

from ...differ import ChangeEvent
from ..model import Rule, Severity


def _message(ev: ChangeEvent) -> str:  # pragma: no cover - findings built directly
    return "suppression matches no finding"


RULE = Rule(
    id="RS200",
    title="Unused suppression",
    description=(
        "An allowlist entry or a `# roschema: ignore=` comment for a check rule "
        "matches no change between the baseline and the target. Reported by "
        "`check` only, at every level."
    ),
    rationale=(
        "A suppression usually outlives the break it allowed once the baseline "
        "moves past it, and then silently hides the next break of the same "
        "target. A misspelt target never matched anything in the first place."
    ),
    levels=(),
    default_severity=Severity.WARN,
    handles=(),
    message=_message,
    example_before='[check.allow] "my_msgs/msg/S.a" = { reason = "removed in 2.0" }',
    example_after="baseline already lacks a, so nothing is removed any more",
)
