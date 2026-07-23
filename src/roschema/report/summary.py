"""Summary counts and per-package semver advisories."""

from __future__ import annotations

from dataclasses import dataclass

from ..rules import Finding


@dataclass(frozen=True)
class PackageAdvisory:
    """Suggested semver bump for a package and the reason for it."""

    package: str
    bump: str  # MAJOR | MINOR | PATCH
    reason: str


@dataclass(frozen=True)
class Summary:
    """Aggregate result of a check."""

    total: int  # reported (non-suppressed) findings
    errors: int
    warnings: int
    suppressed: int
    advisories: tuple[PackageAdvisory, ...]


def summarize(findings: list[Finding]) -> Summary:
    """Compute counts and per-package advisories from finalized findings."""
    reported = [f for f in findings if not f.suppressed]
    errors = sum(1 for f in reported if f.severity == "error")
    warnings = sum(1 for f in reported if f.severity == "warn")
    suppressed = sum(1 for f in findings if f.suppressed)

    by_package: dict[str, list[Finding]] = {}
    for finding in reported:
        by_package.setdefault(finding.package, []).append(finding)
    advisories = tuple(
        _advise(package, by_package[package]) for package in sorted(by_package)
    )
    return Summary(
        total=len(reported),
        errors=errors,
        warnings=warnings,
        suppressed=suppressed,
        advisories=advisories,
    )


def _advise(package: str, findings: list[Finding]) -> PackageAdvisory:
    wire_source_errors = [
        f
        for f in findings
        if f.severity == "error" and set(f.levels) & {"wire", "source"}
    ]
    if wire_source_errors:
        n = len(wire_source_errors)
        return PackageAdvisory(package, "MAJOR", f"{n} wire/source-breaking change(s)")
    additions = [f for f in findings if f.rule == "RS002"]
    if additions:
        return PackageAdvisory(package, "MINOR", f"{len(additions)} additive change(s)")
    return PackageAdvisory(package, "PATCH", f"{len(findings)} change(s)")
