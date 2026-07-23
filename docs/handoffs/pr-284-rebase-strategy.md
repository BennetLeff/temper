# PR #284 Rebase Strategy — `temper-py-bridge` Refactor

**Date:** 2026-07-23
**PR:** [#284](https://github.com/BennetLeff/temper/pull/284)
**Status:** Setup unblocked (commit `eb7ecd27`); build error from main's new `constraints` bridge functions remains.

## Summary

PR #284 introduces the `temper-py-bridge` crate and migrates all bridge call sites from the unqualified `catch_unwind(|| { ... }).map_err(panic_to_err)` pattern (relying on `use std::panic::catch_unwind;` at the top of each bridge file) to the fully-qualified `temper_py_bridge::catch_unwind(...).map_err(temper_py_bridge::panic_to_err)` pattern (relying on the new crate as the single source).

The branch forked from main at merge-base `36c6b8ac` and the PR branch is now **7 commits** ahead; main has diverged by **101 commits** (**594 files**: 7,406 insertions, 449,252 deletions). Main commit `a287ade1` ("feat: port ipc2152 to temper-ipc, constraints to temper-geometry", 2026-07-22) added 5 new `#[pyfunction]` bridge bindings using the OLD unqualified pattern.

CI's auto-merge of the PR branch + main resolves textually (the changes touch different lines), but the merged `bridge.rs` no longer compiles: main's 5 new functions reference `catch_unwind` and `panic_to_err` which the PR branch removed from scope.

## Conflict surface — verified by `git merge-tree`

**1 crate, 1 file, 5 functions** in `temper-geometry`. Confirmed via `git merge-tree --write-tree` — zero textual conflicts in any bridge file. The issue is purely semantic: auto-merge succeeds but the result has E0425 errors.

**`temper-drc-rs` auto-merges cleanly.** The other four bridge files carry zero references to `catch_unwind` or `panic_to_err` on main and are unaffected.

### Bridge files with `catch_unwind` / `panic_to_err` references after merge

| File | On PR (qualified) | On main (unqualified) | After auto-merge | Build state |
|---|---|---|---|---|
| `temper-geometry/src/bridge.rs` | 225 qualified | 5 new unqualified from `a287ade1` | 225 qualified + 5 broken unqualified | **FAILS** (`error[E0425]: cannot find function/value in this scope`) |
| `temper-drc-rs/src/board_py_bridge.rs` | uses `DictExtract`, no `catch_unwind` | no `catch_unwind` | unchanged | compiles |
| `temper-constraint-compiler/src/pyo3_bridge.rs` | uses `DictExtract`, no `catch_unwind` | no `catch_unwind` | unchanged | compiles |
| `temper-rust-router/src/loop_extractor/bridge.rs` | 0 | 0 | unchanged | compiles |
| `temper-rust-router/src/types_py_bridge.rs` | 0 | 0 | unchanged | compiles |

## Rebase recipe — 2 files, 1 cherry-pick

### Step 1 — Cherry-pick `constraints.rs` from main

The 5 new bridge functions call into a `constraints` module that was added on main in `a287ade1` but is NOT on the PR branch:

```bash
git checkout a287ade1 -- packages/temper-geometry/src/constraints.rs
```

The `953b56d0` commit (Rust best practices pass) made a 2-line edit to `constraints.rs` after `a287ade1`. Since the PR branch diverged before that pass, the `a287ade1` version is the one to align with; `953b56d0`'s diff is trivial and will be re-applied when the branch is eventually rebased onto main.

Then register the module in `lib.rs` (insert after `pub mod polygon;` to preserve alphabetical order):

```rust
pub mod constraints;
```

### Step 2 — Add 5 qualified `#[pyfunction]` bindings to `bridge.rs`

The drafted diff (from worktree `/Users/bennet/Desktop/temper/.worktrees/fix/py-bridge-build`, verified `cargo check` passes) adds these bindings using fully-qualified `temper_py_bridge::catch_unwind(...)` calls. Insert in `bridge.rs` between `project_onto_side` and the `drc_inflate` section (after line 1068, matching main's ordering from `a287ade1`):

1. `compute_valid_bounds` — returns `(f64, f64, f64, f64)` (x_min, x_max, y_min, y_max)
2. `compute_boundary_violation` — returns `(f64, f64, f64, f64)` (left, right, bottom, top)
3. `is_within_bounds` — returns `bool`
4. `compute_zone_distance` — returns `f64`
5. `point_in_zone` — returns `bool`

Each wrapper body calls the corresponding `crate::constraints::<fn>(...)` function inside `temper_py_bridge::catch_unwind(|| { ... }).map_err(temper_py_bridge::panic_to_err)`, exactly matching the migration pattern of the other 225 calls in the file.

Also add the corresponding registrations in the `register_functions` block between `project_onto_side` and `drc_inflate` (after line 1268):

```rust
    // constraints
    m.add_function(wrap_pyfunction!(compute_valid_bounds, m)?)?;
    m.add_function(wrap_pyfunction!(compute_boundary_violation, m)?)?;
    m.add_function(wrap_pyfunction!(is_within_bounds, m)?)?;
    m.add_function(wrap_pyfunction!(compute_zone_distance, m)?)?;
    m.add_function(wrap_pyfunction!(point_in_zone, m)?)?;
```

### Step 3 — Verify

```bash
cd packages/temper-geometry
cargo check 2>&1 | tail -10      # zero E0425 errors
cargo test  2>&1 | tail -20       # all constraints module tests pass
cd ../..
uv sync --all-packages            # workspace resolution succeeds
```

### Step 4 — Commit + force-push

```bash
git add packages/temper-geometry/src/constraints.rs \
        packages/temper-geometry/src/lib.rs \
        packages/temper-geometry/src/bridge.rs
git commit -m "fix(py-bridge): reconcile temper-geometry bridge with main's constraints module

Main commit a287ade1 added 5 new #[pyfunction] bindings in
packages/temper-geometry/src/bridge.rs using the OLD unqualified
catch_unwind/panic_to_err pattern that PR #284 removed from scope.
The auto-merge resolves textually but breaks semantically — main's
5 new functions reference symbols no longer in scope.

Reconciled by:
- checking out packages/temper-geometry/src/constraints.rs from a287ade1
- registering pub mod constraints; in lib.rs
- adding the 5 bridge bindings with fully-qualified
  temper_py_bridge::catch_unwind(...).map_err(temper_py_bridge::panic_to_err)
  calls (matching the migration pattern of the other 225 calls in this file)
- registering the 5 new functions in the register_functions block

cargo check + cargo test pass locally on temper-geometry.
temper-drc-rs auto-merges cleanly (per CI logs)."
```

Force-push with-lease:

```bash
git push --force-with-lease origin feat/temper-py-bridge-refactor
```

If `--force-with-lease` is rejected, the PR author pushed in the meantime — STOP, do NOT force.

## Other bridge files — no migration needed

The 4 other bridge files under `temper-drc-rs`, `temper-constraint-compiler`, `temper-rust-router` do not reference `catch_unwind` / `panic_to_err` directly (they use `DictExtract` or are type-only bridges). They auto-merge cleanly per CI. NO work needed there.

## Verification of done condition

- `cargo check` passes in every `packages/temper-*` crate under the current branch
- `uv sync --all-packages` succeeds
- PR #284's CI shows zero E0425 errors
- The 5 new `#[pyfunction]` bindings `compute_valid_bounds`, `compute_boundary_violation`, `is_within_bounds`, `compute_zone_distance`, `point_in_zone` are exposed in the Python layer (verified via `m.add_function(wrap_pyfunction!(...))` registrations)

## Out of scope

- Migrating the `DictExtract`-pattern bridges to `temper_py_bridge` (the PR does not already do this; it is a separate refactor if desired).
- Reordering the `register_functions` block beyond the 5 new additions.
- Tightening / loosening the `temper-py-bridge` edition = "2024" choice — unless `cargo check` reveals an edition interaction that requires changing it (it did not in the local verification).
