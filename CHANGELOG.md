# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/), and the
project adheres to [Semantic Versioning](https://semver.org/).

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
