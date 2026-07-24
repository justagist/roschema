"""Rule registry: turn change events into findings."""

from __future__ import annotations

from ..differ import ChangeEvent, ChangeType
from ..ir import InterfaceFile
from .breaking import ALL_BREAKING_RULES
from .lint import ALL_LINT_RULES
from .model import Finding, LintRule, Rule, parse_inline_ignores


def all_rules() -> tuple[Rule, ...]:
    """Every breaking-change (check) rule roschema ships."""
    return ALL_BREAKING_RULES


def all_lint_rules() -> tuple[LintRule, ...]:
    """Every lint rule roschema ships."""
    return ALL_LINT_RULES


def lint_interfaces(
    interfaces: dict[str, InterfaceFile], rules: tuple[LintRule, ...] | None = None
) -> list[Finding]:
    """Run lint rules over each interface, producing findings.

    Args:
        interfaces: Parsed interfaces keyed by ``package/kind/name``.
        rules: Lint rules to apply; defaults to :func:`all_lint_rules`.

    Returns:
        Findings in ``(interface, rule)`` order.
    """
    active = rules if rules is not None else all_lint_rules()
    findings: list[Finding] = []
    for key in sorted(interfaces):
        iface = interfaces[key]
        for rule in active:
            for hit in rule.check(iface):
                findings.append(
                    Finding(
                        rule=rule.id,
                        severity=rule.default_severity.value,
                        level="lint",
                        interface=key,
                        section=hit.section,
                        target=hit.target,
                        message=hit.message,
                        old_file=None,
                        old_line=None,
                        new_file=iface.source_file,
                        new_line=hit.line,
                        levels=("lint",),
                        inline_ignores=parse_inline_ignores(hit.comment),
                    )
                )
    return findings


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
        inline_ignores=parse_inline_ignores(getattr(event.new, "trailing_comment", None)),
    )
