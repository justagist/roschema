"""Finding reporters: text, JSON and GitHub annotations."""

from __future__ import annotations

from .github import build_github
from .json_report import build_json
from .markdown import build_markdown
from .summary import Coverage, Summary, coverage, summarize
from .text import render_lint, render_text

__all__ = [
    "Coverage",
    "Summary",
    "build_github",
    "build_json",
    "build_markdown",
    "coverage",
    "render_lint",
    "render_text",
    "summarize",
]
