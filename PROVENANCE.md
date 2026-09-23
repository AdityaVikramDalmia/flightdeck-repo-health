# Provenance

Source commit: `494799eea3b9e7ce8686506a288c297ccf96be8d`.

The behavioral starting point is `bin/project-status.sh`, specifically its
per-repository Git status and upstream-ahead observations. This standalone tool
rewrites those observations in Python standard library code. It adds detached and
unborn states, behind/diverged comparisons, exact NUL-delimited status counting,
explicit input paths, JSON output, error/UNKNOWN distinctions, and read-only Git
execution controls.

The source's roster and repository-discovery helpers are deliberately not copied.
Agent attribution, issue tracking, orientation-file/session-log scans, private
project defaults, and external runtime integrations are outside this component.

This is a substantial standalone adaptation, not a verbatim copy of the original
Bash implementation. No original private remote or personal path is required.
The owner selected Apache-2.0 on 2026-09-22. See LICENSE and NOTICE. The repository is a public reference implementation, deprecated for new Claude Code integrations as of 2026-09-22.
