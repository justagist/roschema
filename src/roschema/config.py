"""Configuration: discovery, parsing, and application to findings.

Precedence is CLI flags > per-package ``roschema.toml`` > workspace config
(``roschema.toml`` or ``[tool.roschema]`` in ``pyproject.toml``) > defaults.
"""

from __future__ import annotations

import difflib
import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import cast

from .discovery import DiscoveredPackage, discover
from .rules import Finding, all_lint_rules, all_rules
from .vfs import RealFS, git_toplevel

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised only on py3.10
    import tomli as tomllib

# Cumulative level bundles: selecting a level reports it and everything more
# wire-significant than it.
LEVEL_BUNDLES: dict[str, frozenset[str]] = {
    "wire": frozenset({"wire"}),
    "source": frozenset({"wire", "source"}),
    "introspection": frozenset({"wire", "source", "introspection"}),
    "behavior": frozenset({"wire", "source", "introspection", "behavior"}),
}
DEFAULT_LEVEL = "source"
_SEVERITIES = frozenset({"off", "warn", "error"})


class ConfigError(Exception):
    """Raised on an invalid configuration (exit code 2)."""


@dataclass(frozen=True)
class AllowEntry:
    """An intentional-break allowance for a fully-qualified target."""

    target: str
    rules: tuple[str, ...]
    reason: str


@dataclass(frozen=True)
class ScopeConfig:
    """A ``[check]`` scope, at workspace or package level."""

    level: str | None = None
    deep: bool | None = None
    rules: dict[str, str] = field(default_factory=dict)
    allow: tuple[AllowEntry, ...] = ()


@dataclass(frozen=True)
class Config:
    """Merged configuration for a check run."""

    workspace: ScopeConfig = field(default_factory=ScopeConfig)
    packages: dict[str, ScopeConfig] = field(default_factory=dict)
    lint_rules: dict[str, str] = field(default_factory=dict)
    package_lint_rules: dict[str, dict[str, str]] = field(default_factory=dict)

    def effective_severity(self, rule_id: str, package: str, default: str) -> str:
        """Severity for a rule in a package: package > workspace > default."""
        pkg_cfg = self.packages.get(package)
        if pkg_cfg is not None and rule_id in pkg_cfg.rules:
            return pkg_cfg.rules[rule_id]
        if rule_id in self.workspace.rules:
            return self.workspace.rules[rule_id]
        return default

    def is_explicitly_set(self, rule_id: str, package: str) -> bool:
        """Whether a rule's severity was set in config (bypasses level presets)."""
        pkg_cfg = self.packages.get(package)
        if pkg_cfg is not None and rule_id in pkg_cfg.rules:
            return True
        return rule_id in self.workspace.rules

    def effective_level(self, package: str, cli_level: str | None) -> str:
        """Reporting level: CLI > package > workspace > default."""
        if cli_level:
            return cli_level
        pkg_cfg = self.packages.get(package)
        if pkg_cfg is not None and pkg_cfg.level:
            return pkg_cfg.level
        if self.workspace.level:
            return self.workspace.level
        return DEFAULT_LEVEL

    def effective_deep(self, package: str, cli_deep: bool | None) -> bool:
        """Deep checking: CLI > package > workspace > off."""
        if cli_deep is not None:
            return cli_deep
        pkg_cfg = self.packages.get(package)
        if pkg_cfg is not None and pkg_cfg.deep is not None:
            return pkg_cfg.deep
        return self.workspace.deep or False

    def is_allowed(self, finding: Finding) -> bool:
        """Whether an allowlist entry covers this finding."""
        entries = list(self.workspace.allow)
        pkg_cfg = self.packages.get(finding.package)
        if pkg_cfg is not None:
            entries += list(pkg_cfg.allow)
        for entry in entries:
            if entry.target != finding.qualified_target:
                continue
            if not entry.rules or finding.rule in entry.rules:
                return True
        return False


