"""A VFS backed by message definitions embedded in an MCAP bag.

Schemas recorded by rosbag2 carry the interface definitions inline. This VFS
extracts them and presents a virtual tree (``pkg/msg/Name.msg`` plus a synthetic
``pkg/package.xml``) so the ordinary discovery and parser path works unchanged.

Supported schema encodings:

* ``ros2msg`` -- the concatenated ``.msg`` format (dependent definitions appended
  after ``====`` separators with ``MSG: pkg/Type`` headers). Fully supported.
* ``ros2idl`` -- a best-effort conversion of the msg-equivalent subset (simple
  ``struct`` definitions with scalar/array/sequence/bounded-string fields and
  ``const`` declarations). Annotations, unions, typedefs, enums and other IDL
  constructs are not supported.
"""

from __future__ import annotations

import re
from typing import Any

from .vfs import MappingVFS, VfsError

_SEPARATOR = re.compile(r"^={3,}$")
_MSG_HEADER = re.compile(r"^MSG:\s*(\S+)")
_PACKAGE_XML = '<?xml version="1.0"?>\n<package format="3"><name>{name}</name></package>\n'


class McapTypeFS(MappingVFS):
    """Read-only VFS over the interface definitions embedded in an MCAP file."""

    def __init__(self, bag_path: str) -> None:
        super().__init__(_build_tree(_read_schemas(bag_path)))


def _read_schemas(bag_path: str) -> dict[str, tuple[str, str]]:
    """Return ``{schema_name: (encoding, definition_text)}`` from an MCAP file."""
    try:
        from mcap.reader import make_reader
    except ModuleNotFoundError as exc:
        raise VfsError(
            "MCAP support requires the 'bag' extra: pip install 'roschema[bag]'"
        ) from exc

    schemas: dict[str, tuple[str, str]] = {}
    try:
        with open(bag_path, "rb") as handle:
            reader = make_reader(handle)
            for schema in _iter_schemas(reader):
                text = schema.data.decode("utf-8", errors="replace")
                schemas[schema.name] = (schema.encoding, text)
    except OSError as exc:
        raise VfsError(f"could not read MCAP file {bag_path}: {exc}") from exc
    return schemas


def _iter_schemas(reader: Any) -> list[Any]:
    summary = reader.get_summary()
    if summary is not None and summary.schemas:
        return list(summary.schemas.values())
    seen: dict[int, Any] = {}
    for schema, _channel, _message in reader.iter_messages():
        if schema is not None:
            seen[schema.id] = schema
    return list(seen.values())


def _build_tree(schemas: dict[str, tuple[str, str]]) -> dict[str, str]:
    files: dict[str, str] = {}
    packages: set[str] = set()
    for name, (encoding, text) in schemas.items():
        if encoding == "ros2msg":
            blocks = _split_ros2msg(name, text)
        elif encoding == "ros2idl":
            blocks = _convert_ros2idl(text)
        else:
            continue
        for type_name, body in blocks.items():
            pkg, short = _normalise(type_name)
            files[f"{pkg}/msg/{short}.msg"] = body if body.endswith("\n") else body + "\n"
            packages.add(pkg)
    for pkg in packages:
        files[f"{pkg}/package.xml"] = _PACKAGE_XML.format(name=pkg)
    return files


def _split_ros2msg(main_name: str, text: str) -> dict[str, str]:
    """Split a concatenated ros2msg definition into ``{type_name: body}``."""
    blocks: dict[str, str] = {}
    current = main_name
    lines: list[str] = []
    iterator = iter(text.splitlines())
    for line in iterator:
        if _SEPARATOR.match(line.strip()):
            blocks[current] = "\n".join(lines).strip("\n")
            lines = []
            current = _next_msg_header(iterator, main_name)
            continue
        lines.append(line)
    blocks[current] = "\n".join(lines).strip("\n")
    return blocks


def _next_msg_header(iterator: object, fallback: str) -> str:
    for line in iterator:  # type: ignore[attr-defined]
        stripped = line.strip()
        if not stripped:
            continue
        match = _MSG_HEADER.match(stripped)
        return match.group(1) if match else fallback
    return fallback


def _normalise(type_name: str) -> tuple[str, str]:
    """Return ``(package, short_name)`` from ``pkg/msg/Type`` or ``pkg/Type``."""
    parts = type_name.replace("::", "/").split("/")
    if len(parts) >= 3:
        return parts[0], parts[-1]
    if len(parts) == 2:
        return parts[0], parts[1]
    return "unknown_msgs", parts[-1]


