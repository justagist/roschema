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

From the root of your workspace or repository, compare the working tree against
the base branch (needs [`uv`](https://docs.astral.sh/uv/); nothing else to
install):

```bash
uvx roschema check --against origin/main
```

roschema finds every interface package below the current directory, compares
it with the same packages at `origin/main`, and lists each breaking change with
its rule ID, location and a suggested semver bump. It exits `1` when an error is
found, so it works as a CI gate as is; to run it on every pull request, use the
[GitHub Action](#github-action).

Next steps:

- [What gets reported](#what-gets-reported) explains levels and severities.
- The [rule reference](docs/rules.md) lists every check (`RS***`) and lint
  (`RSL***`) rule, starting with a one-line overview of each.
- The [roschema-demo](https://github.com/justagist/roschema-demo) repo has a
  `robot_msgs` package with a passing and a failing branch to compare, plus a
  ready-to-copy workflow.

## Installation

Requires Python 3.10+; a ROS installation is **not** needed.

```bash
uv tool install roschema            # or: pipx install roschema
uv tool install 'roschema[bag]'     # with MCAP bag support, for bag-check
```

Inside a virtualenv, `pip install roschema` works too. Outside one, Ubuntu 24.04
(the Jazzy platform) refuses `pip install` into the system Python
("externally-managed-environment", PEP 668), so prefer `uv tool` or `pipx`.

To run it without installing anything, use `uvx roschema ...` as in the
quickstart. The [GitHub Action](#github-action) needs no installation either.

## What gets reported

CDR, the ROS 2 wire format, is positional: fields are serialised in declaration
order with no field tags. Adding, removing, reordering or retyping a field
therefore breaks the wire format even when your code still compiles, so
roschema compares interfaces structurally rather than by text.

Every rule belongs to one or more **compatibility levels**. `--level` picks a
cumulative bundle of levels to report; the default is `source`.

| Level | Reports | Example |
|---|---|---|
| `wire` | CDR byte-stream compatibility only | a field added (RS002) |
| `source` | wire + generated C++/Python API | a constant removed (RS020) |
| `introspection` | source + name-based tooling (bags, echo, YAML) | a field renamed (RS005) |
| `behavior` | introspection + semantics (defaults, constant values) | a default changed (RS030) |

Levels decide **what is reported**; each rule's **severity** (`error`, `warn`
or `off`) decides whether a reported finding fails the run. Only errors fail;
warnings are printed but exit `0`. Rules that are off by default (such as RS060)
are reported at every level once you enable them.

The [rule overview](docs/rules.md#overview) shows each rule's levels and default
severity in one table.

## Common usage

```bash
# breaking-change gate in a PR (compare against the base branch)
roschema check --against origin/main

# check before pushing, against the last commit
roschema check --against HEAD

# only this branch's changes, even if main has moved on since it was cut
roschema check --against origin/main...

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

# what would be checked? (discovered packages and interfaces)
roschema ls

# what does a rule report, and why?
roschema explain RS004
```

## Checking

```
roschema check [TARGET] --against BASELINE [--level LEVEL] [--format text|json|github]
               [--deep | --no-deep] [--exit-zero] [--warnings-as-errors] [--allow-empty]
               [--verbose] [--summary FILE] [--config PATH] [--exclude GLOB]
```

`TARGET` selects what to check; omit it to check every interface package below
the current directory.

- **A path** checks the packages below that directory.
- **A package name** (its `<name>` in `package.xml`) checks that package's
  source below the current directory. If there is no such source package, the
  installed copy from the ament index (`AMENT_PREFIX_PATH`) is used, with a
  warning.
- **A glob** such as `'src/**'` checks every package below the matching
  directories, including packages that exist only in a Git or directory
  baseline (so deleting a package is reported).

Discovery skips trees marked with `COLCON_IGNORE` or `AMENT_IGNORE`, which
includes colcon's `build/`, `install/` and `log/` directories.

`--against` accepts a git ref (validated with `git rev-parse`), a directory, an
MCAP bag (`.mcap`) or a lockfile (`roschema.lock`); the type is detected
automatically. Initialised git submodules are compared at the commit the
baseline records for them.

`REF...` (three dots, as in `git diff REF...`) compares against the merge base
of `REF` and `HEAD`, the commit the branch started from. Without it, interfaces
added on `main` after a branch was cut look removed on the branch. In a pull
request's CI, `actions/checkout` already builds the merge with the base branch,
so a plain `origin/main` is enough there.

Every report says how much was compared, for example `compared 12 interface(s)
in 3 package(s); 1 new (my_msgs/msg/Status)`. New interfaces are not findings,
since adding one breaks nothing; the line names the first few so that an
unexpected one (say, from an unrelated checkout below the target) is easy to
spot. A baseline with no interfaces at all is
an error (exit `2`): every current interface would look newly added, so the
check would pass without comparing anything. That usually means the wrong
baseline or target; on the pull request that adds the first interfaces, pass
`--allow-empty`.

Limitations:

- When a git ref and a directory share a name, the git ref wins; prefix the
  directory with `./` (`--against ./main`) to use it instead.
- Lockfile and MCAP baselines have no real paths, so use a workspace or package
  target with them rather than a path glob.
- A submodule whose recorded commit is not available locally (for example after
  a shallow fetch) is skipped with a warning.

### Deep checking

Without `--deep`, an embedded type is compared by name only. `check --deep`
resolves nested types through the workspace and the ament index and reports
transitive breakage (RS110): an interface that embeds, directly or through other
types, a type whose wire layout changed is flagged even when its own definition
did not change, with the chain that connects them. RS110 takes the severity of
the change it traces back to, and suppressed or allowlisted changes are not
followed.

## Linting and formatting

```
roschema lint [TARGET] [--format text|json|github] [--rules RULE=SEV] [--exit-zero]
              [--warnings-as-errors] [--config PATH] [--exclude GLOB]
roschema fmt  [TARGET] [--check] [--exclude GLOB]
```

`lint` checks a single tree, with no baseline. The naming rules follow rosidl:
field names in snake_case (RSL001), constants in UPPER_SNAKE_CASE (RSL002) and
interface names in PascalCase (RSL003). It also flags ambiguous `char` and
scalar `byte` types (RSL005) and fields shared by a service's request and
response (RSL010). RSL004 (missing documentation) and RSL006 (unbounded
fields) are off by default. Enable rules in `[lint.rules]`, or per run with
`--rules`, e.g. `--rules RSL004=warn --rules RSL001=off` (a bare `--rules RSL004`
means `=warn`). `--rules` is repeatable and overrides configuration.

`fmt` formats interface files canonically: a single space between type and
name, no spaces around a constant's `=`, two spaces before a trailing comment
and one trailing newline. Comments, blank lines and section separators are kept,
and so are inline `# roschema: ignore=` suppressions. Formatting is idempotent
and never changes what `check` reports; `fmt --check` exits `1` if any file
would change.

## Freeze (baselines without git)

```
roschema freeze [TARGET] -o roschema.lock
roschema check  [TARGET] --against roschema.lock
```

`freeze` writes a lockfile with each interface's canonical (formatted) text and
its sha256, so a release tarball can carry its own baseline. `check --against
roschema.lock` verifies the hashes and compares against it.

The lockfile also records the roschema `tool_version`, so upgrading roschema
changes that one line on the next `freeze` even when the interfaces are the
same. Comparison ignores it.

## Checking against a recorded bag

```
roschema bag-check BAG.mcap [TARGETS...] [--level LEVEL] [--config PATH]
                   [--format text|json|github] [--exit-zero] [--warnings-as-errors]
                   [--verbose] [--summary FILE] [--exclude GLOB]
```

Needs the `bag` extra (`uv tool install 'roschema[bag]'`).

`bag-check` uses the interface definitions recorded in an MCAP bag as the
baseline and asks whether **current code can still decode the recording**. It
therefore reports at the `wire` level by default; pass `--level` (or set
`[check] level`) to include source-level changes such as removed constants.

The bag's types are compared with the packages installed in the sourced
environment (the ament index), so system packages such as `sensor_msgs` are
compared with their installed definitions. Optional `TARGETS` (paths or package
names) replace the installed copy of their packages with your source: a package
you are editing is checked as it is now, and interfaces you deleted from it are
reported as removed. If two targets provide the same package, the last one
wins. A bag type found neither in the environment nor in a target is reported
as removed (RS040).

Limitations:

- `ros2msg` schemas are fully supported, including the concatenated definitions
  of dependent types and the `SRV:` blocks recorded for service event topics.
- `ros2idl` schemas are converted on a best-effort basis for the subset that has
  a `.msg` equivalent. Other encodings and IDL constructs (enums, unions,
  typedefs, annotations, inheritance, constants outside structs, `wchar`) are a
  tool error (exit `2`).
- Topics recorded without a definition (rosbag2 leaves them empty when it cannot
  find one) are skipped and named in a note.
- Two different definitions of the same type in one bag are a tool error.
  Definitions that differ only in formatting or comments are accepted.

## Configuration

Settings come from `roschema.toml`, or from `[tool.roschema]` in
`pyproject.toml`. A file at the workspace root applies to every package, and a
file in a package directory overrides it for that package. Precedence is CLI >
package > workspace > defaults. roschema looks for the workspace file in the
target directory and its parents, up to the git repository root (or the
filesystem root outside git). In each directory, `roschema.toml` takes
precedence over `pyproject.toml`.

```toml
[check]
level = "source"       # wire | source | introspection | behavior
deep = false           # --deep / --no-deep overrides this

[check.rules]
RS008 = "off"          # off | warn | error

[check.allow]
# an intentional break: a fully-qualified target and a mandatory reason
"my_msgs/msg/State.old_field" = { rules = ["RS001"], reason = "removed in 2.0, see #142" }

[lint.rules]
RSL004 = "warn"
```

Unknown keys, unknown rule IDs (or IDs in the wrong section) and invalid values
are configuration errors (exit `2`), so a misspelt setting cannot silently do
nothing. Setting a rule's severity does not change which levels are reported,
except for rules that are off by default (see
[What gets reported](#what-gets-reported)).

### Suppressing findings

Suppressed findings are counted in the summary but never fail the run.

**Inline:** a trailing comment on the member line in the new version, e.g.
`float64 theta  # roschema: ignore=RS003`. Separate several IDs with commas.
This works for lint rules too.

**Allowlist:** an entry in `[check.allow]`, keyed by the finding's target:

```
<package>/<kind>/<Name>[.<section>][.<member>]
```

- `<kind>` is `msg`, `srv` or `action`.
- `<section>` is given for services (`request`, `response`) and actions (`goal`,
  `result`, `feedback`) only, e.g. `my_srvs/srv/SetMode.request.mode`.
- Findings about a whole interface or section (RS040 interface removed, RS110,
  RS004 fields reordered) have no `<member>`, e.g. `my_msgs/msg/Old`.

`reason` is required. `rules` limits the entry to those rule IDs; omit it to
allow every rule for that target.

A target may be a glob, to allow a planned break across a whole interface or
package without listing every member: `*` matches any run of characters
(including `/` and `.`), `?` one character and `[abc]` one of a set. For
example `"my_msgs/msg/State*"` covers `State` itself and all its members, and
`"vendor_msgs/*"` everything in that package.

`check` warns (RS200) about an allowlist entry or inline check ignore that no
longer matches any finding, e.g. once the baseline has moved past the break, so
stale suppressions do not hide a later one. Remove the entry, or set
`RS200 = "off"` in `[check.rules]`.

## Output

**Text** (the default) starts with what was compared, groups findings by
package and ends with a summary and a semver advice per package:

- **MAJOR** when the package has a wire- or source-level error;
- **MINOR** when it adds an interface or a constant (neither is a finding,
  since neither breaks anything), or an added field (RS002) whose severity you
  lowered to `warn`;
- **PATCH** otherwise.

**`--verbose`** also lists, under "not reported", every change that produced no
reported finding, and why: a new interface or constant (no rule reports either,
at any level; an added field is RS002), a rule whose level is outside the one
being checked, a rule that is off, or a suppression, with the allowlist reason.
Comment-only edits are not changes, so they never appear.

**`--format github`** prints what was compared, then emits `::error`/`::warning`
workflow commands, which GitHub shows as annotations on the PR diff.

**`--summary FILE`** appends a Markdown report to `FILE` as well, whatever the
`--format`: what was compared, a table of findings linked to the rule
reference, the semver advice, and the unreported changes in a collapsed
section. Pointed at `$GITHUB_STEP_SUMMARY`, it becomes the job summary, which
matters because GitHub shows only the first 10 error and 10 warning annotations
of a step.

**`--format json`** emits a stable document (`version: 1`):

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
      "suppressed": false,
      "help_uri": "https://github.com/justagist/roschema/blob/v0.5.0/docs/rules.md#rs003----field-type-changed"
    }
  ],
  "summary": {
    "total": 1,
    "errors": 1,
    "warnings": 0,
    "suppressed": 0,
    "advisories": { "my_msgs": "MAJOR" }
  },
  "coverage": {
    "packages": 1,
    "compared": 1,
    "target_only": 0,
    "baseline_only": 0
  }
}
```

`old`/`new` are `null` when there is no corresponding side (a removed interface
has no `new`). `coverage` counts interfaces present on both sides (`compared`)
and on one side only. `help_uri` links to the rule's section of the
[rule reference](docs/rules.md) for the installed release. With `--verbose`, a
`changes` array lists the unreported changes (each with `rule`, `package`,
`interface`, `section`, `target`, `message` and `reason`), including suppressed
findings with the reason they are suppressed. `lint` output has no
`advisories`, `coverage` or `changes`.

## Exit codes

| Code | `check`, `bag-check`, `lint` | `fmt --check` | Other commands |
|---|---|---|---|
| `0` | no unsuppressed errors (warnings allowed) | every file formatted | success |
| `1` | at least one unsuppressed error | a file would change | n/a |
| `2` | tool or usage error (bad target, baseline, configuration or file, or an empty baseline) | tool or usage error | tool or usage error |

`--warnings-as-errors` makes unsuppressed warnings exit `1` too. `--exit-zero`
turns `1` into `0` for `check`, `bag-check` and `lint`; tool errors still exit
`2`.

## GitHub Action

A composite Action runs `roschema check` on the runner (no setup needed) and
posts the findings as annotations on the PR diff, with a full report (findings,
semver advice and unreported changes) as the job summary:

```yaml
# .github/workflows/interfaces.yml
on: pull_request
jobs:
  interfaces:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v7
        with:
          fetch-depth: 0            # needed for the git-ref baseline
      - uses: justagist/roschema/action@main
        with:
          against: origin/${{ github.base_ref }}
          # version: "roschema==0.5.0"   # pin a release for reproducible results
          # level: source
          # deep: "true"
          # warnings-as-errors: "true"
          # exclude: "vendor_msgs* legacy_msgs/msg/Old"
```

| Input | Default | Meaning |
|---|---|---|
| `target` | `.` | path, package name or glob, as for the CLI |
| `against` | `origin/main` | git ref, directory, `.mcap` bag or `roschema.lock` |
| `level` | (empty) | reporting level; empty uses the configured level, else `source` |
| `format` | `github` | `text`, `json` or `github` |
| `deep` | `"false"` | `"true"` adds `--deep` |
| `allow-empty` | `"false"` | `"true"` adds `--allow-empty` |
| `warnings-as-errors` | `"false"` | `"true"` adds `--warnings-as-errors` |
| `exclude` | (empty) | whitespace-separated globs passed as `--exclude` |
| `version` | `roschema` | the roschema requirement installed with `uvx` |

By default the Action installs the latest roschema release on every run, so new
rules can change results without any change on your side. Set `version` to pin
a release instead. A lockfile or directory baseline needs no `fetch-depth: 0`,
because it is part of the checkout.

## pre-commit

roschema ships [pre-commit](https://pre-commit.com/) hooks. Each runs on the
whole repository: `roschema-check` on every commit, so a commit that only
deletes an interface is checked too, and the others when an interface file is
staged.

```yaml
# .pre-commit-config.yaml
repos:
  - repo: https://github.com/justagist/roschema
    rev: v0.5.0
    hooks:
      - id: roschema-check   # staged changes against the last commit
      - id: roschema-lint
      - id: roschema-fmt     # rewrites files; re-stage them and commit again
```

`args` replaces a hook's arguments, e.g.
`args: [--against, HEAD, --allow-empty, --level, wire]` for `roschema-check`.
`--allow-empty` lets the commit that adds the first interfaces pass.

## Troubleshooting

**"no breaking changes found", but you expected some.** The line under the
header says how many interfaces were compared, and `--verbose` lists the changes
that were seen but not reported, with the reason. Run `roschema ls` with the
same target to see which packages and interfaces are discovered, then check
that:

- the packages are not below a `COLCON_IGNORE` or `AMENT_IGNORE` marker;
- a package-name target did not fall back to the installed copy (the warning
  says so); run from the directory that contains the source, or pass its path;
- packages in git submodules were not skipped (the warning names any submodule
  whose baseline commit is missing; fetch it with `git submodule update`);
- the change's level is included: a constant change is not reported under
  `--level wire`, and `bag-check` defaults to `wire`.

**A configuration error names an unknown key.** Each table accepts only the keys
shown in [Configuration](#configuration); the error suggests the closest one.

## Rule reference

Every rule, its levels, default severity, rationale and an example is
documented in [docs/rules.md](docs/rules.md), generated from the rule metadata.
`roschema explain RULE` prints the same section in the terminal.

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

## Contributing

See [CONTRIBUTING.md](CONTRIBUTING.md) for the development setup, checks and
release process.
