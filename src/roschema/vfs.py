"""Virtual filesystem abstraction.

Discovery and parsing operate only through the :class:`VFS` protocol, so the
same code serves the working tree, a git baseline and (later) an MCAP bag
without any special-casing.
"""

from __future__ import annotations

import posixpath
import re
import subprocess
from fnmatch import fnmatchcase, translate
from pathlib import Path
from typing import Protocol, runtime_checkable


class VfsError(Exception):
    """Raised when a filesystem/source backend cannot satisfy a request."""


@runtime_checkable
class VFS(Protocol):
    """Minimal read-only filesystem interface.

    All paths are POSIX-style and relative to the backend's conceptual root.
    """

    def read_text(self, path: str) -> str:
        """Return the text contents of ``path``."""
        ...

    def glob(self, pattern: str) -> list[str]:
        """Return paths matching a glob ``pattern`` (``**`` spans directories)."""
        ...

    def exists(self, path: str) -> bool:
        """Return whether ``path`` exists (as a file or directory)."""
        ...


class RealFS:
    """VFS backed by the real filesystem, rooted at a base directory."""

    def __init__(self, root: str | Path) -> None:
        self.root = Path(root)

    def read_text(self, path: str) -> str:
        try:
            return (self.root / path).read_text(encoding="utf-8")
        except OSError as exc:
            raise VfsError(f"cannot read {path}: {exc}") from exc

    def glob(self, pattern: str) -> list[str]:
        """Return canonical paths even when the pattern traverses parent directories."""
        return sorted(
            {
                posixpath.normpath(p.relative_to(self.root).as_posix())
                for p in self.root.glob(pattern)
            }
        )

    def exists(self, path: str) -> bool:
        return (self.root / path).exists()


class MappingVFS:
    """A VFS backed by an in-memory ``{path: text}`` mapping.

    Shared by the MCAP and lockfile backends, which each build a virtual tree of
    interface files and synthetic ``package.xml`` entries.
    """

    def __init__(self, files: dict[str, str]) -> None:
        self._files = files

    def read_text(self, path: str) -> str:
        return self._files[path]

    def glob(self, pattern: str) -> list[str]:
        rx = _glob_to_regex(pattern)
        return sorted(p for p in self._files if rx.match(p))

    def exists(self, path: str) -> bool:
        path = path.rstrip("/")
        return path in self._files or any(f.startswith(path + "/") for f in self._files)


def _glob_to_regex(pattern: str) -> re.Pattern[str]:
    """Translate a glob pattern into a full-match regex.

    ``**/`` matches zero or more directory segments, ``*`` matches within a
    single segment, ``?`` matches one non-separator character, and character
    classes follow :mod:`fnmatch`.
    """
    out: list[str] = []
    i = 0
    n = len(pattern)
    while i < n:
        if pattern.startswith("**/", i):
            out.append("(?:[^/]+/)*")
            i += 3
        elif pattern.startswith("**", i):
            out.append(".*")
            i += 2
        elif pattern[i] == "*":
            out.append("[^/]*")
            i += 1
        elif pattern[i] == "?":
            out.append("[^/]")
            i += 1
        elif pattern[i] == "[":
            end = i + 1
            if end < n and pattern[end] == "!":
                end += 1
            if end < n and pattern[end] == "]":
                end += 1
            end = pattern.find("]", end)
            if end == -1:
                out.append(r"\[")
                i += 1
            else:
                out.append("(?=[^/])" + translate(pattern[i : end + 1])[:-2])
                i = end + 1
        else:
            out.append(re.escape(pattern[i]))
            i += 1
    return re.compile("^" + "".join(out) + "$")


def _glob_with_parents(files: list[str], pattern: str) -> list[str]:
    """Expand virtual path segments before traversing their parents."""
    directories = {""}
    for path in files:
        parent = posixpath.dirname(path)
        while parent:
            directories.add(parent)
            parent = posixpath.dirname(parent)
    paths = directories | set(files)
    matches = {""}
    for part in pattern.split("/"):
        if part in ("", "."):
            continue
        if part == "..":
            matches = {posixpath.dirname(p) for p in matches if p in directories and p}
        elif part == "**":
            matches = {
                p for p in paths if any(not m or p == m or p.startswith(m + "/") for m in matches)
            }
        else:
            matches = {
                p
                for p in paths
                if p
                and posixpath.dirname(p) in matches
                and fnmatchcase(posixpath.basename(p), part)
            }
    return sorted(matches & set(files))


