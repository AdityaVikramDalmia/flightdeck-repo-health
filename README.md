# Repo Health

Inspect several Git repositories with one read-only command. See branch state,
working-tree changes, and ahead/behind counts against locally available upstream
refs. Missing information is **UNKNOWN**, with a reason.

**Private release candidate: 0.1.0rc1.** Python 3.9+ and Git 2.36+ are required;
there are no Python packages or services to install. macOS and an unprivileged
Alpine Linux container have been verified. Windows is not a supported target yet.

## Install and run

From this checkout:

```bash
make test
make install PREFIX="$HOME/.local"
export PATH="$HOME/.local/bin:$PATH"

repo-health /path/to/project-one '/path with spaces/project-two'
repo-health --json /path/to/project-one /path/to/project-two
```

The installed executable is self-contained. You can also invoke
`./bin/repo-health` directly. Supply explicit repository roots or subdirectories;
the tool resolves each to its working-tree root. It does not scan your machine or
read a project roster. Inputs are reported in order, including repeated roots.

```bash
repo-health --timeout 5 --json . ../another-project
bash examples/demo.sh
```

The default output is a table. JSON output is one array with a record per input.
A record distinguishes attached branches, detached HEAD, and unborn branches
(branches with no commit yet). Counts distinguish tracked entries, staged edits,
unstaged edits, untracked files, and merge conflicts (the table's UNMERGED column). A rename counts once.

Ahead/behind means commits reachable on only one side of the current HEAD and its
configured upstream comparison ref. It uses **local refs only**: no fetch occurs,
and `equal` does not establish that a remote server is current. An absent upstream,
missing tracking ref, detached HEAD, or unborn branch yields UNKNOWN sync and
`null` counts. Shallow-history comparisons carry a visible warning because
truncated ancestry can change the locally observed counts. Inspection errors
never become clean zeroes.

Exit **0** means no inspection query failed; it can still include dirty or UNKNOWN
states. Exit **1** means at least one path/query failed; other inputs still have
results. Invalid CLI arguments return **2**. Consumers must inspect the fields,
not treat exit 0 as permission to merge, delete, or publish.

Split-index configurations or shared-index artifacts yield UNKNOWN working-tree
counts: Git can refresh their timestamps during an otherwise read-only query.
Initialized submodules are checked for the same condition before parent status
runs. Branch/upstream observations remain available.

The scanner performs no Git mutations, disables optional index locks and
fsmonitor/hooks, and forbids Git transports during inspection. Use trusted
repositories: configured clean filters can execute arbitrary code, so this is
not a sandbox or a guarantee about malicious configuration. Multiple Git calls
are observations, not an atomic snapshot; concurrent writers can invalidate them.

See [the documentation index](docs/README.md), [JSON and count semantics](docs/output.md),
[operational boundaries](docs/boundaries.md), and [provenance](PROVENANCE.md).
