"""Lint rule modules (one rule per module), run against a single tree."""

from __future__ import annotations

from ..model import LintRule
from .rsl001_field_snake_case import RULE as RSL001
from .rsl002_constant_upper_snake import RULE as RSL002
from .rsl003_name_pascal_case import RULE as RSL003
from .rsl004_missing_doc import RULE as RSL004
from .rsl005_discouraged_types import RULE as RSL005
from .rsl006_unbounded import RULE as RSL006
from .rsl010_srv_shadow import RULE as RSL010

ALL_LINT_RULES: tuple[LintRule, ...] = (
    RSL001,
    RSL002,
    RSL003,
    RSL004,
    RSL005,
    RSL006,
    RSL010,
)
