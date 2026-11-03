"""Exercise the composite Action's Bash argument handling."""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

_ACTION = Path(__file__).resolve().parents[1] / "action" / "action.yml"


def _run_action(tmp_path: Path, inputs: dict[str, str]) -> tuple[list[str], bool]:
    """Run the Action's script with ``inputs``; return uvx's arguments and injection."""
    action = _ACTION.read_text()
    script = textwrap.dedent(action.split("      run: |\n", 1)[1])
    # Render expressions as Actions would, so the test also catches interpolation.
    for name, value in inputs.items():
        script = script.replace("${{ inputs." + name + " }}", value)
    uvx = tmp_path / "uvx"
    uvx.write_text('#!/bin/bash\nprintf "%s\\0" "$@" > "$ARGUMENTS_FILE"\n')
    uvx.chmod(0o755)
    arguments = tmp_path / "arguments"
    injection_marker = tmp_path / "executed"
    (tmp_path / "vendor_example").touch()
    env = {
        **os.environ,
        **{f"ROSCHEMA_{name.upper()}": value for name, value in inputs.items()},
        "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "ARGUMENTS_FILE": str(arguments),
        "INJECTION_MARKER": str(injection_marker),
    }
    result = subprocess.run(
        ["bash", "-c", script], cwd=tmp_path, env=env, capture_output=True, text=True
    )
    assert result.returncode == 0, result.stderr
    return arguments.read_bytes().decode().split("\0")[:-1], injection_marker.exists()


def _action_defaults() -> dict[str, str]:
    """Read each input's default from action.yml without a YAML dependency."""
    defaults: dict[str, str] = {}
    name = ""
    for line in _ACTION.read_text().splitlines():
        if line.startswith("  ") and not line.startswith("    ") and line.endswith(":"):
            name = line.strip().rstrip(":")
        elif line.strip().startswith("default:") and name:
            defaults[name] = line.split("default:", 1)[1].strip().strip('"')
    return defaults


@pytest.mark.parametrize(
    "attack_input", [None, "target", "against", "level", "format", "deep", "exclude", "version"]
)
def test_action_passes_inputs_literally(tmp_path, attack_input):
    inputs = {
        "target": "src/my messages",
        "against": "origin/main",
        "level": "source",
        "format": "github",
        "deep": "true",
        "exclude": "vendor_* legacy_msgs/msg/Old",
        "version": "roschema==0.1.2",
    }
    if attack_input is None:
        inputs["deep"], inputs["exclude"] = "false", ""
    else:
        inputs[attack_input] = '$(touch "$INJECTION_MARKER") `touch "$INJECTION_MARKER"` "quoted"'
        if attack_input == "exclude":
            inputs["exclude"] += "\nvendor_*\tlegacy_?"
    actual, injected = _run_action(tmp_path, inputs)
    assert not injected, "Action executed shell code from an input"
    expected = [
        "--from",
        inputs["version"],
        "roschema",
        "check",
        inputs["target"],
        "--against",
        inputs["against"],
        "--format",
        inputs["format"],
        "--level",
        inputs["level"],
    ]
    if inputs["deep"] == "true":
        expected.append("--deep")
    for pattern in inputs["exclude"].split():
        expected.extend(["--exclude", pattern])
    assert actual == expected


def test_action_defaults_leave_level_to_configuration(tmp_path):
    """Default inputs must not override the level configured in roschema.toml."""
    actual, _ = _run_action(tmp_path, _action_defaults())
    assert "--level" not in actual
