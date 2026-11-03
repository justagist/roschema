"""Intermediate representation for ROS 2 interface definitions.

All nodes are frozen dataclasses so parsed interfaces are immutable and safely
shareable between the differ, rules and reporters.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

BUILTIN_TYPES: frozenset[str] = frozenset(
    {
        "bool",
        "byte",
        "char",
        "float32",
        "float64",
        "int8",
        "int16",
        "int32",
        "int64",
        "uint8",
        "uint16",
        "uint32",
        "uint64",
        "string",
        "wstring",
    }
)


class ArrayKind(Enum):
    """How an array is bounded, if the type is an array at all."""

    NONE = "none"
    FIXED = "fixed"  # T[N]
    UNBOUNDED = "unbounded"  # T[]
    BOUNDED = "bounded"  # T[<=N]


class SectionKind(Enum):
    """Which section of an interface file a member belongs to."""

    MESSAGE = "message"
    REQUEST = "request"
    RESPONSE = "response"
    GOAL = "goal"
    RESULT = "result"
    FEEDBACK = "feedback"


@dataclass(frozen=True)
class TypeRef:
    """Structured representation of a field/constant type.

    Args:
        base: The bare type name (e.g. ``float32``, ``Pose``).
        package: Owning package for complex types, or ``None`` for builtins
            and same-package references.
        string_bound: Upper bound for ``string<=N`` / ``wstring<=N``, else ``None``.
        array_kind: Whether and how the type is arrayed.
        array_bound: The ``N`` for fixed (``T[N]``) or bounded (``T[<=N]``) arrays.
        is_builtin: True when the base type is a primitive and no package is set.
    """

    base: str
    package: str | None
    string_bound: int | None
    array_kind: ArrayKind
    array_bound: int | None
    is_builtin: bool

    def render(self) -> str:
        """Render the canonical textual form of this type."""
        base = f"{self.package}/{self.base}" if self.package else self.base
        if self.string_bound is not None:
            base = f"{base}<={self.string_bound}"
        if self.array_kind is ArrayKind.UNBOUNDED:
            return f"{base}[]"
        if self.array_kind is ArrayKind.FIXED:
            return f"{base}[{self.array_bound}]"
        if self.array_kind is ArrayKind.BOUNDED:
            return f"{base}[<={self.array_bound}]"
        return base


@dataclass(frozen=True)
class Default:
    """A field default value, keeping both raw token and parsed form.

    Args:
        raw: Verbatim default text as written in the source.
        value: Parsed Python value (``int``, ``float``, ``bool``, ``str``, or a
            ``tuple`` for array defaults).
    """

    raw: str
    value: object


@dataclass(frozen=True)
class Field:
    """A single field within an interface section."""

    name: str
    type: TypeRef
    default: Default | None
    trailing_comment: str | None
    source_file: str
    line: int
    raw_text: str


@dataclass(frozen=True)
class Constant:
    """A named constant within an interface section.

    Args:
        value_raw: Verbatim constant value token from the source.
        value: Parsed Python value.
    """

    name: str
    type: TypeRef
    value_raw: str
    value: object
    trailing_comment: str | None
    source_file: str
    line: int
    raw_text: str


Member = Field | Constant


@dataclass(frozen=True)
class Section:
    """An ordered group of members (one of the ``---``-delimited sections)."""

    kind: SectionKind
    members: tuple[Member, ...]


@dataclass(frozen=True)
class InterfaceFile:
    """A fully parsed ``.msg``, ``.srv`` or ``.action`` file.

    Args:
        package: Owning ROS package name.
        name: Interface type name without extension (e.g. ``Pose``).
        kind: One of ``msg``, ``srv`` or ``action``.
        sections: Parsed sections in file order.
        source_file: Path the interface was read from.
        raw_text: Original file contents, retained for formatting.
    """

    package: str
    name: str
    kind: str
    sections: tuple[Section, ...]
    source_file: str
    raw_text: str

    @property
    def key(self) -> str:
        """Stable identity used to align interfaces across baselines."""
        return f"{self.package}/{self.kind}/{self.name}"

    def fields(self) -> tuple[Field, ...]:
        """All fields across every section, in order."""
        return tuple(m for s in self.sections for m in s.members if isinstance(m, Field))

    def constants(self) -> tuple[Constant, ...]:
        """All constants across every section, in order."""
        return tuple(m for s in self.sections for m in s.members if isinstance(m, Constant))
