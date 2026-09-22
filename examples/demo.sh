#!/usr/bin/env bash
set -euo pipefail
TOOL="$(cd "$(dirname "$0")/../bin" && pwd)/repo-health"
DEMO_DIR="$(mktemp -d "${TMPDIR:-/tmp}/repo-health-demo.XXXXXXXX")"
trap 'rm -rf "$DEMO_DIR"' EXIT
for name in clean dirty; do
  git init -qb main "$DEMO_DIR/$name"
  git -C "$DEMO_DIR/$name" config user.name 'Example Fixture'
  git -C "$DEMO_DIR/$name" config user.email fixture@example.invalid
  git -C "$DEMO_DIR/$name" config commit.gpgsign false
  printf 'initial\n' >"$DEMO_DIR/$name/source.txt"
  git -C "$DEMO_DIR/$name" add source.txt
  git -C "$DEMO_DIR/$name" -c core.hooksPath=/dev/null commit -qm initial
  git -C "$DEMO_DIR/$name" branch retained
  git -C "$DEMO_DIR/$name" branch --set-upstream-to=retained main >/dev/null
done
printf 'local edit\n' >>"$DEMO_DIR/dirty/source.txt"
printf 'new file\n' >"$DEMO_DIR/dirty/untracked.txt"
"$TOOL" "$DEMO_DIR/clean" "$DEMO_DIR/dirty"
"$TOOL" --json "$DEMO_DIR/clean" "$DEMO_DIR/dirty"
