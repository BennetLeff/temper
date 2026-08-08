<!-- provenance: commit=f7a1fbf8fd155a0c303462717d531f8ae7606b7f dirty=UNKNOWN -->

# Phase 1 U4 — validation.rs ungating and family-coverage growth

**Date**: 2026-08-07
**Task**: Close the family-coverage gap (U4): five portable kernels extracted
from `validation.rs` into `validation_kernels.rs`, registered in the wasm32
test registry, adding drc, safety family coverage.
**Branch**: `wasm/p1-ungate-families`
**Base commit**: `f7a1fbf8f`

## Summary

`packages/temper-drc-rs/src/validation.rs` (908 lines, 11 DRC kernels) was
entirely `#[cfg(feature = "python")]`-gated, so the wasm32 tier had **zero**
coverage of its kernels. Five of the 11 kernels have no pyo3 types in their
signatures and were extracted into a new non-gated module
`validation_kernels.rs`, with the original `validation.rs` providing thin
`#[pyfunction]` wrappers. The pure-kernel functions now compile under both
`--no-default-features` (wasm32) and the default `python` feature set with
no behavioral change.

## Kernels that became portable

| Kernel | Family | Signature purity |
|---|---|---|
| `infer_package_type` | drc | `Option<String>` → `String` |
| `tht_hole_collisions` | drc | `Vec<(String,String,f64,f64,f64)>, f64` → `Vec<String>`; uses `pymath::pow` |
| `trace_length` | drc | `Vec<(Option<String>,f64,f64,f64,f64)>, &str` → `f64`; uses `pymath::pow` |
| `min_hv_lv_trace_clearance` | safety | `&[(f64,f64,f64,f64)], &[(f64,f64,f64,f64)]` → `f64` |
| `issue_fingerprint` | drc | `&str, &str, Vec<String>` → `String` |

## Kernels that stayed python-gated

| Kernel | Reason |
|---|---|
| `rdl_sum` | Calls Python `math.hypot` via a pyo3 `Bound<'_, PyAny>` callable — cannot be wasm-portable |
| `geometric_validate` | Builds `PyList`/`PyDict` inside its decision loop; signature carries `Python<'_>`, returns `PyResult<(Py<PyAny>, Py<PyAny>)>` |
| `parse_drc_violation` | Signature carries `Python<'_>` and `&Bound<'_, PyDict>`; deeply coupled to pyo3 |
| `compute_drc_penalty` | Looks up weights in two `&Bound<'_, PyDict>` objects via pyo3 API |
| `group_violations` | Normalizes Python dicts into `Py<PyDict>` records; signature carries `Python<'_>`, `Vec<Py<PyDict>>` |
| `metrics_summary` | Accumulates via C Python's `PyNumber_Add` (`+` operator); uses `Py<PyAny>` throughout |

## Wasm test registry delta

| Metric | Before | After |
|---|---|---|
| Total registered tests | 95 | 112 |
| Modules with tests | 16 | 17 |
| New tests | — | +17 (all in `validation_kernels`) |

The 17 new tests:
- `infer_package_type_smd_default`
- `infer_package_type_tht`
- `infer_package_type_to_packages`
- `infer_package_type_other_keywords`
- `tht_hole_collisions_no_violations`
- `tht_hole_collisions_collision`
- `tht_hole_collisions_at_threshold`
- `trace_length_empty`
- `trace_length_single_segment`
- `trace_length_skips_other_nets`
- `trace_length_none_net_skipped`
- `min_hv_lv_clearance_empty_returns_inf`
- `min_hv_lv_clearance_single_pair`
- `min_hv_lv_clearance_diagonal`
- `issue_fingerprint_empty_items`
- `issue_fingerprint_sorts_items`
- `issue_fingerprint_single_item`

## Family coverage before → after

The six R5 rule families are: drc, erc, safety, emc, dfm, placement.

| Family | Before (wasm modules) | After (wasm modules) | Delta |
|---|---|---|---|
| drc | 1 (`rules::drc::clearance`) | 2 (+`validation_kernels` — 4 drc kernels) | +1 module, +12 tests |
| safety | 0 | 1 (`validation_kernels::min_hv_lv_trace_clearance`) | +1 module, +3 tests |
| erc | 0 | 0 | — |
| emc | 0 | 0 | — |
| dfm | 2 (`dfm`, `rules::routing::power_pad_teardrop`) | 2 | — |
| placement | 0 | 0 | — |

The safety family now has its first wasm-tier representation (3 tests on
`min_hv_lv_trace_clearance`, the HV↔LV separation kernel). The drc family
gains 12 kernel-level tests.

## Behavioral risk

- **Native (python feature)**: Zero risk. The thin `#[pyfunction]` wrappers
  in `validation.rs` call the exact same function bodies now relocated to
  `validation_kernels.rs`. All native tests pass; `cargo check` (default
  features) compiles cleanly.
- **wasm32**: Float divergence is advisory-only per R15. The wasm32 build
  uses `f64::powf` as the `pymath::pow` fallback (no dlsym on wasm32),
  which LLVM may fold constant-exponent calls to `x*x`/`sqrt`. The three
  expected-fail tests in the wasm runner already document this (B7
  pow-divergence-absent) — no new expected failures were introduced.

## Verification transcript

```
# Base assertion
$ scripts/assert-base.sh origin/main
ASSERT-BASE OK: HEAD == origin/main (f7a1fbf8f)

# Native tests (--no-default-features)
$ cargo test --no-default-features --manifest-path packages/temper-drc-rs/Cargo.toml
test result: ok. 112 passed; 0 failed; 0 ignored

# Native check (default features = python)
$ cargo check --manifest-path packages/temper-drc-rs/Cargo.toml
Finished `dev` profile [unoptimized + debuginfo] target(s) in 1.11s

# Clippy (--no-default-features)
$ cargo clippy --no-default-features --manifest-path packages/temper-drc-rs/Cargo.toml
Finished (0 warnings)

# Wasm32 build
$ cargo build --release --target wasm32-unknown-unknown --no-default-features \
    --manifest-path packages/temper-wasm-test-runner/Cargo.toml
Finished `release` profile [optimized] target(s) in 6.15s

# Wasm32 test run
$ node tools/wasm/run_wasm_tests.mjs \
    target-shared/wasm32-unknown-unknown/release/temper_wasm_test_runner.wasm \
    --json /tmp/wasm_out.json
  passed            91
  failed            0
  expected-fail     4  (native-only properties; see manifest)
  unexpected-pass   0

# Registry consistency check
$ python3 scripts/gen_wasm_test_registry.py --check
wasm test registry up to date: 112 tests across 17 modules
```

## Files changed

- `packages/temper-drc-rs/src/validation_kernels.rs` — **new**: 5 portable kernels + 17 tests
- `packages/temper-drc-rs/src/validation.rs` — pyo3 bridge now delegates to kernels; 6 non-portable kernels unchanged
- `packages/temper-drc-rs/src/lib.rs` — added `pub mod validation_kernels;` (not `#[cfg]`-gated)
- `packages/temper-drc-rs/src/wasm_test_registry.rs` — regenerated (112 tests, +validation_kernels entry)
- `scripts/gen_wasm_test_registry.py` — added `validation_kernels.rs` to ELIGIBLE
