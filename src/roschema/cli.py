"""roschema command-line interface."""

from __future__ import annotations

import json
import os
import posixpath
from collections.abc import Callable
from dataclasses import replace
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from . import __version__
from .config import (
    LEVEL_BUNDLES,
    ConfigError,
    finalize_findings,
    finalize_lint,
    load_config,
)
from .deep import transitive_findings
from .differ import diff_interfaces
from .discovery import (
    Resolution,
    apply_exclude,
    resolve_ament,
    resolve_bag,
    resolve_baseline,
    resolve_target,
)
from .formatter import format_text
from .freeze import build_lock
from .ir import InterfaceFile
from .loader import load_interfaces
from .parser import ParseError
from .report import build_github, build_json, render_lint, render_text
from .rules import Finding, all_lint_rules, evaluate, lint_interfaces
from .vfs import GitTreeFS, RealFS, VfsError, git_toplevel

app = typer.Typer(
    help="Breaking-change detection, linting and formatting for ROS 2 interfaces.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)


def _version_callback(value: bool) -> None:
    """Print the package version and exit before validating command arguments."""
    if value:
        typer.echo(f"roschema version {__version__}")
        raise typer.Exit()


@app.callback()
def _main(
    version: Annotated[
        bool,
        typer.Option(
            "--version",
            "-v",
            callback=_version_callback,
            is_eager=True,
            help="Show version and exit.",
        ),
    ] = False,
) -> None:
    """roschema: keep ROS 2 interface changes honest."""


@app.command()
def check(
    target: Annotated[
        str | None,
        typer.Argument(help="Path, package name, or omit for the current workspace."),
    ] = None,
    against: Annotated[
        str,
        typer.Option("--against", help="Baseline: git ref or directory path."),
    ] = ...,  # type: ignore[assignment]
    fmt: Annotated[
        str, typer.Option("--format", help="Output format: text, json or github.")
    ] = "text",
    level: Annotated[
        str | None,
        typer.Option("--level", help="Reporting level: wire, source, introspection, behavior."),
    ] = None,
    config_path: Annotated[
        Path | None,
        typer.Option("--config", help="Explicit config file (roschema.toml or pyproject.toml)."),
    ] = None,
    deep: Annotated[
        bool | None,
        typer.Option(
            "--deep/--no-deep", help="Resolve nested types and flag transitive breakage (RS110)."
        ),
    ] = None,
    exit_zero: Annotated[
        bool, typer.Option("--exit-zero", help="Exit 0 even when findings exist.")
    ] = False,
    exclude: Annotated[
        list[str] | None,
        typer.Option("--exclude", help="Glob of packages/interfaces to skip."),
    ] = None,
) -> None:
    """Check interface changes against a baseline for breaking changes."""
    if fmt not in ("text", "json", "github"):
        err_console.print(f"[red]error:[/red] unknown format {fmt!r}")
        raise typer.Exit(code=2)
    if level is not None and level not in LEVEL_BUNDLES:
        err_console.print(f"[red]error:[/red] unknown level {level!r}")
        raise typer.Exit(code=2)

    try:
        findings, new_source, old_source, prefix = _compute(
            target, lambda root: resolve_baseline(against, root), level, config_path, exclude, deep
        )
    except (VfsError, ParseError, ConfigError) as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    if old_source.startswith("git:") and Path(against).is_dir():
        err_console.print(
            f"[dim]note: {against!r} matched a git ref; "
            f"use './{against}' to compare against the directory instead.[/dim]"
        )
    _emit(findings, fmt, new_source, old_source, prefix)
    _exit_for(findings, exit_zero)


@app.command(name="bag-check")
def bag_check(
    bag: Annotated[str, typer.Argument(help="Recorded MCAP bag to check against.")],
    targets: Annotated[
        list[str] | None,
        typer.Argument(
            help="Paths/package names to compare against; default is the current "
            "environment (ament index)."
        ),
    ] = None,
    fmt: Annotated[
        str, typer.Option("--format", help="Output format: text, json or github.")
    ] = "text",
    exit_zero: Annotated[
        bool, typer.Option("--exit-zero", help="Exit 0 even when findings exist.")
    ] = False,
    exclude: Annotated[
        list[str] | None,
        typer.Option("--exclude", help="Glob of packages/interfaces to skip."),
    ] = None,
) -> None:
    """Check a recorded MCAP bag against the current environment.

    By default the bag's types are compared against the interfaces available in
    the current ROS environment (the ament index). Supplying TARGETS (paths or
    package names) overlays those definitions on top, so a package you are
    actively editing can be checked from source instead of its installed copy.
    """
    if fmt not in ("text", "json", "github"):
        err_console.print(f"[red]error:[/red] unknown format {fmt!r}")
        raise typer.Exit(code=2)
    if not bag.endswith(".mcap"):
        err_console.print(f"[red]error:[/red] expected a .mcap bag, got {bag!r}")
        raise typer.Exit(code=2)

    excludes = exclude or []
    try:
        old_res = resolve_bag(bag)
        old_ifaces = load_interfaces(old_res.vfs, apply_exclude(old_res.packages, excludes))
        new_ifaces, new_source = _resolve_current(old_ifaces, targets or [], excludes)
        config = load_config(Path.cwd(), (), None)
    except (VfsError, ParseError, ConfigError) as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    findings = finalize_findings(
        evaluate(diff_interfaces(old_ifaces, new_ifaces)), config, None
    )
    _emit(findings, fmt, new_source, old_res.source)
    _exit_for(findings, exit_zero)


def _resolve_current(
    bag_ifaces: dict[str, InterfaceFile], targets: list[str], excludes: list[str]
) -> tuple[dict[str, InterfaceFile], str]:
    """Build the current-side interfaces for a bag check.

    Starts from the ament index (for the packages the bag references), then
    overlays any explicit targets so they take precedence.
    """
    current: dict[str, InterfaceFile] = {}
    for package in sorted({key.split("/", 1)[0] for key in bag_ifaces}):
        res = resolve_ament(package)
        if res is not None:
            current.update(load_interfaces(res.vfs, apply_exclude(res.packages, excludes)))
    for target in targets:
        res = resolve_target(target, include_empty=True)
        replaced = {pkg.name for pkg in res.packages}
        current = {key: iface for key, iface in current.items() if iface.package not in replaced}
        current.update(load_interfaces(res.vfs, apply_exclude(res.packages, excludes)))
    source = "targets+environment" if targets else "environment (ament index)"
    return current, source


def _compute(
    target: str | None,
    resolve_old: Callable[[Path], Resolution],
    level: str | None,
    config_path: Path | None,
    exclude: list[str] | None,
    deep: bool | None = None,
) -> tuple[list[Finding], str, str, str]:
    """Resolve both sides, diff and finalize; the shared check pipeline."""
    new_res = resolve_target(target, allow_empty_glob=True)
    if not isinstance(new_res.vfs, RealFS):
        raise VfsError("target must be a directory or workspace")
    old_res = resolve_old(new_res.vfs.root)
    config = load_config(new_res.vfs.root, new_res.packages, config_path)
    excludes = exclude or []
    new_ifaces = load_interfaces(new_res.vfs, apply_exclude(new_res.packages, excludes))
    old_packages = old_res.packages
    prefix = _display_prefix(new_res.vfs.root)
    if new_res.glob_pattern is not None:
        if old_res.source.startswith(("mcap:", "lock:")):
            raise VfsError(
                "path glob targets require a Git or directory baseline; "
                "use a workspace target for lockfile or MCAP baselines"
            )
        pattern = new_res.glob_pattern
        if isinstance(old_res.vfs, GitTreeFS):
            pattern = posixpath.join(prefix, pattern)
        manifests = set(old_res.vfs.glob(pattern.rstrip("/") + "/**/package.xml"))
        scope = {p.name for p in new_res.packages} | {
            p.name
            for p in old_packages
            if posixpath.join(p.path, "package.xml") in manifests
        }
        if not scope:
            raise VfsError(f"target glob {target!r} matched no interface packages on either side")
        old_packages = tuple(p for p in old_packages if p.name in scope)
    old_ifaces = load_interfaces(old_res.vfs, apply_exclude(old_packages, excludes))
    raw = evaluate(diff_interfaces(old_ifaces, new_ifaces))
    deep_packages = {p.name for p in new_res.packages if config.effective_deep(p.name, deep)}
    if deep_packages:
        raw = raw + [
            f for f in transitive_findings(new_ifaces, raw) if f.package in deep_packages
        ]
    findings = finalize_findings(raw, config, level)
    return findings, new_res.source, old_res.source, prefix


def _display_prefix(target_dir: Path) -> str:
    """Repo-root-relative prefix for a real-filesystem target, or ``""``."""
    top = git_toplevel(target_dir)
    if top is None:
        return ""
    rel = os.path.relpath(target_dir, top)
    return "" if rel == "." else rel


def _exit_for(findings: list[Finding], exit_zero: bool) -> None:
    if exit_zero:
        raise typer.Exit(code=0)
    has_error = any(f.severity == "error" and not f.suppressed for f in findings)
    raise typer.Exit(code=1 if has_error else 0)


def _emit(
    findings: list[Finding],
    fmt: str,
    new_source: str,
    old_source: str,
    display_prefix: str = "",
) -> None:
    if fmt == "json":
        typer.echo(json.dumps(build_json(findings), indent=2))
    elif fmt == "github":
        for line in build_github(findings, display_prefix):
            typer.echo(line)
    else:
        render_text(findings, console, new_source, old_source)


@app.command()
def lint(
    target: Annotated[
        str | None,
        typer.Argument(help="Path, package name, or omit for the current workspace."),
    ] = None,
    fmt: Annotated[
        str, typer.Option("--format", help="Output format: text, json or github.")
    ] = "text",
    config_path: Annotated[
        Path | None, typer.Option("--config", help="Explicit config file.")
    ] = None,
    rules: Annotated[
        list[str] | None,
        typer.Option(
            "--rules",
            help="Rule severity override(s), e.g. RSL004=warn or RSL001=off "
            "(bare RSL### means =warn). Repeatable; beats config.",
        ),
    ] = None,
    exit_zero: Annotated[
        bool, typer.Option("--exit-zero", help="Exit 0 even when findings exist.")
    ] = False,
    exclude: Annotated[
        list[str] | None,
        typer.Option("--exclude", help="Glob of packages/interfaces to skip."),
    ] = None,
) -> None:
    """Lint interface definitions in a single tree (no baseline)."""
    if fmt not in ("text", "json", "github"):
        err_console.print(f"[red]error:[/red] unknown format {fmt!r}")
        raise typer.Exit(code=2)

    try:
        overrides = _parse_rule_overrides(rules or [])
        res = resolve_target(target)
        if not isinstance(res.vfs, RealFS):
            raise VfsError("lint target must be a directory or workspace")
        config = load_config(res.vfs.root, res.packages, config_path)
        config = replace(config, lint_rules={**config.lint_rules, **overrides})
        interfaces = load_interfaces(res.vfs, apply_exclude(res.packages, exclude or []))
    except (VfsError, ParseError, ConfigError) as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    findings = finalize_lint(lint_interfaces(interfaces), config)
    if fmt == "json":
        typer.echo(json.dumps(build_json(findings), indent=2))
    elif fmt == "github":
        for line in build_github(findings, _display_prefix(res.vfs.root)):
            typer.echo(line)
    else:
        render_lint(findings, console, res.source)

    if exit_zero:
        raise typer.Exit(code=0)
    has_error = any(f.severity == "error" and not f.suppressed for f in findings)
    raise typer.Exit(code=1 if has_error else 0)


def _parse_rule_overrides(items: list[str]) -> dict[str, str]:
    """Parse ``--rules RSL004=warn`` items (bare ``RSL###`` means ``=warn``)."""
    valid = {rule.id for rule in all_lint_rules()}
    out: dict[str, str] = {}
    for item in items:
        rule_id, _, severity = item.partition("=")
        rule_id = rule_id.strip()
        severity = severity.strip() or "warn"
        if rule_id not in valid:
            raise ConfigError(f"--rules: unknown lint rule {rule_id!r}")
        if severity not in ("off", "warn", "error"):
            raise ConfigError(f"--rules: invalid severity {severity!r} for {rule_id}")
        out[rule_id] = severity
    return out


@app.command()
def fmt(
    target: Annotated[
        str | None,
        typer.Argument(help="Path, package name, or omit for the current workspace."),
    ] = None,
    check_only: Annotated[
        bool, typer.Option("--check", help="Report files that need formatting; do not write.")
    ] = False,
    exclude: Annotated[
        list[str] | None,
        typer.Option("--exclude", help="Glob of packages/interfaces to skip."),
    ] = None,
) -> None:
    """Canonically format interface files (idempotent, comment-preserving)."""
    try:
        res = resolve_target(target)
        if not isinstance(res.vfs, RealFS):
            raise VfsError("fmt target must be a directory or workspace")
        packages = apply_exclude(res.packages, exclude or [])
        changed: list[str] = []
        for pkg in packages:
            for ref in pkg.interfaces:
                original = res.vfs.read_text(ref.path)
                formatted = format_text(original, ref.path)
                if formatted != original:
                    changed.append(ref.path)
                    if not check_only:
                        (res.vfs.root / ref.path).write_text(formatted)
    except (VfsError, ParseError) as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    verb = "would reformat" if check_only else "reformatted"
    for path in changed:
        console.print(f"{verb} {path}")
    if check_only:
        if changed:
            console.print(f"[yellow]{len(changed)} file(s) need formatting[/yellow]")
            raise typer.Exit(code=1)
        console.print("[green]all files formatted[/green]")
        raise typer.Exit(code=0)
    console.print(f"{len(changed)} file(s) reformatted")
    raise typer.Exit(code=0)


@app.command()
def freeze(
    target: Annotated[
        str | None,
        typer.Argument(help="Path, package name, or omit for the current workspace."),
    ] = None,
    output: Annotated[
        Path, typer.Option("-o", "--output", help="Lockfile path to write.")
    ] = Path("roschema.lock"),
    exclude: Annotated[
        list[str] | None,
        typer.Option("--exclude", help="Glob of packages/interfaces to skip."),
    ] = None,
) -> None:
    """Write a roschema.lock baseline (canonical text + sha256 per interface)."""
    try:
        res = resolve_target(target)
        interfaces = load_interfaces(res.vfs, apply_exclude(res.packages, exclude or []))
    except (VfsError, ParseError) as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    output.write_text(build_lock(interfaces, __version__))
    console.print(f"wrote {len(interfaces)} interface(s) to {output}")


@app.command()
def ls(
    target: Annotated[
        str | None,
        typer.Argument(help="Path, package name, or omit for the current workspace."),
    ] = None,
    json_out: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
    exclude: Annotated[
        list[str] | None,
        typer.Option("--exclude", help="Glob of packages/interfaces to skip."),
    ] = None,
) -> None:
    """List discovered interface packages and the source they came from."""
    try:
        resolution = resolve_target(target)
    except VfsError as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    packages = apply_exclude(resolution.packages, exclude or [])
    resolution = Resolution(vfs=resolution.vfs, packages=packages, source=resolution.source)

    if json_out:
        typer.echo(json.dumps(_to_json(resolution), indent=2))
        return
    _print_text(resolution)


def _to_json(resolution: Resolution) -> dict[str, object]:
    return {
        "source": resolution.source,
        "packages": [
            {
                "name": pkg.name,
                "path": pkg.path,
                "interfaces": [
                    {"kind": ref.kind, "name": ref.name, "path": ref.path}
                    for ref in pkg.interfaces
                ],
            }
            for pkg in resolution.packages
        ],
    }


def _print_text(resolution: Resolution) -> None:
    console.print(f"[bold]source:[/bold] {resolution.source}")
    if not resolution.packages:
        console.print("[yellow]no interface packages found[/yellow]")
        return
    total = 0
    for pkg in resolution.packages:
        console.print(f"\n[bold cyan]{pkg.name}[/bold cyan]  [dim]{pkg.path}[/dim]")
        for ref in pkg.interfaces:
            console.print(f"  {ref.kind:<7} {ref.name}  [dim]{ref.path}[/dim]")
            total += 1
    plural = "interface" if total == 1 else "interfaces"
    console.print(
        f"\n[dim]{len(resolution.packages)} package(s), {total} {plural}[/dim]"
    )


if __name__ == "__main__":  # pragma: no cover
    app()
