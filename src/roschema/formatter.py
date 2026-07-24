"""Canonical formatting for interface files.

The formatter normalises only inter-token whitespace: a single space between a
type and name (and before a default), no spaces around a constant's ``=``, two
spaces before a trailing comment, one trailing newline. Comments (including
``# roschema: ignore=`` suppressions), blank lines and section separators are
preserved, and default/constant value text is kept verbatim. Consequently a
formatted file parses to the same IR as the original, so ``fmt`` never changes
what ``check`` reports.
"""

from __future__ import annotations

from .ir import Constant, Member
from .parser.core import _parse_member, _split_comment


def format_text(text: str, source_file: str = "<fmt>") -> str:
    """Return the canonical formatting of interface ``text``.

    Raises:
        ParseError: If a member line is malformed.
    """
    out: list[str] = []
    for lineno, raw in enumerate(text.splitlines(), start=1):
        if raw.strip() == "---":
            out.append("---")
            continue
        code, comment = _split_comment(raw)
        if not code.strip():
            out.append(comment.rstrip() if comment else "")
            continue
        out.append(_render(_parse_member(raw, code, comment, lineno, source_file)))
    while out and out[-1] == "":
        out.pop()
    return "\n".join(out) + "\n" if out else ""


def _render(member: Member) -> str:
    if isinstance(member, Constant):
        base = f"{member.type.render()} {member.name}={member.value_raw}"
    else:
        base = f"{member.type.render()} {member.name}"
        if member.default is not None:
            base += f" {member.default.raw}"
    if member.trailing_comment:
        base += f"  {member.trailing_comment}"
    return base
