# roschema

Catch breaking ROS 2 interface changes in the PR, not on the robot.

`roschema` detects breaking changes, lints and formats ROS 2 interface
definitions (`.msg`, `.srv`, `.action`) with zero ROS dependencies, so it runs
in a bare CI container.

> Work in progress. The full README (quickstart, compatibility-level table,
> rule reference, CI snippet) lands with later phases.

## Checking

```
roschema check [TARGET] --against REF [--level LEVEL] [--format text|json|github]
               [--exit-zero] [--config PATH] [--exclude GLOB]
```

`--against` accepts a git ref (validated with `git rev-parse`) or a directory.
Exit codes: `0` clean, `1` breaking changes found, `2` tool/usage error.
`--exit-zero` forces `0`. Warnings alone do not fail (exit `0`).

## Freeze (non-git baselines)

```
roschema freeze [TARGET] -o roschema.lock
roschema check  [TARGET] --against roschema.lock
```

`freeze` writes a lockfile holding each interface's canonical (post-`fmt`) text
plus a sha256, so a release tarball can carry its own baseline without git.
`check --against roschema.lock` reads it back (sha256-verified) and compares.

## Deep checking

`check --deep` resolves nested complex types through the workspace and ament
index and reports transitive breakage (`RS110`): an interface that embeds -
directly or through nested types - another whose wire layout changed is flagged
even when its own definition is unchanged, with the causal chain shown. Without
`--deep`, nested types are compared by name only.

## Linting and formatting

```
roschema lint [TARGET] [--format text|json|github] [--exit-zero]
roschema fmt  [TARGET] [--check]
```

`lint` checks a single tree (no baseline). Naming rules follow rosidl: field
names snake_case (RSL001), constants UPPER_SNAKE (RSL002), interface names
PascalCase (RSL003); it also flags deprecated `char`/scalar-`byte` (RSL005) and
request/response field shadowing in services (RSL010). RSL004 (missing doc) and
RSL006 (unbounded) are off by default; enable via `[lint.rules]`.

`fmt` canonically formats interface files (single space between type and name,
`=` without spaces for constants, one trailing newline) while preserving
comments, blank lines and section separators. It is idempotent and never
changes what `check` reports; `--check` exits `1` if any file would change.
Inline `# roschema: ignore=` suppressions survive formatting.

## Checking against a recorded bag

```
pip install 'roschema[bag]'
roschema bag-check recording.mcap [TARGETS...] [--format ...]
```

`bag-check` reads the interface definitions embedded in an MCAP bag and checks
whether they are still compatible with your **current environment** - the bag is
the baseline, so it flags changes that would stop current code from reading the
recorded data. By default the bag's types are resolved from the ament index
(`AMENT_PREFIX_PATH`), i.e. the packages installed in the sourced environment,
so system packages like `sensor_msgs` are compared against their installed
definitions rather than reported as missing.

Optional `TARGETS` (paths or package names) are overlaid on top of the
environment, so a package you are editing can be checked from source instead of
its installed copy. A bag type found in neither the environment nor any target
is reported as removed (RS040). `ros2msg` schemas (including concatenated
dependent definitions) are fully supported; `ros2idl` is a best-effort
conversion of the msg-equivalent subset.

## Compatibility levels

`--level` selects a cumulative bundle of what is reported; the default is
`source`.

| Level | Reports |
|---|---|
| `wire` | CDR byte-stream compatibility only |
| `source` | wire + generated C++/Python API |
| `introspection` | source + name-based tooling (bags, echo, YAML) |
| `behavior` | introspection + semantics (defaults, constant values) |

## Configuration

`roschema.toml` at the workspace root, a per-package `roschema.toml`, or
`[tool.roschema]` in `pyproject.toml`. Precedence: CLI > package > workspace >
defaults.

```toml
[check]
level = "source"

[check.rules]
RS008 = "off"          # off | warn | error

[check.allow]
# intentional breaks need a fully-qualified target and a mandatory reason
"my_msgs/msg/State.old_field" = { rules = ["RS001"], reason = "removed in 2.0, see #142" }
```

Inline suppression: a trailing comment on the new-side member line, e.g.
`float64 theta  # roschema: ignore=RS003` (comma-separate multiple IDs).
Suppressed findings are counted, not failed.

## JSON output

`--format json` emits a stable document (`version: 1`):

```json
{
  "version": 1,
  "findings": [
    {
      "rule": "RS003",
      "severity": "error",
      "level": "wire",
      "package": "my_msgs",
      "interface": "my_msgs/msg/Pose",
      "section": "message",
      "target": "theta",
      "message": "type changed float32 -> float64",
      "old": { "file": "my_msgs/msg/Pose.msg", "line": 1 },
      "new": { "file": "my_msgs/msg/Pose.msg", "line": 1 },
      "suppressed": false
    }
  ],
  "summary": {
    "total": 1,
    "errors": 1,
    "warnings": 0,
    "suppressed": 0,
    "advisories": { "my_msgs": "MAJOR" }
  }
}
```

`old`/`new` are `null` when there is no corresponding side (e.g. a removed
interface has no `new`). `--format github` emits `::error`/`::warning`
workflow-command annotations instead.
