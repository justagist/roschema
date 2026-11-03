"""Integration tests for `roschema check`."""

from __future__ import annotations

import json
import shutil
import subprocess

import pytest
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


def test_github_annotation_paths_are_repo_relative(tmp_path):
    repo = make_git_repo(tmp_path / "repo")
    write_package(repo / "src", "pkg", msgs={"A": "float32 x\n"})  # package at src/pkg
    git_commit_all(repo, "v1")
    (repo / "src" / "pkg" / "msg" / "A.msg").write_text("float64 x\n")

    # target is the subdirectory: the annotation path must be repo-root-relative
    result = runner.invoke(
        app, ["check", str(repo / "src" / "pkg"), "--against", "HEAD", "--format", "github"]
    )
    assert result.exit_code == 1
    assert "file=src/pkg/msg/A.msg" in result.stdout


def test_github_no_prefix_at_repo_root(tmp_path):
    repo = make_git_repo(tmp_path / "repo")
    write_package(repo / "src", "pkg", msgs={"A": "float32 x\n"})
    git_commit_all(repo, "v1")
    (repo / "src" / "pkg" / "msg" / "A.msg").write_text("float64 x\n")

    result = runner.invoke(
        app, ["check", str(repo), "--against", "HEAD", "--format", "github"]
    )
    assert result.exit_code == 1
    assert "file=src/pkg/msg/A.msg" in result.stdout  # VFS-relative already full


def test_json_paths_stay_vfs_relative(tmp_path):
    repo = make_git_repo(tmp_path / "repo")
    write_package(repo / "src", "pkg", msgs={"A": "float32 x\n"})
    git_commit_all(repo, "v1")
    (repo / "src" / "pkg" / "msg" / "A.msg").write_text("float64 x\n")

    result = runner.invoke(
        app, ["check", str(repo / "src" / "pkg"), "--against", "HEAD", "--format", "json"]
    )
    data = json.loads(result.stdout)
    assert data["findings"][0]["new"]["file"] == "msg/A.msg"  # unchanged by prefixing


def test_check_glob_target_two_depths(tmp_path, monkeypatch):
    repo = make_git_repo(tmp_path / "repo")
    write_package(repo / "src", "a", msgs={"A": "float32 x\n"})
    write_package(repo / "src" / "nested", "b", msgs={"B": "float32 y\n"})
    git_commit_all(repo, "v1")
    (repo / "src" / "a" / "msg" / "A.msg").write_text("float64 x\n")
    (repo / "src" / "nested" / "b" / "msg" / "B.msg").write_text("float64 y\n")
    git_commit_all(repo, "v2")
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["check", "src/**", "--against", "HEAD~1"])
    assert result.exit_code == 1
    assert "a/msg/A.x" in result.stdout
    assert "b/msg/B.y" in result.stdout  # matched at a deeper level


def test_check_glob_scopes_out_unmatched_packages(tmp_path, monkeypatch):
    write_package(tmp_path / "new" / "src", "a", msgs={"A": "float64 x\n"})  # changed
    write_package(tmp_path / "old", "a", msgs={"A": "float32 x\n"})
    write_package(tmp_path / "old", "b", msgs={"B": "int32 y\n"})  # only in baseline
    monkeypatch.chdir(tmp_path / "new")

    result = runner.invoke(
        app, ["check", "src/*", "--against", str(tmp_path / "old"), "--format", "json"]
    )
    assert result.exit_code == 1
    data = json.loads(result.stdout)
    packages = {f["package"] for f in data["findings"]}
    assert packages == {"a"}  # b is out of the glob scope, not reported as removed


