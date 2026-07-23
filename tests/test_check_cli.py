"""Integration tests for `roschema check`."""

from __future__ import annotations

from typer.testing import CliRunner

from _helpers import git_commit_all, make_git_repo, write_package
from roschema.cli import app

runner = CliRunner()


def test_check_against_directory_reports_and_exits_1(tmp_path):
    write_package(tmp_path / "old", "my_msgs", msgs={"Pose": "float32 theta\nint32 a\n"})
    write_package(tmp_path / "new", "my_msgs", msgs={"Pose": "float64 theta\n"})
    result = runner.invoke(
        app, ["check", str(tmp_path / "new"), "--against", str(tmp_path / "old")]
    )
    assert result.exit_code == 1
    assert "RS003" in result.stdout  # theta type changed
    assert "RS001" in result.stdout  # a removed


def test_check_against_git_ref(tmp_path):
    repo = make_git_repo(tmp_path / "repo")
    write_package(repo, "my_msgs", msgs={"Pose": "float32 theta\n"})
    git_commit_all(repo, "v1")
    (repo / "my_msgs" / "msg" / "Pose.msg").write_text("float64 theta\n")
    git_commit_all(repo, "v2")

    result = runner.invoke(app, ["check", str(repo), "--against", "HEAD~1"])
    assert result.exit_code == 1
    assert "RS003" in result.stdout


def test_check_clean_exits_0(tmp_path):
    write_package(tmp_path / "old", "my_msgs", msgs={"Pose": "float32 theta\n"})
    write_package(tmp_path / "new", "my_msgs", msgs={"Pose": "float32 theta\n"})
    result = runner.invoke(
        app, ["check", str(tmp_path / "new"), "--against", str(tmp_path / "old")]
    )
    assert result.exit_code == 0
    assert "no breaking changes" in result.stdout


def test_check_warning_only_exits_0(tmp_path):
    write_package(tmp_path / "old", "my_msgs", msgs={"S": "uint8[<=4] a\n"})
    write_package(tmp_path / "new", "my_msgs", msgs={"S": "uint8[<=9] a\n"})
    result = runner.invoke(
        app, ["check", str(tmp_path / "new"), "--against", str(tmp_path / "old")]
    )
    assert result.exit_code == 0  # RS008 is a warning
    assert "RS008" in result.stdout


def test_check_exit_zero_flag(tmp_path):
    write_package(tmp_path / "old", "my_msgs", msgs={"Pose": "float32 theta\n"})
    write_package(tmp_path / "new", "my_msgs", msgs={"Pose": "float64 theta\n"})
    result = runner.invoke(
        app,
        ["check", str(tmp_path / "new"), "--against", str(tmp_path / "old"), "--exit-zero"],
    )
    assert result.exit_code == 0
    assert "RS003" in result.stdout


def test_check_unknown_format_exits_2(tmp_path):
    write_package(tmp_path / "old", "my_msgs", msgs={"Pose": "float32 t\n"})
    write_package(tmp_path / "new", "my_msgs", msgs={"Pose": "float32 t\n"})
    result = runner.invoke(
        app,
        ["check", str(tmp_path / "new"), "--against", str(tmp_path / "old"), "--format", "xml"],
    )
    assert result.exit_code == 2


def test_check_mcap_baseline_not_supported(tmp_path):
    write_package(tmp_path / "new", "my_msgs", msgs={"Pose": "float32 t\n"})
    result = runner.invoke(
        app, ["check", str(tmp_path / "new"), "--against", "baseline.mcap"]
    )
    assert result.exit_code == 2
