"""Line-based parser for the ROS 2 interface definition grammar.

The grammar is line-oriented, so the parser walks the file line by line rather
than building a token stream. Each non-trivia line is one member (field or
constant); ``---`` lines split sections.
"""

from __future__ import annotations

import re

from ..ir import (
    BUILTIN_TYPES,
    ArrayKind,
    Constant,
    Default,
    Field,
    InterfaceFile,
    Section,
    SectionKind,
    TypeRef,
)
from .errors import ParseError

_KIND_SECTIONS: dict[str, tuple[SectionKind, ...]] = {
    "msg": (SectionKind.MESSAGE,),
    "srv": (SectionKind.REQUEST, SectionKind.RESPONSE),
    "action": (SectionKind.GOAL, SectionKind.RESULT, SectionKind.FEEDBACK),
}

_IDENT = re.compile(r"[A-Za-z_]\w*")
_NAME_RE = re.compile(r"^[A-Za-z_]\w*$")
_ARRAY_RE = re.compile(r"^(?P<base>.*?)\[(?P<spec>|<=\d+|\d+)\]$")
_STRING_RE = re.compile(r"^(w?string)(?:<=(\d+))?$")

_INT_TYPES = frozenset(
    {"byte", "char", "int8", "int16", "int32", "int64", "uint8", "uint16", "uint32", "uint64"}
)
_FLOAT_TYPES = frozenset({"float32", "float64"})


def parse_text(
    text: str, source_file: str, package: str, name: str, kind: str
) -> InterfaceFile:
    """Parse interface source into an :class:`InterfaceFile`.

    Args:
        text: Full file contents.
        source_file: Path used in error messages and IR nodes.
        package: Owning ROS package name.
        name: Interface type name (no extension).
        kind: One of ``msg``, ``srv``, ``action``.

    Returns:
        The parsed interface.

    Raises:
        ParseError: On any grammar violation, with source location.
    """
    if kind not in _KIND_SECTIONS:
        raise ParseError(f"unknown interface kind {kind!r}", source_file, 1, 1)
    expected = _KIND_SECTIONS[kind]

    # Partition lines into sections at bare `---` separators.
    groups: list[list[tuple[int, str]]] = [[]]
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if raw.strip() == "---":
            groups.append([])
        else:
            groups[-1].append((lineno, raw))

    if len(groups) != len(expected):
        sep = len(groups) - 1
        want = len(expected) - 1
        raise ParseError(
            f"{kind} file must have exactly {want} '---' separator(s), found {sep}",
            source_file,
            1,
            1,
        )

    sections = tuple(
        Section(kind=skind, members=_parse_section(lines, source_file))
        for skind, lines in zip(expected, groups, strict=True)
    )
    return InterfaceFile(
        package=package,
        name=name,
        kind=kind,
        sections=sections,
        source_file=source_file,
        raw_text=text,
    )


def _parse_section(
    lines: list[tuple[int, str]], source_file: str
) -> tuple[Field | Constant, ...]:
    members: list[Field | Constant] = []
    for lineno, raw in lines:
        code, comment = _split_comment(raw)
        if not code.strip():
            continue  # blank or full-line comment: trivia
        members.append(_parse_member(raw, code, comment, lineno, source_file))
    return tuple(members)


def _split_comment(line: str) -> tuple[str, str]:
    """Split a line into (code, comment), honouring quoted strings.

    The comment portion includes the leading ``#``; it is empty when absent.
    """
    quote: str | None = None
    esc = False
    for i, ch in enumerate(line):
        if quote is not None:
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
        elif ch == "#":
            return line[:i], line[i:]
    return line, ""


def _parse_member(
    raw: str, code: str, comment: str, lineno: int, source_file: str
) -> Field | Constant:
    indent = len(raw) - len(raw.lstrip())
    body = code.strip()
    parts = body.split(None, 1)
    type_token = parts[0]
    type_ref = _parse_type(type_token, indent + 1, lineno, raw, source_file)

    comment_text = comment.strip() or None

    if len(parts) == 1:
        raise ParseError(
            "expected a name after the type",
            source_file,
            lineno,
            indent + len(type_token) + 1,
            raw,
        )

    rest = parts[1]
    name_match = _IDENT.match(rest)
    if not name_match:
        raise ParseError(
            "expected a valid identifier for the member name",
            source_file,
            lineno,
            indent + len(type_token) + 2,
            raw,
        )
    member_name = name_match.group(0)
    sep_idx = name_match.end()
    if sep_idx < len(rest) and rest[sep_idx] not in " \t=":
        raise ParseError(
            "invalid character in member name",
            source_file,
            lineno,
            indent + len(type_token) + 1 + sep_idx + 1,
            raw,
        )
    after = rest[sep_idx:].lstrip()

    if after.startswith("="):
        value_raw = after[1:].strip()
        if value_raw == "":
            raise ParseError(
                "constant is missing a value after '='", source_file, lineno, indent + 1, raw
            )
        if type_ref.array_kind is not ArrayKind.NONE:
            raise ParseError(
                "constants cannot be arrays", source_file, lineno, indent + 1, raw
            )
        if not type_ref.is_builtin:
            raise ParseError(
                "constant type must be a primitive type", source_file, lineno, indent + 1, raw
            )
        return Constant(
            name=member_name,
            type=type_ref,
            value_raw=value_raw,
            value=_parse_value(value_raw, type_ref),
            trailing_comment=comment_text,
            source_file=source_file,
            line=lineno,
            raw_text=raw,
        )

    default: Default | None = None
    if after:
        default = Default(raw=after, value=_parse_value(after, type_ref))
    return Field(
        name=member_name,
        type=type_ref,
        default=default,
        trailing_comment=comment_text,
        source_file=source_file,
        line=lineno,
        raw_text=raw,
    )


