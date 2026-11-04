"""Tests for configuration loading, precedence and finalization."""

from __future__ import annotations

import pytest

from _helpers import make_git_repo, write_package
from roschema.config import (
    AllowEntry,
    Config,
    ConfigError,
    ScopeConfig,
    finalize_findings,
    finalize_lint,
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
    (tmp_path / "roschema.toml").write_text('[check.allow]\n"p/msg/T.a" = { rules = ["RS001"] }\n')
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
    constant = _finding("RSY", levels=("source",))
    assert finalize_findings([constant], Config(), "introspection") == []  # bags ignore constants
    assert len(finalize_findings([constant], Config(), "source")) == 1


def test_finalize_inline_suppression():
    out = finalize_findings([_finding("RS005", inline=("RS005",))], Config(), None)
    assert out[0].suppressed is True
    assert out[0].suppressed_reason == "an inline ignore"


def test_package_allowlist_reason_takes_precedence():
    entry = ("demo/msg/T.a", ("RS001",))
    cfg = Config(
        workspace=ScopeConfig(allow=(AllowEntry(*entry, "workspace reason"),)),
        packages={"demo": ScopeConfig(allow=(AllowEntry(*entry, "package reason"),))},
    )
    assert cfg.allow_reason(_finding("RS001")) == "package reason"


@pytest.mark.parametrize(
    ("target", "allowed"),
    [
        ("demo/msg/T*", True),
        ("demo/*", True),
        ("demo/msg/T.?", True),
        ("demo/msg/U*", False),
        ("demo/msg/T", False),  # an exact target names only the interface itself
    ],
)
def test_allowlist_glob_targets(target, allowed):
    cfg = Config(workspace=ScopeConfig(allow=(AllowEntry(target, (), "planned 2.0 break"),)))
    assert (cfg.allow_reason(_finding("RS001")) is not None) is allowed


def test_finalize_allowlist_suppression():
    cfg = Config(
        workspace=ScopeConfig(
            allow=(AllowEntry("demo/msg/T.a", ("RS001",), "intentional, see #1"),)
        )
    )
    out = finalize_findings([_finding("RS001")], cfg, None)
    assert out[0].suppressed is True
    assert out[0].suppressed_reason == "the allowlist: intentional, see #1"


def test_finalize_records_dropped_findings():
    cfg = Config(workspace=ScopeConfig(rules={"RS001": "off"}))
    behaviour = _finding("RS030", severity="warn", levels=("behavior",))
    dropped: list = []
    assert finalize_findings([_finding("RS001"), behaviour], cfg, "source", dropped=dropped) == []
    assert [(f.rule, reason) for f, reason in dropped] == [
        ("RS001", "rule off; enable it in [check.rules]"),
        ("RS030", "behavior-level rule; checking at source"),
    ]


def test_finalize_allowlist_rule_scoped():
    cfg = Config(
        workspace=ScopeConfig(allow=(AllowEntry("demo/msg/T.a", ("RS999",), "wrong rule"),))
    )
    out = finalize_findings([_finding("RS001")], cfg, None)
    assert out[0].suppressed is False  # allow entry names a different rule


def test_configured_severity_keeps_level_preset():
    """Restating or raising a rule's severity must not widen the selected level."""
    behaviour = _finding("RS030", severity="warn", levels=("behavior",))
    for severity in ("warn", "error"):
        cfg = Config(workspace=ScopeConfig(rules={"RS030": severity}))
        assert finalize_findings([behaviour], cfg, None) == []
        assert len(finalize_findings([behaviour], cfg, "behavior")) == 1


def test_rs060_opt_in():
    off = _finding("RS060", severity="off", levels=("behavior",))
    assert finalize_findings([off], Config(), None) == []  # off by default
    cfg = Config(workspace=ScopeConfig(rules={"RS060": "error"}))
    out = finalize_findings([off], cfg, None)
    assert len(out) == 1 and out[0].severity == "error"


@pytest.mark.parametrize("package_format", ["roschema.toml", "pyproject.toml"])
def test_package_target_inherits_workspace_and_keeps_overrides(tmp_path, package_format):
    (tmp_path / "roschema.toml").write_text(
        '[check.rules]\nRS001 = "warn"\nRS003 = "off"\n'
        '[lint.rules]\nRSL001 = "warn"\nRSL004 = "error"\n'
    )
    pkg = write_package(tmp_path / "src", "demo", msgs={"T": "int32 x\n"})
    prefix = "tool.roschema." if package_format == "pyproject.toml" else ""
    (pkg / package_format).write_text(
        f'[{prefix}check.rules]\nRS003 = "warn"\n[{prefix}lint.rules]\nRSL001 = "off"\n'
    )
    for root in (tmp_path, pkg):
        cfg = load_config(root, _pkgs(root))
        assert cfg.effective_severity("RS001", "demo", "error") == "warn"
        assert cfg.effective_severity("RS003", "demo", "error") == "warn"
        lint = finalize_lint([_finding("RSL001"), _finding("RSL004")], cfg)
        assert [(f.rule, f.severity) for f in lint] == [("RSL004", "error")]


def test_config_search_stops_at_git_root(tmp_path):
    (tmp_path / "roschema.toml").write_text('[check.rules]\nRS003 = "off"\n')
    repo = make_git_repo(tmp_path / "repo")
    pkg = write_package(repo / "src", "demo", msgs={"T": "int32 x\n"})
    cfg = load_config(pkg, _pkgs(pkg))
    assert cfg.effective_severity("RS003", "demo", "error") == "error"


def test_explicit_workspace_config_still_allows_package_overrides(tmp_path):
    pkg = write_package(tmp_path, "demo", msgs={"T": "int32 x\n"})
    explicit = tmp_path / "ci.toml"
    explicit.write_text('[check.rules]\nRS001 = "warn"\nRS003 = "off"\n')
    (pkg / "roschema.toml").write_text('[check.rules]\nRS003 = "warn"\n')
    cfg = load_config(pkg, _pkgs(pkg), explicit)
    assert cfg.effective_severity("RS001", "demo", "error") == "warn"
    assert cfg.effective_severity("RS003", "demo", "error") == "warn"


@pytest.mark.parametrize(
    "package_config,section,rule",
    [
        (False, "check.rules", "RS999"),
        (True, "lint.rules", "RSL999"),
        (False, "check.rules", "RSL001"),
        (False, "lint.rules", "RS001"),
    ],
)
def test_unknown_rule_ids_are_configuration_errors(tmp_path, section, rule, package_config):
    pkg = write_package(tmp_path, "demo", msgs={"T": "int32 x\n"})
    config_dir = pkg if package_config else tmp_path
    (config_dir / "roschema.toml").write_text(f'[{section}]\n{rule} = "warn"\n')
    with pytest.raises(ConfigError, match="unknown.*rule"):
        load_config(tmp_path, _pkgs(tmp_path))


def test_unknown_allowlist_rule_is_configuration_error(tmp_path):
    (tmp_path / "roschema.toml").write_text(
        '[check.allow]\n"demo/msg/T.x" = {rules = ["RS999"], reason = "intentional"}\n'
    )
    with pytest.raises(ConfigError, match="unknown.*rule"):
        load_config(tmp_path, ())


def test_deep_setting_must_be_boolean(tmp_path):
    (tmp_path / "roschema.toml").write_text('[check]\ndeep = "true"\n')
    with pytest.raises(ConfigError, match="deep.*boolean"):
        load_config(tmp_path, ())


@pytest.mark.parametrize("package_format", ["roschema.toml", "pyproject.toml"])
def test_root_package_config_without_discovered_interfaces(tmp_path, package_format):
    """Keep root package overrides and inherited settings without interface discovery."""
    (tmp_path / "roschema.toml").write_text('[check.rules]\nRS003 = "warn"\n')
    pkg = write_package(tmp_path, "demo")
    prefix = "tool.roschema." if package_format == "pyproject.toml" else ""
    (pkg / package_format).write_text(
        f'[{prefix}check.rules]\nRS001 = "off"\n'
        f'[{prefix}check.allow]\n"demo/msg/T.a" = {{reason = "intentional"}}\n'
    )
    cfg = load_config(pkg, ())
    assert cfg.effective_severity("RS001", "demo", "error") == "off"
    assert cfg.effective_severity("RS003", "demo", "error") == "warn"
    assert cfg.effective_severity("RS001", "other", "error") == "error"
    assert cfg.allow_reason(_finding("RS001")) == "intentional"


@pytest.mark.parametrize("package_format", ["roschema.toml", "pyproject.toml"])
@pytest.mark.parametrize(
    "setting",
    [
        'check = "invalid"',
        'lint = "invalid"',
        'check.rules = "invalid"',
        'check.allow = "invalid"',
        'lint.rules = "invalid"',
        "check.level = []",
        "check.rules.RS001 = []",
    ],
)
def test_invalid_package_config_shape_is_error(tmp_path, package_format, setting):
    """Malformed package sections must produce configuration errors."""
    pkg = write_package(tmp_path, "demo", msgs={"T": "int32 x\n"})
    prefix = "[tool.roschema]\n" if package_format == "pyproject.toml" else ""
    (pkg / package_format).write_text(prefix + setting + "\n")
    with pytest.raises(ConfigError):
        load_config(tmp_path, _pkgs(tmp_path))


def test_scalar_pyproject_roschema_section_is_error(tmp_path):
    """Reject a scalar tool section before attempting to parse its settings."""
    (tmp_path / "pyproject.toml").write_text('[tool]\nroschema = "invalid"\n')
    with pytest.raises(ConfigError):
        load_config(tmp_path, ())


@pytest.mark.parametrize(
    "toml,message",
    [
        ('[chek]\nlevel = "wire"\n', "configuration: unknown key 'chek'; did you mean 'check'?"),
        ('[check]\nlevle = "wire"\n', "[check]: unknown key 'levle'; did you mean 'level'?"),
        ('[check.rule]\nRS002 = "off"\n', "[check]: unknown key 'rule'; did you mean 'rules'?"),
        ('[lint.rule]\nRSL001 = "off"\n', "[lint]: unknown key 'rule'; did you mean 'rules'?"),
        (
            '[check.allow]\n"p/msg/T.a" = {reason = "x", rule = ["RS001"]}\n',
            "allowlist entry 'p/msg/T.a': unknown key 'rule'; did you mean 'rules'?",
        ),
    ],
)
def test_unknown_keys_are_configuration_errors(tmp_path, toml, message):
    """Misspelt settings must fail rather than silently fall back to defaults."""
    (tmp_path / "roschema.toml").write_text(toml)
    with pytest.raises(ConfigError) as exc:
        load_config(tmp_path, ())
    assert str(exc.value) == message
