"""Resolve a CLI target to a concrete set of discoverable interfaces."""

from __future__ import annotations

import os
from fnmatch import fnmatch
from pathlib import Path

from ..vfs import VFS, GitTreeFS, RealFS, VfsError, git_toplevel, rev_parse_verify
from .discover import discover, discover_named
from .model import DiscoveredPackage, Resolution

_KINDS = ("msg", "srv", "action")


def resolve_target(
    target: str | None,
    cwd: str | Path | None = None,
    *,
    allow_empty_glob: bool = False,
    include_empty: bool = False,
) -> Resolution:
    """Resolve ``target`` following the precedence in the design brief.

    1. ``None`` -> treat the current working directory as a workspace root.
    2. An existing directory path -> discover packages beneath it.
    3. A bare package name -> its source package under the working directory,
       else the installed copy from the ament index (``AMENT_PREFIX_PATH``).

    Args:
        target: Path, package name, or ``None``.
        cwd: Override for the working directory (used in tests).
        allow_empty_glob: Defer an empty match error until the baseline is scoped.
        include_empty: Include interface-less packages when replacing source overlays.

    Returns:
        A :class:`Resolution` bundling the backend, packages and a source label.

    Raises:
        VfsError: If a named target cannot be resolved or is ambiguous (exit
            code 2 at the CLI).
    """
    base = Path(cwd) if cwd is not None else Path.cwd()

    if target is None:
        vfs = RealFS(base)
        return Resolution(
            vfs=vfs,
            packages=discover(vfs, ".", include_empty=include_empty),
            source=f"workspace:{base}",
        )

    if not os.path.isabs(target) and any(ch in target for ch in "*?["):
        return _resolve_glob(
            base, target, allow_empty=allow_empty_glob, include_empty=include_empty
        )

    path = (base / target) if not os.path.isabs(target) else Path(target)
    if path.is_dir():
        vfs = RealFS(path)
        return Resolution(
            vfs=vfs,
            packages=discover(vfs, ".", include_empty=include_empty),
            source=f"path:{path}",
        )

    source = _resolve_source_package(base, target, include_empty=include_empty)
    if source is not None:
        return source

    ament = resolve_ament(target)
    if ament is not None:
        return ament

    raise VfsError(
        f"cannot resolve target {target!r}: not a directory and not found on AMENT_PREFIX_PATH"
    )


def _resolve_source_package(
    base: Path, name: str, *, include_empty: bool = False
) -> Resolution | None:
    """Resolve a package by ``<name>`` among the sources under ``base``, or ``None``."""
    matches = [p for p in discover(RealFS(base), ".", include_empty=True) if p.name == name]
    if not matches:
        return None
    if len(matches) > 1:
        paths = ", ".join(p.path for p in matches)
        raise VfsError(f"package {name!r} is defined in several places: {paths}")
    path = base / matches[0].path
    vfs = RealFS(path)
    return Resolution(
        vfs=vfs,
        packages=discover(vfs, ".", include_empty=include_empty),
        source=f"path:{path}",
    )


def _resolve_glob(
    base: Path, pattern: str, *, allow_empty: bool = False, include_empty: bool = False
) -> Resolution:
    """Expand a glob target (dirs) and union the packages discovered under each.

    The VFS is rooted at ``base`` and package paths carry their sub-paths, so a
    baseline still resolves each package at its own repo sub-path. The matched
    pattern is retained so baseline-only packages can also enter the scope.
    """
    vfs = RealFS(base)
    seen: dict[str, DiscoveredPackage] = {}
    for match in sorted(base.glob(pattern)):
        if not match.is_dir():
            continue
        rel = match.relative_to(base).as_posix()
        for pkg in discover(vfs, rel or ".", include_empty=include_empty):
            seen[pkg.path] = pkg
    if not seen and not allow_empty:
        raise VfsError(f"target glob {pattern!r} matched no interface packages")
    packages = tuple(sorted(seen.values(), key=lambda p: p.name))
    return Resolution(
        vfs=vfs,
        packages=packages,
        source=f"glob:{pattern}",
        glob_pattern=Path(pattern).as_posix(),
    )


def resolve_baseline(against: str, target_dir: str | Path) -> Resolution:
    """Resolve the ``--against`` baseline for a check.

    Auto-detected in order: an ``.mcap`` bag, a ``roschema.lock`` file, a git
    ref (validated against the repo containing ``target_dir``), then a directory
    path. MCAP and lockfile baselines arrive in later phases.

    Args:
        against: The ``--against`` argument value.
        target_dir: Directory of the interfaces being checked; used to find the
            git repo and the sub-path to compare at the baseline ref.

    Returns:
        A :class:`Resolution` for the baseline interfaces.

    Raises:
        VfsError: If the baseline cannot be resolved.
    """
    target_dir = Path(target_dir)
    if against.endswith(".mcap"):
        return resolve_bag(against)
    if against.endswith(".lock"):
        return resolve_lock(against)

    # Explicit path forms bypass git detection entirely, so `./main` compares
    # against a directory even when a git ref `main` also exists.
    if against.startswith(("./", "../")) or os.path.isabs(against):
        path = Path(against)
        if path.is_dir():
            vfs = RealFS(path)
            return Resolution(vfs=vfs, packages=discover(vfs, "."), source=f"path:{path}")
        raise VfsError(f"no such baseline directory: {against}")

    repo_root = git_toplevel(target_dir)
    if repo_root is not None and _is_git_ref(repo_root, against):
        rel = os.path.relpath(target_dir, repo_root)
        git_vfs = GitTreeFS(repo_root, against)
        packages = discover(git_vfs, "." if rel == "." else rel)
        return Resolution(vfs=git_vfs, packages=packages, source=f"git:{against}")

    path = Path(against)
    if path.is_dir():
        real_vfs: VFS = RealFS(path)
        return Resolution(vfs=real_vfs, packages=discover(real_vfs, "."), source=f"path:{path}")

    raise VfsError(f"cannot resolve baseline {against!r}: not a git ref, directory, .mcap or .lock")


def resolve_bag(bag_path: str) -> Resolution:
    """Resolve an MCAP bag's embedded interface definitions as a source.

    Raises:
        VfsError: If the bag cannot be read or lacks usable schemas.
    """
    from ..mcap_fs import McapTypeFS

    if not Path(bag_path).is_file():
        raise VfsError(f"no such MCAP file: {bag_path}")
    vfs = McapTypeFS(bag_path)
    return Resolution(vfs=vfs, packages=discover(vfs, "."), source=f"mcap:{bag_path}")


def resolve_lock(lock_path: str) -> Resolution:
    """Resolve a ``roschema.lock`` file's interfaces as a source.

    Raises:
        VfsError: If the lockfile is missing or fails verification.
    """
    from ..freeze import LockFS

    if not Path(lock_path).is_file():
        raise VfsError(f"no such lockfile: {lock_path}")
    vfs = LockFS(lock_path)
    return Resolution(vfs=vfs, packages=discover(vfs, "."), source=f"lock:{lock_path}")


def _is_git_ref(repo_root: Path, ref: str) -> bool:
    try:
        rev_parse_verify(repo_root, ref)
    except VfsError:
        return False
    return True


def resolve_ament(name: str) -> Resolution | None:
    """Resolve a package by name via the ament index, or ``None`` if not found."""
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
