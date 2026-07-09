---
date: "2026-07-08"
topic: router-build-unblock
status: requirements
tier: standard-feature
---

# Router Build Unblock — Fix temper-rust-router GIL Crash on Conda Python

## Summary

`import temper_rust_router` crashes with `PyInterpreterState_Get: the function must be called with the GIL held` on Miniforge/conda Python. The `.so` extension links `@rpath/libpython3.12.dylib` — a "double-libpython" signature where both the extension and the host interpreter link libpython, causing a GIL-state mismatch. The fix is to split the Rust crate into a pure-Rust rlib (no pyo3) consumed by `temper-constraint-compiler`, and a thin cdylib-only pyo3 wrapper. As immediate unblock, recreate the venv on python-build-standalone (non-conda).

## Problem Frame

`temper_rust_router` is a pyo3 extension module that also serves as a Rust library dependency for `temper-constraint-compiler`. The `Cargo.toml` specifies `crate-type = ["cdylib", "rlib"]` — the `rlib` variant (needed because the constraint-compiler path-depends on the router) is what lets libpython leak into the extension. pyo3's guidance is that a crate imported as a Python module should be `cdylib`-only. On conda Python, pyo3 is especially prone to linking libpython, producing the double-libpython crash.

The crash blocks all routing workstreams (W1-W5) and prevents `PlaceRouteLoop` from running end-to-end on this machine.

## Requirements

### R1 — Crate split (durable fix)

Split `temper-rust-router` into two crates:
- `temper-rust-router-core` — pure-Rust rlib: SAT solver binding, topology extraction, loop extraction. No pyo3. No libpython.
- `temper-rust-router` — cdylib-only pyo3 wrapper: imports and re-exports from `-core`. Thin binding layer.

`temper-constraint-compiler` depends on `temper-rust-router-core`, not the pyo3 wrapper.

Gate: `import temper_rust_router` succeeds without GIL crash. `PlaceRouteLoop.run()` completes end-to-end on a fresh `uv venv --python 3.12` checkout on macOS arm64 and writes a routed `.kicad_pcb`.

Module boundary rule: Any module that does not import `pyo3` belongs in `temper-rust-router-core`. Modules that import `pyo3` (e.g. `bridge.rs`, `types_py_bridge.rs`) stay in the wrapper crate.

### R2 — Venv recreation (immediate unblock)

The project venv must use a non-conda Python interpreter (python-build-standalone via `uv venv --python 3.12` or Homebrew Python). This avoids the libpython double-link. Low effort, sidesteps the crash while R1 is in progress.

Gate: `import temper_rust_router` succeeds. Existing test suite passes unchanged.

### R3 — Build reproducibility

Document in `.python-version` (`3.12`) and note in README that the project requires non-conda Python. The project's Python dependency must not depend on conda.

R3 is verifiable only after R1 is complete — the import gate depends on the split crate structure.

Gate: `uv venv && uv pip install -e .` produces a working `temper_rust_router` import on a clean checkout.

## Key Decisions

- **Split the crate, don't patch the build.** Forcing `-undefined dynamic_lookup` via a macOS build.rs link-arg (#3) is a targeted workaround but doesn't fix the architectural issue — the router crate serving both as a Python extension and a Rust library dependency. The split separates concerns correctly.
- **Non-conda Python is the project standard.** Conda Python's libpython linking behavior is incompatible with pyo3 extensions. The project's Python dependency should be python-build-standalone (via `uv`) or Homebrew Python.

## Scope Boundaries

- pyo3 version or maturin configuration changes are out of scope — the crate split is the fix.
- Other crates in the workspace are unaffected — only `temper-rust-router` is split.
- The non-conda venv is a permanent environment change (also serving as the fastest unblock path). The crate split (R1) is an architectural fix addressing the root cause.

## Success Criteria

1. R1: `import temper_rust_router` succeeds without GIL crash on a fresh `uv venv --python 3.12`
2. R1: `PlaceRouteLoop.run()` completes end-to-end on the temper board
3. R1: `temper-constraint-compiler` builds against `temper-rust-router-core` without pyo3 dependency
4. R2: Existing test suite passes unchanged
