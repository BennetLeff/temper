---
title: "Five silent-staleness modes in a shared venv — and the two gates that answer different questions about it"
date: "2026-08-19"
category: best-practices
module: development_workflow
problem_type: best_practice
component: development_workflow
severity: critical
applies_when:
  - "a worktree agent builds or tests Rust/Python extensions and the venv it imports from is shared with other checkouts"
  - "a measurement contradicts a change that was just made, and the venv/extension provenance is not the first thing suspected"
  - "deciding whether a venv-identity gate and a per-crate freshness gate should be one gate or two"
  - "reading a plausible-looking number produced by `.venv/bin/python` and trusting it without checking whose code it imported"
tags:
  - shared-venv
  - editable-install
  - worktree-isolation
  - measurement-integrity
  - stale-extension
  - gate-ordering
---

# Five silent-staleness modes in a shared venv

The shared `.venv` at the main checkout is editable-installed against the
**main checkout**. Any worktree that imports from it — directly or via a
gate script — gets `main`'s code, not the worktree's, unless it isolates.
Five distinct ways this goes wrong were confirmed in 2026-08, in two
incidents:

- **Modes 1-4, 2026-08-11** — a worktree *poisons* the venv
  (`docs/evidence/2026-08-11-worktree-poisons-shared-venv.md`):

  1. `maturin` refuses if `VIRTUAL_ENV` and `CONDA_PREFIX` are both set
     (loud — the safe end).
  2. Plain `uv run maturin develop` from a worktree targets a per-worktree
     venv and no-ops against the shared one (silent no-op).
  3. `maturin develop --active` from a worktree **rewrites the SHARED
     venv's editable pointers** to that worktree (the hijack).
  4. `maturin develop` reports "Installed" while leaving the `.so`
     untouched (the build tool's success message is never trusted).

- **Mode 5, 2026-08-17** — no poisoning needed; the *healthy* shared venv
  simply serves `main`'s code to a worktree agent
  (`docs/evidence/2026-08-17-shared-venv-serves-main-code.md`).

Mode 3 is silent even to a freshness gate: a hijacked-but-not-yet-rebuilt
venv imports a `.so` that is content-fresh *relative to the worktree it was
built from*, so `check_stale_extensions.py` has no way to know it is
comparing against the wrong checkout's sources.

## The two gates answer different questions — keep them separate

- **`scripts/check_venv_integrity.py`** asks a *repo-wide identity*
  question: "does this venv even belong to this repo root at all, or is
  some/all of it silently sourced from a different checkout?" Its unit of
  scan is the venv's installed site-packages (`.pth` files and
  `direct_url.json` records), not source crates.
- **`scripts/check_stale_extensions.py`** asks a *per-crate freshness*
  question about a venv it already trusts: "was the artifact built from the
  sources currently on disk?" Its unit of scan is one crate at a time,
  discovered from `packages/`.

The identity question is **logically prior**: a freshness verdict computed
against a hijacked venv is meaningless, not merely stale. Folding the two
into one gate would blur that ordering. CI runs `check_venv_integrity.py`
immediately before `check_stale_extensions.py` (python-tests.yml `test`
job) precisely because the ordering matters. Both mirror the 0/3/5
exit-code convention on purpose — same job, same reader.

## The defences

1. **`make venv-isolate` in your worktree** — the worktree gets its own
   `.venv` and both the poisoning and the serving-wrong-code questions
   disappear. Measured cost: ~700 MB disk, ~85s wall time with a warm
   cache. It is deliberately opt-in, not the default for every worktree:
   at fleet scale (dozens of worktrees, low double-digit GB free), blanket
   isolation is the same disk-multiplication hazard it solves. Isolate the
   worktrees actually doing build/test work; rely on the content-hash
   freshness gate everywhere else
   (`docs/evidence/2026-07-28-worktree-env-isolation.md`).
2. **Verify what you are importing before you believe a number** —
   `python -c "import temper_placer; print(temper_placer.__file__)"` and
   confirm the path is your worktree.
3. **Run the gates before you believe a number, not after a result
   surprises you** — `make venv-integrity-check` and `make extensions-check`.
4. **When a measurement contradicts a change you just made, suspect the
   measurement before the change.** Ask what the number would look like if
   your edit were not in effect at all — "identical to before" is the
   signature of measuring the wrong tree.

## Related

- `docs/evidence/2026-08-11-worktree-poisons-shared-venv.md`
- `docs/evidence/2026-08-17-shared-venv-serves-main-code.md`
- `docs/evidence/2026-07-27-stale-extension-gate.md`
- `docs/solutions/best-practices/shared-venv-worktree-validates-wrong-tree-2026-07-29.md`
  — the earlier, related sys.path trap.
- `docs/solutions/best-practices/green-rust-tests-are-not-evidence-the-extension-was-rebuilt-2026-07-27.md`
  — why green `cargo test` is not evidence the installed `.so` is current.