def test_baseline_git_ref_shadows_dir_with_note(tmp_path, monkeypatch):
    repo = make_git_repo(tmp_path / "repo")
    write_package(repo / "pkgs", "m", msgs={"P": "float32 x\n"})
    git_commit_all(repo, "c1")
    subprocess.run(["git", "-C", str(repo), "branch", "snap"], check=True)
    (repo / "pkgs" / "m" / "msg" / "P.msg").write_text("float64 x\n")
    (repo / "snap").mkdir()  # a directory colliding with the ref name
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["check", "pkgs/m", "--against", "snap"])
    assert result.exit_code == 1
    assert "RS003" in result.output  # the git ref won (baseline order)
    assert "note:" in result.output  # shadow diagnostic printed


def test_baseline_dotslash_uses_directory(tmp_path, monkeypatch):
    new = tmp_path / "new"
    write_package(new, "m", msgs={"P": "float64 x\n"})
    base = tmp_path / "base"
    write_package(base, "m", msgs={"P": "float32 x\n"})
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["check", str(new), "--against", "./base"])
    assert result.exit_code == 1
    assert "RS003" in result.stdout


def test_check_missing_mcap_baseline_errors(tmp_path):
    write_package(tmp_path / "new", "my_msgs", msgs={"Pose": "float32 t\n"})
    result = runner.invoke(
        app, ["check", str(tmp_path / "new"), "--against", "baseline.mcap"]
    )
    assert result.exit_code == 2  # file does not exist


def test_check_mixed_bound_changes_fail(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    write_package(old, "my_msgs", msgs={"T": "string<=64[<=4] names\n"})
    write_package(new, "my_msgs", msgs={"T": "string<=8[<=16] names\n"})
    result = runner.invoke(app, ["check", str(new), "--against", str(old)])
    assert result.exit_code == 1
    assert "RS007" in result.stdout


@pytest.mark.parametrize("workspace", [".", "nested"])
@pytest.mark.parametrize("pattern", ["src/**", "src/*", "./src/[ab]*"])
@pytest.mark.parametrize("delete_all", [False, True])
def test_glob_reports_deleted_packages(tmp_path, monkeypatch, pattern, delete_all, workspace):
    repo = make_git_repo(tmp_path / "repo")
    base = repo / workspace
    write_package(base / "src", "a", msgs={"A": "int32 x\n"})
    write_package(base / "src" / "nested", "b", msgs={"B": "int32 y\n"})
    write_package(base / "outside", "other", msgs={"T": "int32 z\n"})
    git_commit_all(repo, "baseline")
    shutil.rmtree(base / "src" / "a")
    shutil.rmtree(base / "outside")
    if delete_all:
        shutil.rmtree(base / "src")
    monkeypatch.chdir(base)

    result = runner.invoke(app, ["check", pattern, "--against", "HEAD", "--format", "json"])
    assert result.exit_code == 1, result.output
    findings = json.loads(result.stdout)["findings"]
    assert {f["package"] for f in findings} == (
        {"a", "b"} if delete_all and "[ab]" not in pattern else {"a"}
    )
    assert {f["rule"] for f in findings} == {"RS040"}


def test_glob_without_matches_on_either_side_is_error(tmp_path, monkeypatch):
    repo = make_git_repo(tmp_path / "repo")
    write_package(repo, "other", msgs={"T": "int32 z\n"})
    git_commit_all(repo, "baseline")
    monkeypatch.chdir(repo)
    result = runner.invoke(app, ["check", "src/**", "--against", "HEAD"])
    assert result.exit_code == 2
    assert "matched no interface packages" in result.output


def test_glob_reports_deletion_in_directory_baseline(tmp_path, monkeypatch):
    old, new = tmp_path / "old", tmp_path / "new"
    write_package(old / "src", "gone", msgs={"T": "int32 x\n"})
    write_package(old / "outside", "other", msgs={"T": "int32 x\n"})
    new.mkdir()
    monkeypatch.chdir(new)
    result = runner.invoke(app, ["check", "src/**", "--against", str(old)])
    assert result.exit_code == 1
    assert "gone/msg/T" in result.stdout
    assert "other/msg/T" not in result.stdout
