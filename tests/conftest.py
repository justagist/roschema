"""Shared pytest fixtures."""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_ament(monkeypatch: pytest.MonkeyPatch) -> None:
    """Clear AMENT_PREFIX_PATH so tests never pick up a host ROS installation.

    Tests that exercise ament resolution set it explicitly.
    """
    monkeypatch.delenv("AMENT_PREFIX_PATH", raising=False)
