//! IPC-2221B ampacity model (Wave 2, CP-SAT gates slice).
//!
//! Python reference: `temper_placer/placer/cp_sat/gates.py`
//! (`_ipc2152_forward`, `_min_width_ipc2152`) — the physics model behind
//! the CURRENT_DENSITY gate's bisection inversion of the IPC-2221
//! forward map.
//!
//! Bit-exactness: identical f64 operation order; `pow` is resolved via
//! dlsym so the crate matches the host Python runtime's own libm (the uv
//! standalone build's `pow` can differ from the statically-bound
//! `f64::powf` in the last ulp, same class as the sin/cos divergence in
//! temper-geometry's pad_geometry); the final `round(x, 3)` replicates
//! Python's banker's rounding (round-half-even), not f64::round (half
//! away from zero).
//!
//! **k coefficients**: IPC-2221B §6.2, k = 0.048 (external) / 0.024
//! (internal), matching the authoritative kernel in
//! `temper-drc-rs/src/ipc.rs`. Historical note: this crate once carried
//! `k_ext = 0.065` (unsourced, fabricated) with an ad-hoc `* 0.65`
//! internal derate; the 2026-08-15 safety audit found the combination
//! under-conservative. The corrected values are the ones documented in
//! `docs/hardware/TRACE_WIDTH_CALCULATIONS.md` §2 (IPC-2221B formula,
//! k = 0.048 external / 0.024 internal) and verified bit-exactly against
//! the temper-drc-rs kernel by the differential tests.

#[cfg(feature = "python")]
use pyo3::exceptions::PyRuntimeError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use std::panic::{self};

#[cfg(feature = "python")]
fn catch_unwind_f64(f: impl FnOnce() -> f64) -> PyResult<f64> {
    match panic::catch_unwind(panic::AssertUnwindSafe(f)) {
        Ok(v) => Ok(v),
        Err(panic_info) => {
            let msg = if let Some(s) = panic_info.downcast_ref::<String>() {
                s.clone()
            } else if let Some(s) = panic_info.downcast_ref::<&str>() {
                s.to_string()
            } else {
                "unknown panic in temper_constraints::ipc".to_string()
            };
            Err(PyRuntimeError::new_err(format!("temper_constraints panic: {msg}")))
        }
    }
}

// ---------------------------------------------------------------------------
// Host-libm pow (same pattern as temper-geometry's pad_geometry dlsym
// cos/sin — the uv standalone Python's own libm can differ from the
// crate's statically-bound libm in the last ulp).
// ---------------------------------------------------------------------------

use std::sync::OnceLock;

type MathFn = unsafe extern "C" fn(f64, f64) -> f64;

#[cfg(not(target_arch = "wasm32"))]
fn dlsym_pow() -> Option<MathFn> {
    use std::ffi::c_char;
    unsafe extern "C" {
        fn dlsym(handle: *const c_char, symbol: *const c_char) -> *mut c_char;
    }
    // `RTLD_DEFAULT` is `((void *) 0)` on glibc but `((void *) -2)` in
    // Darwin's `<dlfcn.h>`; hardcoding null made every macOS lookup miss
    // silently ("dlsym(0x0, pow): invalid handle") and fall back to
    // `f64::powf`, defeating the host-libm match this helper exists for.
    #[cfg(target_vendor = "apple")]
    const RTLD_DEFAULT: *const c_char = usize::MAX.wrapping_sub(1) as *const c_char; // (void *) -2
    #[cfg(not(target_vendor = "apple"))]
    const RTLD_DEFAULT: *const c_char = core::ptr::null();
    unsafe {
        let p = dlsym(RTLD_DEFAULT, c"pow".as_ptr());
        if p.is_null() {
            None
        } else {
            Some(std::mem::transmute::<*mut c_char, MathFn>(p))
        }
    }
}

