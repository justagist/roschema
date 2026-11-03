"""Changes that produce no reported finding, such as an added interface."""

from __future__ import annotations

from dataclasses import dataclass

from ..differ import ChangeEvent, ChangeType
from ..rules import Finding

NEW_INTERFACE = "a new interface breaks nothing"
NEW_CONSTANT = "a new constant breaks nothing"
# The reasons given for additions: no rule reports them, at any level, but they
# still make a package's next release a MINOR one.
ADDED = (NEW_INTERFACE, NEW_CONSTANT)


@dataclass(frozen=True)
class Change:
    """A change between baseline and target that is not a reported finding.

    Args:
        interface: Interface key (``package/kind/name``).
        section: Section value, or ``None`` for an interface-level change.
        target: Member name, or ``""`` for the whole interface.
        message: What changed.
        reason: Why it is not reported.
        rule: The rule that would report it, if any.
    """

    interface: str
    section: str | None
    target: str
    message: str
    reason: str
    rule: str | None = None

    @property
    def package(self) -> str:
        """Owning package name (first segment of the interface key)."""
        return self.interface.split("/", 1)[0]

    @property
    def qualified_target(self) -> str:
        """Fully-qualified target, written as for a :class:`Finding`."""
        parts = [self.interface]
        if self.section and self.section != "message":
            parts.append(self.section)
        if self.target:
            parts.append(self.target)
        return ".".join(parts)

    @classmethod
    def from_finding(cls, finding: Finding, reason: str) -> Change:
        """A finding that is not reported, for ``reason``."""
        return cls(
            finding.interface,
            finding.section,
            finding.target,
            finding.message,
            reason,
            finding.rule,
        )


def by_location(changes: list[Change]) -> list[Change]:
    """``changes`` sorted by interface, section and member, for listing."""
    return sorted(changes, key=lambda c: (c.interface, c.section or "", c.target))


def suppressed_changes(findings: list[Finding]) -> list[Change]:
    """The suppressed findings among ``findings``, with why each is suppressed."""
    return [
        Change.from_finding(f, f"suppressed by {f.suppressed_reason}")
        for f in findings
        if f.suppressed
    ]


def additions(events: list[ChangeEvent]) -> list[Change]:
    """The added interfaces and constants among ``events``."""
    out: list[Change] = []
    for event in events:
        if event.type is ChangeType.INTERFACE_ADDED:
            out.append(Change(event.interface, None, "", "interface added", NEW_INTERFACE))
        elif event.type is ChangeType.CONSTANT_ADDED:
            type_ref = getattr(event.new, "type", None)
            declared = type_ref.render() if type_ref is not None else ""
            value = getattr(event.new, "value_raw", "")
            message = f"constant added: {declared} {event.target}={value}"
            section = event.section.value if event.section else None
            out.append(Change(event.interface, section, event.target, message, NEW_CONSTANT))
    return out
