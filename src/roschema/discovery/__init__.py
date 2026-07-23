"""Discovery: resolve targets and enumerate interface packages via a VFS."""

from __future__ import annotations

from .discover import discover, discover_named
from .model import DiscoveredPackage, InterfaceRef, Resolution
from .resolve import apply_exclude, resolve_baseline, resolve_target

__all__ = [
    "DiscoveredPackage",
    "InterfaceRef",
    "Resolution",
    "apply_exclude",
    "discover",
    "discover_named",
    "resolve_baseline",
    "resolve_target",
]
