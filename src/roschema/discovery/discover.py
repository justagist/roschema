"""Discover interface packages and files through a VFS."""

from __future__ import annotations

import posixpath
import re

from ..vfs import VFS
from .model import DiscoveredPackage, InterfaceRef

_KINDS = ("msg", "srv", "action")
_NAME_RE = re.compile(r"<name>\s*([A-Za-z0-9_-]+)\s*</name>")


def discover(
    vfs: VFS, root: str = ".", *, include_empty: bool = False
) -> tuple[DiscoveredPackage, ...]:
    """Find interface packages by walking for ``package.xml`` under ``root``.

    Only packages that actually contain ``msg``/``srv``/``action`` definitions
    are returned. Package names come from ``package.xml`` (``<name>``), falling
    back to the directory name. Trees marked with ``COLCON_IGNORE`` or
    ``AMENT_IGNORE`` are skipped before reading package manifests.

    Args:
        vfs: Backend to read through.
        root: Directory (VFS-relative) to walk; ``"."`` means the VFS root.
        include_empty: Include packages without interfaces for source overlays.

    Returns:
        Discovered packages, sorted by name.
    """
    prefix = "" if root in ("", ".") else root.rstrip("/") + "/"
    packages: list[DiscoveredPackage] = []
    for pkg_xml in vfs.glob(prefix + "**/package.xml"):
        pkg_dir = posixpath.dirname(pkg_xml)
        if _is_ignored(vfs, pkg_dir):
            continue
        name = _package_name(vfs, pkg_xml, pkg_dir)
        interfaces = _collect_interfaces(vfs, name, pkg_dir)
        if interfaces or include_empty:
            packages.append(DiscoveredPackage(name=name, path=pkg_dir, interfaces=interfaces))
    packages.sort(key=lambda p: p.name)
    return tuple(packages)


def _is_ignored(vfs: VFS, directory: str) -> bool:
    """Check for discovery ignore markers up to the VFS root."""
    while True:
        if any(
            vfs.exists(posixpath.join(directory, marker))
            for marker in ("COLCON_IGNORE", "AMENT_IGNORE")
        ):
            return True
        if not directory:
            return False
        directory = posixpath.dirname(directory)


def discover_named(vfs: VFS, package: str, root: str = ".") -> tuple[DiscoveredPackage, ...]:
    """Collect interfaces for a known package name without needing ``package.xml``.

    Used for ament-index resolution, where the install layout is
    ``share/<package>/{msg,srv,action}`` and the name is already known.
    """
    pkg_dir = "" if root in ("", ".") else root.rstrip("/")
    interfaces = _collect_interfaces(vfs, package, pkg_dir)
    if not interfaces:
        return ()
    return (DiscoveredPackage(name=package, path=pkg_dir, interfaces=interfaces),)


def _collect_interfaces(vfs: VFS, package: str, pkg_dir: str) -> tuple[InterfaceRef, ...]:
    base = pkg_dir + "/" if pkg_dir else ""
    refs: list[InterfaceRef] = []
    for kind in _KINDS:
        for path in vfs.glob(f"{base}{kind}/*.{kind}"):
            name = posixpath.splitext(posixpath.basename(path))[0]
            refs.append(InterfaceRef(package=package, kind=kind, name=name, path=path))
    refs.sort(key=lambda r: (r.kind, r.name))
    return tuple(refs)


def _package_name(vfs: VFS, pkg_xml: str, pkg_dir: str) -> str:
    try:
        match = _NAME_RE.search(vfs.read_text(pkg_xml))
    except OSError:
        match = None
    if match:
        return match.group(1)
    return posixpath.basename(pkg_dir) or pkg_dir
