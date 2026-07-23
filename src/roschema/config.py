"""Configuration: discovery, parsing, and application to findings.

Precedence is CLI flags > per-package ``roschema.toml`` > workspace config
(``roschema.toml`` or ``[tool.roschema]`` in ``pyproject.toml``) > defaults.
"""

from __future__ import annotations

import sys
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import cast

from .discovery import DiscoveredPackage
from .rules import Finding

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised only on py3.10
    import tomli as tomllib  # type: ignore[import-not-found]

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

    def effective_severity(self, rule_id: str, package: str, default: str) -> str:
        """Severity for a rule in a package: package > workspace > default."""
        pkg_cfg = self.packages.get(package)
        if pkg_cfg is not None and rule_id in pkg_cfg.rules:
            return pkg_cfg.rules[rule_id]
        if rule_id in self.workspace.rules:
            return self.workspace.rules[rule_id]
        return default

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
        bundle = LEVEL_BUNDLES[config.effective_level(pkg, cli_level)]
        if not (set(finding.levels) & bundle):
            continue
        if finding.rule in finding.inline_ignores or config.is_allowed(finding):
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
    workspace_scope, lint_rules = _load_workspace(root, config_path)
    package_configs: dict[str, ScopeConfig] = {}
    for pkg in packages:
        if not pkg.path:
            continue
        pkg_toml = root / pkg.path / "roschema.toml"
        if pkg_toml.is_file():
            package_configs[pkg.name] = _parse_scope(_read_toml(pkg_toml))
    return Config(
        workspace=workspace_scope, packages=package_configs, lint_rules=lint_rules
    )


def _load_workspace(
    root: Path, config_path: Path | None
) -> tuple[ScopeConfig, dict[str, str]]:
    if config_path is not None:
        if not config_path.is_file():
            raise ConfigError(f"config file not found: {config_path}")
        data = _read_toml(config_path)
        if config_path.name == "pyproject.toml":
            data = _as_dict(_as_dict(data.get("tool")).get("roschema"))
        return _parse_loaded(data)

    roschema_toml = root / "roschema.toml"
    if roschema_toml.is_file():
        return _parse_loaded(_read_toml(roschema_toml))

    pyproject = root / "pyproject.toml"
    if pyproject.is_file():
        data = _as_dict(_as_dict(_read_toml(pyproject).get("tool")).get("roschema"))
        if data:
            return _parse_loaded(data)

    return ScopeConfig(), {}


def _read_toml(path: Path) -> dict[str, object]:
    try:
        with path.open("rb") as handle:
            return cast("dict[str, object]", tomllib.load(handle))
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise ConfigError(f"could not read {path}: {exc}") from exc


def _parse_loaded(data: dict[str, object]) -> tuple[ScopeConfig, dict[str, str]]:
    scope = _parse_scope(data)
    lint = _as_dict(data.get("lint"))
    lint_rules = _parse_rules(_as_dict(lint.get("rules")), where="[lint.rules]")
    return scope, lint_rules


def _parse_scope(data: dict[str, object]) -> ScopeConfig:
    check = _as_dict(data.get("check"))
    level = check.get("level")
    if level is not None and level not in LEVEL_BUNDLES:
        raise ConfigError(
            f"invalid level {level!r}; expected one of {sorted(LEVEL_BUNDLES)}"
        )
    deep = check.get("deep")
    return ScopeConfig(
        level=level if isinstance(level, str) else None,
        deep=deep if isinstance(deep, bool) else None,
        rules=_parse_rules(_as_dict(check.get("rules")), where="[check.rules]"),
        allow=_parse_allow(_as_dict(check.get("allow"))),
    )


def _parse_rules(raw: dict[str, object], where: str) -> dict[str, str]:
    rules: dict[str, str] = {}
    for rule_id, severity in raw.items():
        if severity not in _SEVERITIES:
            raise ConfigError(
                f"{where}: {rule_id} has invalid severity {severity!r}; "
                f"expected off, warn or error"
            )
        rules[rule_id] = str(severity)
    return rules


def _parse_allow(raw: dict[str, object]) -> tuple[AllowEntry, ...]:
    entries: list[AllowEntry] = []
    for target, spec in raw.items():
        spec_dict = _as_dict(spec)
        reason = spec_dict.get("reason")
        if not isinstance(reason, str) or not reason.strip():
            raise ConfigError(
                f"allowlist entry {target!r} must include a non-empty 'reason'"
            )
        raw_rules = spec_dict.get("rules", [])
        rules = tuple(str(r) for r in raw_rules) if isinstance(raw_rules, list) else ()
        entries.append(AllowEntry(target=target, rules=rules, reason=reason))
    return tuple(entries)


def _as_dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}
