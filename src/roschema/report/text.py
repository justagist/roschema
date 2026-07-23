"""Human-readable text report, grouped by package then interface."""

from __future__ import annotations

from rich.console import Console

from ..rules import LEVEL_LABEL, Finding

_SEVERITY_STYLE = {"error": "red", "warn": "yellow"}


def render_text(
    findings: list[Finding], console: Console, new_source: str, old_source: str
) -> None:
    """Render findings to ``console``.

    Args:
        findings: Findings to display, already in report order.
        console: Rich console to print to.
        new_source: Label for the interfaces being checked.
        old_source: Label for the baseline they are compared against.
    """
    console.print(f"[bold]checking[/bold] {new_source}  [dim]against[/dim]  {old_source}")
    if not findings:
        console.print("[green]no breaking changes found[/green]")
        return

    by_package: dict[str, list[Finding]] = {}
    for finding in findings:
        by_package.setdefault(finding.interface.split("/", 1)[0], []).append(finding)

    for package in sorted(by_package):
        console.print(f"\n[bold cyan]{package}[/bold cyan]")
        for finding in by_package[package]:
            _print_finding(console, finding)

    errors = sum(1 for f in findings if f.severity == "error")
    warnings = sum(1 for f in findings if f.severity == "warn")
    console.print(
        f"\n[bold]{len(findings)} finding(s):[/bold] "
        f"[red]{errors} error(s)[/red], [yellow]{warnings} warning(s)[/yellow]"
    )


def _print_finding(console: Console, finding: Finding) -> None:
    style = _SEVERITY_STYLE.get(finding.severity, "white")
    label = LEVEL_LABEL.get(finding.level, finding.level)
    console.print(
        f"  [bold]{finding.rule}[/bold] [{style}]{finding.severity}[/{style}]  "
        f"{finding.qualified_target}: {finding.message}  [dim]({label})[/dim]"
    )
    location = _location(finding)
    if location:
        console.print(f"      [dim]{location}[/dim]")


def _location(finding: Finding) -> str:
    old = _loc(finding.old_file, finding.old_line)
    new = _loc(finding.new_file, finding.new_line)
    if old and new:
        return f"{old} -> {new}"
    return old or new


def _loc(file: str | None, line: int | None) -> str:
    if not file:
        return ""
    return f"{file}:{line}" if line is not None else file
