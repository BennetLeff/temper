//! IPC-2152 ampacity model (Wave 2, CP-SAT gates slice).
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

use pyo3::exceptions::PyRuntimeError;
use pyo3::prelude::*;
use std::panic::{self};

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

fn dlsym_pow() -> Option<MathFn> {
    use std::ffi::c_char;
    unsafe extern "C" {
        fn dlsym(handle: *const c_char, symbol: *const c_char) -> *mut c_char;
    }
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

/// IPC-2152 forward current capacity (A). Mirrors `_ipc2152_forward`
/// exactly: `k_ext * (temp_rise_c ** 0.44) * (area_mils2 ** 0.725)`,
/// internal layers derated to 65%.
fn ipc2152_forward(width_mm: f64, copper_oz: f64, temp_rise_c: f64, internal_layer: bool) -> f64 {
    let width_mils = width_mm * 39.3701;
    let thickness_mils = copper_oz * 1.37;
    let area_mils2 = width_mils * thickness_mils;
    let k_ext = 0.065;
    let current_ext = k_ext * math_pow(temp_rise_c, 0.44) * math_pow(area_mils2, 0.725);
    if internal_layer {
        current_ext * 0.65
    } else {
        current_ext
    }
}

/// Minimum trace width (mm) to carry `current_a` — bisection over the
/// forward map, exactly mirroring `_min_width_ipc2152` (60 iterations,
/// `hi` returned, banker's-rounded to 3 decimals).
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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_forward_matches_known_point() {
        // 1 mm, 1 oz, 10 C rise, external: 39.3701 * 1.37 = 53.937... mils^2
        // k_ext * 10^0.44 * area^0.725 = 3.225 A
        let cap = ipc2152_forward(1.0, 1.0, 10.0, false);
        assert!((cap - 3.225).abs() < 0.01, "capacity {cap}");
        let derated = ipc2152_forward(1.0, 1.0, 10.0, true);
        assert!((derated - cap * 0.65).abs() < 1e-12);
    }

    #[test]
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

    #[test]
    fn test_zero_current_returns_zero() {
        assert_eq!(min_width_ipc2152(0.0, 1.0, 10.0, false), 0.0);
        assert_eq!(min_width_ipc2152(-1.0, 1.0, 10.0, false), 0.0);
    }

    #[test]
    fn test_round_ties_even_matches_python() {
        // Python round(0.0045, 3) = 0.004 (banker's); round(0.0055, 3) = 0.006.
        // f64: 0.0045 is not exact; use values whose scaled form is exact.
        assert_eq!((0.004f64 * 1000.0).round_ties_even() / 1000.0, 0.004);
        // 2.5 -> 2 (even), 3.5 -> 4 (even)
        assert_eq!(2.5f64.round_ties_even(), 2.0);
        assert_eq!(3.5f64.round_ties_even(), 4.0);
    }
}
