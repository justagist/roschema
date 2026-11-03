"""Integration tests for `roschema check`."""

from __future__ import annotations

import json
import shutil
import subprocess
import sys

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


def test_check_warnings_as_errors_fails_on_warning(tmp_path):
    write_package(tmp_path / "old", "my_msgs", msgs={"S": "uint8[<=4] a\n"})
    write_package(tmp_path / "new", "my_msgs", msgs={"S": "uint8[<=9] a\n"})
    result = runner.invoke(
        app,
        [
            "check",
            str(tmp_path / "new"),
            "--against",
            str(tmp_path / "old"),
            "--warnings-as-errors",
        ],
    )
    assert result.exit_code == 1
    assert "RS008 warn" in result.stdout


def test_check_reports_coverage(tmp_path):
    write_package(tmp_path / "old", "my_msgs", msgs={"A": "int32 a\n", "B": "int32 b\n"})
    write_package(tmp_path / "new", "my_msgs", msgs={"A": "int32 a\n", "C": "int32 c\n"})
    write_package(tmp_path / "new", "other_msgs", msgs={"D": "int32 d\n"})
    result = runner.invoke(
        app, ["check", str(tmp_path / "new"), "--against", str(tmp_path / "old")]
    )
    assert (
        "compared 1 interface(s) in 2 package(s); 2 only in the target, 1 only in the baseline"
        in result.stdout
    )


def test_check_empty_baseline_is_an_error(tmp_path):
    repo = make_git_repo(tmp_path / "repo")
    (repo / "README").write_text("no interfaces yet\n")
    git_commit_all(repo, "v1")
    write_package(repo, "my_msgs", msgs={"Pose": "float32 theta\n"})

    result = runner.invoke(app, ["check", str(repo), "--against", "HEAD"])
    assert result.exit_code == 2
    assert "the baseline (git:HEAD) has no interfaces" in result.output

    allowed = runner.invoke(app, ["check", str(repo), "--against", "HEAD", "--allow-empty"])
    assert allowed.exit_code == 0
    assert "compared 0 interface(s) in 1 package(s); 1 only in the target" in allowed.stdout


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

    result = runner.invoke(app, ["check", str(repo), "--against", "HEAD", "--format", "github"])
    assert result.exit_code == 1
    assert "file=src/pkg/msg/A.msg" in result.stdout  # VFS-relative already full


def test_github_unlocated_findings_use_interface_file(tmp_path):
    repo = make_git_repo(tmp_path / "repo")
    write_package(repo / "src", "pkg", msgs={"A": "int32 a\nint32 b\nint32 c\n"})
    git_commit_all(repo, "v1")
    (repo / "src" / "pkg" / "msg" / "A.msg").write_text("int32 b\nint32 a\n")

    result = runner.invoke(
        app, ["check", str(repo / "src" / "pkg"), "--against", "HEAD", "--format", "github"]
    )
    assert result.exit_code == 1
    annotations = [line for line in result.stdout.splitlines() if line.startswith("::")]
    lines = {line.split("::")[1].split(",title=")[1]: line for line in annotations}
    assert lines["RS001"].startswith("::error file=src/pkg/msg/A.msg,title=RS001::")
    assert lines["RS004"].startswith("::error file=src/pkg/msg/A.msg,title=RS004::")


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


def test_check_package_name_uses_workspace_source(tmp_path, monkeypatch):
    """A package name must compare its source, not an installed copy, with the baseline."""
    repo = make_git_repo(tmp_path / "repo")
    write_package(repo / "src", "my_msgs", msgs={"P": "float32 x\n"})
    git_commit_all(repo, "v1")
    install = repo / "install"
    write_package(install / "share", "my_msgs", msgs={"P": "float32 x\n"})
    (install / "COLCON_IGNORE").touch()
    (repo / "src" / "my_msgs" / "msg" / "P.msg").write_text("float64 x\n")
    monkeypatch.setenv("AMENT_PREFIX_PATH", str(install))
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["check", "my_msgs", "--against", "HEAD"])
    assert result.exit_code == 1
    assert "RS003" in result.output
    assert "installed copy" not in result.output


def test_check_package_name_from_ament_warns(tmp_path, monkeypatch):
    install = tmp_path / "install"
    write_package(install / "share", "my_msgs", msgs={"P": "float32 x\n"})
    (tmp_path / "elsewhere").mkdir()
    monkeypatch.setenv("AMENT_PREFIX_PATH", str(install))
    monkeypatch.chdir(tmp_path / "elsewhere")

    result = runner.invoke(app, ["ls", "my_msgs"])
    assert result.exit_code == 0
    assert "is not a source package under the working directory; using the installed" in (
        result.output
    )


def test_check_from_superproject_compares_submodule_packages(tmp_path, monkeypatch):
    sub = make_git_repo(tmp_path / "sub")
    write_package(sub, "my_msgs", msgs={"P": "float32 x\n"})
    git_commit_all(sub, "v1")
    repo = make_git_repo(tmp_path / "repo")
    subprocess.run(
        [
            "git",
            "-C",
            str(repo),
            "-c",
            "protocol.file.allow=always",
            "submodule",
            "add",
            "-q",
            str(sub),
            "src/vendor",
        ],
        check=True,
        capture_output=True,
    )
    git_commit_all(repo, "add submodule")
    (repo / "src" / "vendor" / "my_msgs" / "msg" / "P.msg").write_text("float64 x\n")
    monkeypatch.chdir(repo)

    result = runner.invoke(app, ["check", "--against", "HEAD"])
    assert result.exit_code == 1
    assert "RS003" in result.output


