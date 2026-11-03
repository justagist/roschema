"""Summary counts and per-package semver advisories."""

from __future__ import annotations

from collections.abc import Collection
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


@dataclass(frozen=True)
class Coverage:
    """How many interfaces a check compared, counted across both sides."""

    packages: int
    compared: int  # present on both sides
    target_only: int
    baseline_only: int

    @property
    def baseline_empty(self) -> bool:
        """True when the baseline holds no interfaces, so nothing can break."""
        return self.compared + self.baseline_only == 0

    def describe(self) -> str:
        """One-line description, e.g. ``compared 3 interface(s) in 1 package(s)``."""
        text = f"compared {self.compared} interface(s) in {self.packages} package(s)"
        extra = [
            f"{count} only in the {side}"
            for count, side in ((self.target_only, "target"), (self.baseline_only, "baseline"))
            if count
        ]
        return f"{text}; {', '.join(extra)}" if extra else text


def coverage(old: Collection[str], new: Collection[str]) -> Coverage:
    """Count the interface keys (``package/kind/name``) on each side of a check."""
    old_keys, new_keys = set(old), set(new)
    return Coverage(
        packages=len({key.split("/", 1)[0] for key in old_keys | new_keys}),
        compared=len(old_keys & new_keys),
        target_only=len(new_keys - old_keys),
        baseline_only=len(old_keys - new_keys),
    )


def summarize(findings: list[Finding]) -> Summary:
    """Compute counts and per-package advisories from finalized findings."""
    reported = [f for f in findings if not f.suppressed]
    errors = sum(1 for f in reported if f.severity == "error")
    warnings = sum(1 for f in reported if f.severity == "warn")
    suppressed = sum(1 for f in findings if f.suppressed)

    by_package: dict[str, list[Finding]] = {}
    for finding in reported:
        by_package.setdefault(finding.package, []).append(finding)
    advisories = tuple(_advise(package, by_package[package]) for package in sorted(by_package))
    return Summary(
        total=len(reported),
        errors=errors,
        warnings=warnings,
        suppressed=suppressed,
        advisories=advisories,
    )


def _advise(package: str, findings: list[Finding]) -> PackageAdvisory:
    wire_source_errors = [
        f for f in findings if f.severity == "error" and set(f.levels) & {"wire", "source"}
    ]
    if wire_source_errors:
        n = len(wire_source_errors)
        return PackageAdvisory(package, "MAJOR", f"{n} wire/source-breaking change(s)")
    additions = [f for f in findings if f.rule == "RS002"]
    if additions:
        return PackageAdvisory(package, "MINOR", f"{len(additions)} additive change(s)")
    return PackageAdvisory(package, "PATCH", f"{len(findings)} change(s)")
