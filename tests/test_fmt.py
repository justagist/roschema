"""Tests for the formatter and `roschema fmt`.

Includes the two guarantees: fmt never changes what check reports (cosmetic
only), and inline suppressions survive formatting.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from typer.testing import CliRunner

from _helpers import write_package
from roschema.cli import app
from roschema.differ import diff_interfaces
from roschema.formatter import format_text
from roschema.parser import parse_text
from roschema.rules import evaluate, parse_inline_ignores

runner = CliRunner()
FIXTURES = Path(__file__).parent / "fixtures"
_FIXTURE_FILES = sorted(
    p
    for ext in ("*.msg", "*.srv", "*.action")
    for p in FIXTURES.rglob(ext)
)


def test_fmt_normalizes_inter_token_whitespace():
    assert format_text("int32   a\n") == "int32 a\n"
    assert format_text("int32 X = 5\n") == "int32 X=5\n"
    assert format_text("float32  theta   # yaw\n") == "float32 theta  # yaw\n"
    assert format_text("int32   a    7\n") == "int32 a 7\n"


def test_fmt_preserves_sections_comments_and_blanks():
    src = "# header\n\nint32 a\n---\nint32 b\n"
    assert format_text(src) == "# header\n\nint32 a\n---\nint32 b\n"


def test_fmt_single_trailing_newline():
    assert format_text("int32 a\n\n\n") == "int32 a\n"
    assert format_text("int32 a") == "int32 a\n"


@pytest.mark.parametrize("path", _FIXTURE_FILES, ids=lambda p: p.name)
def test_fmt_is_idempotent(path):
    original = path.read_text()
    once = format_text(original, str(path))
    assert format_text(once, str(path)) == once


@pytest.mark.parametrize("path", _FIXTURE_FILES, ids=lambda p: p.name)
def test_fmt_does_not_change_check(path):
    original = path.read_text()
    formatted = format_text(original, str(path))
    kind = path.suffix.lstrip(".")
    old = parse_text(original, "old", "p", path.stem, kind)
    new = parse_text(formatted, "new", "p", path.stem, kind)
    assert evaluate(diff_interfaces({old.key: old}, {new.key: new})) == []


def test_fmt_check_safety_on_messy_input():
    messy = "float32   theta  # roschema: ignore=RS003\nint32 a  5\nint32 X = 1\n"
    formatted = format_text(messy)
    old = parse_text(messy, "old", "p", "T", "msg")
    new = parse_text(formatted, "new", "p", "T", "msg")
    assert evaluate(diff_interfaces({old.key: old}, {new.key: new})) == []


def test_fmt_preserves_inline_suppression():
    formatted = format_text("float32   theta   #roschema:ignore=RS005\n")
    assert "roschema" in formatted
    (field,) = parse_text(formatted, "o", "p", "T", "msg").fields()
    assert "RS005" in parse_inline_ignores(field.trailing_comment)


def test_cli_fmt_check_flags_unformatted(tmp_path):
    write_package(tmp_path, "p", msgs={"Foo": "int32   a\n"})
    result = runner.invoke(app, ["fmt", str(tmp_path), "--check"])
    assert result.exit_code == 1
    assert "would reformat" in result.stdout


def test_cli_fmt_writes_and_is_stable(tmp_path):
    write_package(tmp_path, "p", msgs={"Foo": "int32   a  # doc\n"})
    path = tmp_path / "p" / "msg" / "Foo.msg"
    result = runner.invoke(app, ["fmt", str(tmp_path)])
    assert result.exit_code == 0
    assert path.read_text() == "int32 a  # doc\n"
    # already formatted -> --check now clean
    again = runner.invoke(app, ["fmt", str(tmp_path), "--check"])
    assert again.exit_code == 0