class GitTreeFS:
    """VFS backed by a git tree object, read without touching the working tree.

    Uses ``git ls-tree`` (cached) for listing and ``git show`` for contents.
    Initialised submodules are read at the commit ``ref`` records for them, so
    their packages are compared like any other.
    """

    def __init__(self, repo_root: str | Path, ref: str) -> None:
        self.repo_root = Path(repo_root)
        self.ref = ref
        self._files: list[str] | None = None
        self._submodules: dict[str, GitTreeFS] = {}
        self._missing: list[str] = []

    @property
    def files(self) -> list[str]:
        """Repo-relative paths tracked at ``ref`` (cached across calls)."""
        if self._files is None:
            files: list[str] = []
            out = self._git(["ls-tree", "-r", "-z", self.ref])
            for entry in filter(None, out.split("\0")):
                meta, path = entry.split("\t", 1)
                mode, _, sha = meta.split()
                if mode == "160000":
                    files += self._submodule_files(path, sha)
                else:
                    files.append(path)
            self._files = sorted(files)
        return self._files

    @property
    def missing_submodules(self) -> list[str]:
        """Initialised submodules whose recorded commit is not available locally."""
        _ = self.files
        nested = [
            f"{prefix}/{path}"
            for prefix, sub in self._submodules.items()
            for path in sub.missing_submodules
        ]
        return sorted(self._missing + nested)

    def _submodule_files(self, path: str, sha: str) -> list[str]:
        """Register an initialised submodule and return its files under ``path``."""
        sub_root = self.repo_root / path
        if not (sub_root / ".git").exists():
            return []  # not initialised: the working tree has nothing there either
        try:
            subprocess.run(
                ["git", "-C", str(sub_root), "cat-file", "-e", f"{sha}^{{commit}}"],
                capture_output=True,
                check=True,
            )
        except subprocess.CalledProcessError:
            self._missing.append(path)
            return []
        sub = GitTreeFS(sub_root, sha)
        self._submodules[path] = sub
        return [f"{path}/{f}" for f in sub.files]

    def read_text(self, path: str) -> str:
        for prefix, sub in self._submodules.items():
            if path.startswith(prefix + "/"):
                return sub.read_text(path[len(prefix) + 1 :])
        return self._git(["show", f"{self.ref}:{path}"])

    def glob(self, pattern: str) -> list[str]:
        """Match tracked paths, expanding globs before any parent traversal."""
        if ".." in pattern.split("/"):
            return _glob_with_parents(self.files, pattern)
        rx = _glob_to_regex(pattern)
        return sorted(f for f in self.files if rx.match(f))

    def exists(self, path: str) -> bool:
        path = path.rstrip("/")
        return any(f == path or f.startswith(path + "/") for f in self.files)

    def _git(self, args: list[str]) -> str:
        try:
            proc = subprocess.run(
                ["git", "-C", str(self.repo_root), *args],
                capture_output=True,
                text=True,
                encoding="utf-8",
                check=True,
            )
        except FileNotFoundError as exc:  # git not installed
            raise VfsError("git executable not found") from exc
        except subprocess.CalledProcessError as exc:
            raise VfsError(
                f"git {' '.join(args)} failed: {exc.stderr.strip()}"
            ) from exc
        return proc.stdout


def git_toplevel(path: str | Path) -> Path | None:
    """Return the git repository root containing ``path``, or ``None``."""
    try:
        proc = subprocess.run(
            ["git", "-C", str(path), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except (FileNotFoundError, subprocess.CalledProcessError):
        return None
    return Path(proc.stdout.strip())


def rev_parse_verify(repo_root: str | Path, ref: str) -> str:
    """Resolve and validate a git ref, returning its full SHA.

    Raises:
        VfsError: If the ref does not exist.
    """
    try:
        proc = subprocess.run(
            ["git", "-C", str(repo_root), "rev-parse", "--verify", f"{ref}^{{commit}}"],
            capture_output=True,
            text=True,
            encoding="utf-8",
            check=True,
        )
    except FileNotFoundError as exc:
        raise VfsError("git executable not found") from exc
    except subprocess.CalledProcessError as exc:
        raise VfsError(f"not a valid git ref: {ref}") from exc
    return proc.stdout.strip()
