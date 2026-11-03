"""Summary counts and per-package semver advisories."""

from __future__ import annotations

from collections import Counter
from collections.abc import Collection, Sequence
from dataclasses import dataclass

from ..rules import Finding
from .changes import ADDED, Change


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


# New interfaces named in the coverage line; the rest are counted.
_NAMED = 3


@dataclass(frozen=True)
class Coverage:
    """How many interfaces a check compared, counted across both sides."""

    packages: int
    compared: int  # present on both sides
    new: tuple[str, ...]  # interface keys only in the target, sorted
    baseline_only: int

    @property
    def target_only(self) -> int:
        """Number of interfaces only in the target."""
        return len(self.new)

    @property
    def baseline_empty(self) -> bool:
        """True when the baseline holds no interfaces, so nothing can break."""
        return self.compared + self.baseline_only == 0

    def describe(self) -> str:
        """One-line description naming the first few new interfaces.

        For example ``compared 3 interface(s) in 1 package(s); 1 new
        (my_msgs/msg/Pose)``.
        """
        parts = [f"compared {self.compared} interface(s) in {self.packages} package(s)"]
        if self.new:
            names = ", ".join(self.new[:_NAMED])
            if len(self.new) > _NAMED:
                names += f" and {len(self.new) - _NAMED} more"
            parts.append(f"{len(self.new)} new ({names})")
        if self.baseline_only:
            parts.append(f"{self.baseline_only} removed")
        return "; ".join(parts)


def coverage(old: Collection[str], new: Collection[str]) -> Coverage:
    """Count the interface keys (``package/kind/name``) on each side of a check."""
    old_keys, new_keys = set(old), set(new)
    return Coverage(
        packages=len({key.split("/", 1)[0] for key in old_keys | new_keys}),
        compared=len(old_keys & new_keys),
        new=tuple(sorted(new_keys - old_keys)),
        baseline_only=len(old_keys - new_keys),
    )


def summarize(findings: list[Finding], changes: Sequence[Change] = ()) -> Summary:
    """Compute counts and per-package advisories from finalized findings.

    Additions among ``changes`` (an added interface or constant) are not
    findings, but they make a package's advice at least MINOR.
    """
    reported = [f for f in findings if not f.suppressed]
    errors = sum(1 for f in reported if f.severity == "error")
    warnings = sum(1 for f in reported if f.severity == "warn")
    suppressed = sum(1 for f in findings if f.suppressed)

    by_package: dict[str, list[Finding]] = {}
    for finding in reported:
        by_package.setdefault(finding.package, []).append(finding)
    added = Counter(c.package for c in changes if c.reason in ADDED)
    advisories = tuple(
        _advise(package, by_package.get(package, []), added[package])
        for package in sorted(by_package.keys() | added.keys())
    )
    return Summary(
        total=len(reported),
        errors=errors,
        warnings=warnings,
        suppressed=suppressed,
        advisories=advisories,
    )


def _advise(package: str, findings: list[Finding], added: int) -> PackageAdvisory:
    wire_source_errors = [
        f for f in findings if f.severity == "error" and set(f.levels) & {"wire", "source"}
    ]
    if wire_source_errors:
        n = len(wire_source_errors)
        return PackageAdvisory(package, "MAJOR", f"{n} wire/source-breaking change(s)")
    additions = added + sum(1 for f in findings if f.rule == "RS002")
    if additions:
        return PackageAdvisory(package, "MINOR", f"{additions} additive change(s)")
    return PackageAdvisory(package, "PATCH", f"{len(findings)} change(s)")
