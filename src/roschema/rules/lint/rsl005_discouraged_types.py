"""RSL005: discouraged types (`char`, and `byte` outside a byte array)."""

from __future__ import annotations

from ...ir import ArrayKind, InterfaceFile
from ..model import LintHit, LintRule, Severity
from ._common import iter_fields


def _check(iface: InterfaceFile) -> list[LintHit]:
    hits: list[LintHit] = []
    for section, field in iter_fields(iface):
        base = field.type.base
        is_scalar = field.type.array_kind is ArrayKind.NONE
        discouraged = base == "char" or (base == "byte" and is_scalar)
        if discouraged:
            hits.append(
                LintHit(
                    section=section,
                    target=field.name,
                    line=field.line,
                    message=(
                        f"field '{field.name}' uses discouraged type "
                        f"'{field.type.render()}' (prefer uint8; use byte[] for binary data)"
                    ),
                    comment=field.trailing_comment,
                )
            )
    return hits


RULE = LintRule(
    id="RSL005",
    title="Discouraged type",
    description="Uses `char`, or a scalar `byte`, whose generated types are ambiguous.",
    rationale=(
        "rosidl generates `char` as `uint8` although the ROS 2 type table lists it "
        "as a DDS `char`, and a scalar `byte` becomes a Python `bytes` object rather "
        "than an integer; `uint8` states the intent. `byte[]` remains idiomatic for "
        "opaque binary data."
    ),
    default_severity=Severity.WARN,
    check=_check,
    example_flagged="char mode\nbyte flag",
    example_preferred="uint8 mode\nuint8 flag",
)
