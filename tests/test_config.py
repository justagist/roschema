"""Tests for configuration loading, precedence and finalization."""

from __future__ import annotations

import pytest

from _helpers import write_package
from roschema.config import (
    AllowEntry,
    Config,
    ConfigError,
    ScopeConfig,
    finalize_findings,
    load_config,
)
from roschema.discovery import discover
from roschema.rules import Finding
from roschema.vfs import RealFS


def _pkgs(root):
    return discover(RealFS(root), ".")


def _finding(rule, severity="error", levels=("wire",), target="a", inline=()):
    return Finding(
        rule=rule,
        severity=severity,
        level=levels[0],
        interface="demo/msg/T",
        section="message",
        target=target,
        message="m",
        old_file=None,
        old_line=None,
        new_file=None,
        new_line=None,
        levels=levels,
        inline_ignores=inline,
    )


def test_workspace_config_severity_and_level(tmp_path):
    (tmp_path / "roschema.toml").write_text(
        '[check]\nlevel = "wire"\n[check.rules]\nRS008 = "off"\nRS002 = "warn"\n'
    )
    write_package(tmp_path, "my_pkg", msgs={"Foo": "int32 a\n"})
    cfg = load_config(tmp_path, _pkgs(tmp_path))
    assert cfg.workspace.level == "wire"
    assert cfg.effective_severity("RS008", "my_pkg", "error") == "off"
    assert cfg.effective_severity("RS002", "my_pkg", "error") == "warn"
    assert cfg.effective_level("my_pkg", None) == "wire"
    assert cfg.effective_level("my_pkg", "source") == "source"  # CLI overrides


def test_package_overrides_workspace(tmp_path):
    (tmp_path / "roschema.toml").write_text('[check.rules]\nRS001 = "warn"\n')
    write_package(tmp_path, "my_pkg", msgs={"Foo": "int32 a\n"})
    (tmp_path / "my_pkg" / "roschema.toml").write_text('[check.rules]\nRS001 = "off"\n')
    cfg = load_config(tmp_path, _pkgs(tmp_path))
    assert cfg.effective_severity("RS001", "my_pkg", "error") == "off"  # package wins
    assert cfg.effective_severity("RS001", "other", "error") == "warn"  # workspace fallback


def test_pyproject_tool_roschema(tmp_path):
    (tmp_path / "pyproject.toml").write_text('[tool.roschema.check.rules]\nRS003 = "warn"\n')
    write_package(tmp_path, "my_pkg", msgs={"Foo": "int32 a\n"})
    cfg = load_config(tmp_path, _pkgs(tmp_path))
    assert cfg.effective_severity("RS003", "my_pkg", "error") == "warn"


def test_invalid_severity_is_config_error(tmp_path):
    (tmp_path / "roschema.toml").write_text('[check.rules]\nRS001 = "fatal"\n')
    with pytest.raises(ConfigError):
        load_config(tmp_path, ())


def test_invalid_level_is_config_error(tmp_path):
    (tmp_path / "roschema.toml").write_text('[check]\nlevel = "galaxy"\n')
    with pytest.raises(ConfigError):
        load_config(tmp_path, ())


def test_allow_without_reason_is_config_error(tmp_path):
    (tmp_path / "roschema.toml").write_text(
        '[check.allow]\n"p/msg/T.a" = { rules = ["RS001"] }\n'
    )
    with pytest.raises(ConfigError):
        load_config(tmp_path, ())


def test_finalize_off_drops():
    cfg = Config(workspace=ScopeConfig(rules={"RS001": "off"}))
    assert finalize_findings([_finding("RS001")], cfg, None) == []


def test_finalize_severity_override():
    out = finalize_findings(
        [_finding("RS001")], Config(workspace=ScopeConfig(rules={"RS001": "warn"})), None
    )
    assert out[0].severity == "warn"


def test_finalize_level_filter():
    f = _finding("RSX", levels=("introspection",))
    assert finalize_findings([f], Config(), "wire") == []  # not in wire bundle
    assert len(finalize_findings([f], Config(), "introspection")) == 1


def test_finalize_inline_suppression():
    out = finalize_findings([_finding("RS005", inline=("RS005",))], Config(), None)
    assert out[0].suppressed is True


def test_finalize_allowlist_suppression():
    cfg = Config(
        workspace=ScopeConfig(
            allow=(AllowEntry("demo/msg/T.a", ("RS001",), "intentional, see #1"),)
        )
    )
    out = finalize_findings([_finding("RS001")], cfg, None)
    assert out[0].suppressed is True


def test_finalize_allowlist_rule_scoped():
    cfg = Config(
        workspace=ScopeConfig(
            allow=(AllowEntry("demo/msg/T.a", ("RS999",), "wrong rule"),)
        )
    )
    out = finalize_findings([_finding("RS001")], cfg, None)
    assert out[0].suppressed is False  # allow entry names a different rule


def test_explicit_config_bypasses_level_preset():
    behaviour = _finding("RS030", severity="warn", levels=("behavior",))
    # default level is source: behaviour findings are filtered out
    assert finalize_findings([behaviour], Config(), None) == []
    # explicitly configuring the rule bypasses the level preset
    cfg = Config(workspace=ScopeConfig(rules={"RS030": "warn"}))
    assert len(finalize_findings([behaviour], cfg, None)) == 1


def test_rs060_opt_in():
    off = _finding("RS060", severity="off", levels=("behavior",))
    assert finalize_findings([off], Config(), None) == []  # off by default
    cfg = Config(workspace=ScopeConfig(rules={"RS060": "error"}))
    out = finalize_findings([off], cfg, None)
    assert len(out) == 1 and out[0].severity == "error"
