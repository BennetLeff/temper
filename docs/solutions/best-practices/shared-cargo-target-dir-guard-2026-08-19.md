---
title: "Shared cargo build cache: enforce CARGO_TARGET_DIR with a PATH wrapper, not a shell convention"
date: "2026-08-19"
category: best-practices
module: development_workflow
problem_type: best_practice
component: development_workflow
severity: high
applies_when:
  - "running `cargo build` / `cargo test` / `cargo clippy` / `maturin develop` directly (not through `make`) from any worktree of this repo"
  - "choosing how to share a cargo build cache across git worktrees that each carry their own copy of `.cargo/config.toml`"
  - "writing guidance for agents whose tool-calling harness starts a fresh shell per command"
tags:
  - cargo-target-dir
  - shared-build-cache
  - worktree-isolation
  - path-wrapper
  - multi-agent-workflow
---

# Shared cargo build cache: enforce `CARGO_TARGET_DIR` with a PATH wrapper, not a shell convention

## The problem

`.cargo/config.toml` sets `build.target-dir` to the *relative* path
`target-shared`. Cargo resolves a relative `target-dir` against the config
file's own directory — and every git worktree gets its own tracked **copy**
of that file. So, absent an override, each worktree lands on its own
`target-shared` and compiles all 10 pyo3 crates from cold. `CARGO_TARGET_DIR`
overrides `build.target-dir` and can hold an absolute path, which is why the
sharing is done there rather than in the config: a hardcoded absolute path
in the tracked config would also break CI, whose checkout lives at a
different absolute path.

The recurrences (51 GB on 2026-07-28, 36.6 GB across 25 caches on
2026-08-06, ~74 GB across 99 worktrees on 2026-08-11/12) are documented in
`docs/evidence/2026-08-13-cargo-target-dir-shell-convention-failure.md`.

## Why the shell-convention remedy failed

"Source `scripts/cargo_shared_env.sh` once per shell" was correct for a
persistent interactive shell but not for how agents actually invoke
commands: **agent tool-calling harnesses start a fresh shell process per
tool call**, so exported env vars do not persist between calls. Sourcing
the script in one call has zero effect on a `cargo build` issued in the
next call — the overwhelmingly common pattern. This was confirmed live
while investigating the 2026-08-12 recurrence (export in one shell, check
in a fresh one: unset; bare `cargo metadata` with the var unset resolved to
a per-worktree `target-shared`). A convention that depends on shell state
surviving across tool calls is not a defense at all.

The `source`-based guidance is still correct and still works for a
genuinely persistent interactive shell (it is what the wrapper itself uses
internally), but it is no longer the primary defense.

## The fix: a PATH wrapper

`make cargo-target-dir-guard` installs a `cargo` wrapper at
`~/.local/bin/cargo` (ahead of `~/.cargo/bin` on PATH) that fixes
`CARGO_TARGET_DIR` for **every** cargo/maturin invocation on this host, from
any worktree, in any shell — no sourcing, no remembering. `make worktree`
and `make venv-isolate` install/refresh it automatically. Setting up a
worktree by hand (`git worktree add`, not `make worktree`): run
`python3 scripts/install_cargo_target_dir_guard.py` once.

Properties, all deliberate:

- **Repo-scoped**: checked via `git rev-parse --git-common-dir`; never
  touches other cargo projects on the host.
- **Respects an explicit override**: an explicitly-set `CARGO_TARGET_DIR`
  is honored rather than overridden.
- **`make` was never the gap**: `CARGO_TARGET_DIR` is computed and exported
  at the top of the Makefile itself, recomputed fresh on every `make`
  invocation, and inherited by every recipe command — the gap was always
  direct `cargo`/`maturin` calls outside `make`.

A standing gate backs the wrapper: `scripts/check_no_worktree_target_dirs.py`
(`make check-worktree-target-dirs`, `CLEAN=1` to also delete violations
that pass a `CACHEDIR.TAG` safety check) catches anything that still slips
through — e.g. a worktree that existed before the guard was installed.

## The trade-off, stated

Cargo takes an exclusive lock on the target directory, so concurrent builds
in different worktrees serialise instead of running in parallel. That is
still far cheaper than each doing a cold build — after the first, the rest
are incremental.

## Related

- `docs/evidence/2026-08-13-cargo-target-dir-shell-convention-failure.md`
  — the recurrences and the live confirmation of the mechanism.
- `docs/solutions/best-practices/shared-mutable-state-dominant-cost-multi-agent-repo-2026-07-28.md`
  — the first (51 GB) incident in context.
- `docs/evidence/2026-07-28-worktree-env-isolation.md` — why per-worktree
  isolation of `.venv` is still opt-in despite the shared cache.
