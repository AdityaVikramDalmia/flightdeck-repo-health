# Operational boundaries

The scanner invokes Git inspection commands only: `rev-parse`, `symbolic-ref`,
`show-ref`, `status`, `ls-files`, read-only `config --get`/`--get-all`, `for-each-ref`, and
`rev-list`. It does not fetch, push, checkout, stage, commit, prune, or alter refs.
No application state is written. Tests and the example use disposable fixtures.

Caller-provided `GIT_*` overrides are removed so a different `GIT_DIR`, index, or
worktree cannot silently redirect the selected input. Child Git commands receive
`GIT_OPTIONAL_LOCKS=0`, fsmonitor and hooks disabled, replacement objects disabled,
and prompting disabled. Git transports are forbidden with an empty
`GIT_ALLOW_PROTOCOL`; `GIT_NO_LAZY_FETCH=1` also suppresses automatic object fetching
on Git versions supporting it. This does not sandbox trusted Git extensions such
as configured clean filters. Do not use this tool to inspect hostile repositories.

Upstream comparisons use the configured local or remote-tracking ref already on
disk. Deleted remotes, missing mapping/ref data, and branches without upstreams
remain UNKNOWN. A remote-tracking ref can be stale. Shallow repositories expose
only available local history; this tool does not unshallow them or validate the
completeness/freshness of their history. Such comparisons include a visible
shallow-history warning. Inspection is not a full Git integrity
check. Warnings and failed object queries are surfaced rather than treated as zero.

Each Git subprocess has a timeout, default 10 seconds, configurable through
`--timeout`. That is a per-query budget, not a total scan budget. A large repository
can require substantial memory to enumerate status or traverse local history.
The tool does not recursively discover repositories or count ignored file contents.
Timed-out or interrupted queries are stopped together with helpers in their own
process group. A trusted extension that deliberately detaches into another process
group, or changes credentials beyond the scanner's signaling permissions, is
outside that cleanup boundary. Handled signals during process creation are
deferred until the newly created query can be cleaned up. SIGKILL cannot run cleanup. SIGTERM/SIGHUP return `128 + signal`;
keyboard interruption returns 130.

Multiple queries cannot establish an atomic snapshot while files, index entries,
or refs are changing. Stop writers if you need stable observations. The results
are descriptive; they do not establish that deleting a worktree, merging a branch,
or publishing code is safe.

Supported baseline: Python 3.9+ and Git 2.36+, with `make` for tests/installation.
The Git floor is checked before status/index queries and avoids older versions that interpret `core.fsmonitor=false` as a
hook pathname rather than a boolean; see the compatibility note in `git-config(1)`.
Validation uses macOS and an unprivileged Alpine Linux container, Python 3.14,
and synthetic Git fixtures with no network during tests.
The executable is pure Python standard library; Git remains a runtime dependency.
Windows has not been verified.

Git's split-index reader refreshes shared-index modification times even with
`GIT_OPTIONAL_LOCKS=0`. Before any index-reading query, the scanner checks
`core.splitIndex` and uses a filesystem directory listing for `sharedindex.*`
artifacts in the selected worktree's Git administration directory. Any such
configuration or artifact skips working-tree inspection with an UNKNOWN result;
the tool does not delete artifacts or convert the index. Directory-read failures
are inspection errors. Initialized submodules are checked recursively because
parent status can read their indexes despite `submodule.recurse=false`; no
submodule is initialized or fetched. Concurrent changes can race this preflight,
so the existing stable-repository requirement applies to submodules too.