def finalize_findings(
    findings: list[Finding], config: Config, cli_level: str | None
) -> list[Finding]:
    """Apply config to raw findings.

    Drops rules turned ``off`` and findings outside the selected level, adjusts
    severities, and flags inline-suppressed / allowlisted findings (kept in the
    list with ``suppressed=True`` so they can still be counted and emitted).
    """
    out: list[Finding] = []
    for finding in findings:
        pkg = finding.package
        severity = config.effective_severity(finding.rule, pkg, finding.severity)
        if severity == "off":
            continue
        finding = replace(finding, severity=severity)
        # A rule whose severity is set explicitly in config bypasses the level
        # preset (an opt-in rule like RS060 is reported once enabled).
        if not config.is_explicitly_set(finding.rule, pkg):
            bundle = LEVEL_BUNDLES[config.effective_level(pkg, cli_level)]
            if not (set(finding.levels) & bundle):
                continue
        if finding.rule in finding.inline_ignores or config.is_allowed(finding):
            finding = replace(finding, suppressed=True)
        out.append(finding)
    return out


def finalize_lint(
    findings: list[Finding], config: Config, cli_rules: dict[str, str] | None = None
) -> list[Finding]:
    """Apply ``[lint.rules]`` severities and inline suppression to lint findings.

    Lint has no baseline, so there is no level filter or allowlist; only severity
    overrides (including ``off``) and inline ``# roschema: ignore=`` apply.
    """
    out: list[Finding] = []
    for finding in findings:
        severity = config.package_lint_rules.get(finding.package, {}).get(
            finding.rule, config.lint_rules.get(finding.rule, finding.severity)
        )
        if cli_rules is not None:
            severity = cli_rules.get(finding.rule, severity)
        if severity == "off":
            continue
        finding = replace(finding, severity=severity)
        if finding.rule in finding.inline_ignores:
            finding = replace(finding, suppressed=True)
        out.append(finding)
    return out


def load_config(
    root: Path,
    packages: tuple[DiscoveredPackage, ...],
    config_path: Path | None = None,
) -> Config:
    """Discover and parse workspace and per-package configuration.

    Args:
        root: Workspace/target root directory.
        packages: Discovered packages (to locate per-package configs).
        config_path: Explicit workspace config file overriding discovery.

    Raises:
        ConfigError: On malformed config or an allow entry missing a reason.
    """
    root = root.resolve()
    workspace_scope, lint_rules = _load_workspace(root, config_path)
    if (root / "package.xml").is_file() and not any(not pkg.path for pkg in packages):
        packages += tuple(pkg for pkg in discover(RealFS(root), include_empty=True) if not pkg.path)
    package_configs: dict[str, ScopeConfig] = {}
    package_lint_rules: dict[str, dict[str, str]] = {}
    for pkg in packages:
        loaded = _load_directory_config(root / pkg.path)
        if loaded is not None:
            package_configs[pkg.name], package_lint_rules[pkg.name] = loaded
    return Config(
        workspace=workspace_scope,
        packages=package_configs,
        lint_rules=lint_rules,
        package_lint_rules=package_lint_rules,
    )


def _load_workspace(
    root: Path, config_path: Path | None
) -> tuple[ScopeConfig, dict[str, str]]:
    """Find inherited workspace settings without treating a package as its workspace."""
    if config_path is not None:
        if not config_path.is_file():
            raise ConfigError(f"config file not found: {config_path}")
        data = _read_toml(config_path)
        if config_path.name == "pyproject.toml":
            data = _as_dict(_as_dict(data.get("tool"), "[tool]").get("roschema"), "[tool.roschema]")
        return _parse_loaded(data)

    boundary = git_toplevel(root)
    package_root = (root / "package.xml").is_file()
    for directory in (root, *root.parents):
        if directory != root or not package_root:
            loaded = _load_directory_config(directory)
            if loaded is not None:
                return loaded
        if directory == boundary:
            break
    return ScopeConfig(), {}


def _load_directory_config(directory: Path) -> tuple[ScopeConfig, dict[str, str]] | None:
    """Read a directory's roschema config, preferring roschema.toml."""
    roschema_toml = directory / "roschema.toml"
    if roschema_toml.is_file():
        return _parse_loaded(_read_toml(roschema_toml))
    pyproject = directory / "pyproject.toml"
    if pyproject.is_file():
        tool = _as_dict(_read_toml(pyproject).get("tool"), "[tool]")
        data = _as_dict(tool.get("roschema"), "[tool.roschema]")
        if data:
            return _parse_loaded(data)
    return None


