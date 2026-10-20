#!/bin/sh
set -eu
ROOT=$(CDPATH= cd -- "$(dirname -- "$0")" && pwd)
export CARGO_TARGET_DIR=${CARGO_TARGET_DIR:-/tmp/temper-lcr-revc-host-target}
cargo fmt --manifest-path "$ROOT/Cargo.toml" --check
cargo test --manifest-path "$ROOT/Cargo.toml" --locked
cargo clippy --manifest-path "$ROOT/Cargo.toml" --locked --all-targets -- -D warnings
cargo build --manifest-path "$ROOT/Cargo.toml" --locked --release
if [ "$(uname -s)" = Darwin ] && [ "$(uname -m)" = arm64 ]; then
    mkdir -p "$ROOT/bin" "$ROOT/verification"
    cp "$CARGO_TARGET_DIR/release/temper-lcr" "$ROOT/bin/temper-lcr-macos-arm64"
    (cd "$ROOT" && shasum -a 256 Cargo.toml Cargo.lock build.sh README.md src/*.rs tests/*.rs bin/* > verification/SHA256SUMS)
fi
printf 'Host executable: %s/release/temper-lcr\n' "$CARGO_TARGET_DIR"
