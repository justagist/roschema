"""Parse discovered interfaces from a VFS into an IR map keyed by interface."""

from __future__ import annotations

from .discovery import DiscoveredPackage
from .ir import InterfaceFile
from .parser import parse_text
from .vfs import VFS


def load_interfaces(
    vfs: VFS, packages: tuple[DiscoveredPackage, ...]
) -> dict[str, InterfaceFile]:
    """Read and parse every discovered interface.

    Args:
        vfs: Backend the interface paths are read from.
        packages: Discovered packages whose interfaces to parse.

    Returns:
        Map of ``package/kind/name`` to the parsed interface.

    Raises:
        ParseError: If any interface is malformed.
    """
    result: dict[str, InterfaceFile] = {}
    for pkg in packages:
        for ref in pkg.interfaces:
            text = vfs.read_text(ref.path)
            iface = parse_text(text, ref.path, ref.package, ref.name, ref.kind)
            result[iface.key] = iface
    return result
