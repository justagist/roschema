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
from typing import Any, BinaryIO

from .differ import diff_interfaces
from .parser import parse_text
from .vfs import MappingVFS, VfsError

_SEPARATOR = re.compile(r"^={3,}$")
_MSG_HEADER = re.compile(r"^MSG:\s*(\S+)")
_PACKAGE_XML = '<?xml version="1.0"?>\n<package format="3"><name>{name}</name></package>\n'


class McapTypeFS(MappingVFS):
    """Read-only VFS over the interface definitions embedded in an MCAP file."""

    def __init__(self, bag_path: str) -> None:
        super().__init__(_build_tree(_read_schemas(bag_path)))


def _read_schemas(bag_path: str) -> list[tuple[str, str, str]]:
    """Return every schema as ``(name, encoding, definition_text)``."""
    try:
        from mcap.reader import make_reader
    except ModuleNotFoundError as exc:
        raise VfsError(
            "MCAP support requires the 'bag' extra: pip install 'roschema[bag]'"
        ) from exc

    schemas: list[tuple[str, str, str]] = []
    try:
        with open(bag_path, "rb") as handle:
            reader = make_reader(handle)
            for schema in _iter_schemas(reader, handle):
                text = schema.data.decode("utf-8", errors="replace")
                schemas.append((schema.name, schema.encoding, text))
    except OSError as exc:
        raise VfsError(f"could not read MCAP file {bag_path}: {exc}") from exc
    return schemas


def _iter_schemas(reader: Any, handle: BinaryIO) -> list[Any]:
    summary = reader.get_summary()
    if summary is not None and summary.schemas:
        return list(summary.schemas.values())
    from mcap.reader import NonSeekingReader

    handle.seek(0)
    seen: dict[int, Any] = {}
    for schema, _channel, _message in NonSeekingReader(handle).iter_messages():
        if schema is not None:
            seen[schema.id] = schema
    return list(seen.values())


def _build_tree(schemas: list[tuple[str, str, str]]) -> dict[str, str]:
    definitions: dict[str, str] = {}
    for name, encoding, text in schemas:
        if encoding == "ros2msg":
            blocks = _split_ros2msg(name, text)
        elif encoding == "ros2idl":
            blocks = _convert_ros2idl(text)
        else:
            raise VfsError(f"unsupported MCAP schema encoding {encoding!r} for {name}")
        if not blocks:
            raise VfsError(f"unsupported {encoding} schema {name}: no convertible definitions")
        for type_name, body in blocks.items():
            pkg, short = _normalise(type_name)
            _store_definition(definitions, f"{pkg}/msg/{short}", body)
    if not definitions:
        raise VfsError("MCAP contains no usable ROS schemas")
    files: dict[str, str] = {}
    packages: set[str] = set()
    for name, body in definitions.items():
        pkg, short = _normalise(name)
        files[f"{pkg}/msg/{short}.msg"] = body if body.endswith("\n") else body + "\n"
        packages.add(pkg)
    for pkg in packages:
        files[f"{pkg}/package.xml"] = _PACKAGE_XML.format(name=pkg)
    return files


def _store_definition(definitions: dict[str, str], name: str, body: str) -> None:
    """Coalesce equivalent schemas and reject conflicting type definitions."""
    if name in definitions:
        pkg, short = _normalise(name)
        old = parse_text(definitions[name], name, pkg, short, "msg")
        new = parse_text(body, name, pkg, short, "msg")
        if diff_interfaces({old.key: old}, {new.key: new}):
            raise VfsError(f"conflicting MCAP definitions for {name}")
    else:
        definitions[name] = body


def _split_ros2msg(main_name: str, text: str) -> dict[str, str]:
    """Split a concatenated ros2msg definition into ``{type_name: body}``."""
    blocks: dict[str, str] = {}
    current = main_name
    lines: list[str] = []
    iterator = iter(text.splitlines())
    for line in iterator:
        if _SEPARATOR.match(line.strip()):
            _store_definition(blocks, current, "\n".join(lines).strip("\n"))
            lines = []
            current = _next_msg_header(iterator, main_name)
            continue
        lines.append(line)
    _store_definition(blocks, current, "\n".join(lines).strip("\n"))
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
    code = re.sub(r'"(?:\\.|[^"\\])*"', lambda m: " " * len(m.group()), text)
    if re.search(
        r"\b(?:enum|union|typedef)\s+\w+|(?:^|[;{}])\s*@\w+|\bstruct\s+\w+\s*:",
        code,
        re.MULTILINE,
    ):
        raise VfsError("unsupported ros2idl construct; conversion would be incomplete")
    blocks: dict[str, str] = {}
    outside_structs: list[str] = []
    end = 0
    for struct_match in _STRUCT_RE.finditer(code):
        outside_structs.append(code[end : struct_match.start()])
        name = struct_match.group(1)
        pkg = _enclosing_package(text, struct_match.start())
        end = struct_match.end() + len(_struct_body(code, struct_match.end()))
        body = text[struct_match.end() : end]
        end += 1
        lines = _convert_struct_body(body)
        if lines is None:
            raise VfsError(f"unsupported ros2idl struct {pkg}/msg/{name}")
        _store_definition(blocks, f"{pkg}/msg/{name}", "\n".join(lines))
    outside_structs.append(code[end:])
    if re.search(r"\bconst\b", "".join(outside_structs)):
        raise VfsError("unsupported ros2idl constant outside a struct")
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
