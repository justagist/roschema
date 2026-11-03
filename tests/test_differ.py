"""Tests for the structural differ: one per change-event type."""

from __future__ import annotations

import pytest

from roschema.differ import ChangeType, diff_interfaces
from roschema.ir import SectionKind
from roschema.parser import parse_text


def _events(old: str, new: str, kind: str = "msg"):
    o = parse_text(old, "old", "p", "T", kind)
    n = parse_text(new, "new", "p", "T", kind)
    return diff_interfaces({o.key: o}, {n.key: n})


def _types(events):
    return [e.type for e in events]


def test_field_added():
    assert _types(_events("int32 a\n", "int32 a\nint32 b\n")) == [ChangeType.FIELD_ADDED]


def test_field_removed():
    assert _types(_events("int32 a\nint32 b\n", "int32 a\n")) == [ChangeType.FIELD_REMOVED]


def test_field_renamed_single_event():
    events = _events("float32 theta\n", "float32 yaw\n")
    assert _types(events) == [ChangeType.FIELD_RENAMED]
    assert events[0].detail["old_name"] == "theta"
    assert events[0].target == "yaw"


def test_rename_needs_same_position_and_type():
    # different type at same position -> not a rename
    assert _types(_events("float32 theta\n", "int32 yaw\n")) == [
        ChangeType.FIELD_REMOVED,
        ChangeType.FIELD_ADDED,
    ]


def test_type_changed():
    assert _types(_events("float32 x\n", "float64 x\n")) == [ChangeType.FIELD_TYPE_CHANGED]


def test_fixed_array_size_is_type_change():
    assert _types(_events("int32[3] x\n", "int32[4] x\n")) == [ChangeType.FIELD_TYPE_CHANGED]


def test_array_kind_changed():
    assert _types(_events("int32[] x\n", "int32[4] x\n")) == [
        ChangeType.FIELD_ARRAY_KIND_CHANGED
    ]


def test_bound_tightened_and_loosened():
    assert _types(_events("string<=64 s\n", "string<=16 s\n")) == [
        ChangeType.FIELD_BOUND_TIGHTENED
    ]
    assert _types(_events("uint8[<=4] a\n", "uint8[<=9] a\n")) == [
        ChangeType.FIELD_BOUND_LOOSENED
    ]


def test_string_bound_removed_is_loosened():
    assert _types(_events("string<=10 s\n", "string s\n")) == [
        ChangeType.FIELD_BOUND_LOOSENED
    ]


def test_reordered():
    events = _events("int32 a\nint32 b\n", "int32 b\nint32 a\n")
    assert _types(events) == [ChangeType.FIELD_REORDERED]
    assert events[0].detail["old_order"] == ["a", "b"]
    assert events[0].detail["new_order"] == ["b", "a"]


def test_default_changed():
    assert _types(_events("int32 a 1\n", "int32 a 2\n")) == [
        ChangeType.FIELD_DEFAULT_CHANGED
    ]


def test_constant_events():
    assert _types(_events("int32 X=1\n", "")) == [ChangeType.CONSTANT_REMOVED]
    assert _types(_events("", "int32 X=1\n")) == [ChangeType.CONSTANT_ADDED]
    assert _types(_events("int32 X=1\n", "int32 X=2\n")) == [
        ChangeType.CONSTANT_VALUE_CHANGED
    ]
    assert _types(_events("int32 X=1\n", "uint8 X=1\n")) == [
        ChangeType.CONSTANT_TYPE_CHANGED
    ]


def test_interface_added_and_removed():
    o = parse_text("int32 a\n", "old", "p", "T", "msg")
    events = diff_interfaces({o.key: o}, {})
    assert _types(events) == [ChangeType.INTERFACE_REMOVED]
    events = diff_interfaces({}, {o.key: o})
    assert _types(events) == [ChangeType.INTERFACE_ADDED]


def test_section_carried_on_event():
    events = _events("int32 a\n---\nint32 b\n", "int32 a\n---\nfloat32 b\n", kind="srv")
    assert _types(events) == [ChangeType.FIELD_TYPE_CHANGED]
    assert events[0].section is SectionKind.RESPONSE


def test_no_events_for_identical():
    assert _events("int32 a  # doc\n", "int32 a  # different doc\n") == []


def test_message_version_not_bumped_event():
    events = _events(
        "uint32 MESSAGE_VERSION=1\nint32 a\n",
        "uint32 MESSAGE_VERSION=1\nint32 a\nint32 b\n",
    )
    assert ChangeType.MESSAGE_VERSION_NOT_BUMPED in _types(events)


def test_message_version_bumped_no_event():
    events = _events(
        "uint32 MESSAGE_VERSION=1\nint32 a\n",
        "uint32 MESSAGE_VERSION=2\nint32 a\nint32 b\n",
    )
    assert ChangeType.MESSAGE_VERSION_NOT_BUMPED not in _types(events)


def test_message_version_no_event_without_structural_change():
    # only a default change is not structural, so RS060's event must not fire
    events = _events(
        "uint32 MESSAGE_VERSION=1\nint32 a 1\n",
        "uint32 MESSAGE_VERSION=1\nint32 a 2\n",
    )
    assert ChangeType.MESSAGE_VERSION_NOT_BUMPED not in _types(events)


def test_tightening_either_bound_takes_precedence():
    for old, new in [
        ("string<=64[<=4] names\n", "string<=8[<=16] names\n"),
        ("string<=8[<=16] names\n", "string<=64[<=4] names\n"),
    ]:
        assert _types(_events(old, new)) == [ChangeType.FIELD_BOUND_TIGHTENED]


def test_loosening_both_bounds_stays_a_single_event():
    assert _types(_events("string<=8[<=4] names\n", "string<=64[<=16] names\n")) == [
        ChangeType.FIELD_BOUND_LOOSENED
    ]


@pytest.mark.parametrize(
    "old,new,event",
    [
        ("float64 INVALID=nan\n", "float64 INVALID=NaN\n", None),
        ("float64 x nan\n", "float64 x nan\n", None),
        ("float64[] x [nan, 1]\n", "float64[] x [NaN, 1.0]\n", None),
        ("float64 INVALID=nan\n", "float64 INVALID=1\n", ChangeType.CONSTANT_VALUE_CHANGED),
        ("float64 x nan\n", "float64 x 1\n", ChangeType.FIELD_DEFAULT_CHANGED),
        ("float64[] x [nan, 1]\n", "float64[] x [nan, 2]\n", ChangeType.FIELD_DEFAULT_CHANGED),
        ("float64[] x [nan]\n", "float64[] x [nan, 1]\n", ChangeType.FIELD_DEFAULT_CHANGED),
    ],
)
def test_nan_value_equivalence(old, new, event):
    """NaNs compare equally without hiding changes to neighbouring array values."""
    assert _types(_events(old, new)) == ([] if event is None else [event])
