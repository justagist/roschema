"""Tests for the CLI version option."""

from __future__ import annotations

import pytest
from typer.testing import CliRunner

from roschema import __version__
from roschema.cli import app

runner = CliRunner()


@pytest.mark.parametrize("args", [["--version"], ["-v"], ["--version", "check"]])
def test_version_exits_without_required_arguments(args):
    result = runner.invoke(app, args)
    assert result.exit_code == 0
    assert result.stdout == f"roschema version {__version__}\n"


def test_no_arguments_still_shows_help():
    result = runner.invoke(app, [])
    assert result.exit_code == 2
    assert "Usage:" in result.output
