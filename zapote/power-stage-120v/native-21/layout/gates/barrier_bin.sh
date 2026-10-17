#!/bin/sh
# Print the path of a release zapote-power-barrier built from this checkout's Rust sources, building it when needed.
#   BIN=$(sh native-21/layout/gates/barrier_bin.sh)
# The release build gives a byte-identical barrier report in 32 s against 304 s for the debug build (s44 board,
# 2026-10-15). target-shared is written by every worktree and cargo's fingerprints follow paths and mtimes, so the
# binary there may come from other sources: it is reused only when its stamp (BIN.key: the git trees of
# zapote/packages and zapote/Cargo.lock / Cargo.toml at HEAD, plus any uncommitted diff of them) matches this checkout,
# else cargo builds it here and writes the stamp. Build output goes to stderr; stdout is the path only.
set -e
Z=$(cd "$(dirname "$0")/../../../.." && pwd)            # zapote/ (the cargo workspace)
T=${CARGO_TARGET_DIR:-/Users/bennet/Desktop/temper/target-shared}
BIN=$T/release/zapote-power-barrier
KEY=$(cd "$Z" && { git rev-parse HEAD:zapote/packages HEAD:zapote/Cargo.lock HEAD:zapote/Cargo.toml
                   git diff HEAD -- packages Cargo.lock Cargo.toml; } | shasum | cut -c1-40)
if [ -x "$BIN" ] && [ "$(cat "$BIN.key" 2>/dev/null)" = "$KEY" ]; then
  echo "$BIN"
  exit 0
fi
echo "barrier_bin: building the release barrier binary for this checkout (stamp $KEY)" >&2
(cd "$Z" && CARGO_TARGET_DIR=$T cargo build --release --locked --quiet -p zapote-harness --bin zapote-power-barrier) >&2
echo "$KEY" > "$BIN.key"
echo "$BIN"
