# Shared cargo build cache -- source this before invoking cargo/maturin directly.
#
#     source scripts/cargo_shared_env.sh
#
# Why: `.cargo/config.toml` sets `build.target-dir = "target-shared"`, a
# RELATIVE path. Cargo resolves it against the config file's own directory, and
# every git worktree gets its own tracked COPY of that file -- so each worktree
# resolves to its own `target-shared` and compiles all 10 pyo3 crates from cold.
# That is the mechanism behind the 51 GB incident the config block cites, and it
# recurred on 2026-08-06: 25 private caches totalling 36.6 GB, with the disk at
# 98% and 16 GB reclaimed by hand.
#
# `CARGO_TARGET_DIR` overrides `build.target-dir`, and unlike the config it can
# hold an absolute path. Deriving it from `--git-common-dir` resolves to the
# main checkout's `target-shared` identically from the main checkout, from
# `.claude/worktrees/*`, and from worktrees outside the repo tree entirely
# (agents routinely create them under /private/tmp).
#
# The Makefile exports the same value (see its `CARGO_TARGET_DIR :=` line), so
# anything run through `make` is already correct. This file exists for the paths
# that do NOT go through make -- `cargo test`, `cargo build`, `cargo clippy`,
# and direct `maturin develop` -- which is most of what agents actually run.
#
# Trade-off, unchanged from the config block: cargo takes an exclusive lock on
# the target directory, so concurrent builds in different worktrees serialise
# rather than running in parallel. That is still far cheaper than each doing a
# cold build, because after the first the rest are incremental.

_temper_git_common_dir="$(git rev-parse --path-format=absolute --git-common-dir 2>/dev/null)" || {
    echo "cargo_shared_env.sh: not inside a git repository; CARGO_TARGET_DIR unchanged" >&2
    return 1 2>/dev/null || exit 1
}

CARGO_TARGET_DIR="$(dirname "$_temper_git_common_dir")/target-shared"
export CARGO_TARGET_DIR
unset _temper_git_common_dir

if [ -n "${TEMPER_CARGO_ENV_VERBOSE:-}" ]; then
    echo "CARGO_TARGET_DIR=$CARGO_TARGET_DIR"
fi
