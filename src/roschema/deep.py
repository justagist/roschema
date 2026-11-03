"""Deep (transitive) breakage detection for `check --deep` (RS110).

Shallow checking compares nested complex types by name only. Deep checking
resolves the type-dependency graph through the workspace and ament index, then
flags any interface that embeds -- directly or transitively -- a type whose wire
layout changed, even when the embedding interface's own text is unchanged.
"""

from __future__ import annotations

from collections import deque

from .discovery import resolve_ament
from .ir import InterfaceFile
from .loader import load_interfaces
from .rules import Finding
from .rules.breaking.rs110_transitive import RULE as RS110


def transitive_findings(
    new_ifaces: dict[str, InterfaceFile], direct: list[Finding]
) -> list[Finding]:
    """Return RS110 findings for interfaces broken via a changed embedded type.

    Each RS110 finding takes the severity of the root it traces back to, so a
    warning-level change never fails the interfaces that embed it.

    Args:
        new_ifaces: Current interfaces (the target set).
        direct: Finalised findings from the ordinary diff; interfaces with a
            reported (unsuppressed) wire-level finding are the roots of
            transitive breakage.
    """
    roots = [f for f in direct if "wire" in f.levels and not f.suppressed]
    if not roots:
        return []
    # Search error roots first so an interface reaching both reports the error.
    tiers = [
        (severity, {f.interface for f in roots if f.severity == severity})
        for severity in ("error", "warn")
    ]

    graph = dict(new_ifaces)
    _augment_dependencies(graph)
    edges = {key: _referenced_keys(iface) for key, iface in graph.items()}

    findings: list[Finding] = []
    for key in sorted(new_ifaces):
        traced = [
            (severity, chain)
            for severity, changed in tiers
            if (chain := _first_changed_dependency(key, edges, changed)) is not None
        ]
        if not traced:
            continue
        severity, chain = traced[0]
        iface = new_ifaces[key]
        findings.append(
            Finding(
                rule=RS110.id,
                severity=severity,
                level=RS110.primary_level,
                interface=key,
                section=None,
                target="",
                message=f"transitively broken via {' -> '.join(chain)}",
                old_file=None,
                old_line=None,
                new_file=iface.source_file,
                new_line=None,
                levels=RS110.levels,
            )
        )
    return findings


def _referenced_keys(iface: InterfaceFile) -> set[str]:
    """Interface keys of every complex field type referenced by ``iface``."""
    keys: set[str] = set()
    for field in iface.fields():
        if field.type.is_builtin:
            continue
        pkg = field.type.package or iface.package
        keys.add(f"{pkg}/msg/{field.type.base}")
    return keys


def _augment_dependencies(ifaces: dict[str, InterfaceFile]) -> None:
    """Resolve referenced-but-absent types from the ament index, transitively."""
    while True:
        needed = {
            key
            for iface in list(ifaces.values())
            for key in _referenced_keys(iface)
            if key not in ifaces
        }
        if not needed:
            return
        added = False
        for package in sorted({key.split("/", 1)[0] for key in needed}):
            res = resolve_ament(package)
            if res is None:
                continue
            for key, iface in load_interfaces(res.vfs, res.packages).items():
                if key not in ifaces:
                    ifaces[key] = iface
                    added = True
        if not added:
            return  # remaining deps are unresolvable; stop


def _first_changed_dependency(
    start: str, edges: dict[str, set[str]], changed: set[str]
) -> list[str] | None:
    """Shortest dependency chain from ``start`` to a changed type, or ``None``."""
    visited = {start}
    queue: deque[list[str]] = deque([start, dep] for dep in edges.get(start, set()))
    while queue:
        path = queue.popleft()
        node = path[-1]
        if node in changed:
            return path
        if node in visited:
            continue
        visited.add(node)
        for dep in edges.get(node, set()):
            queue.append([*path, dep])
    return None
