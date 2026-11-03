"""Rule and finding data types shared by every rule module."""

from __future__ import annotations

import re
from collections.abc import Callable
from dataclasses import dataclass
from enum import Enum

from ..differ import ChangeEvent, ChangeType
from ..ir import InterfaceFile

_IGNORE_RE = re.compile(r"roschema:\s*ignore\s*=\s*([\w,\s]+)")


def parse_inline_ignores(comment: str | None) -> tuple[str, ...]:
    """Parse ``# roschema: ignore=RS001,RSL002`` from a trailing comment."""
    if not comment:
        return ()
    match = _IGNORE_RE.search(comment)
    if not match:
        return ()
    return tuple(part.strip() for part in match.group(1).split(",") if part.strip())


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
    """One reported rule violation.

    ``level`` is the primary (most wire-significant) level for display/JSON;
    ``levels`` is the rule's full level set, used for ``--level`` filtering.
    ``inline_ignores`` are the rule IDs suppressed by a trailing
    ``# roschema: ignore=...`` comment on the new-side member.
    """

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
    levels: tuple[str, ...] = ()
    inline_ignores: tuple[str, ...] = ()

    @property
    def package(self) -> str:
        """Owning package name (first segment of the interface key)."""
        return self.interface.split("/", 1)[0]

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


@dataclass(frozen=True)
class LintHit:
    """A single lint violation located within one interface.

    Args:
        section: Section value the hit is in, or ``None`` for file-level.
        target: Member name, or ``""`` for a file-level hit.
        line: 1-based line of the offending member, if applicable.
        message: Human-readable description.
        comment: Trailing comment on the member line (for inline suppression).
    """

    section: str | None
    target: str
    line: int | None
    message: str
    comment: str | None = None


@dataclass(frozen=True)
class LintRule:
    """A lint rule that inspects a single interface (no baseline).

    Args:
        id: Permanent identifier (``RSL###``).
        title: Short human title.
        description: What the rule detects.
        rationale: Why it matters.
        default_severity: Severity when not overridden by config.
        check: Yields a :class:`LintHit` per violation in an interface.
        example_flagged/example_preferred: Illustrative snippets for the docs.
    """

    id: str
    title: str
    description: str
    rationale: str
    default_severity: Severity
    check: Callable[[InterfaceFile], list[LintHit]]
    example_flagged: str = ""
    example_preferred: str = ""
