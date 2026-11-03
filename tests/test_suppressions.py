"""Tests for unused-suppression reporting (RS200)."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from _helpers import write_package
from roschema.cli import app

runner = CliRunner()


def _check(tmp_path, old: str, new: str, config: str, *extra: str):
    write_package(tmp_path / "old", "p", msgs={"S": old})
    write_package(tmp_path / "new", "p", msgs={"S": new})
    for side in ("old", "new"):
        write_package(tmp_path / side, "q", msgs={"Q": "int32 q\n"})
    (tmp_path / "new" / "roschema.toml").write_text(config)
    return runner.invoke(
        app,
        ["check", str(tmp_path / "new"), "--against", str(tmp_path / "old"), *extra],
    )


def test_unused_allowlist_entries_are_reported(tmp_path):
    config = (
        "[check.allow]\n"
        '"p/msg/S.a" = { rules = ["RS001"], reason = "stale: a no longer changes" }\n'
        '"p/msg/S.typo" = { reason = "misspelt target" }\n'
        '"p/msg/S.b" = { reason = "used: b is removed" }\n'
        '"p/msg/S.c" = { rules = ["RS030"], reason = "used, though outside the level" }\n'
        '"other_pkg/msg/X.y" = { reason = "package not checked" }\n'
        '"q/msg/Q.q" = { reason = "package excluded" }\n'
    )
    result = _check(
        tmp_path,
        "int32 a\nint32 b\nint32 c 1\n",
        "int32 a\nint32 c 2\n",
        config,
        "--format",
        "json",
        "--exclude",
        "q",
    )
    doc = json.loads(result.stdout)
    unused = [
        (f["target"], f["message"], f["suppressed"])
        for f in doc["findings"]
        if f["rule"] == "RS200"
    ]
    assert unused == [
        ("a", "allowlist entry matches no finding for RS001", False),
        ("typo", "allowlist entry matches no finding", False),
    ]
    assert result.exit_code == 0  # RS200 is a warning
    assert doc["summary"]["advisories"] == {}  # stale config says nothing about a release


def test_unused_inline_ignore_points_at_its_line(tmp_path):
    result = _check(
        tmp_path,
        "int32 a\nint32 b\n",
        "int32 a  # roschema: ignore=RS003\nint64 b  # roschema: ignore=RS003,RSL001\n",
        "",
        "--format",
        "github",
    )
    lines = [line for line in result.stdout.splitlines() if "RS200" in line]
    assert lines == [
        "::warning file=p/msg/S.msg,line=1,title=RS200::"
        "RS200 p/msg/S.a: inline ignore of RS003 matches no finding"
    ]


def test_unused_suppressions_follow_configured_severity(tmp_path):
    stale = '[check.allow]\n"p/msg/S.a" = { reason = "stale" }\n'
    failing = _check(tmp_path / "w", "int32 a\n", "int32 a\n", stale, "--warnings-as-errors")
    assert failing.exit_code == 1
    assert "RS200" in failing.stdout

    off = _check(tmp_path / "o", "int32 a\n", "int32 a\n", '[check.rules]\nRS200 = "off"\n' + stale)
    assert off.exit_code == 0
    assert "RS200" not in off.stdout
