"""Shared helpers for lint rules.

Naming patterns mirror ``rosidl_adapter`` (the ROS 2 interface generator), so
roschema flags exactly what ``rosidl`` itself rejects rather than inventing its
own rules.
"""

from __future__ import annotations

import re
from collections.abc import Iterator

from ...ir import Constant, Field, InterfaceFile

# rosidl_adapter/parser.py patterns.
FIELD_NAME = re.compile(r"^[a-z]([a-z0-9_]?[a-z0-9])*$")
CONSTANT_NAME = re.compile(r"^[A-Z]([A-Z0-9_]?[A-Z0-9])*$")
MESSAGE_NAME = re.compile(r"^[A-Z][A-Za-z0-9]*$")


def iter_fields(iface: InterfaceFile) -> Iterator[tuple[str, Field]]:
    """Yield ``(section_value, field)`` for every field in order."""
    for section in iface.sections:
        for member in section.members:
            if isinstance(member, Field):
                yield section.kind.value, member


def iter_constants(iface: InterfaceFile) -> Iterator[tuple[str, Constant]]:
    """Yield ``(section_value, constant)`` for every constant in order."""
    for section in iface.sections:
        for member in section.members:
            if isinstance(member, Constant):
                yield section.kind.value, member