def test_text_output_keeps_long_lines_whole(tmp_path):
    """Non-terminal output (CI logs) must not split paths across lines."""
    deep = tmp_path / ("nested_directory_" * 6)
    write_package(deep / "old", "my_msgs", msgs={"Pose": "float32 theta\n"})
    write_package(deep / "new", "my_msgs", msgs={"Pose": "float64 theta\n"})
    result = runner.invoke(app, ["check", str(deep / "new"), "--against", str(deep / "old")])
    assert f"checking path:{deep / 'new'}  against  path:{deep / 'old'}" in result.stdout


def test_commands_never_use_the_locale_encoding(tmp_path):
    """Non-ASCII comments must work regardless of locale (e.g. cp1252 on Windows)."""
    repo = make_git_repo(tmp_path / "repo")
    write_package(repo, "my_msgs", msgs={"P": "float64 x  # metres, ±0.5 °\n"})
    git_commit_all(repo, "v1")
    (repo / "my_msgs" / "msg" / "P.msg").write_text("float64  x  # metres, ±0.5 °\n", "utf-8")
    lock = tmp_path / "roschema.lock"
    for args in (
        ["check", "--against", "HEAD"],
        ["lint"],
        ["fmt"],
        ["freeze", "-o", str(lock)],
        ["check", "--against", str(lock)],
    ):
        result = subprocess.run(
            [
                sys.executable,
                "-X",
                "warn_default_encoding",
                "-W",
                "error::EncodingWarning",
                "-m",
                "roschema.cli",
                *args,
            ],
            cwd=repo,
            capture_output=True,
            text=True,
            encoding="utf-8",
        )
        assert result.returncode == 0, (args, result.stderr)


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
    result = runner.invoke(app, ["check", str(tmp_path / "new"), "--against", "baseline.mcap"])
    assert result.exit_code == 2  # file does not exist


def test_check_mixed_bound_changes_fail(tmp_path):
    old, new = tmp_path / "old", tmp_path / "new"
    write_package(old, "my_msgs", msgs={"T": "string<=64[<=4] names\n"})
    write_package(new, "my_msgs", msgs={"T": "string<=8[<=16] names\n"})
    result = runner.invoke(app, ["check", str(new), "--against", str(old)])
    assert result.exit_code == 1
    assert "RS007" in result.stdout


@pytest.mark.parametrize(
    "pattern,delete_all,workspace,removed",
    [
        ("src/**", False, ".", {"a"}),
        ("src/**", True, ".", {"a", "b"}),
        ("src/*", False, ".", {"a"}),
        ("./src/[ab]*", False, ".", {"a"}),
        ("src/**", True, "nested", {"a", "b"}),
    ],
)
def test_glob_reports_deleted_packages(
    tmp_path, monkeypatch, pattern, delete_all, workspace, removed
):
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
    assert {f["package"] for f in findings} == removed
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


def test_direct_package_check_inherits_workspace_config(tmp_path, monkeypatch):
    repo = make_git_repo(tmp_path / "repo")
    pkg = write_package(repo / "src", "demo", msgs={"T": "int32 x\n"})
    (repo / "roschema.toml").write_text('[check.rules]\nRS003 = "warn"\n')
    git_commit_all(repo, "baseline")
    (pkg / "msg" / "T.msg").write_text("float64 x\n")
    monkeypatch.chdir(repo)
    for target in [str(repo), str(pkg)]:
        result = runner.invoke(app, ["check", target, "--against", "HEAD", "--format", "json"])
        assert result.exit_code == 0
        findings = json.loads(result.stdout)["findings"]
        assert [(f["rule"], f["severity"]) for f in findings] == [("RS003", "warn")]


def test_deleted_last_interface_keeps_package_config(tmp_path):
    """A package's removal rules still apply after its last interface is deleted."""
    repo = make_git_repo(tmp_path / "repo")
    pkg = write_package(repo / "src", "demo", msgs={"T": "int32 x\n"})
    (pkg / "roschema.toml").write_text('[check.rules]\nRS040 = "warn"\n')
    git_commit_all(repo, "baseline")
    (pkg / "msg" / "T.msg").unlink()
    result = runner.invoke(app, ["check", str(pkg), "--against", "HEAD", "--format", "json"])
    assert result.exit_code == 0, result.output
    findings = json.loads(result.stdout)["findings"]
    assert [(f["rule"], f["severity"]) for f in findings] == [("RS040", "warn")]


@pytest.mark.parametrize("baseline", ["git", "directory"])
@pytest.mark.parametrize("pattern", ["src/nested/../*", "src/*/../*", "src/missing*/../*"])
def test_glob_parent_traversal_preserves_deletion_scope(tmp_path, monkeypatch, baseline, pattern):
    """Match traversal through existing glob directories on each baseline independently."""
    old = make_git_repo(tmp_path / "old")
    for name in ("gone", "survivor"):
        write_package(old / "src", name, msgs={"T": "int32 x\n"})
    write_package(old / "outside", "other", msgs={"T": "int32 x\n"})
    (old / "src" / "nested").mkdir()
    (old / "src" / "nested" / "keep").touch()
    git_commit_all(old, "baseline")
    new = tmp_path / "new"
    shutil.copytree(old, new)
    shutil.rmtree(new / "src" / "gone")
    shutil.rmtree(new / "outside")
    monkeypatch.chdir(new)
    against = "HEAD" if baseline == "git" else str(old)
    result = runner.invoke(app, ["check", pattern, "--against", against, "--format", "json"])
    if "missing" in pattern:
        assert result.exit_code == 2
        assert "matched no interface packages" in result.output
    else:
        assert result.exit_code == 1, result.output
        findings = json.loads(result.stdout)["findings"]
        assert [(f["package"], f["rule"]) for f in findings] == [("gone", "RS040")]
