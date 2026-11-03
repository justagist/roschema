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
    import tomli as tomllib

_PACKAGE_XML = '<?xml version="1.0"?>\n<package format="3"><name>{name}</name></package>\n'


def _toml_string(value: str) -> str:
    """Render ``value`` as a fully-escaped TOML basic (single-line) string.

    Using a basic string (not a ``'''`` literal block) means interface text
    containing ``'''`` cannot corrupt the lockfile.
    """
    out = ['"']
    for ch in value:
        if ch == "\\":
            out.append("\\\\")
        elif ch == '"':
            out.append('\\"')
        elif ch == "\n":
            out.append("\\n")
        elif ch == "\t":
            out.append("\\t")
        elif ch == "\r":
            out.append("\\r")
        elif ch == "\b":
            out.append("\\b")
        elif ch == "\f":
            out.append("\\f")
        elif ord(ch) < 0x20 or ord(ch) == 0x7F:
            out.append(f"\\u{ord(ch):04x}")
        else:
            out.append(ch)
    out.append('"')
    return "".join(out)


def build_lock(interfaces: dict[str, InterfaceFile], tool_version: str) -> str:
    """Serialise interfaces to lockfile TOML (canonical text + sha256)."""
    out = ["# roschema lockfile -- generated; do not edit by hand.", ""]
    out.append(f"tool_version = {_toml_string(tool_version)}")
    out.append("")
    for key in sorted(interfaces):
        iface = interfaces[key]
        text = format_text(iface.raw_text, iface.source_file)
        if not text.endswith("\n"):
            text += "\n"
        digest = hashlib.sha256(text.encode()).hexdigest()
        out.append("[[interface]]")
        out.append(f"key = {_toml_string(key)}")
        out.append(f"package = {_toml_string(iface.package)}")
        out.append(f"kind = {_toml_string(iface.kind)}")
        out.append(f"name = {_toml_string(iface.name)}")
        out.append(f"sha256 = {_toml_string(digest)}")
        out.append(f"text = {_toml_string(text)}")
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
        try:
            text = str(entry["text"])
            pkg, kind, name = entry["package"], entry["kind"], entry["name"]
            expected = entry["sha256"]
        except (KeyError, TypeError) as exc:
            raise VfsError(f"malformed lockfile entry in {lock_path}: missing {exc}") from exc
        if hashlib.sha256(text.encode()).hexdigest() != expected:
            raise VfsError(f"lockfile entry {entry.get('key')!r} failed sha256 verification")
        files[f"{pkg}/{kind}/{name}.{kind}"] = text
        files[f"{pkg}/package.xml"] = _PACKAGE_XML.format(name=pkg)
    return files
