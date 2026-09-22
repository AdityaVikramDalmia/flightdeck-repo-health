# Output and count semantics

`repo-health --json PATH [PATH ...]` prints one JSON array. Every explicit input
gets one row, including missing and invalid directories. No implicit discovery,
roster, aliases, project names, or global session metadata is involved.

| Field | Meaning |
| --- | --- |
| `input` | The input path spelling |
| `path` | Git working-tree root, or `null` if unavailable |
| `state` | `branch`, `detached`, `unborn`, or `unknown` |
| `branch` | Local branch name when identifiable |
| `head` | Resolved commit ID; `null` for unborn or failed resolution |
| `cleanliness` | `clean`, `dirty`, or `unknown` |
| `counts` | Observed working-tree counts, or `null` when unreliable |
| `upstream` | Full locally resolved upstream ref, or `null` |
| `upstream_remote` / `upstream_merge` | Configured remote and first merge target used by Git's upstream comparison |
| `sync` | `equal`, `ahead`, `behind`, `diverged`, or `unknown` |
| `ahead` / `behind` | Commit counts, or `null` when unknown |
| `sync_reason` | Scope or reason the comparison was unavailable |
| `warnings` / `errors` | Explicit limitations and failed inspections |

`counts.tracked` counts changed tracked status entries. `staged` counts entries
changed in the index; `unstaged` counts entries changed in the working tree. One
file can be both staged and unstaged, so these counts are not additive. A rename
is one entry even though Git names its source and destination. `unmerged` counts
conflict entries. `untracked` counts Git's non-ignored untracked file entries with
`--untracked-files=all`; nested Git repositories may appear as a directory entry.
Submodule changes are reported as changed submodule entries, not recursively as
individual files. Ignored files and empty directories are excluded.

Assume-unchanged and skip-worktree index flags can conceal modifications. If
present, cleanliness and counts become UNKNOWN, even if visible status is empty.
This includes ordinary sparse checkouts. Git queries that emit stderr diagnostics are treated conservatively as inspection
failures, including an otherwise expected missing-value exit code. A diagnostic
cannot silently become an absent upstream or detached branch.

A failed status query leaves branch/upstream information available if those
queries succeeded. A failed comparison leaves working-tree information available.
A bad input does not cancel subsequent repositories. `errors` determines exit 1;
expected absent upstream state and known index-flag limitations use UNKNOWN with
an explanation and do not alone cause exit 1.

The table escapes control characters, non-ASCII characters, and column delimiters
inside values, so a newline in a directory name does not create a fake extra row.
JSON preserves original strings through ordinary JSON escaping. Neither format
is a freshness guarantee or a transactional authorization for later actions.

Split-index configurations, residual `sharedindex.*` artifacts, or an initialized
submodule with either condition leave working-tree counts and cleanliness UNKNOWN.
The scanner skips index-reading status queries rather than allowing Git to refresh
shared-index timestamps. Residual artifacts can therefore cause conservative
UNKNOWN results even after conversion back to an ordinary index.

A branch with multiple configured merge targets compares Git's first upstream,
and `upstream_merge` reports that same target. A warning names the limitation;
other merge targets are not included in the ahead/behind calculation. Shallow
repositories also carry an explicit warning: counts reflect their truncated
local history and are not a claim about the complete ancestry graph.
