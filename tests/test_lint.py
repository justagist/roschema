"""Tests for lint rules (rosidl-aligned naming) and lint finalization."""

from __future__ import annotations

import json

import pytest
from typer.testing import CliRunner

from _helpers import write_package
from roschema.cli import app
from roschema.config import Config, finalize_lint
from roschema.parser import parse_text
from roschema.rules import lint_interfaces

runner = CliRunner()


def _lint(text, kind="msg", name="T"):
    iface = parse_text(text, f"p/{kind}/{name}.{kind}", "p", name, kind)
    return lint_interfaces({iface.key: iface})


def _ids(findings):
    return sorted({f.rule for f in findings})


def test_rsl001_field_snake_case():
    assert "RSL001" in _ids(_lint("int32 BadField\n"))
    assert "RSL001" in _ids(_lint("int32 trailing_\n"))
    assert "RSL001" not in _ids(_lint("int32 good_field\n"))


def test_rsl002_constant_upper_snake():
    assert "RSL002" in _ids(_lint("int32 badName=1\n"))
    assert "RSL002" not in _ids(_lint("int32 GOOD_NAME=1\n"))


def test_rsl003_interface_pascal_case():
    assert "RSL003" in _ids(_lint("int32 a\n", name="lower_name"))
    assert "RSL003" not in _ids(_lint("int32 a\n", name="GoodName"))


def test_rsl004_off_by_default():
    raw = _lint("int32 a\n")  # no trailing comment
    assert "RSL004" in _ids(raw)
    assert finalize_lint(raw, Config()) == []  # off -> dropped
    enabled = finalize_lint(raw, Config(lint_rules={"RSL004": "warn"}))
    assert "RSL004" in _ids(enabled)


def test_rsl005_discouraged_types():
    assert "RSL005" in _ids(_lint("char c\n"))
    assert "RSL005" in _ids(_lint("byte b\n"))
    assert "RSL005" not in _ids(_lint("byte[] data\n"))  # byte array is fine
    assert "RSL005" not in _ids(_lint("uint8 x\n"))


def test_rsl006_unbounded_off_by_default():
    raw = _lint("string s  # doc\n")  # unbounded string
    assert "RSL006" in _ids(raw)
    assert finalize_lint(raw, Config()) == []
    assert _ids(finalize_lint(raw, Config(lint_rules={"RSL006": "warn"}))) == ["RSL006"]
    assert "RSL006" not in _ids(_lint("string<=8 s  # doc\n"))


def test_rsl010_srv_request_response_shadow():
    assert "RSL010" in _ids(_lint("int32 value\n---\nint32 value\n", kind="srv"))
    assert "RSL010" not in _ids(_lint("int32 req\n---\nint32 resp\n", kind="srv"))


def test_lint_inline_suppression():
    raw = _lint("int32 BadField  # roschema: ignore=RSL001\n")
    out = finalize_lint(raw, Config())
    rsl001 = [f for f in out if f.rule == "RSL001"]
    assert rsl001 and rsl001[0].suppressed is True


def test_lint_severity_override_off():
    raw = _lint("int32 BadField\n")
    assert finalize_lint(raw, Config(lint_rules={"RSL001": "off"})) == []


def test_cli_lint_reports_and_exits_1(tmp_path):
    write_package(tmp_path, "p", msgs={"Bad": "int32 BadField  # doc\n"})
    result = runner.invoke(app, ["lint", str(tmp_path)])
    assert result.exit_code == 1
    assert "RSL001" in result.stdout


def test_cli_lint_clean_exits_0(tmp_path):
    write_package(tmp_path, "p", msgs={"Good": "int32 good_field  # doc\n"})
    result = runner.invoke(app, ["lint", str(tmp_path)])
    assert result.exit_code == 0
    assert "no lint issues" in result.stdout


def test_cli_lint_rules_enables_off_rule(tmp_path):
    # RSL004 (missing doc) is off by default; --rules enables it
    write_package(tmp_path, "p", msgs={"Good": "int32 good_field\n"})
    default = runner.invoke(app, ["lint", str(tmp_path)])
    assert default.exit_code == 0
    enabled = runner.invoke(app, ["lint", str(tmp_path), "--rules", "RSL004=error"])
    assert enabled.exit_code == 1
    assert "RSL004" in enabled.stdout


def test_cli_lint_rules_bare_means_warn(tmp_path):
    write_package(tmp_path, "p", msgs={"Good": "int32 good_field\n"})
    result = runner.invoke(app, ["lint", str(tmp_path), "--rules", "RSL004"])
    assert result.exit_code == 0  # warn does not fail
    assert "RSL004" in result.stdout


def test_cli_lint_rules_off_beats_config(tmp_path):
    (tmp_path / "roschema.toml").write_text('[lint.rules]\nRSL001 = "error"\n')
    write_package(tmp_path, "p", msgs={"Bad": "int32 BadField  # doc\n"})
    result = runner.invoke(app, ["lint", str(tmp_path), "--rules", "RSL001=off"])
    assert result.exit_code == 0  # CLI override beats config


def test_cli_lint_rules_rejects_bad_input(tmp_path):
    write_package(tmp_path, "p", msgs={"Good": "int32 good_field  # doc\n"})
    assert runner.invoke(app, ["lint", str(tmp_path), "--rules", "RSL999=warn"]).exit_code == 2
    assert runner.invoke(app, ["lint", str(tmp_path), "--rules", "RSL001=loud"]).exit_code == 2


@pytest.mark.parametrize(
    "package_severity,options,expected",
    [
        ("off", [], {"other": "warn"}),
        ("error", [], {"demo": "error", "other": "warn"}),
        ("error", ["--rules", "RSL001=off"], {}),
    ],
)
def test_package_lint_precedence(tmp_path, package_severity, options, expected):
    for package in ("demo", "other"):
        write_package(tmp_path, package, msgs={"T": "int32 BadField # doc\n"})
    (tmp_path / "roschema.toml").write_text('[lint.rules]\nRSL001 = "warn"\n')
    (tmp_path / "demo" / "roschema.toml").write_text(
        f'[lint.rules]\nRSL001 = "{package_severity}"\n'
    )
    result = runner.invoke(app, ["lint", str(tmp_path), "--format", "json", *options])
    assert result.exit_code == (1 if "error" in expected.values() else 0)
    findings = json.loads(result.stdout)["findings"]
    assert {f["package"]: f["severity"] for f in findings} == expected


def test_lint_json_has_no_semver_advice(tmp_path):
    write_package(tmp_path, "demo", msgs={"T": "int32 BadField\n"})
    result = runner.invoke(app, ["lint", str(tmp_path), "--format", "json"])
    assert result.exit_code == 1
    assert json.loads(result.stdout)["summary"] == {
        "total": 1,
        "errors": 1,
        "warnings": 0,
        "suppressed": 0,
    }


@pytest.mark.parametrize(
    "field_type,unbounded",
    [
        ("string[4]", True),
        ("wstring[<=4]", True),
        ("string<=8[]", True),
        ("string<=8[4]", False),
        ("wstring<=8[<=4]", False),
        ("int32[4]", False),
    ],
)
def test_rsl006_checks_string_elements_independently(field_type, unbounded):
    findings = finalize_lint(
        _lint(f"{field_type} names # doc\n"), Config(lint_rules={"RSL006": "error"})
    )
    assert [(f.rule, f.severity) for f in findings] == ([("RSL006", "error")] if unbounded else [])