# --- ros2idl (best-effort msg-equivalent subset) ---

_IDL_SCALAR = {
    "boolean": "bool",
    "octet": "byte",
    "char": "char",
    "wchar": "char",
    "int8": "int8",
    "uint8": "uint8",
    "int16": "int16",
    "uint16": "uint16",
    "int32": "int32",
    "uint32": "uint32",
    "int64": "int64",
    "uint64": "uint64",
    "float": "float32",
    "double": "float64",
    "short": "int16",
    "unsigned short": "uint16",
    "long": "int32",
    "unsigned long": "uint32",
    "long long": "int64",
    "unsigned long long": "uint64",
    "string": "string",
    "wstring": "wstring",
}
_MODULE_RE = re.compile(r"\bmodule\s+(\w+)\s*\{")
_STRUCT_RE = re.compile(r"\bstruct\s+(\w+)\s*\{")
_CONST_RE = re.compile(r"const\s+(\w[\w ]*?)\s+(\w+)\s*=\s*(.+?)\s*;")


def _convert_ros2idl(text: str) -> dict[str, str]:
    """Convert the msg-equivalent subset of an IDL blob into ``{type: body}``."""
    text = re.sub(r"//[^\n]*", "", text)
    text = re.sub(r"/\*.*?\*/", "", text, flags=re.DOTALL)
    blocks: dict[str, str] = {}
    for struct_match in _STRUCT_RE.finditer(text):
        name = struct_match.group(1)
        pkg = _enclosing_package(text, struct_match.start())
        body = _struct_body(text, struct_match.end())
        lines = _convert_struct_body(body)
        if lines is not None:
            blocks[f"{pkg}/msg/{name}"] = "\n".join(lines)
    return blocks


def _enclosing_package(text: str, pos: int) -> str:
    modules = [m.group(1) for m in _MODULE_RE.finditer(text, 0, pos)]
    for mod in modules:
        if mod != "msg":
            return mod
    return "unknown_msgs"


def _struct_body(text: str, start: int) -> str:
    depth = 1
    i = start
    while i < len(text) and depth > 0:
        if text[i] == "{":
            depth += 1
        elif text[i] == "}":
            depth -= 1
            if depth == 0:
                return text[start:i]
        i += 1
    return text[start:i]


def _convert_struct_body(body: str) -> list[str] | None:
    lines: list[str] = []
    for const in _CONST_RE.finditer(body):
        idl_type, cname, value = const.group(1).strip(), const.group(2), const.group(3)
        ros_type = _IDL_SCALAR.get(idl_type)
        if ros_type is None:
            return None
        lines.append(f"{ros_type} {cname}={value}")
    without_consts = _CONST_RE.sub("", body)
    for statement in without_consts.split(";"):
        statement = statement.strip()
        if not statement:
            continue
        field = _convert_idl_field(statement)
        if field is None:
            return None
        lines.append(field)
    return lines


def _convert_idl_field(statement: str) -> str | None:
    array_suffix = ""
    array_match = re.search(r"(\w+)\s*\[\s*(\d+)\s*\]$", statement)
    if array_match:
        statement = statement[: array_match.start()] + array_match.group(1)
        array_suffix = f"[{array_match.group(2)}]"

    parts = statement.rsplit(None, 1)
    if len(parts) != 2:
        return None
    type_part, field_name = parts[0].strip(), parts[1]

    ros_type = _convert_idl_type(type_part)
    if ros_type is None:
        return None
    return f"{ros_type}{array_suffix} {field_name}"


def _convert_idl_type(type_part: str) -> str | None:
    seq = re.match(r"sequence\s*<\s*(.+?)\s*(?:,\s*(\d+)\s*)?>$", type_part)
    if seq:
        inner = _convert_idl_type(seq.group(1))
        if inner is None:
            return None
        return f"{inner}[<={seq.group(2)}]" if seq.group(2) else f"{inner}[]"

    string_bound = re.match(r"(w?string)\s*<\s*(\d+)\s*>$", type_part)
    if string_bound:
        return f"{string_bound.group(1)}<={string_bound.group(2)}"

    if "::" in type_part:
        pkg, short = _normalise(type_part)
        return f"{pkg}/{short}"

    return _IDL_SCALAR.get(type_part)
