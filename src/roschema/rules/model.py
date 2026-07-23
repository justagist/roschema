"""Rule and finding data types shared by every rule module."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from ..differ import ChangeEvent, ChangeType

# Compatibility levels, ordered most- to least- wire-significant.
LEVEL_ORDER = ("wire", "source", "introspection", "behavior")
LEVEL_LABEL = {
    "wire": "wire-breaking",
    "source": "source-breaking",
    "introspection": "introspection-breaking",
    "behavior": "behavioural",
}


class Severity(str, Enum):
    """Configured severity of a rule."""

    ERROR = "error"
    WARN = "warn"
    OFF = "off"


@dataclass(frozen=True)
class Rule:
    """A single rule: metadata, the events it handles and its message builder.

    Args:
        id: Permanent identifier (e.g. ``RS003``); never renumbered.
        title: Short human title.
        description: What the rule detects.
        rationale: Why it matters.
        levels: Compatibility levels this rule's findings violate.
        default_severity: Severity when not overridden by config.
        handles: Change-event types this rule turns into findings.
        message: Builds the finding message from an event.
        example_before/example_after: Illustrative snippets for the docs.
    """

    id: str
    title: str
    description: str
    rationale: str
    levels: tuple[str, ...]
    default_severity: Severity
    handles: tuple[ChangeType, ...]
    message: Callable[[ChangeEvent], str]
    example_before: str = ""
    example_after: str = ""

    @property
    def primary_level(self) -> str:
        """The most wire-significant level this rule violates."""
        for level in LEVEL_ORDER:
            if level in self.levels:
                return level
        return "behavior"


@dataclass(frozen=True)
class Finding:
    """One reported rule violation."""

    rule: str
    severity: str
    level: str
    interface: str
    section: str | None
    target: str
    message: str
    old_file: str | None
    old_line: int | None
    new_file: str | None
    new_line: int | None
    suppressed: bool = False

    @property
    def qualified_target(self) -> str:
        """Fully-qualified target: ``pkg/kind/Name[.section].member``.

        The ``message`` section is elided (a plain ``.msg`` has only one), but
        service/action sections are kept so findings read unambiguously.
        """
        parts = [self.interface]
        if self.section and self.section != "message":
            parts.append(self.section)
        if self.target:
            parts.append(self.target)
        return ".".join(parts)
