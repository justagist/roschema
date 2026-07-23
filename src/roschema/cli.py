"""roschema command-line interface."""

from __future__ import annotations

import json
from typing import Annotated

import typer
from rich.console import Console

from .discovery import Resolution, apply_exclude, resolve_target
from .vfs import VfsError

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
