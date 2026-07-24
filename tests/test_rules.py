"""Tests for the breaking-change rules and the registry."""

from __future__ import annotations

from roschema.differ import diff_interfaces
from roschema.parser import parse_text
from roschema.rules import evaluate


def _findings(old: str, new: str, kind: str = "msg"):
    o = parse_text(old, "old", "p", "T", kind)
    n = parse_text(new, "new", "p", "T", kind)
    return evaluate(diff_interfaces({o.key: o}, {n.key: n}))


def _ids(findings):
    return [f.rule for f in findings]


def test_rs001_field_removed():
    (f,) = _findings("int32 a\nint32 b\n", "int32 a\n")
    assert f.rule == "RS001" and f.severity == "error" and f.level == "wire"
    assert f.qualified_target == "p/msg/T.b"


def test_rs002_field_added():
    assert _ids(_findings("int32 a\n", "int32 a\nint32 b\n")) == ["RS002"]


def test_rs003_type_changed_message():
    (f,) = _findings("float32 theta\n", "float64 theta\n")
    assert f.rule == "RS003"
    assert f.message == "type changed float32 -> float64"


def test_rs004_reordered():
    assert _ids(_findings("int32 a\nint32 b\n", "int32 b\nint32 a\n")) == ["RS004"]


def test_rs005_renamed_not_add_remove():
    (f,) = _findings("float32 theta\n", "float32 yaw\n")
    assert f.rule == "RS005"
    assert f.message == "field renamed 'theta' -> 'yaw'"


def test_rs006_array_kind():
    assert _ids(_findings("int32[] a\n", "int32[3] a\n")) == ["RS006"]


def test_rs007_tightened_is_error():
    (f,) = _findings("string<=64 s\n", "string<=16 s\n")
    assert f.rule == "RS007" and f.severity == "error"


def test_rs008_loosened_is_warn():
    (f,) = _findings("uint8[<=4] a\n", "uint8[<=9] a\n")
    assert f.rule == "RS008" and f.severity == "warn"


def test_rs040_interface_removed():
    o = parse_text("int32 a\n", "old", "p", "T", "msg")
    (f,) = evaluate(diff_interfaces({o.key: o}, {}))
    assert f.rule == "RS040" and f.severity == "error"


def test_section_qualified_target_for_action():
    old = "int32 speed\n---\n---\n"
    new = "float32 speed\n---\n---\n"
    (f,) = _findings(old, new, kind="action")
    assert f.rule == "RS003"
    assert f.qualified_target == "p/action/T.goal.speed"


def test_interface_added_has_no_finding():
    o = parse_text("int32 a\n", "new", "p", "T", "msg")
    assert evaluate(diff_interfaces({}, {o.key: o})) == []


def test_rs020_constant_removed():
    assert _ids(_findings("int32 X=1\nint32 Y=2\n", "int32 X=1\n")) == ["RS020"]


def test_rs021_constant_value_changed():
    (f,) = _findings("int32 X=1\n", "int32 X=2\n")
    assert f.rule == "RS021" and f.message == "constant value changed 1 -> 2"
    assert f.severity == "error"


def test_rs022_constant_type_changed():
    (f,) = _findings("int32 X=1\n", "uint8 X=1\n")
    assert f.rule == "RS022"


def test_constant_added_has_no_finding():
    assert _findings("int32 X=1\n", "int32 X=1\nint32 Y=2\n") == []


def test_rs030_default_changed_is_behaviour_warn():
    (f,) = _findings("int32 a 1\n", "int32 a 2\n")
    assert f.rule == "RS030" and f.severity == "warn" and f.level == "behavior"
    assert f.message == "default changed 1 -> 2"


def test_rs030_default_added_and_removed():
    (added,) = _findings("int32 a\n", "int32 a 5\n")
    assert added.message == "default added: 5"
    (removed,) = _findings("int32 a 5\n", "int32 a\n")
    assert removed.message.startswith("default removed")


def test_rs060_fires_off_by_default_when_not_bumped():
    old = "uint32 MESSAGE_VERSION=1\nint32 a\n"
    new = "uint32 MESSAGE_VERSION=1\nint32 a\nint32 b\n"
    findings = _findings(old, new)
    rs060 = [f for f in findings if f.rule == "RS060"]
    assert len(rs060) == 1
    assert rs060[0].severity == "off"  # opt-in; enabled via config


def test_rs060_not_fired_when_bumped():
    old = "uint32 MESSAGE_VERSION=1\nint32 a\n"
    new = "uint32 MESSAGE_VERSION=2\nint32 a\nint32 b\n"
    assert "RS060" not in _ids(_findings(old, new))


def test_rs060_needs_the_constant():
    assert "RS060" not in _ids(_findings("int32 a\n", "int32 a\nint32 b\n"))
