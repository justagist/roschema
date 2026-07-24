"""Breaking-change rule modules (one rule per module).

RS050 is intentionally absent as a standalone rule: per the design, a
service/action section is a *scope*, not a rule. Its effect is realised by
qualifying child findings with their section (see ``Finding.qualified_target``),
so section-scoped changes read as e.g. ``pkg/action/Move.goal.speed``.
"""

from __future__ import annotations

from ..model import Rule
from .rs001_field_removed import RULE as RS001
from .rs002_field_added import RULE as RS002
from .rs003_field_type_changed import RULE as RS003
from .rs004_fields_reordered import RULE as RS004
from .rs005_field_renamed import RULE as RS005
from .rs006_array_kind_changed import RULE as RS006
from .rs007_bound_tightened import RULE as RS007
from .rs008_bound_loosened import RULE as RS008
from .rs020_constant_removed import RULE as RS020
from .rs021_constant_value_changed import RULE as RS021
from .rs022_constant_type_changed import RULE as RS022
from .rs030_default_changed import RULE as RS030
from .rs040_interface_removed import RULE as RS040
from .rs060_message_version import RULE as RS060

ALL_BREAKING_RULES: tuple[Rule, ...] = (
    RS001,
    RS002,
    RS003,
    RS004,
    RS005,
    RS006,
    RS007,
    RS008,
    RS020,
    RS021,
    RS022,
    RS030,
    RS040,
    RS060,
)
