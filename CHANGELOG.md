# Changelog

The format follows [Keep a Changelog](https://keepachangelog.com/), and the
project adheres to [Semantic Versioning](https://semver.org/).

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
