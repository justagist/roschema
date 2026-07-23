"""Human-readable text report, grouped by package then interface."""

from __future__ import annotations

from rich.console import Console

from ..rules import LEVEL_LABEL, Finding
from .summary import summarize

_SEVERITY_STYLE = {"error": "red", "warn": "yellow"}
_BUMP_STYLE = {"MAJOR": "red", "MINOR": "yellow", "PATCH": "green"}


def render_text(
    findings: list[Finding], console: Console, new_source: str, old_source: str
) -> None:
    """Render findings to ``console`` with a summary and semver advisories.

    Suppressed findings are not listed individually but are counted.
    """
    console.print(f"[bold]checking[/bold] {new_source}  [dim]against[/dim]  {old_source}")
    reported = [f for f in findings if not f.suppressed]

    if not reported:
        console.print("[green]no breaking changes found[/green]")
        _print_suppressed(console, findings)
        return

    by_package: dict[str, list[Finding]] = {}
    for finding in reported:
        by_package.setdefault(finding.package, []).append(finding)
    for package in sorted(by_package):
        console.print(f"\n[bold cyan]{package}[/bold cyan]")
        for finding in by_package[package]:
            _print_finding(console, finding)

    summary = summarize(findings)
    console.print(
        f"\n[bold]{summary.total} finding(s):[/bold] "
        f"[red]{summary.errors} error(s)[/red], [yellow]{summary.warnings} warning(s)[/yellow]"
    )
    _print_suppressed(console, findings)
    for advisory in summary.advisories:
        style = _BUMP_STYLE.get(advisory.bump, "white")
        console.print(
            f"  [{style}]{advisory.package}: suggests {advisory.bump} version bump[/{style}] "
            f"[dim]({advisory.reason})[/dim]"
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


def _print_suppressed(console: Console, findings: list[Finding]) -> None:
    count = sum(1 for f in findings if f.suppressed)
    if count:
        console.print(f"[dim]{count} finding(s) suppressed[/dim]")


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
