"""Human-readable text report, grouped by package then interface."""

from __future__ import annotations

from collections.abc import Sequence

from rich.console import Console

from ..rules import LEVEL_LABEL, Finding
from .changes import Change
from .summary import Coverage, Summary, summarize

_SEVERITY_STYLE = {"error": "red", "warn": "yellow"}
_BUMP_STYLE = {"MAJOR": "red", "MINOR": "yellow", "PATCH": "green"}


def render_text(
    findings: list[Finding],
    console: Console,
    new_source: str,
    old_source: str,
    coverage: Coverage,
    changes: Sequence[Change] = (),
) -> None:
    """Render findings to ``console`` with coverage, a summary and semver advisories.

    Suppressed findings are not listed individually but are counted. Additions
    among ``changes`` count towards the semver advice.
    """
    console.print(f"[bold]checking[/bold] {new_source}  [dim]against[/dim]  {old_source}")
    console.print(f"[dim]{coverage.describe()}[/dim]")
    reported = [f for f in findings if not f.suppressed]
    summary = summarize(findings, changes)

    if not reported:
        console.print("[green]no breaking changes found[/green]")
        _print_suppressed(console, findings)
        _print_advisories(console, summary)
        return

    by_package: dict[str, list[Finding]] = {}
    for finding in reported:
        by_package.setdefault(finding.package, []).append(finding)
    for package in sorted(by_package):
        console.print(f"\n[bold cyan]{package}[/bold cyan]")
        for finding in by_package[package]:
            _print_finding(console, finding)

    console.print(
        f"\n[bold]{summary.total} finding(s):[/bold] "
        f"[red]{summary.errors} error(s)[/red], [yellow]{summary.warnings} warning(s)[/yellow]"
    )
    _print_suppressed(console, findings)
    _print_advisories(console, summary)


def _print_advisories(console: Console, summary: Summary) -> None:
    for advisory in summary.advisories:
        style = _BUMP_STYLE.get(advisory.bump, "white")
        console.print(
            f"  [{style}]{advisory.package}: suggests {advisory.bump} version bump[/{style}] "
            f"[dim]({advisory.reason})[/dim]"
        )


def render_lint(findings: list[Finding], console: Console, source: str) -> None:
    """Render lint findings (no baseline, no semver advisory)."""
    console.print(f"[bold]linting[/bold] {source}")
    reported = [f for f in findings if not f.suppressed]
    if not reported:
        console.print("[green]no lint issues found[/green]")
        _print_suppressed(console, findings)
        return

    by_package: dict[str, list[Finding]] = {}
    for finding in reported:
        by_package.setdefault(finding.package, []).append(finding)
    for package in sorted(by_package):
        console.print(f"\n[bold cyan]{package}[/bold cyan]")
        for finding in by_package[package]:
            _print_finding(console, finding)

    errors = sum(1 for f in reported if f.severity == "error")
    warnings = sum(1 for f in reported if f.severity == "warn")
    console.print(
        f"\n[bold]{len(reported)} issue(s):[/bold] "
        f"[red]{errors} error(s)[/red], [yellow]{warnings} warning(s)[/yellow]"
    )
    _print_suppressed(console, findings)


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
