"""Data types describing what discovery found."""

from __future__ import annotations

from dataclasses import dataclass

from ..vfs import VFS


@dataclass(frozen=True)
class InterfaceRef:
    """A discovered interface file, not yet parsed.

    Args:
        package: Owning package name.
        kind: One of ``msg``, ``srv``, ``action``.
        name: Interface type name without extension.
        path: Path within the owning VFS.
    """

    package: str
    kind: str
    name: str
    path: str

    @property
    def key(self) -> str:
        """Stable identity ``package/kind/name``."""
        return f"{self.package}/{self.kind}/{self.name}"


@dataclass(frozen=True)
class DiscoveredPackage:
    """A discovered package and its interface definitions."""

    name: str
    path: str
    interfaces: tuple[InterfaceRef, ...]


@dataclass(frozen=True)
class Resolution:
    """The outcome of resolving a target to discoverable interfaces.

    Args:
        vfs: Backend the interfaces are read from.
        packages: Interface packages found, sorted by name.
        source: Human-readable description of where they came from.
    """

    vfs: VFS
    packages: tuple[DiscoveredPackage, ...]
    source: str
    glob_pattern: str | None = None
    """Directory glob to resolve independently against the comparison baseline."""
