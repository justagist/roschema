"""Find suppressions that no longer suppress anything (RS200)."""

from __future__ import annotations

from collections.abc import Collection
from fnmatch import fnmatchcase

from .config import AllowEntry, Config
from .ir import InterfaceFile
from .rules import Finding, all_rules, parse_inline_ignores

_RULE = "RS200"


def unused_suppressions(
    raw: list[Finding],
    config: Config,
    interfaces: dict[str, InterfaceFile],
    checked: Collection[str],
    excluded: Collection[str],
) -> list[Finding]:
    """RS200 findings for allowlist entries and inline ignores that match no finding.

    Args:
        raw: Every finding of the check before configuration is applied, so a
            suppression still counts as used when its rule is outside the
            checked level or turned off.
        config: The check's configuration, holding the allowlists.
        interfaces: Current interfaces, whose inline ignores are checked.
        checked: Keys of the interfaces compared, on either side.
        excluded: Keys of the interfaces dropped by ``--exclude``; entries
            covering only those are out of scope.
    """
    packages = {key.split("/", 1)[0] for key in checked}
    out = [
        _unused_entry(owner, entry)
        for owner, entry in _allow_entries(config)
        if _in_scope(owner, entry, packages, checked, excluded)
        and not _entry_used(owner, entry, raw)
    ]
    check_rules = {rule.id for rule in all_rules()} - {_RULE}
    # Match where the suppression applies: a finding carries the ignores of
    # its new-side member, which need not share the member's section (RS060).
    used = {(f.rule, f.new_file, f.new_line) for f in raw if f.rule in f.inline_ignores}
    for key in sorted(interfaces):
        for section in interfaces[key].sections:
            for member in section.members:
                for rule in parse_inline_ignores(member.trailing_comment):
                    if rule in check_rules and (
                        (rule, member.source_file, member.line) not in used
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


def _allow_entries(config: Config) -> list[tuple[str | None, AllowEntry]]:
    """Allowlist entries with the package whose configuration holds them (None: workspace)."""
    entries: list[tuple[str | None, AllowEntry]] = [(None, e) for e in config.workspace.allow]
    for package, scope in config.packages.items():
        entries += [(package, e) for e in scope.allow]
    return entries


def _in_scope(
    owner: str | None,
    entry: AllowEntry,
    packages: Collection[str],
    checked: Collection[str],
    excluded: Collection[str],
) -> bool:
    if owner is not None:
        if owner not in packages:
            return False
    elif not any(fnmatchcase(name, entry.target.split("/", 1)[0]) for name in packages):
        return False
    # A target for interfaces that are only excluded is out of scope, but one
    # that matches no interface at all (a typo) is not.
    interface = entry.target.split(".", 1)[0]
    return not any(fnmatchcase(key, interface) for key in excluded) or any(
        fnmatchcase(key, interface) for key in checked
    )


def _entry_used(owner: str | None, entry: AllowEntry, raw: list[Finding]) -> bool:
    # A package's entries only apply to that package's findings.
    return any(
        (owner is None or f.package == owner)
        and fnmatchcase(f.qualified_target, entry.target)
        and (not entry.rules or f.rule in entry.rules)
        for f in raw
    )


def _unused_entry(owner: str | None, entry: AllowEntry) -> Finding:
    interface, _, member = entry.target.partition(".")
    rules = f" for {', '.join(entry.rules)}" if entry.rules else ""
    message = f"allowlist entry matches no finding{rules}"
    if owner is not None and interface.split("/", 1)[0] != owner:
        # Report under the owning package, so its RS200 severity applies.
        message = (
            f"allowlist entry {entry.target!r} in {owner}'s configuration matches no finding{rules}"
        )
        _, sep, rest = interface.partition("/")
        interface = owner + sep + rest
    return _finding(interface, None, member, message)


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
