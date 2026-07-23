"""Parser error type with source-location rendering."""

from __future__ import annotations


class ParseError(Exception):
    """Raised on a malformed interface definition.

    Carries a source location so the CLI can render a ``file:line:col`` message
    with a caret snippet and exit with code 2.

    Args:
        message: Human-readable description of the problem.
        source_file: Path of the offending file.
        line: 1-based line number.
        col: 1-based column number.
        source_line: The full offending line, used to draw the caret snippet.
    """

    def __init__(
        self,
        message: str,
        source_file: str,
        line: int,
        col: int,
        source_line: str = "",
    ) -> None:
        self.message = message
        self.source_file = source_file
        self.line = line
        self.col = col
        self.source_line = source_line
        super().__init__(self.render())

    def render(self) -> str:
        """Format the error as a multi-line message with a caret snippet."""
        header = f"{self.source_file}:{self.line}:{self.col}: error: {self.message}"
        if not self.source_line:
            return header
        caret = " " * (self.col - 1) + "^"
        return f"{header}\n{self.source_line}\n{caret}"
