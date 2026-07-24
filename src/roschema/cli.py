"""roschema command-line interface."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer
from rich.console import Console

from .config import (
    LEVEL_BUNDLES,
    ConfigError,
    finalize_findings,
    finalize_lint,
    load_config,
)
from .differ import diff_interfaces
from .discovery import (
    Resolution,
    apply_exclude,
    resolve_baseline,
    resolve_target,
)
from .formatter import format_text
from .loader import load_interfaces
from .parser import ParseError
from .report import build_github, build_json, render_lint, render_text
from .rules import Finding, evaluate, lint_interfaces
from .vfs import RealFS, VfsError

app = typer.Typer(
    help="Breaking-change detection, linting and formatting for ROS 2 interfaces.",
    no_args_is_help=True,
    add_completion=False,
)
console = Console()
err_console = Console(stderr=True)


@app.callback()
def _main() -> None:
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
        new_res = resolve_target(target)
        if not isinstance(new_res.vfs, RealFS):
            raise VfsError("check target must be a directory or workspace")
        old_res = resolve_baseline(against, new_res.vfs.root)
        config = load_config(new_res.vfs.root, new_res.packages, config_path)
        new_ifaces = load_interfaces(new_res.vfs, apply_exclude(new_res.packages, exclude or []))
        old_ifaces = load_interfaces(old_res.vfs, apply_exclude(old_res.packages, exclude or []))
    except (VfsError, ParseError, ConfigError) as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    findings = finalize_findings(
        evaluate(diff_interfaces(old_ifaces, new_ifaces)), config, level
    )
    _emit(findings, fmt, new_res.source, old_res.source)

    if exit_zero:
        raise typer.Exit(code=0)
    has_error = any(f.severity == "error" and not f.suppressed for f in findings)
    raise typer.Exit(code=1 if has_error else 0)


def _emit(findings: list[Finding], fmt: str, new_source: str, old_source: str) -> None:
    if fmt == "json":
        typer.echo(json.dumps(build_json(findings), indent=2))
    elif fmt == "github":
        for line in build_github(findings):
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
        res = resolve_target(target)
        if not isinstance(res.vfs, RealFS):
            raise VfsError("lint target must be a directory or workspace")
        config = load_config(res.vfs.root, res.packages, config_path)
        interfaces = load_interfaces(res.vfs, apply_exclude(res.packages, exclude or []))
    except (VfsError, ParseError, ConfigError) as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    findings = finalize_lint(lint_interfaces(interfaces), config)
    if fmt == "json":
        typer.echo(json.dumps(build_json(findings), indent=2))
    elif fmt == "github":
        for line in build_github(findings):
            typer.echo(line)
    else:
        render_lint(findings, console, res.source)

    if exit_zero:
        raise typer.Exit(code=0)
    has_error = any(f.severity == "error" and not f.suppressed for f in findings)
    raise typer.Exit(code=1 if has_error else 0)


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
