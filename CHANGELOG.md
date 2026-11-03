# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/), and the
project adheres to [Semantic Versioning](https://semver.org/).

## [Unreleased]

### Added

- `--against REF...` compares against the merge base of `REF` and `HEAD`, so a
  branch that is behind `main` is not blamed for `main`'s newer changes.
- Allowlist targets may be globs, e.g. `"my_msgs/msg/State*"`.
- RS200 warns about allowlist entries and inline ignores that match no finding.

## [0.4.0] - 2026-11-03

### Added

- JSON findings link to their rule's documentation (`help_uri`).
- `roschema explain RULE` prints a rule's reference section.
- `check --verbose` and `bag-check --verbose` list the changes that are not
  reported (added, outside the level, rule off or suppressed) with the reason;
  JSON adds a `changes` array.
- `--summary FILE` appends a Markdown report; the Action writes it to the job
  summary, so every finding and the semver advice are visible even when GitHub
  truncates the annotations.

### Changed

- The semver advice suggests MINOR for a package that adds an interface or a
  constant, and is printed even when there are no findings.
- The coverage line names the first few new interfaces and says "new" and
  "removed" instead of "only in the target" and "only in the baseline".

## [0.3.0] - 2026-11-03

### Added

- Reports say how many interfaces were compared, and on which side the rest
  exist only (JSON: `coverage`).
- `--warnings-as-errors` for `check`, `bag-check` and `lint`, and the Action's
  `warnings-as-errors` input.

### Changed

- Python 3.14 is supported and tested.
- An empty baseline is an error (exit `2`) instead of a silent pass; pass
  `--allow-empty` (Action: `allow-empty`) when that is expected.

### Fixed

- `--format github` attaches findings with no new-side location, such as a
  removed field or a reorder, to the interface's file instead of leaving GitHub
  to show them against the workflow file.
- The Action uses `astral-sh/setup-uv@v10.3.3` (Node 24) with its cache off,
  removing the Node 20 deprecation and missing `uv.lock` warnings.

## [0.2.1] - 2026-11-03

### Added

- `docs/rules.md` opens with a one-line overview of every rule, and lint rules
  show flagged and preferred examples.
- `CONTRIBUTING.md` with the development checks and release process.

### Changed

- README restructured for new users: levels and severities, target resolution,
  suppression syntax, exit codes, Action inputs and troubleshooting.

## [0.2.0] - 2026-11-03

### Added

- `bag-check --level` and `--config`.
- Git baselines read initialised submodules at their recorded commit, and warn
  when that commit is not available locally.

### Changed

- `bag-check` reports at the `wire` level by default, since constant and other
  source-level changes do not stop current code decoding a recording.
- Package-name targets resolve to the workspace source package before the
  installed copy, with a warning when the installed copy is used.
- Adding or removing a sequence bound (`T[]` <-> `T[<=N]`) is reported as a
  bound change (RS007/RS008) rather than an array-kind change (RS006).
- RS110 takes the severity of the change it traces back to and ignores
  suppressed, allowlisted or disabled changes.
- Configuring a rule's severity no longer reports it outside the selected
  level; only rules that are off by default (such as RS060) bypass the level.
- The GitHub Action passes `--level` only when set, so configured levels apply.
- RS002 is tagged `wire` only, and RSL005 explains why `char` and scalar `byte`
  are ambiguous instead of calling them deprecated.

### Fixed

- `bag-check` skips schemas recorded without a definition and compares service
  event schemas (`SRV:` blocks) instead of failing.
- A same-package type written with its package (`pkg/Type` inside `pkg`) is no
  longer reported as a type change.
- Duplicate field or constant names are parse errors, as in rosidl.
- Unknown configuration keys are configuration errors, with a suggestion.
- `lint --format json` no longer includes semver advisories.
- Text output no longer wraps long lines when not writing to a terminal.
- Files are read and written as UTF-8 regardless of locale.
- GitHub annotation text is escaped.
- `wchar` in MCAP IDL schemas is rejected instead of narrowed to `char`.
- The README's GitHub Action example references an existing ref (`@main`).

## [0.1.3] - 2026-11-03

### Added

- `--version` / `-v` to display the installed package version.

### Fixed

- Pass GitHub Action inputs as literal arguments to prevent shell injection.
- Report tightened bounds even when another bound on the same field increases.
- Include deleted packages when checking glob targets against Git or directory
  baselines, including globs with parent traversal; reject path globs for lockfile
  and MCAP baselines.
- Reject unsupported, conflicting or unusable MCAP schemas instead of silently
  checking incomplete definitions, while preserving supported IDL string constants.
- Accept equivalent NaN constants and defaults when comparing repeated MCAP schemas.
- Replace each installed package's full interface set with its source target in
  `bag-check`, so deleted source interfaces are reported as removed.
- Honour workspace and package deep-check settings, with `--deep` / `--no-deep`
  taking precedence.
- Inherit enclosing workspace configuration when targeting a package directly,
  and apply package lint overrides from `roschema.toml` or `pyproject.toml`.
- Preserve root package settings in `bag-check` and after deleting its last interface.
- Reject unknown or misplaced rule identifiers and invalid configuration values.
- Detect unbounded string elements inside arrays and sequences with RSL006.

## [0.1.2] - 2026-11-03

### Fixed

- Respect `COLCON_IGNORE` and `AMENT_IGNORE` during package discovery to avoid
  reading generated build and install trees, including dangling package symlinks.

## [0.1.1] - 2026-07-25

Packaging and documentation release; no behavioural changes to the CLI.

### Added

- `py.typed` marker (PEP 561) so downstream type-checkers use roschema's types.
- `Typing :: Typed` and Python 3.10-3.13 classifiers; `Repository` and `Issues`
  project URLs.
- README: installation section, common-usage recipes, a demo screenshot, and a
  link to the [roschema-demo](https://github.com/justagist/roschema-demo) repo.

### Changed

- Dropped the redundant Apache license classifier in favour of the SPDX
  `license` expression.

### Fixed

- Removed a broken demo image reference from the README.

## [0.1.0] - 2026-07-24

First release.

### Added

- `check`: breaking-change detection against a git ref, directory, MCAP bag or
  lockfile baseline. Rules RS001-RS110 across the wire / source / introspection
  / behaviour compatibility levels, with cumulative `--level` presets and
  per-package semver bump advice.
- `lint`: rosidl-aligned naming and style rules (RSL001-RSL010), with `--rules`
  overrides.
- `fmt`: canonical, idempotent formatting that never changes what `check`
  reports; inline `# roschema: ignore=` suppressions survive formatting.
- `bag-check`: check a recorded MCAP bag against the current environment
  (ament index), with optional source targets overlaid.
- `freeze`: lockfile baselines for non-git distribution; `--deep` reports
  transitive breakage (RS110).
- `ls`: discovery diagnostics.
- Configuration via `roschema.toml` / `pyproject.toml`, inline suppression and
  reasoned allowlists; text / JSON / GitHub output formats; a composite GitHub
  Action.
