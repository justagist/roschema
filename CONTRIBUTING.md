# Contributing

## Setup

roschema uses [uv](https://docs.astral.sh/uv/):

```bash
uv sync --extra dev --extra bag
```

## Checks

CI runs these on every pull request; run them before pushing:

```bash
uv run pytest
uv run ruff check .
uv run ruff format --check .
uv run mypy --strict src
uv run python -m roschema.rules.gendocs --check
```

The tests do not need ROS and work in a shell with a ROS environment sourced:
`pyproject.toml` disables the ROS launch pytest plugins, which cannot be
imported in the roschema virtualenv.

Every fix or feature should come with a test that fails without it.

## Rules

Each rule lives in its own module under `src/roschema/rules/breaking/` (check
rules, `RS***`) or `src/roschema/rules/lint/` (lint rules, `RSL***`) and is
registered in that package's `__init__.py`. Rule IDs are permanent: never
renumber or reuse one.

`docs/rules.md` is generated from the rule metadata. After changing a rule,
regenerate it:

```bash
uv run python -m roschema.rules.gendocs
```

## Releases

1. Bump `version` in `pyproject.toml` and turn the `[Unreleased]` section of
   `CHANGELOG.md` into a dated `[X.Y.Z]` section.
2. Merge to `main`.
3. Tag the merge commit and push the tag:

   ```bash
   git tag -a vX.Y.Z -m "Release X.Y.Z"
   git push origin vX.Y.Z
   ```

The release workflow then checks that the tag matches the package version, runs
the checks, builds the sdist and wheel, and publishes them to PyPI.
