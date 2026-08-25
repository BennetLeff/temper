<!-- provenance: commit=eb5022510d8f1272adf0a27d76c849aa2bb6e210 dirty=false -->

# Per-worktree `target-shared` caches: three disk recurrences and why the shell-convention remedy failed

**Date:** 2026-07-28 (first), 2026-08-06 (second), 2026-08-11/12 (third), 2026-08-13 (mechanism confirmed), 2026-08-15 (fix landed)
**Status:** resolved — a PATH wrapper (`install_cargo_target_dir_guard.py`) enforces `CARGO_TARGET_DIR` for every cargo/maturin invocation on the host

## The mechanism

`.cargo/config.toml` sets `build.target-dir` to the *relative* path
`target-shared`. Cargo resolves a relative `target-dir` against the config
file's own directory — and every git worktree gets its own tracked **copy**
of that file. So, absent an override, each worktree lands on its own
`target-shared` and compiles all 10 pyo3 crates from cold.

`CARGO_TARGET_DIR` overrides `build.target-dir` and can hold an absolute
path, which is why the sharing is done there rather than in the config: a
hardcoded absolute path in the tracked config would also break CI, whose
checkout lives at a different absolute path.

## The recurrences

| Date | Scale | Cleanup |
|---|---|---|
| 2026-07-28 | **51 GB** (first documented incident; commit `dc8de067`, per `docs/solutions/best-practices/shared-mutable-state-dominant-cost-multi-agent-repo-2026-07-28.md`) | 23 GB reclaimed by deleting 258 per-worktree `target/`/`.venv` directories |
| 2026-08-06 | **25 private caches totalling 36.6 GB**, disk at 98% | 16 GB reclaimed by hand |
| 2026-08-11/12 | **~74 GB across 99 worktrees** — despite the documented `source scripts/cargo_shared_env.sh` remedy being in every agent brief | fixed by the PATH wrapper (commit `1e2a69ee5`, 2026-08-15) |

Agent worktrees were the main source, because they are created outside a
persistent shell's lifetime and run `cargo test` / `cargo build` /
`cargo clippy` / `maturin develop` directly, one tool call at a time.

## Why "source it once per shell" failed (confirmed 2026-08-13)

The `source scripts/cargo_shared_env.sh`-once-per-shell guidance was
correct for a persistent interactive shell but not for how agents actually
invoke commands. Agent tool-calling harnesses start a **fresh shell process
per tool call** — shell state, including exported env vars, does not
persist between calls. Sourcing the script in one call has zero effect on a
`cargo build` issued in the next call, which is the overwhelmingly common
pattern.

This was confirmed directly while investigating the 2026-08-12 recurrence:

- exporting `CARGO_TARGET_DIR` in one shell and checking it in a fresh one
  showed it **unset**;
- a bare `cargo metadata` run from a worktree with the var unset resolved
  `target_directory` to that worktree's own private `target-shared` —
  reproducing the incident mechanism live.

## The fix

`make cargo-target-dir-guard` installs a `cargo` wrapper at
`~/.local/bin/cargo` (ahead of `~/.cargo/bin` on PATH) that fixes
`CARGO_TARGET_DIR` for **every** cargo/maturin invocation on this host,
from any worktree, in any shell — no sourcing, no remembering. `make
worktree` and `make venv-isolate` install/refresh it automatically.

It is scoped to this repo only (checked via `git rev-parse
--git-common-dir`) and never touches other cargo projects on the host, and
it respects an explicitly-set `CARGO_TARGET_DIR` rather than overriding it.
`scripts/check_no_worktree_target_dirs.py` (`make check-worktree-target-dirs`,
`CLEAN=1` to also delete) is the standing gate that catches anything that
still slips through.

The "anything run through `make` already exports the same value" claim was
verified and holds: `CARGO_TARGET_DIR` is computed and exported at the top
of the Makefile itself, recomputed fresh on every `make` invocation, and
inherited by every recipe command. `make extensions`, `make build`, etc.
were never the gap — direct `cargo`/`maturin` calls outside `make` were.

## The trade-off, stated

Cargo takes an exclusive lock on the target directory, so concurrent builds
in different worktrees serialise instead of running in parallel. That is
still far cheaper than each doing a cold build — after the first, the rest
are incremental.

## Related

- `docs/solutions/best-practices/shared-cargo-target-dir-guard-2026-08-19.md`
  — the full design rationale for the wrapper over the alternatives.
- `docs/solutions/best-practices/shared-mutable-state-dominant-cost-multi-agent-repo-2026-07-28.md`
  — the first (51 GB) incident in its same-day context.