/// `wasm32` has no dynamic loader, so every lookup misses and the
/// statically-bound `f64::powf` fallback below is used instead.
///
/// **This is a `cfg`, not a stub for convenience.** Declaring `dlsym` on
/// `wasm32` emits an `env.dlsym` *import* into the module, and a module with a
/// non-empty import list cannot be instantiated by a bare isolate — the host
/// must supply JS glue for it. That is invisible to `cargo check` and even to
/// `cargo build`: it only appears when something instantiates the module.
///
/// The semantics are right, not merely expedient (see `temper-drc-rs`'s
/// `pymath.rs`, same pattern): the indirection exists to track *the host
/// CPython interpreter's* libm, and in a Worker there is no interpreter to
/// track — the module's own compiled-in libm is the only implementation
/// present.
#[cfg(target_arch = "wasm32")]
fn dlsym_pow() -> Option<MathFn> {
    None
}

unsafe extern "C" fn fallback_pow(x: f64, y: f64) -> f64 {
    f64::powf(x, y)
}

fn host_pow() -> &'static MathFn {
    static F: OnceLock<MathFn> = OnceLock::new();
    F.get_or_init(|| dlsym_pow().unwrap_or(fallback_pow))
}

fn math_pow(x: f64, y: f64) -> f64 {
    unsafe { host_pow()(x, y) }
}

// ---------------------------------------------------------------------------
// Model
// ---------------------------------------------------------------------------

/// IPC-2221B forward current capacity (A). Mirrors `_ipc2152_forward`
/// exactly: `k * (temp_rise_c ** 0.44) * (area_mils2 ** 0.725)` with the
/// IPC-2221B layer-dependent k coefficient (0.048 external / 0.024
/// internal), instead of the earlier fabricated `k_ext = 0.065` with an
/// ad-hoc 65% internal derate.
///
/// Source: IPC-2221B §6.2 (current-carrying capacity), k = 0.048
/// (external) / 0.024 (internal). This is the same kernel as the
/// authoritative `temper-drc-rs/src/ipc.rs` `estimate_trace_current`
/// (k = 0.048 / 0.024); the internal-layer reduction is carried by the k
/// coefficient itself (0.024 = 0.048 × 0.5), NOT by a separate
/// multiplier — the old `* 0.65` was unsourced and under-conservative
/// (2026-08-15 safety audit; corrected values per
/// docs/hardware/TRACE_WIDTH_CALCULATIONS.md §2).
fn ipc2152_forward(width_mm: f64, copper_oz: f64, temp_rise_c: f64, internal_layer: bool) -> f64 {
    let width_mils = width_mm * 39.3701;
    let thickness_mils = copper_oz * 1.37;
    let area_mils2 = width_mils * thickness_mils;
    let k = if internal_layer { 0.024 } else { 0.048 };
    k * math_pow(temp_rise_c, 0.44) * math_pow(area_mils2, 0.725)
}

/// Minimum trace width (mm) to carry `current_a` — bisection over the
/// IPC-2221B forward map, exactly mirroring `_min_width_ipc2152` (60
/// iterations, `hi` returned, banker's-rounded to 3 decimals).
fn min_width_ipc2152(current_a: f64, copper_oz: f64, temp_rise_c: f64, internal_layer: bool) -> f64 {
    if current_a <= 0.0 {
        return 0.0;
    }
    let mut lo = 0.001f64;
    let mut hi = 50.0f64;
    for _ in 0..60 {
        let mid = (lo + hi) / 2.0;
        let cap = ipc2152_forward(mid, copper_oz, temp_rise_c, internal_layer);
        if cap < current_a {
            lo = mid;
        } else {
            hi = mid;
        }
    }
    // Python round(x, 3): banker's rounding (round-half-even).
    (hi * 1000.0).round_ties_even() / 1000.0
}