def _parse_type(
    token: str, col: int, lineno: int, raw: str, source_file: str
) -> TypeRef:
    array_kind = ArrayKind.NONE
    array_bound: int | None = None
    base_part = token

    if "[" in token or "]" in token:
        m = _ARRAY_RE.match(token)
        if not m:
            raise ParseError(
                f"malformed array specifier in type {token!r}", source_file, lineno, col, raw
            )
        base_part = m.group("base")
        spec = m.group("spec")
        if spec == "":
            array_kind = ArrayKind.UNBOUNDED
        elif spec.startswith("<="):
            array_kind = ArrayKind.BOUNDED
            array_bound = int(spec[2:])
        else:
            array_kind = ArrayKind.FIXED
            array_bound = int(spec)

    if base_part == "":
        raise ParseError(
            f"missing base type in {token!r}", source_file, lineno, col, raw
        )

    if "/" in base_part:
        pkg, _, tname = base_part.partition("/")
        if not _NAME_RE.match(pkg) or not _NAME_RE.match(tname):
            raise ParseError(
                f"invalid namespaced type {base_part!r}", source_file, lineno, col, raw
            )
        return TypeRef(
            base=tname,
            package=pkg,
            string_bound=None,
            array_kind=array_kind,
            array_bound=array_bound,
            is_builtin=False,
        )

    sm = _STRING_RE.match(base_part)
    if sm:
        return TypeRef(
            base=sm.group(1),
            package=None,
            string_bound=int(sm.group(2)) if sm.group(2) else None,
            array_kind=array_kind,
            array_bound=array_bound,
            is_builtin=True,
        )

    if base_part in BUILTIN_TYPES:
        return TypeRef(
            base=base_part,
            package=None,
            string_bound=None,
            array_kind=array_kind,
            array_bound=array_bound,
            is_builtin=True,
        )

    if not _NAME_RE.match(base_part):
        raise ParseError(
            f"invalid type name {base_part!r}", source_file, lineno, col, raw
        )
    return TypeRef(
        base=base_part,
        package=None,
        string_bound=None,
        array_kind=array_kind,
        array_bound=array_bound,
        is_builtin=False,
    )


def _parse_value(raw: str, type_ref: TypeRef) -> object:
    """Parse a default/constant value into a Python object, type-aware."""
    s = raw.strip()
    if s.startswith("[") and s.endswith("]"):
        inner = s[1:-1].strip()
        if inner == "":
            return ()
        return tuple(_parse_scalar(x.strip(), type_ref.base) for x in _split_list(inner))
    return _parse_scalar(s, type_ref.base)


def _parse_scalar(s: str, base: str) -> object:
    if len(s) >= 2 and s[0] in "'\"" and s[-1] == s[0]:
        return _unquote(s)
    if base in ("string", "wstring"):
        return s
    if base == "bool":
        low = s.lower()
        if low in ("true", "1"):
            return True
        if low in ("false", "0"):
            return False
        return s
    if base in _FLOAT_TYPES:
        try:
            return float(s)
        except ValueError:
            return s
    if base in _INT_TYPES:
        try:
            return int(s, 0)
        except ValueError:
            return s
    # Complex type or unknown: best-effort literal.
    for conv in (int, float):
        try:
            return conv(s)
        except ValueError:
            continue
    return s


def _split_list(inner: str) -> list[str]:
    """Split comma-separated list contents, honouring quoted elements."""
    out: list[str] = []
    quote: str | None = None
    esc = False
    buf: list[str] = []
    for ch in inner:
        if quote is not None:
            buf.append(ch)
            if esc:
                esc = False
            elif ch == "\\":
                esc = True
            elif ch == quote:
                quote = None
        elif ch in ("'", '"'):
            quote = ch
            buf.append(ch)
        elif ch == ",":
            out.append("".join(buf))
            buf = []
        else:
            buf.append(ch)
    out.append("".join(buf))
    return out


def _unquote(s: str) -> str:
    inner = s[1:-1]
    return inner.replace("\\" + s[0], s[0]).replace("\\\\", "\\")
