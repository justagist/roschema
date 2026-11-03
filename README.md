# roschema

[![CI](https://github.com/justagist/roschema/actions/workflows/ci.yml/badge.svg)](https://github.com/justagist/roschema/actions/workflows/ci.yml)
[![PyPI](https://img.shields.io/pypi/v/roschema.svg)](https://pypi.org/project/roschema/)
[![Python versions](https://img.shields.io/pypi/pyversions/roschema.svg)](https://pypi.org/project/roschema/)
[![License: Apache-2.0](https://img.shields.io/badge/License-Apache_2.0-blue.svg)](LICENSE)
[![Ruff](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/ruff/main/assets/badge/v2.json)](https://github.com/astral-sh/ruff)
[![Checked with mypy](https://img.shields.io/badge/mypy-strict-blue.svg)](https://mypy-lang.org/)

Catch breaking ROS 2 interface changes in the PR, not on the robot.

`roschema` detects breaking changes, lints and formats ROS 2 interface
definitions (`.msg`, `.srv`, `.action`) with zero ROS dependencies, so it runs
in a bare CI container.

![roschema flagging a breaking interface change](https://raw.githubusercontent.com/justagist/_assets/main/roschema/roschema_demo.png)

## Quickstart

Test it without installing (expects `uvx` is present):

```bash
# in a pull request, compare the working tree against the base branch
uvx roschema check --against origin/main
```

See the full [rule reference](docs/rules.md) for every check (`RS***`) and lint
(`RSL***`) rule.

Prefer a runnable example? The [roschema-demo](https://github.com/justagist/roschema-demo)
repo has a `robot_msgs` package with a passing and a failing branch to compare,
plus a ready-to-copy GitHub Action workflow.

## Installation

Requires Python 3.10+ (ROS installation **not** necessary).

```bash
pip install roschema              # or: uv tool install roschema
pip install 'roschema[bag]'       # optional: MCAP bag support (for bag-check)
```

Or run it without installing anything using `uvx`:

```bash
uvx roschema check --against origin/main
```

Using roschema as a [GitHub Action](#github-action) needs **no installation or
setup** - the action provisions it on the runner for you.

## Common usage

```bash
# breaking-change gate in a PR (compare against the base branch)
roschema check --against origin/main

# check before pushing, against the last commit
roschema check --against HEAD

# scope to one package, or a subtree with a glob (and exclude vendored packages)
roschema check src/my_msgs --against origin/main
roschema check 'src/**' --against origin/main --exclude 'vendor_*'

# only fail on wire-level breaks (loosest gate)
roschema check --against origin/main --level wire

# machine-readable output for tooling
roschema check --against origin/main --format json

# style/naming check, and a formatting gate for CI
roschema lint
roschema fmt --check

# pin a release baseline, then check against it later (no git needed)
roschema freeze -o roschema.lock
roschema check --against roschema.lock

# is this recorded bag still compatible with the installed interfaces?
roschema bag-check recording.mcap
```

## Checking

```
roschema check [TARGET] --against REF [--level LEVEL] [--format text|json|github]
               [--deep] [--exit-zero] [--config PATH] [--exclude GLOB]
```

`TARGET` is a path, a package name, or a glob (`'src/**'`) that expands to every
package underneath; omit it for the current workspace. Discovery skips trees
marked with `COLCON_IGNORE` or `AMENT_IGNORE`, including standard colcon build
and install directories. Glob targets include matching packages deleted from a Git
or directory baseline. Lockfile and MCAP baselines have synthetic paths; use a
workspace target with those baselines instead of a path glob.

`--against` accepts a git ref (validated with `git rev-parse`), a directory, an
MCAP bag (`.mcap`) or a lockfile (`roschema.lock`); the type is auto-detected. A
git ref is preferred when a directory of the same name also exists -- prefix the
argument with `./` (e.g. `--against ./main`) to force the directory. Exit codes:
`0` clean, `1` breaking changes found, `2` tool/usage error. `--exit-zero` forces
`0`. Warnings alone do not fail (exit `0`).

CDR is positional -- fields are serialised in declaration order with no field
tags -- so adding, removing, reordering or retyping a field is wire-breaking
even when your code still compiles. That is why the taxonomy is structural, and
why the default `source` level already reports wire-level changes.

## Freeze (non-git baselines)

```
roschema freeze [TARGET] -o roschema.lock
roschema check  [TARGET] --against roschema.lock
```

`freeze` writes a lockfile holding each interface's canonical (post-`fmt`) text
plus a sha256, so a release tarball can carry its own baseline without git.
`check --against roschema.lock` reads it back (sha256-verified) and compares.

The lockfile records the roschema `tool_version` for provenance; upgrading
roschema therefore changes that one line on the next `freeze` even when the
interfaces are identical. It is not read during comparison -- `check` diffs only
the interface text -- so the churn is cosmetic.

## Deep checking

`check --deep` resolves nested complex types through the workspace and ament
index and reports transitive breakage (`RS110`): an interface that embeds -
directly or through nested types - another whose wire layout changed is flagged
even when its own definition is unchanged, with the causal chain shown. Without
`--deep`, nested types are compared by name only.

## Linting and formatting

```
roschema lint [TARGET] [--format text|json|github] [--rules RULE=SEV] [--exit-zero]
roschema fmt  [TARGET] [--check]
```

`lint` checks a single tree (no baseline). Naming rules follow rosidl: field
names snake_case (RSL001), constants UPPER_SNAKE (RSL002), interface names
PascalCase (RSL003); it also flags deprecated `char`/scalar-`byte` (RSL005) and
request/response field shadowing in services (RSL010). RSL004 (missing doc) and
RSL006 (unbounded) are off by default; enable via `[lint.rules]` or per run with
`--rules` (e.g. `--rules RSL004=warn --rules RSL001=off`; a bare `--rules RSL004`
means `=warn`). `--rules` is repeatable and beats config.

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
its installed copy. Each source package replaces its entire installed interface
set, so deleted source interfaces are reported as removed even when an installed
copy remains. If targets overlap, the last target wins for that package. A bag
type found in neither the environment nor any target
is reported as removed (RS040). `ros2msg` schemas (including concatenated
dependent definitions) are fully supported; `ros2idl` is a best-effort
conversion of the msg-equivalent subset. Unsupported encodings or IDL constructs,
conflicting definitions of the same type (including embedded dependencies), and
bags without usable ROS schemas produce a tool error (exit `2`). Equivalent
definitions that differ only in formatting or comments are accepted.

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
defaults. Workspace discovery searches upwards to the Git repository root, or
the filesystem root outside Git. Package configurations override inherited
workspace values even when checking the package directly by path. At each
directory, `roschema.toml` takes precedence over `[tool.roschema]`.

```toml
[check]
level = "source"
deep = false          # --deep / --no-deep overrides this

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

## GitHub Action

A composite action wraps `uvx roschema check` and posts inline annotations on
the PR diff:

```yaml
# .github/workflows/interfaces.yml
on: pull_request
jobs:
  interfaces:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
        with:
          fetch-depth: 0            # needed for the git-ref baseline
      - uses: justagist/roschema/action@v1
        with:
          against: origin/${{ github.base_ref }}
          # level: source
          # deep: "true"
          # exclude: "vendor_msgs* legacy_msgs/msg/Old"
```

`against` takes the same values as the CLI (git ref, directory, `.mcap`,
`roschema.lock`). A lockfile or directory baseline needs no `fetch-depth: 0`
because it is a plain file in the checkout.

## Rule reference

Every rule, its levels, default severity and rationale is documented in
[docs/rules.md](docs/rules.md), generated from the rule metadata with
`python -m roschema.rules.gendocs`.

## Non-goals

roschema deliberately does **not**:

- generate migration or translation rules;
- parse ROS 1 `.msg` (md5 semantics differ);
- parse hand-written `.idl` beyond the MCAP-embedded subset;
- provide any registry or server component;
- parse `CMakeLists.txt` for discovery (directory convention + ament index only).

## Relationship to REP-2011 and type hashes

These are complementary layers, not alternatives:

- **roschema** prevents *accidental* breaks at PR time, before anything ships.
- **RIHS type hashes** (REP-2011) detect a pub/sub *mismatch at runtime* -- after
  the fact, on the robot.
- **REP-2011 type-description distribution / translation** mitigates *intentional*
  evolution by carrying enough information to translate between versions.

roschema is the earliest gate: catch the break in review so the later layers
never have to.
