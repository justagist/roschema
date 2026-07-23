"""roschema command-line interface."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console

from .differ import diff_interfaces
from .discovery import (
    Resolution,
    apply_exclude,
    resolve_baseline,
    resolve_target,
)
from .loader import load_interfaces
from .parser import ParseError
from .report import render_text
from .rules import evaluate
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
        str, typer.Option("--format", help="Output format (text).")
    ] = "text",
    exit_zero: Annotated[
        bool, typer.Option("--exit-zero", help="Exit 0 even when findings exist.")
    ] = False,
    exclude: Annotated[
        list[str] | None,
        typer.Option("--exclude", help="Glob of packages/interfaces to skip."),
    ] = None,
) -> None:
    """Check interface changes against a baseline for breaking changes."""
    if fmt != "text":
        err_console.print(f"[red]error:[/red] format {fmt!r} is not supported yet (Phase 4)")
        raise typer.Exit(code=2)

    try:
        new_res = resolve_target(target)
        if not isinstance(new_res.vfs, RealFS):
            raise VfsError("check target must be a directory or workspace")
        old_res = resolve_baseline(against, new_res.vfs.root)
        new_ifaces = load_interfaces(new_res.vfs, apply_exclude(new_res.packages, exclude or []))
        old_ifaces = load_interfaces(old_res.vfs, apply_exclude(old_res.packages, exclude or []))
    except (VfsError, ParseError) as exc:
        err_console.print(f"[red]error:[/red] {exc}")
        raise typer.Exit(code=2) from exc

    findings = evaluate(diff_interfaces(old_ifaces, new_ifaces))
    render_text(findings, console, new_res.source, old_res.source)

    if exit_zero:
        raise typer.Exit(code=0)
    has_error = any(f.severity == "error" and not f.suppressed for f in findings)
    raise typer.Exit(code=1 if has_error else 0)


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
