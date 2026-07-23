"""Shared test helpers for building temporary workspaces and git repos."""

from __future__ import annotations

import subprocess
from pathlib import Path

_PACKAGE_XML = """<?xml version="1.0"?>
<package format="3">
  <name>{name}</name>
  <version>0.0.0</version>
  <description>test package</description>
  <maintainer email="a@b.co">a</maintainer>
  <license>Apache-2.0</license>
</package>
"""


def write_package(
    root: Path,
    name: str,
    msgs: dict[str, str] | None = None,
    srvs: dict[str, str] | None = None,
    actions: dict[str, str] | None = None,
    dirname: str | None = None,
) -> Path:
    """Create a package directory with a package.xml and interface files.

    Args:
        root: Workspace root to create the package under.
        name: Package ``<name>`` written into package.xml.
        msgs/srvs/actions: Maps of interface name -> file body.
        dirname: Directory name if it should differ from ``name``.

    Returns:
        The created package directory.
    """
    pkg_dir = root / (dirname or name)
    pkg_dir.mkdir(parents=True, exist_ok=True)
    (pkg_dir / "package.xml").write_text(_PACKAGE_XML.format(name=name))
    for kind, entries in (("msg", msgs), ("srv", srvs), ("action", actions)):
        if not entries:
            continue
        d = pkg_dir / kind
        d.mkdir(exist_ok=True)
        for iface_name, body in entries.items():
            (d / f"{iface_name}.{kind}").write_text(body)
    return pkg_dir


def _git(cwd: Path, *args: str) -> None:
    subprocess.run(["git", "-C", str(cwd), *args], check=True, capture_output=True, text=True)


def make_git_repo(root: Path) -> Path:
    """Initialise an empty git repo with a deterministic identity."""
    root.mkdir(parents=True, exist_ok=True)
    _git(root, "init", "-q")
    _git(root, "config", "user.email", "test@example.com")
    _git(root, "config", "user.name", "test")
    _git(root, "config", "commit.gpgsign", "false")
    return root


def git_commit_all(repo: Path, message: str) -> None:
    """Stage everything and create a commit."""
    _git(repo, "add", "-A")
    _git(repo, "commit", "-q", "-m", message)
