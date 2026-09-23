# Repo Health

Inspect several Git repositories with one read-only command: branch state,
working-tree changes, and ahead/behind counts against locally available upstream
refs, with missing information reported as **UNKNOWN** and a reason.

> **Status:** public Apache-2.0 reference implementation, deprecated for new Claude Code
> integrations as of 2026-09-22. Not a claim that Claude Code replaces every capability; no
> ongoing feature work or support is promised.

## What it does

- Takes explicit repository roots or subdirectories and resolves each to its
  working-tree root. It does not scan your machine or read a project roster. Inputs
  are reported in order, including repeated roots.
- Prints a table by default; `--json` prints one array with a record per input.
- Distinguishes attached branches, detached HEAD, and unborn branches (branches with
  no commit yet), and counts tracked entries, staged edits, unstaged edits, untracked
  files, and merge conflicts.

## Why it exists

A status summary that turns a missing upstream or a failed query into zeroes makes
an unknown repository look clean. Repo Health reports what it could not observe as
UNKNOWN, and inspection errors never become clean zeroes. It observes without
changing anything: no Git mutations, no fetch, optional index locks and
fsmonitor/hooks disabled, and Git transports forbidden during inspection.

## Install

Version 0.1.0rc1. Python 3.9+ and Git 2.36+ are required; there are no Python
packages or services to install. Windows is not a supported target yet.

```bash
git clone https://github.com/AdityaVikramDalmia/flightdeck-repo-health.git
cd flightdeck-repo-health
make install PREFIX="$HOME/.local"
export PATH="$HOME/.local/bin:$PATH"
```

The installed executable is self-contained. You can also invoke
`./bin/repo-health` directly.

## Quick use

```bash
bash examples/demo.sh
repo-health /path/to/project-one '/path with spaces/project-two'
repo-health --json /path/to/project-one /path/to/project-two
repo-health --timeout 5 --json . ../another-project
```

The demo builds a clean and a dirty fixture repository in a temporary directory and
prints both output forms.

## Output and exit codes

The default output is a table. JSON output is one array with a record per input. A
rename counts once; merge conflicts appear in the table's UNMERGED column.

Ahead/behind means commits reachable on only one side of the current HEAD and its
configured upstream comparison ref. An absent upstream, missing tracking ref,
detached HEAD, or unborn branch yields UNKNOWN sync and `null` counts.

Exit **0** means no inspection query failed; it can still include dirty or UNKNOWN
states. Exit **1** means at least one path/query failed; other inputs still have
results. Invalid CLI arguments return **2**.

See [the documentation index](docs/README.md), [JSON and count semantics](docs/output.md),
[operational boundaries](docs/boundaries.md), and [provenance](PROVENANCE.md).

## Limits

- Ahead/behind uses **local refs only**: no fetch occurs, and `equal` does not
  establish that a remote server is current.
- Shallow-history comparisons carry a visible warning because truncated ancestry can
  change the locally observed counts.
- Consumers must inspect the fields, not treat exit 0 as permission to merge,
  delete, or publish.
- Split-index configurations or shared-index artifacts yield UNKNOWN working-tree
  counts: Git can refresh their timestamps during an otherwise read-only query.
  Initialized submodules are checked for the same condition before parent status
  runs. Branch/upstream observations remain available.
- Use trusted repositories: configured clean filters can execute arbitrary code, so
  this is not a sandbox or a guarantee about malicious configuration.
- Multiple Git calls are observations, not an atomic snapshot; concurrent writers
  can invalidate them.

## Test

```bash
make test
```

macOS and an unprivileged Alpine Linux container have been verified.

## License and maintenance

Copyright 2026 Aditya Dalmia. Licensed under [Apache-2.0](LICENSE), with
[attribution](NOTICE) and [source provenance](PROVENANCE.md). This is a public
reference implementation, deprecated for new Claude Code integrations as of 2026-09-22. See the [release preparation index](docs/release/README.md),
[contributing guide](CONTRIBUTING.md), and [security contact](SECURITY.md).
