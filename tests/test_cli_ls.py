"""Tests for the `roschema ls` command."""

from __future__ import annotations

import json

from typer.testing import CliRunner

from _helpers import write_package
from roschema.cli import app

runner = CliRunner()


def test_ls_text(tmp_path):
    write_package(tmp_path, "pkg_a", msgs={"Foo": "int32 a\n"})
    result = runner.invoke(app, ["ls", str(tmp_path)])
    assert result.exit_code == 0
    assert "pkg_a" in result.stdout
    assert "Foo" in result.stdout
    assert "source:" in result.stdout


def test_ls_json(tmp_path):
    write_package(tmp_path, "pkg_a", msgs={"Foo": "int32 a\n"}, srvs={"Do": "---\n"})
    result = runner.invoke(app, ["ls", str(tmp_path), "--json"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert data["packages"][0]["name"] == "pkg_a"
    kinds = {i["kind"] for i in data["packages"][0]["interfaces"]}
    assert kinds == {"msg", "srv"}


def test_ls_exclude(tmp_path):
    write_package(tmp_path, "pkg_a", msgs={"Foo": "int32 a\n"})
    write_package(tmp_path, "pkg_b", msgs={"Bar": "int32 b\n"})
    result = runner.invoke(app, ["ls", str(tmp_path), "--json", "--exclude", "pkg_b"])
    assert result.exit_code == 0
    data = json.loads(result.stdout)
    assert [p["name"] for p in data["packages"]] == ["pkg_a"]


def test_ls_unresolvable_target_exits_2(tmp_path, monkeypatch):
    monkeypatch.setenv("AMENT_PREFIX_PATH", "")
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["ls", "nope_pkg"])
    assert result.exit_code == 2
