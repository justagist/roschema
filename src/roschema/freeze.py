"""Lockfile support: write a `roschema.lock` and read it back as a VFS.

A lockfile captures the canonical (post-`fmt`) text of every interface plus a
sha256, so a release tarball can carry its own baseline without git. Reading it
back presents the same virtual tree as any other source, so discovery, parsing
and diffing run unchanged.
"""

from __future__ import annotations

import hashlib
import sys

from .formatter import format_text
from .ir import InterfaceFile
from .vfs import MappingVFS, VfsError

if sys.version_info >= (3, 11):
    import tomllib
else:  # pragma: no cover - exercised only on py3.10
    import tomli as tomllib  # type: ignore[import-not-found]

_PACKAGE_XML = '<?xml version="1.0"?>\n<package format="3"><name>{name}</name></package>\n'


def build_lock(interfaces: dict[str, InterfaceFile], tool_version: str) -> str:
    """Serialise interfaces to lockfile TOML (canonical text + sha256)."""
    out = ["# roschema lockfile -- generated; do not edit by hand.", ""]
    out.append(f'tool_version = "{tool_version}"')
    out.append("")
    for key in sorted(interfaces):
        iface = interfaces[key]
        text = format_text(iface.raw_text, iface.source_file)
        if not text.endswith("\n"):
            text += "\n"
        digest = hashlib.sha256(text.encode()).hexdigest()
        out.append("[[interface]]")
        out.append(f'key = "{key}"')
        out.append(f'package = "{iface.package}"')
        out.append(f'kind = "{iface.kind}"')
        out.append(f'name = "{iface.name}"')
        out.append(f'sha256 = "{digest}"')
        out.append("text = '''")
        out.append(text + "'''")
        out.append("")
    return "\n".join(out) + "\n"


class LockFS(MappingVFS):
    """Read-only VFS over a `roschema.lock` file (sha256-verified)."""

    def __init__(self, lock_path: str) -> None:
        super().__init__(_load_lock(lock_path))


def _load_lock(lock_path: str) -> dict[str, str]:
    try:
        with open(lock_path, "rb") as handle:
            data = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise VfsError(f"could not read lockfile {lock_path}: {exc}") from exc

    files: dict[str, str] = {}
    entries = data.get("interface", [])
    if not isinstance(entries, list):
        raise VfsError(f"malformed lockfile {lock_path}: 'interface' must be a table array")
    for entry in entries:
        text = str(entry["text"])
        digest = hashlib.sha256(text.encode()).hexdigest()
        if digest != entry.get("sha256"):
            raise VfsError(
                f"lockfile entry {entry.get('key')!r} failed sha256 verification"
            )
        pkg, kind, name = entry["package"], entry["kind"], entry["name"]
        files[f"{pkg}/{kind}/{name}.{kind}"] = text
        files[f"{pkg}/package.xml"] = _PACKAGE_XML.format(name=pkg)
    return files
