"""Public parser API: text/file entry points and the error type."""

from __future__ import annotations

from pathlib import Path

from ..ir import InterfaceFile
from .core import parse_text
from .errors import ParseError

_EXT_KIND = {".msg": "msg", ".srv": "srv", ".action": "action"}


def parse_file(path: str | Path) -> InterfaceFile:
    """Parse an interface file from disk, deriving identity from its path.

    Expects the ROS layout ``.../<package>/<msg|srv|action>/<Name>.<ext>``.

    Args:
        path: Path to a ``.msg``, ``.srv`` or ``.action`` file.

    Returns:
        The parsed interface.

    Raises:
        ParseError: On a malformed file or an unexpected path layout.
    """
    p = Path(path)
    kind = _EXT_KIND.get(p.suffix)
    if kind is None:
        raise ParseError(f"unsupported extension {p.suffix!r}", str(p), 1, 1)
    package = p.parent.parent.name
    return parse_text(p.read_text(encoding="utf-8"), str(p), package, p.stem, kind)


__all__ = ["ParseError", "parse_file", "parse_text"]
