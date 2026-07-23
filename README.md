# roschema

Catch breaking ROS 2 interface changes in the PR, not on the robot.

`roschema` detects breaking changes, lints and formats ROS 2 interface
definitions (`.msg`, `.srv`, `.action`) with zero ROS dependencies, so it runs
in a bare CI container.

> Work in progress. See `docs/decisions.md` for build status; the full README
> (quickstart, compatibility-level table, rule reference, CI snippet) lands with
> later phases.
