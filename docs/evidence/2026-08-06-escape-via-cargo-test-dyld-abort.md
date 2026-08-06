# `escape_via.rs` aborts `cargo test -p temper-geometry` on macOS

**Date:** 2026-08-06
**Branch:** `phaseb/router-v6-kernels` (#751 Phase B)
**Status:** unresolved — recorded so it is not rediscovered from scratch

## Symptom

```
$ cargo test --manifest-path packages/temper-geometry/Cargo.toml --features python
   Running unittests src/lib.rs
dyld[97975]: symbol not found in flat namespace '_PyBool_Type'
error: test failed, to rerun pass `--lib`
  process didn't exit successfully: ... (signal: 6, SIGABRT)
```

The binary aborts at **load**, before any test runs, so all of the crate's
Rust unit tests are hidden — not failed, never executed.

## Isolated to `escape_via.rs`, by bisection not inference

| tree | `cargo test` result |
|---|---|
| `origin/main` (no `escape_via.rs`) | **462 + 31 + 9 + 1 passed** |
| this branch | SIGABRT, `_PyBool_Type` |
| this branch, `escape_via` commented out of `lib.rs` | **462 + 31 + 9 passed** |

So the module's presence is the trigger. Two candidate causes were ruled
out by direct experiment:

* **Not the `PyOverflowError` added for the `**`-overflow fix.** Replacing
  that `Err(...)` with `Ok(f64::INFINITY)` still aborts.
* **Not "the crate returns `bool` to Python".** `origin/main`'s
  `bridge.rs` already has five `-> PyResult<bool>` pyfunctions
  (`rect_contains_point`, `point_in_rect`, `is_convex`, …) and its tests
  pass.

## Why it was invisible until now

`escape_via.rs` was committed without ever compiling (6 errors, pyo3 0.29
renamed `Bound::downcast` to `cast`). `cargo test` therefore could not run
on any earlier commit of this branch — this is the first time the crate's
Rust tests have been runnable with the module present.

## What is NOT affected

* The **Python-side** escape_via differential and PBT: **164 passed, 0
  failed**, with the extension built via `maturin develop --release`.
  Those exercise the kernel through the real interpreter, where libpython
  is present.
* `cargo check` and `cargo clippy --all-targets -- -D warnings`: both clean.

## Likely mechanism, and the open question

macOS builds here carry `-C link-arg=-undefined -C link-arg=dynamic_lookup`
(`.cargo/config.toml`), which lets a pyo3 `extension-module` link without
libpython and resolve CPython symbols at load time from the interpreter that
`dlopen`s it. A **test binary** is not loaded by an interpreter, so a
flat-namespace lookup of `_PyBool_Type` has nothing to resolve against.

That mechanism is macOS-specific, and `.cargo/config.toml` states the
intent that "`cargo build`/`cargo test` are unaffected either way: they
build the rlib and the test harness links libpython normally."

**RESOLVED 2026-08-06, after #751 merged: CI is not affected, for a reason
worse than the bug.**

CI does not run `cargo test` on this crate at all. It runs it on exactly two
crates — `temper-orchestration` (`python-tests.yml:839`) and
`temper-design-bundle` (`:2011`). Every other crate, `temper-geometry`
included, gets only `cargo check` and `cargo clippy --all-targets`. The
workflow says so itself at `:830`:

> A pyo3 crate that `maturin develop` builds still needs its `#[cfg(test)]`
> modules exercised somewhere

So the abort could not break CI, because **the 502 unit tests it hides were
already never run there**. What changed is that they can no longer be run
locally on macOS either, which was the last place they executed.

That is the finding worth acting on: this crate's Rust unit tests are now
unreachable on both paths. Two options, neither taken here —

1. add a `cargo test` step for `temper-geometry` mirroring the
   `temper-orchestration` entry, which would also surface this abort in CI
   on Linux, where `dynamic_lookup` does not apply; or
2. fix the abort so the tests run on macOS again.

Option 1 is the smaller change and closes the coverage gap for every kernel
this crate now owns — congestion, escape_via, heatmap, placement
suggestions, routing demand, apply-suggestions — roughly 2,700 LOC added on
2026-08-06.

## Related

`temper-placer/temper-constraints` has the same `_PyBool_Type` abort on
macOS, reported during the `RTLD_DEFAULT` work (#792) and confirmed there
as reproducing on unmodified `origin/main`. This one differs in that
`origin/main`'s `temper-geometry` does **not** abort — the regression
arrives with this module.
