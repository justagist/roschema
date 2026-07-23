"""Resolve a CLI target to a concrete set of discoverable interfaces."""

from __future__ import annotations

import os
from fnmatch import fnmatch
from pathlib import Path

from ..vfs import RealFS, VfsError
from .discover import discover, discover_named
from .model import DiscoveredPackage, Resolution

_KINDS = ("msg", "srv", "action")


def resolve_target(target: str | None, cwd: str | Path | None = None) -> Resolution:
    """Resolve ``target`` following the precedence in the design brief.

    1. ``None`` -> treat the current working directory as a workspace root.
    2. An existing directory path -> discover packages beneath it.
    3. A bare package name -> resolve via the ament index (``AMENT_PREFIX_PATH``).

    Args:
        target: Path, package name, or ``None``.
        cwd: Override for the working directory (used in tests).

    Returns:
        A :class:`Resolution` bundling the backend, packages and a source label.

    Raises:
        VfsError: If a named target cannot be resolved (exit code 2 at the CLI).
    """
    base = Path(cwd) if cwd is not None else Path.cwd()

    if target is None:
        vfs = RealFS(base)
        return Resolution(vfs=vfs, packages=discover(vfs, "."), source=f"workspace:{base}")

    path = (base / target) if not os.path.isabs(target) else Path(target)
    if path.is_dir():
        vfs = RealFS(path)
        return Resolution(vfs=vfs, packages=discover(vfs, "."), source=f"path:{path}")

    ament = _resolve_ament(target)
    if ament is not None:
        return ament

    raise VfsError(
        f"cannot resolve target {target!r}: not a directory and not found on "
        f"AMENT_PREFIX_PATH"
    )


def _resolve_ament(name: str) -> Resolution | None:
    for prefix in _ament_prefixes():
        share = Path(prefix) / "share" / name
        if not any((share / kind).is_dir() for kind in _KINDS):
            continue
        vfs = RealFS(share)
        packages = discover_named(vfs, name, ".")
        if packages:
            return Resolution(vfs=vfs, packages=packages, source=f"ament:{prefix}")
    return None


def _ament_prefixes() -> list[str]:
    raw = os.environ.get("AMENT_PREFIX_PATH", "")
    return [p for p in raw.split(os.pathsep) if p]


def apply_exclude(
    packages: tuple[DiscoveredPackage, ...], patterns: list[str]
) -> tuple[DiscoveredPackage, ...]:
    """Drop interfaces (and emptied packages) matching any exclude glob.

    A pattern is matched against the package name, the interface key
    (``pkg/kind/name``) and the interface path.
    """
    if not patterns:
        return packages
    kept: list[DiscoveredPackage] = []
    for pkg in packages:
        if any(fnmatch(pkg.name, pat) for pat in patterns):
            continue
        ifaces = tuple(
            ref
            for ref in pkg.interfaces
            if not any(fnmatch(ref.key, pat) or fnmatch(ref.path, pat) for pat in patterns)
        )
        if ifaces:
            kept.append(DiscoveredPackage(name=pkg.name, path=pkg.path, interfaces=ifaces))
    return tuple(kept)
