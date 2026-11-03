"""Tests for the VFS backends."""

from __future__ import annotations

import subprocess

import pytest

from _helpers import git_commit_all, make_git_repo, set_git_identity, write_package
from roschema.vfs import GitTreeFS, RealFS, VfsError, _glob_to_regex, rev_parse_verify


def test_realfs_read_glob_exists(tmp_path):
    write_package(tmp_path, "pkg_a", msgs={"Foo": "int32 a\n"})
    fs = RealFS(tmp_path)
    assert fs.exists("pkg_a/package.xml")
    assert not fs.exists("pkg_a/nope")
    assert fs.glob("**/package.xml") == ["pkg_a/package.xml"]
    assert fs.read_text("pkg_a/msg/Foo.msg") == "int32 a\n"


def test_realfs_read_missing_raises_vfserror(tmp_path):
    with pytest.raises(VfsError):
        RealFS(tmp_path).read_text("does_not_exist.msg")


def test_loader_surfaces_vfserror_on_vanished_file(tmp_path):
    from roschema.discovery import discover
    from roschema.loader import load_interfaces

    write_package(tmp_path, "pkg_a", msgs={"Foo": "int32 a\n"})
    fs = RealFS(tmp_path)
    packages = discover(fs, ".")
    (tmp_path / "pkg_a" / "msg" / "Foo.msg").unlink()  # discovered, then gone
    with pytest.raises(VfsError):
        load_interfaces(fs, packages)


def test_glob_to_regex():
    rx = _glob_to_regex("**/package.xml")
    assert rx.match("package.xml")
    assert rx.match("a/b/package.xml")
    assert not rx.match("a/package.xml.bak")
    star = _glob_to_regex("msg/*.msg")
    assert star.match("msg/Foo.msg")
    assert not star.match("msg/sub/Foo.msg")


def test_gittreefs_lists_and_reads(tmp_path):
    repo = make_git_repo(tmp_path / "repo")
    write_package(repo, "pkg_a", msgs={"Foo": "int32 a\n"})
    git_commit_all(repo, "init")

    fs = GitTreeFS(repo, "HEAD")
    assert "pkg_a/package.xml" in fs.files
    assert fs.glob("**/*.msg") == ["pkg_a/msg/Foo.msg"]
    assert fs.read_text("pkg_a/msg/Foo.msg") == "int32 a\n"
    assert fs.exists("pkg_a/msg")
    assert not fs.exists("pkg_a/srv")


def test_gittreefs_reads_historical_content(tmp_path):
    repo = make_git_repo(tmp_path / "repo")
    write_package(repo, "pkg_a", msgs={"Foo": "int32 a\n"})
    git_commit_all(repo, "v1")
    (repo / "pkg_a" / "msg" / "Foo.msg").write_text("int32 a\nint32 b\n")
    git_commit_all(repo, "v2")

    old = GitTreeFS(repo, "HEAD~1")
    assert old.read_text("pkg_a/msg/Foo.msg") == "int32 a\n"
    new = GitTreeFS(repo, "HEAD")
    assert new.read_text("pkg_a/msg/Foo.msg") == "int32 a\nint32 b\n"


def _add_submodule(repo, sub, path):
    subprocess.run(
        ["git", "-C", str(repo), "-c", "protocol.file.allow=always", "submodule", "add",
         "-q", str(sub), path],
        check=True,
        capture_output=True,
    )


def test_gittreefs_reads_submodules_at_recorded_commit(tmp_path):
    sub = make_git_repo(tmp_path / "sub")
    write_package(sub, "pkg_b", msgs={"Bar": "int32 b\n"})
    git_commit_all(sub, "v1")
    repo = make_git_repo(tmp_path / "repo")
    _add_submodule(repo, sub, "vendor")
    git_commit_all(repo, "add submodule")
    set_git_identity(repo / "vendor")
    (repo / "vendor" / "pkg_b" / "msg" / "Bar.msg").write_text("int64 b\n")
    git_commit_all(repo / "vendor", "v2")  # moves the checkout, not the recorded commit

    fs = GitTreeFS(repo, "HEAD")
    assert fs.glob("**/*.msg") == ["vendor/pkg_b/msg/Bar.msg"]
    assert fs.read_text("vendor/pkg_b/msg/Bar.msg") == "int32 b\n"
    assert fs.missing_submodules == []


def test_gittreefs_reports_unavailable_submodule_commit(tmp_path):
    sub = make_git_repo(tmp_path / "sub")
    write_package(sub, "pkg_b", msgs={"Bar": "int32 b\n"})
    git_commit_all(sub, "v1")
    repo = make_git_repo(tmp_path / "repo")
    _add_submodule(repo, sub, "vendor")
    subprocess.run(
        ["git", "-C", str(repo), "update-index", "--cacheinfo", f"160000,{'1' * 40},vendor"],
        check=True,
    )
    subprocess.run(["git", "-C", str(repo), "commit", "-q", "-m", "unknown commit"], check=True)

    fs = GitTreeFS(repo, "HEAD")
    assert fs.files == [".gitmodules"]
    assert fs.missing_submodules == ["vendor"]


def test_gittreefs_bad_ref_raises(tmp_path):
    repo = make_git_repo(tmp_path / "repo")
    write_package(repo, "pkg_a", msgs={"Foo": "int32 a\n"})
    git_commit_all(repo, "init")
    with pytest.raises(VfsError):
        _ = GitTreeFS(repo, "no-such-ref").files


def test_rev_parse_verify(tmp_path):
    repo = make_git_repo(tmp_path / "repo")
    write_package(repo, "pkg_a", msgs={"Foo": "int32 a\n"})
    git_commit_all(repo, "init")
    sha = rev_parse_verify(repo, "HEAD")
    assert len(sha) == 40
    with pytest.raises(VfsError):
        rev_parse_verify(repo, "definitely-not-a-ref")
