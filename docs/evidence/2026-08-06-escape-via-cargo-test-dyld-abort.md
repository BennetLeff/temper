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

**Unverified:** whether Linux CI hits this. It plausibly does not — the
`dynamic_lookup` rustflags are under `[target.*-apple-darwin]` only — but
that has not been tested, and CI runs `cargo test` per crate. Treat this as
a possible CI failure on the branch until someone checks a Linux run.

## Related

`temper-placer/temper-constraints` has the same `_PyBool_Type` abort on
macOS, reported during the `RTLD_DEFAULT` work (#792) and confirmed there
as reproducing on unmodified `origin/main`. This one differs in that
`origin/main`'s `temper-geometry` does **not** abort — the regression
arrives with this module.
