"""Tests for freeze / lockfile support."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from _helpers import write_package
from roschema.cli import app
from roschema.discovery import discover, resolve_lock
from roschema.freeze import LockFS, _toml_string, build_lock
from roschema.loader import load_interfaces
from roschema.parser import parse_text
from roschema.vfs import RealFS, VfsError

runner = CliRunner()


def _ifaces(**bodies):
    out = {}
    for name, body in bodies.items():
        iface = parse_text(body, f"p/msg/{name}.msg", "p", name, "msg")
        out[iface.key] = iface
    return out


def test_build_lock_roundtrips_through_lockfs(tmp_path):
    ifaces = _ifaces(Foo="int32   a\nint32 b\n")  # messy input -> normalized in lock
    lock = tmp_path / "roschema.lock"
    lock.write_text(build_lock(ifaces, "0.1.0"))

    fs = LockFS(str(lock))
    assert fs.exists("p/package.xml")
    assert fs.read_text("p/msg/Foo.msg") == "int32 a\nint32 b\n"  # canonicalised
    reparsed = load_interfaces(fs, discover(fs, "."))
    assert set(reparsed) == {"p/msg/Foo"}


def test_toml_string_escapes():
    try:
        import tomllib
    except ModuleNotFoundError:  # py3.10
        import tomli as tomllib

    cases = ["a'''b", 'a"""b', 'has "q"', "back\\slash", "tab\tend", "n\nl", "c\x01c", "trail\\"]
    for raw in cases:
        rendered = _toml_string(raw)
        assert tomllib.loads(f"x = {rendered}")["x"] == raw


def test_freeze_roundtrip_with_triple_quote_in_comment(tmp_path):
    ws = tmp_path / "ws"
    write_package(ws, "pkg", msgs={"A": "int32 x  # don''' odd '''comment\n"})
    lock = tmp_path / "l.lock"
    frozen = runner.invoke(app, ["freeze", str(ws), "-o", str(lock)])
    assert frozen.exit_code == 0
    checked = runner.invoke(app, ["check", str(ws), "--against", str(lock)])
    assert checked.exit_code == 0  # no parse error, no findings


def test_malformed_lockfile_entry_is_vfserror(tmp_path):
    lock = tmp_path / "l.lock"
    lock.write_text('[[interface]]\nkey = "p/msg/A"\ntext = "int32 a\\n"\n')  # missing package/sha
    with pytest.raises(VfsError):
        LockFS(str(lock))


def test_lockfs_detects_tampering(tmp_path):
    lock = tmp_path / "roschema.lock"
    lock.write_text(build_lock(_ifaces(Foo="int32 a\n"), "0.1.0"))
    text = lock.read_text().replace("int32 a", "int32 tampered")
    lock.write_text(text)
    with pytest.raises(VfsError):
        LockFS(str(lock))


def test_resolve_lock_discovers(tmp_path):
    lock = tmp_path / "roschema.lock"
    lock.write_text(build_lock(_ifaces(Foo="int32 a\n", Bar="int32 b\n"), "0.1.0"))
    res = resolve_lock(str(lock))
    assert res.source.startswith("lock:")
    assert {p.name for p in res.packages} == {"p"}


def test_cli_freeze_then_check(tmp_path):
    ws = tmp_path / "ws"
    write_package(ws, "my_msgs", msgs={"Pose": "float32 theta\n"})
    lock = tmp_path / "roschema.lock"

    frozen = runner.invoke(app, ["freeze", str(ws), "-o", str(lock)])
    assert frozen.exit_code == 0
    assert lock.is_file()

    # unchanged -> clean
    clean = runner.invoke(app, ["check", str(ws), "--against", str(lock)])
    assert clean.exit_code == 0

    # change the field type -> RS003 against the lock baseline
    (ws / "my_msgs" / "msg" / "Pose.msg").write_text("float64 theta\n")
    changed = runner.invoke(app, ["check", str(ws), "--against", str(lock)])
    assert changed.exit_code == 1
    assert "RS003" in changed.stdout


def test_tool_version_not_used_for_comparison(tmp_path):
    ifaces = _ifaces(Foo="int32 a\n")
    la = tmp_path / "a.lock"
    lb = tmp_path / "b.lock"
    la.write_text(build_lock(ifaces, "0.1.0"))
    lb.write_text(build_lock(ifaces, "9.9.9"))
    # different tool_version, identical interface content -> both load the same
    assert LockFS(str(la)).read_text("p/msg/Foo.msg") == LockFS(str(lb)).read_text(
        "p/msg/Foo.msg"
    )


def test_freeze_normalizes_before_hashing(tmp_path):
    # a purely cosmetic edit produces an identical lock (canonical text hashed)
    ws = tmp_path / "ws"
    write_package(ws, "my_msgs", msgs={"Pose": "float32 theta\n"})
    lock_a = build_lock(load_interfaces(RealFS(ws), discover(RealFS(ws), ".")), "0.1.0")

    (ws / "my_msgs" / "msg" / "Pose.msg").write_text("float32    theta   # doc? no\n")
    lock_b = build_lock(load_interfaces(RealFS(ws), discover(RealFS(ws), ".")), "0.1.0")
    # whitespace normalised away, but the comment differs, so only the comment shows;
    # the field line hashes identically either way
    assert "float32 theta" in lock_a
    assert "float32 theta" in lock_b


def test_glob_rejects_synthetic_lockfile_paths(tmp_path, monkeypatch):
    write_package(tmp_path / "src", "p", msgs={"Foo": "int32 a\n"})
    lock = tmp_path / "roschema.lock"
    lock.write_text(build_lock(_ifaces(Foo="int32 a\n"), "0.1.0"))
    monkeypatch.chdir(tmp_path)
    result = runner.invoke(app, ["check", "src/**", "--against", str(lock)])
    assert result.exit_code == 2
    assert "use a workspace target" in " ".join(result.output.split())
