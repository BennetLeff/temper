---
module: temper_placer
date: "2026-07-06"
problem_type: build_error
component: router
severity: medium
symptoms:
  - "Fatal Python error: PyInterpreterState_Get: the function must be called with the GIL held on import temper_rust_router"
  - "No Python traceback — crash in PyInit before any user code runs"
  - "The .so loaded via ctypes.CDLL but crashed via normal Python import"
root_cause: config_error
resolution_type: environment_setup
tags:
  - rust
  - maturin
  - cargo-clean
  - gil
  - pyo3
  - build-artifacts
  - stale-objects
---

# Stale Rust Build Artifacts Cause GIL Crash on Import

## Problem

`import temper_rust_router` crashed with `Fatal Python error: PyInterpreterState_Get: the function must be called with the GIL held, after Python initialization and before Python finalization, but the GIL is released`. No Python traceback — crash in `PyInit_temper_rust_router` before any user code runs. Reproduced across all installation methods (maturin develop, maturin build + pip install).

## Symptoms

- Fatal Python error at module import, no traceback
- The `.so` loaded successfully via `ctypes.CDLL` (bypasses `PyInit`) confirming binary was structurally valid
- Reproduced after `maturin develop` and after `maturin build` + `pip install` — different output paths, same stale intermediate artifacts
- Error message: `PyInterpreterState_Get` — a CPython function that must be called with the GIL held

## Solution

```bash
cargo clean && maturin develop
```

A full `cargo clean` removes all stale build artifacts from the `target/` directory. A fresh rebuild produces a correctly-linked `.so`.

## Why This Works

Rust build artifacts in `target/` persist across `maturin` rebuilds and can contain object files from previous branch checkouts with different crate versions, feature flags, or `pyo3` ABI bindings. When maturin re-links without a clean, incompatible object files produce a corrupt `PyInit` function that calls into the Python C API without acquiring the GIL first — a calling-convention mismatch that manifests as a crash rather than a link error.

`cargo clean` removes all intermediate artifacts, forcing a full rebuild against the current checkout's dependency tree.

## Prevention

- Run `cargo clean` when switching branches that modify the Rust crate or its Cargo.toml
- Run `cargo clean` after significant dependency upgrades (pyo3 version bumps, feature flag changes)
- CI should always build from clean (the `target/` cache is CI-level, not inter-branch)

## See Also

- `docs/solutions/build-errors/ci-main-advance-pr-failure-5-bug-classes-2026-07-01.md` — maturin-related CI failures
- `docs/solutions/test-failures/refactor-breakage-test-imports-stale-references-2026-06-29.md` — staleness as failure mode pattern
