"""Find suppressions that no longer suppress anything (RS200)."""

from __future__ import annotations

from collections.abc import Collection
from fnmatch import fnmatch, fnmatchcase

from .config import AllowEntry, Config
from .ir import InterfaceFile
from .rules import Finding, all_rules, parse_inline_ignores

_RULE = "RS200"


def unused_suppressions(
    raw: list[Finding],
    config: Config,
    interfaces: dict[str, InterfaceFile],
    packages: Collection[str],
    excludes: Collection[str],
) -> list[Finding]:
    """RS200 findings for allowlist entries and inline ignores that match no finding.

    Args:
        raw: Every finding of the check before configuration is applied, so a
            suppression still counts as used when its rule is outside the
            checked level or turned off.
        config: The check's configuration, holding the allowlists.
        interfaces: Current interfaces, whose inline ignores are checked.
        packages: Names of the packages compared; allowlist entries for other
            packages are out of scope.
        excludes: The ``--exclude`` globs; entries for excluded interfaces are
            out of scope.
    """
    out = [
        _unused_entry(entry)
        for entry in _allow_entries(config)
        if _in_scope(entry, packages, excludes) and not _entry_used(entry, raw)
    ]
    check_rules = {rule.id for rule in all_rules()} - {_RULE}
    used = {(f.rule, f.interface, f.section, f.target) for f in raw}
    for key in sorted(interfaces):
        for section in interfaces[key].sections:
            for member in section.members:
                for rule in parse_inline_ignores(member.trailing_comment):
                    if rule in check_rules and (
                        (rule, key, section.kind.value, member.name) not in used
                    ):
                        out.append(
                            _finding(
                                key,
                                section.kind.value,
                                member.name,
                                f"inline ignore of {rule} matches no finding",
                                member.source_file,
                                member.line,
                            )
                        )
    return out


def _allow_entries(config: Config) -> list[AllowEntry]:
    entries = list(config.workspace.allow)
    for scope in config.packages.values():
        entries += scope.allow
    return entries


def _in_scope(entry: AllowEntry, packages: Collection[str], excludes: Collection[str]) -> bool:
    package = entry.target.split("/", 1)[0]
    interface = entry.target.split(".", 1)[0]
    if any(fnmatch(interface, pattern) or fnmatch(package, pattern) for pattern in excludes):
        return False
    return any(fnmatchcase(name, package) for name in packages)


def _entry_used(entry: AllowEntry, raw: list[Finding]) -> bool:
    return any(
        fnmatchcase(f.qualified_target, entry.target) and (not entry.rules or f.rule in entry.rules)
        for f in raw
    )


def _unused_entry(entry: AllowEntry) -> Finding:
    interface, _, member = entry.target.partition(".")
    rules = f" for {', '.join(entry.rules)}" if entry.rules else ""
    return _finding(interface, None, member, f"allowlist entry matches no finding{rules}")


def _finding(
    interface: str,
    section: str | None,
    target: str,
    message: str,
    file: str | None = None,
    line: int | None = None,
) -> Finding:
    return Finding(
        rule=_RULE,
        severity="warn",
        level="suppression",
        interface=interface,
        section=section,
        target=target,
        message=message,
        old_file=None,
        old_line=None,
        new_file=file,
        new_line=line,
    )
