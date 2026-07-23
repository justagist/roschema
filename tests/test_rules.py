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


def test_constants_and_defaults_have_no_rule_yet():
    # RS020-RS030 land in Phase 5; the differ emits events but nothing fires.
    assert _findings("int32 X=1\n", "int32 X=2\n") == []
    assert _findings("int32 a 1\n", "int32 a 2\n") == []


def test_section_qualified_target_for_action():
    old = "int32 speed\n---\n---\n"
    new = "float32 speed\n---\n---\n"
    (f,) = _findings(old, new, kind="action")
    assert f.rule == "RS003"
    assert f.qualified_target == "p/action/T.goal.speed"


def test_interface_added_has_no_finding():
    o = parse_text("int32 a\n", "new", "p", "T", "msg")
    assert evaluate(diff_interfaces({}, {o.key: o})) == []