def _read_toml(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as handle:
            return cast("dict[str, object]", tomllib.load(handle))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"could not read {path}: {exc}") from exc


def _parse_loaded(data: dict[str, object]) -> tuple[ScopeConfig, dict[str, str]]:
    """Parse check and lint settings from a configuration table."""
    _reject_unknown(data, ("check", "lint"), "configuration")
    scope = _parse_scope(data)
    lint = _as_dict(data.get("lint"), "[lint]")
    _reject_unknown(lint, ("rules",), "[lint]")
    lint_rules = _parse_rules(_as_dict(lint.get("rules"), "[lint.rules]"), where="[lint.rules]")
    return scope, lint_rules


def _parse_scope(data: dict[str, object]) -> ScopeConfig:
    """Validate a check scope and parse its overrides and allowlist."""
    check = _as_dict(data.get("check"), "[check]")
    _reject_unknown(check, ("level", "deep", "rules", "allow"), "[check]")
    level = check.get("level")
    if level is not None and (not isinstance(level, str) or level not in LEVEL_BUNDLES):
        raise ConfigError(
            f"invalid level {level!r}; expected one of {sorted(LEVEL_BUNDLES)}"
        )
    deep = check.get("deep")
    if deep is not None and not isinstance(deep, bool):
        raise ConfigError("[check]: deep must be a boolean")
    return ScopeConfig(
        level=level if isinstance(level, str) else None,
        deep=deep if isinstance(deep, bool) else None,
        rules=_parse_rules(_as_dict(check.get("rules"), "[check.rules]"), where="[check.rules]"),
        allow=_parse_allow(_as_dict(check.get("allow"), "[check.allow]")),
    )


def _parse_rules(raw: dict[str, object], where: str) -> dict[str, str]:
    """Validate rule identifiers and severities for the given section."""
    rules: dict[str, str] = {}
    active = all_lint_rules() if where == "[lint.rules]" else all_rules()
    valid = {rule.id for rule in active}
    for rule_id, severity in raw.items():
        if rule_id not in valid:
            raise ConfigError(f"{where}: unknown rule {rule_id!r}")
        if not isinstance(severity, str) or severity not in _SEVERITIES:
            raise ConfigError(
                f"{where}: {rule_id} has invalid severity {severity!r}; "
                f"expected off, warn or error"
            )
        rules[rule_id] = str(severity)
    return rules


def _parse_allow(raw: dict[str, object]) -> tuple[AllowEntry, ...]:
    """Parse reasoned allowlist entries with validated rule identifiers."""
    entries: list[AllowEntry] = []
    for target, spec in raw.items():
        spec_dict = _as_dict(spec, f"allowlist entry {target!r}")
        _reject_unknown(spec_dict, ("rules", "reason"), f"allowlist entry {target!r}")
        reason = spec_dict.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ConfigError(
                f"allowlist entry {target!r} must include a non-empty 'reason'"
            )
        raw_rules = spec_dict.get("rules", [])
        if not isinstance(raw_rules, list):
            raise ConfigError(f"allowlist entry {target!r}: rules must be a list")
        rules = tuple(str(r) for r in raw_rules)
        unknown = set(rules) - {rule.id for rule in all_rules()}
        if unknown:
            raise ConfigError(f"allowlist entry {target!r}: unknown rule IDs {sorted(unknown)}")
        entries.append(AllowEntry(target=target, rules=rules, reason=reason))
    return tuple(entries)


def _reject_unknown(table: dict[str, object], known: tuple[str, ...], where: str) -> None:
    """Reject misspelt or unsupported keys so their settings never silently do nothing."""
    for key in table:
        if key not in known:
            close = difflib.get_close_matches(key, known, n=1)
            hint = f"; did you mean {close[0]!r}?" if close else f"; expected one of {list(known)}"
            raise ConfigError(f"{where}: unknown key {key!r}{hint}")


def _as_dict(value: object, where: str) -> dict[str, object]:
    """Accept an optional table without silently discarding malformed settings."""
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise ConfigError(f"{where} must be a table")
    return value
