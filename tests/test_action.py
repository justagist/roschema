"""Exercise the composite Action's Bash argument handling."""

from __future__ import annotations

import os
import subprocess
import textwrap
from pathlib import Path

import pytest

_ACTION = Path(__file__).resolve().parents[1] / "action" / "action.yml"


@pytest.mark.parametrize(
    "attack_input", ["target", "against", "level", "format", "deep", "exclude", "version"]
)
def test_action_passes_inputs_literally(tmp_path, attack_input):
    inputs = {
        "target": "src/my messages",
        "against": "origin/main",
        "level": "source",
        "format": "github",
        "deep": "true",
        "exclude": "vendor_*\nlegacy_msgs/msg/Old\tother_*",
        "version": "roschema==0.1.2",
    }
    inputs[attack_input] = '$(printf injected) `printf injected` "quoted"'
    action = _ACTION.read_text()
    script = textwrap.dedent(action.split("      run: |\n", 1)[1])
    # Render expressions as Actions would, so the test also catches interpolation.
    for name, value in inputs.items():
        script = script.replace("${{ inputs." + name + " }}", value)
    uvx = tmp_path / "uvx"
    uvx.write_text('#!/bin/bash\nprintf "%s\\0" "$@" > "$ARGUMENTS_FILE"\n')
    uvx.chmod(0o755)
    arguments = tmp_path / "arguments"
    env = {
        **os.environ,
        **{f"ROSCHEMA_{name.upper()}": value for name, value in inputs.items()},
        "PATH": str(tmp_path) + os.pathsep + os.environ["PATH"],
        "ARGUMENTS_FILE": str(arguments),
    }
    result = subprocess.run(["bash", "-c", script], env=env, capture_output=True, text=True)
    assert result.returncode == 0, result.stderr
    actual = arguments.read_bytes().decode().split("\0")[:-1]
    expected = [
        "--from",
        inputs["version"],
        "roschema",
        "check",
        inputs["target"],
        "--against",
        inputs["against"],
        "--level",
        inputs["level"],
        "--format",
        inputs["format"],
    ]
    if inputs["deep"] == "true":
        expected.append("--deep")
    for pattern in inputs["exclude"].split():
        expected.extend(["--exclude", pattern])
    assert actual == expected
