"""Structural diff of parsed interfaces into typed change events.

Alignment is positional-aware because CDR serialisation is positional: fields
match by name within a section, renames are detected as a removed/added pair at
the same index with an identical type, and a changed relative order of common
fields is itself a (wire-breaking) event.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from enum import Enum

from .ir import ArrayKind, Constant, Field, InterfaceFile, SectionKind


class ChangeType(Enum):
    """The kinds of change the differ can report."""

    INTERFACE_ADDED = "interface_added"
    INTERFACE_REMOVED = "interface_removed"
    FIELD_ADDED = "field_added"
    FIELD_REMOVED = "field_removed"
    FIELD_RENAMED = "field_renamed"
    FIELD_TYPE_CHANGED = "field_type_changed"
    FIELD_ARRAY_KIND_CHANGED = "field_array_kind_changed"
    FIELD_BOUND_TIGHTENED = "field_bound_tightened"
    FIELD_BOUND_LOOSENED = "field_bound_loosened"
    FIELD_REORDERED = "field_reordered"
    FIELD_DEFAULT_CHANGED = "field_default_changed"
    CONSTANT_ADDED = "constant_added"
    CONSTANT_REMOVED = "constant_removed"
    CONSTANT_VALUE_CHANGED = "constant_value_changed"
    CONSTANT_TYPE_CHANGED = "constant_type_changed"


@dataclass(frozen=True)
class ChangeEvent:
    """A single structural change between the old and new interface sets.

    Args:
        type: What changed.
        interface: Interface key (``package/kind/name``) the change belongs to.
        section: Section the change is in, or ``None`` for interface-level events.
        target: Member name the change is about (``""`` for interface/section-level).
        old: The old IR node (Field/Constant/InterfaceFile), if any.
        new: The new IR node, if any.
        detail: Extra structured context (e.g. reordering orders).
    """

    type: ChangeType
    interface: str
    section: SectionKind | None
    target: str
    old: object | None = None
    new: object | None = None
    detail: dict[str, object] = field(default_factory=dict)


def diff_interfaces(
    old: dict[str, InterfaceFile], new: dict[str, InterfaceFile]
) -> list[ChangeEvent]:
    """Diff two interface sets keyed by ``package/kind/name``."""
    events: list[ChangeEvent] = []
    for key in sorted(set(old) | set(new)):
        old_iface = old.get(key)
        new_iface = new.get(key)
        if old_iface is not None and new_iface is None:
            events.append(
                ChangeEvent(ChangeType.INTERFACE_REMOVED, key, None, "", old=old_iface)
            )
        elif new_iface is not None and old_iface is None:
            events.append(
                ChangeEvent(ChangeType.INTERFACE_ADDED, key, None, "", new=new_iface)
            )
        elif old_iface is not None and new_iface is not None:
            _diff_interface(key, old_iface, new_iface, events)
    return events


def _diff_interface(
    key: str, old: InterfaceFile, new: InterfaceFile, events: list[ChangeEvent]
) -> None:
    for sec_old, sec_new in zip(old.sections, new.sections, strict=False):
        _diff_fields(key, sec_old.kind, sec_old.members, sec_new.members, events)
        _diff_constants(key, sec_old.kind, sec_old.members, sec_new.members, events)


def _diff_fields(
    key: str,
    section: SectionKind,
    old_members: tuple[object, ...],
    new_members: tuple[object, ...],
    events: list[ChangeEvent],
) -> None:
    old_fields = [m for m in old_members if isinstance(m, Field)]
    new_fields = [m for m in new_members if isinstance(m, Field)]
    old_by = {f.name: (i, f) for i, f in enumerate(old_fields)}
    new_by = {f.name: (i, f) for i, f in enumerate(new_fields)}
    removed = [n for n in old_by if n not in new_by]
    added = [n for n in new_by if n not in old_by]

    # Rename detection: removed + added at the same index with identical type.
    for old_name in list(removed):
        old_idx, old_field = old_by[old_name]
        for new_name in list(added):
            new_idx, new_field = new_by[new_name]
            if new_idx == old_idx and old_field.type == new_field.type:
                events.append(
                    ChangeEvent(
                        ChangeType.FIELD_RENAMED,
                        key,
                        section,
                        new_name,
                        old=old_field,
                        new=new_field,
                        detail={"old_name": old_name},
                    )
                )
                removed.remove(old_name)
                added.remove(new_name)
                break

    for name in removed:
        events.append(
            ChangeEvent(ChangeType.FIELD_REMOVED, key, section, name, old=old_by[name][1])
        )
    for name in added:
        events.append(
            ChangeEvent(ChangeType.FIELD_ADDED, key, section, name, new=new_by[name][1])
        )

    for name in (n for n in old_by if n in new_by):
        old_field = old_by[name][1]
        new_field = new_by[name][1]
        change = _classify_type_change(old_field, new_field)
        if change is not None:
            events.append(
                ChangeEvent(change, key, section, name, old=old_field, new=new_field)
            )
        elif old_field.default != new_field.default:
            events.append(
                ChangeEvent(
                    ChangeType.FIELD_DEFAULT_CHANGED,
                    key,
                    section,
                    name,
                    old=old_field,
                    new=new_field,
                )
            )

    old_order = [f.name for f in old_fields if f.name in new_by]
    new_order = [f.name for f in new_fields if f.name in old_by]
    if old_order != new_order and sorted(old_order) == sorted(new_order):
        events.append(
            ChangeEvent(
                ChangeType.FIELD_REORDERED,
                key,
                section,
                "",
                detail={"old_order": old_order, "new_order": new_order},
            )
        )


def _classify_type_change(old: Field, new: Field) -> ChangeType | None:
    """Return the single most significant type-related change, or ``None``."""
    o, n = old.type, new.type
    if o.base != n.base or o.package != n.package or o.is_builtin != n.is_builtin:
        return ChangeType.FIELD_TYPE_CHANGED
    if o.array_kind != n.array_kind:
        return ChangeType.FIELD_ARRAY_KIND_CHANGED
    # A fixed array's size is part of the wire layout: any change is a type change.
    if o.array_kind is ArrayKind.FIXED and o.array_bound != n.array_bound:
        return ChangeType.FIELD_TYPE_CHANGED
    if o.array_kind is ArrayKind.BOUNDED and o.array_bound != n.array_bound:
        return _bound_direction(o.array_bound, n.array_bound)
    if o.string_bound != n.string_bound:
        return _bound_direction(o.string_bound, n.string_bound)
    return None


def _bound_direction(old_bound: int | None, new_bound: int | None) -> ChangeType:
    """Tightened when the capacity shrinks, loosened when it grows (None = inf)."""
    old_cap = math.inf if old_bound is None else old_bound
    new_cap = math.inf if new_bound is None else new_bound
    if new_cap < old_cap:
        return ChangeType.FIELD_BOUND_TIGHTENED
    return ChangeType.FIELD_BOUND_LOOSENED


def _diff_constants(
    key: str,
    section: SectionKind,
    old_members: tuple[object, ...],
    new_members: tuple[object, ...],
    events: list[ChangeEvent],
) -> None:
    old_by = {c.name: c for c in old_members if isinstance(c, Constant)}
    new_by = {c.name: c for c in new_members if isinstance(c, Constant)}
    for name in (n for n in old_by if n not in new_by):
        events.append(
            ChangeEvent(ChangeType.CONSTANT_REMOVED, key, section, name, old=old_by[name])
        )
    for name in (n for n in new_by if n not in old_by):
        events.append(
            ChangeEvent(ChangeType.CONSTANT_ADDED, key, section, name, new=new_by[name])
        )
    for name in (n for n in old_by if n in new_by):
        old_c = old_by[name]
        new_c = new_by[name]
        if old_c.type != new_c.type:
            events.append(
                ChangeEvent(
                    ChangeType.CONSTANT_TYPE_CHANGED, key, section, name, old=old_c, new=new_c
                )
            )
        elif old_c.value != new_c.value:
            events.append(
                ChangeEvent(
                    ChangeType.CONSTANT_VALUE_CHANGED, key, section, name, old=old_c, new=new_c
                )
            )
