"""Tests for discovery and target resolution."""

from __future__ import annotations

import pytest

from _helpers import git_commit_all, make_git_repo, write_package
from roschema.discovery import (
    apply_exclude,
    discover,
    discover_named,
    resolve_baseline,
    resolve_target,
)
from roschema.vfs import GitTreeFS, RealFS, VfsError


def test_discover_finds_interface_packages(tmp_path):
    write_package(tmp_path, "pkg_a", msgs={"Foo": "int32 a\n"}, srvs={"Do": "---\n"})
    write_package(tmp_path, "pkg_b", actions={"Move": "---\n---\n"})
    write_package(tmp_path, "plain_pkg")  # no interfaces -> skipped

    pkgs = discover(RealFS(tmp_path), ".")
    assert [p.name for p in pkgs] == ["pkg_a", "pkg_b"]
    a = pkgs[0]
    assert {(r.kind, r.name) for r in a.interfaces} == {("msg", "Foo"), ("srv", "Do")}
    assert a.interfaces[0].key == "pkg_a/msg/Foo"


@pytest.mark.parametrize("marker", ["COLCON_IGNORE", "AMENT_IGNORE"])
@pytest.mark.parametrize("root", [".", "build", "build/nested"])
def test_discover_skips_ignored_trees(tmp_path, marker, root):
    write_package(tmp_path / "src", "pkg_a", msgs={"Foo": "int32 a\n"})
    build = tmp_path / "build"
    write_package(build / "nested", "generated", msgs={"Foo": "int32 a\n"})
    (build / marker).touch()
    broken = build / "nested" / "broken"
    broken.mkdir()
    (broken / "package.xml").symlink_to(tmp_path / "missing.xml")

    pkgs = discover(RealFS(tmp_path), root)
    assert [p.name for p in pkgs] == (["pkg_a"] if root == "." else [])


def test_discover_skips_ignored_vfs_root(tmp_path):
    write_package(tmp_path, "pkg_a", msgs={"Foo": "int32 a\n"})
    (tmp_path / "COLCON_IGNORE").touch()
    assert discover(RealFS(tmp_path)) == ()


def test_discover_skips_ignored_git_tree(tmp_path):
    repo = make_git_repo(tmp_path / "repo")
    write_package(repo / "src", "pkg_a", msgs={"Foo": "int32 a\n"})
    write_package(repo / "ignored", "pkg_b", msgs={"Foo": "int32 a\n"})
    (repo / "ignored" / "COLCON_IGNORE").touch()
    git_commit_all(repo, "init")

    assert [p.name for p in discover(GitTreeFS(repo, "HEAD"))] == ["pkg_a"]


def test_discover_uses_package_xml_name_over_dir(tmp_path):
    write_package(tmp_path, "real_name", msgs={"Foo": "int32 a\n"}, dirname="other_dir")
    (pkg,) = discover(RealFS(tmp_path), ".")
    assert pkg.name == "real_name"
    assert pkg.path == "other_dir"


def test_discover_over_git_tree(tmp_path):
    repo = make_git_repo(tmp_path / "repo")
    write_package(repo, "pkg_a", msgs={"Foo": "int32 a\n"})
    git_commit_all(repo, "init")
    pkgs = discover(GitTreeFS(repo, "HEAD"), ".")
    assert [p.name for p in pkgs] == ["pkg_a"]
    assert pkgs[0].interfaces[0].path == "pkg_a/msg/Foo.msg"


def test_discover_named(tmp_path):
    share = tmp_path / "share" / "my_msgs"
    write_package(tmp_path / "share", "my_msgs", msgs={"Foo": "int32 a\n"})
    # emulate ament layout rooted at share/my_msgs
    (pkg,) = discover_named(RealFS(share), "my_msgs", ".")
    assert pkg.name == "my_msgs"
    assert pkg.interfaces[0].key == "my_msgs/msg/Foo"


def test_apply_exclude(tmp_path):
    write_package(tmp_path, "pkg_a", msgs={"Foo": "int32 a\n", "Bar": "int32 b\n"})
    write_package(tmp_path, "pkg_b", msgs={"Baz": "int32 c\n"})
    pkgs = discover(RealFS(tmp_path), ".")

    no_b = apply_exclude(pkgs, ["pkg_b"])
    assert [p.name for p in no_b] == ["pkg_a"]

    no_foo = apply_exclude(pkgs, ["pkg_a/msg/Foo"])
    a = next(p for p in no_foo if p.name == "pkg_a")
    assert {r.name for r in a.interfaces} == {"Bar"}


def test_resolve_target_none_is_workspace(tmp_path):
    write_package(tmp_path, "pkg_a", msgs={"Foo": "int32 a\n"})
    res = resolve_target(None, cwd=tmp_path)
    assert res.source.startswith("workspace:")
    assert [p.name for p in res.packages] == ["pkg_a"]


def test_resolve_target_path(tmp_path):
    write_package(tmp_path / "ws", "pkg_a", msgs={"Foo": "int32 a\n"})
    res = resolve_target("ws", cwd=tmp_path)
    assert res.source.startswith("path:")
    assert [p.name for p in res.packages] == ["pkg_a"]


def test_resolve_target_ament(tmp_path, monkeypatch):
    prefix = tmp_path / "install"
    write_package(prefix / "share", "my_msgs", msgs={"Foo": "int32 a\n"})
    monkeypatch.setenv("AMENT_PREFIX_PATH", str(prefix))
    res = resolve_target("my_msgs", cwd=tmp_path)
    assert res.source == f"ament:{prefix}"
    assert res.packages[0].name == "my_msgs"


def test_resolve_target_unresolvable(tmp_path, monkeypatch):
    monkeypatch.setenv("AMENT_PREFIX_PATH", "")
    with pytest.raises(VfsError):
        resolve_target("nonexistent_pkg", cwd=tmp_path)


def test_resolve_target_glob(tmp_path):
    write_package(tmp_path / "src", "a", msgs={"A": "int32 x\n"})
    write_package(tmp_path / "src" / "nested", "b", msgs={"B": "int32 y\n"})
    write_package(tmp_path, "c", msgs={"C": "int32 z\n"})  # outside src/
    res = resolve_target("src/**", cwd=tmp_path)
    assert res.source.startswith("glob:")
    assert {p.name for p in res.packages} == {"a", "b"}  # c not matched


def test_resolve_target_glob_empty_is_error(tmp_path):
    with pytest.raises(VfsError):
        resolve_target("nope/**", cwd=tmp_path)


def test_resolve_baseline_absolute_path_bypasses_git(tmp_path):
    repo = make_git_repo(tmp_path / "repo")  # a git repo exists, so refs resolve
    write_package(repo, "m", msgs={"P": "float32 x\n"})
    git_commit_all(repo, "c1")
    ext = tmp_path / "ext"
    write_package(ext, "m", msgs={"P": "float32 x\n"})
    # an absolute path is treated as a directory, never a git ref
    res = resolve_baseline(str(ext), repo)
    assert res.source.startswith("path:")


def test_resolve_baseline_dotslash_missing_dir_errors(tmp_path):
    repo = make_git_repo(tmp_path / "repo")
    write_package(repo, "m", msgs={"P": "float32 x\n"})
    git_commit_all(repo, "c1")
    with pytest.raises(VfsError):
        resolve_baseline("./nope", repo)  # explicit path form, does not fall back to git