// ---------------------------------------------------------------------------
// PyO3 bridge
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (width_mm, copper_oz = 1.0, temp_rise_c = 10.0, internal_layer = false))]
pub fn ipc2152_forward_py(
    width_mm: f64,
    copper_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> PyResult<f64> {
    catch_unwind_f64(|| ipc2152_forward(width_mm, copper_oz, temp_rise_c, internal_layer))
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (current_a, copper_oz = 1.0, temp_rise_c = 10.0, internal_layer = false))]
pub fn min_width_ipc2152_py(
    current_a: f64,
    copper_oz: f64,
    temp_rise_c: f64,
    internal_layer: bool,
) -> PyResult<f64> {
    catch_unwind_f64(|| min_width_ipc2152(current_a, copper_oz, temp_rise_c, internal_layer))
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    /// The host-libm indirection is actually wired, not silently bypassed.
    ///
    /// Before the Darwin `RTLD_DEFAULT` correction this failed on macOS:
    /// `dlsym(NULL, ...)` reports `invalid handle` there, so every lookup
    /// returned `None` and the fallback silently became the live route while
    /// the code claimed bit-exactness with the host interpreter. Nothing else
    /// in the suite could notice — the fallback is a *plausible* answer.
    #[cfg(not(target_arch = "wasm32"))]
    #[cfg_attr(test, test)]
    fn host_libm_symbols_actually_resolve() {
        assert!(dlsym_pow().is_some(), "dlsym could not resolve `pow`");
    }

    #[cfg_attr(test, test)]
    fn test_forward_matches_known_point() {
        // 1 mm, 1 oz, 10 C rise, external: 39.3701 * 1.37 = 53.937... mils^2
        // k * 10^0.44 * area^0.725 = 0.048 * 2.7538... * 18.016... = 2.382 A
        let cap = ipc2152_forward(1.0, 1.0, 10.0, false);
        assert!((cap - 2.382).abs() < 0.01, "capacity {cap}");
        // Internal: k = 0.024 = 0.048 / 2 exactly, so capacity is exactly
        // half of external — the IPC-2221B internal-layer coefficient, not
        // a separate derate multiplier.
        let internal = ipc2152_forward(1.0, 1.0, 10.0, true);
        assert!((internal - cap * 0.5).abs() < 1e-12, "internal {internal}");
    }

    #[cfg_attr(test, test)]
    fn test_min_width_roundtrip() {
        // The width that carries 2 A: forward capacity within one
        // 3-decimal rounding step of the target (rounding can undershoot
        // by up to a rounding step; the bisection itself is exact).
        let w = min_width_ipc2152(2.0, 1.0, 10.0, false);
        assert!(w > 0.0);
        let cap = ipc2152_forward(w, 1.0, 10.0, false);
        assert!(cap >= 2.0 - 0.01, "capacity {cap} at width {w}");
        // A width one rounding step narrower must fail (or be within the
        // same step of the boundary).
        let below = ipc2152_forward(w - 0.001, 1.0, 10.0, false);
        assert!(below <= 2.0 + 0.01);
    }

    #[cfg_attr(test, test)]
    fn test_zero_current_returns_zero() {
        assert_eq!(min_width_ipc2152(0.0, 1.0, 10.0, false), 0.0);
        assert_eq!(min_width_ipc2152(-1.0, 1.0, 10.0, false), 0.0);
    }

    #[cfg_attr(test, test)]
    fn test_round_ties_even_matches_python() {
        // Python round(0.0045, 3) = 0.004 (banker's); round(0.0055, 3) = 0.006.
        // f64: 0.0045 is not exact; use values whose scaled form is exact.
        assert_eq!((0.004f64 * 1000.0).round_ties_even() / 1000.0, 0.004);
        // 2.5 -> 2 (even), 3.5 -> 4 (even)
        assert_eq!(2.5f64.round_ties_even(), 2.0);
        assert_eq!(3.5f64.round_ties_even(), 4.0);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        #[cfg(not(target_arch = "wasm32"))] ("ipc::tests::host_libm_symbols_actually_resolve", host_libm_symbols_actually_resolve),
        ("ipc::tests::test_forward_matches_known_point", test_forward_matches_known_point),
        ("ipc::tests::test_min_width_roundtrip", test_min_width_roundtrip),
        ("ipc::tests::test_zero_current_returns_zero", test_zero_current_returns_zero),
        ("ipc::tests::test_round_ties_even_matches_python", test_round_ties_even_matches_python),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
