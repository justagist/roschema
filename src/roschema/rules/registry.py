"""Rule registry: turn change events into findings."""

from __future__ import annotations

import re

from ..differ import ChangeEvent, ChangeType
from .breaking import ALL_BREAKING_RULES
from .model import Finding, Rule

_IGNORE_RE = re.compile(r"roschema:\s*ignore\s*=\s*([\w,\s]+)")


def all_rules() -> tuple[Rule, ...]:
    """Every rule roschema ships (currently the breaking-change set)."""
    return ALL_BREAKING_RULES


def evaluate(events: list[ChangeEvent], rules: tuple[Rule, ...] | None = None) -> list[Finding]:
    """Produce findings by dispatching each event to the rules that handle it.

    Args:
        events: Change events from the differ, in report order.
        rules: Rule set to apply; defaults to :func:`all_rules`.

    Returns:
        Findings in event order.
    """
    active = rules if rules is not None else all_rules()
    dispatch: dict[ChangeType, list[Rule]] = {}
    for rule in active:
        for change_type in rule.handles:
            dispatch.setdefault(change_type, []).append(rule)

    findings: list[Finding] = []
    for event in events:
        for rule in dispatch.get(event.type, []):
            findings.append(_build(rule, event))
    return findings


def _build(rule: Rule, event: ChangeEvent) -> Finding:
    return Finding(
        rule=rule.id,
        severity=rule.default_severity.value,
        level=rule.primary_level,
        interface=event.interface,
        section=event.section.value if event.section else None,
        target=event.target,
        message=rule.message(event),
        old_file=getattr(event.old, "source_file", None),
        old_line=getattr(event.old, "line", None),
        new_file=getattr(event.new, "source_file", None),
        new_line=getattr(event.new, "line", None),
        levels=rule.levels,
        inline_ignores=_inline_ignores(getattr(event.new, "trailing_comment", None)),
    )


def _inline_ignores(comment: str | None) -> tuple[str, ...]:
    """Parse ``# roschema: ignore=RS001,RS002`` from a trailing comment."""
    if not comment:
        return ()
    match = _IGNORE_RE.search(comment)
    if not match:
        return ()
    return tuple(part.strip() for part in match.group(1).split(",") if part.strip())
