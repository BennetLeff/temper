#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export CARGO_TARGET_DIR=${CARGO_TARGET_DIR:-/tmp/temper-lcr-revb-host-target}
cargo fmt --manifest-path "$ROOT/Cargo.toml" --check
cargo test --manifest-path "$ROOT/Cargo.toml" --locked
cargo clippy --manifest-path "$ROOT/Cargo.toml" --locked --all-targets -- -D warnings
cargo build --manifest-path "$ROOT/Cargo.toml" --locked --release
printf 'Host executable: %s/release/temper-lcr\n' "$CARGO_TARGET_DIR"
