"""Tests for --deep transitive breakage (RS110)."""

from __future__ import annotations

from dataclasses import replace

import pytest
from typer.testing import CliRunner

from _helpers import write_package
from roschema.cli import app
from roschema.deep import transitive_findings
from roschema.differ import diff_interfaces
from roschema.parser import parse_text
from roschema.rules import evaluate

runner = CliRunner()


def _iface(name, body):
    return parse_text(body, f"my_msgs/msg/{name}.msg", "my_msgs", name, "msg")


def _map(*ifaces):
    return {i.key: i for i in ifaces}


def test_rs110_flags_embedding_interface():
    old = _map(
        _iface("Point", "float64 x\nfloat64 y\n"),
        _iface("Pose", "my_msgs/Point position\nfloat32 theta\n"),
    )
    new = _map(
        _iface("Point", "float32 x\nfloat64 y\n"),  # x type changed (wire)
        _iface("Pose", "my_msgs/Point position\nfloat32 theta\n"),  # unchanged text
    )
    direct = evaluate(diff_interfaces(old, new))
    deep = transitive_findings(new, direct)
    assert [f.rule for f in deep] == ["RS110"]
    assert deep[0].interface == "my_msgs/msg/Pose"
    assert "my_msgs/msg/Point" in deep[0].message


def test_rs110_not_emitted_without_a_changed_dep():
    new = _map(
        _iface("Point", "float64 x\n"),
        _iface("Pose", "my_msgs/Point position\n"),
    )
    # no direct findings -> nothing changed -> no transitive breakage
    assert transitive_findings(new, []) == []


def test_rs110_not_emitted_for_a_non_wire_change():
    old = _map(_iface("Point", "float64 x\n"), _iface("Pose", "my_msgs/Point p\nint32 A=1\n"))
    new = _map(_iface("Point", "float64 x\n"), _iface("Pose", "my_msgs/Point p\nint32 A=2\n"))
    direct = evaluate(diff_interfaces(old, new))  # RS021 (constant), source/behavior only
    assert transitive_findings(new, direct) == []


def test_rs110_takes_root_severity_and_skips_suppressed_roots():
    old = _map(_iface("Point", "string<=8 s\n"), _iface("Pose", "my_msgs/Point p\n"))
    new = _map(_iface("Point", "string<=16 s\n"), _iface("Pose", "my_msgs/Point p\n"))
    loosened = evaluate(diff_interfaces(old, new))  # RS008, a warning
    assert [(f.rule, f.severity) for f in transitive_findings(new, loosened)] == [("RS110", "warn")]
    suppressed = [replace(f, suppressed=True) for f in loosened]
    assert transitive_findings(new, suppressed) == []


def test_rs110_prefers_an_error_root():
    old = _map(
        _iface("Near", "string<=8 s\n"),
        _iface("Far", "float64 x\n"),
        _iface("Mid", "my_msgs/Far f\n"),
        _iface("Top", "my_msgs/Near n\nmy_msgs/Mid m\n"),
    )
    new = dict(old)
    new.update(_map(_iface("Near", "string<=16 s\n"), _iface("Far", "float32 x\n")))
    deep = transitive_findings(new, evaluate(diff_interfaces(old, new)))
    top = next(f for f in deep if f.interface == "my_msgs/msg/Top")
    assert top.severity == "error"
    assert "my_msgs/msg/Far" in top.message


def test_cli_deep_respects_allowlisted_root(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    write_package(old, "demo", msgs={"Point": "int32 x\n", "Wrapper": "demo/Point point\n"})
    write_package(new, "demo", msgs={"Point": "float64 x\n", "Wrapper": "demo/Point point\n"})
    (new / "roschema.toml").write_text(
        '[check.allow]\n"demo/msg/Point.x" = {rules = ["RS003"], reason = "planned"}\n'
    )
    result = runner.invoke(app, ["check", str(new), "--against", str(old), "--deep"])
    assert result.exit_code == 0
    assert "RS110" not in result.stdout


def test_cli_deep_adds_rs110(tmp_path):
    old = tmp_path / "old"
    new = tmp_path / "new"
    write_package(
        old,
        "my_msgs",
        msgs={
            "Point": "float64 x\nfloat64 y\n",
            "Pose": "my_msgs/Point position\nfloat32 theta\n",
        },
    )
    write_package(
        new,
        "my_msgs",
        msgs={
            "Point": "float32 x\nfloat64 y\n",  # changed
            "Pose": "my_msgs/Point position\nfloat32 theta\n",  # unchanged
        },
    )

    shallow = runner.invoke(app, ["check", str(new), "--against", str(old)])
    assert "RS110" not in shallow.stdout

    deep = runner.invoke(app, ["check", str(new), "--against", str(old), "--deep"])
    assert deep.exit_code == 1
    assert "RS110" in deep.stdout
    assert "Pose" in deep.stdout


@pytest.mark.parametrize(
    "workspace_deep,package_deep,options,expected",
    [
        (True, None, [], True),
        (False, True, [], True),
        (True, False, [], False),
        (True, None, ["--no-deep"], False),
        (False, False, ["--deep"], True),
    ],
)
def test_config_deep_precedence(tmp_path, workspace_deep, package_deep, options, expected):
    old, new = tmp_path / "old", tmp_path / "new"
    for root, field_type in [(old, "int32"), (new, "float64")]:
        write_package(
            root,
            "demo",
            msgs={
                "Point": f"{field_type} x\n",
                "Wrapper": "demo/Point point\n",
            },
        )
    (new / "roschema.toml").write_text(f"[check]\ndeep = {str(workspace_deep).lower()}\n")
    if package_deep is not None:
        (new / "demo" / "roschema.toml").write_text(
            f"[check]\ndeep = {str(package_deep).lower()}\n"
        )
    result = runner.invoke(app, ["check", str(new), "--against", str(old), *options])
    assert result.exit_code == 1
    assert ("RS110" in result.stdout) == expected
