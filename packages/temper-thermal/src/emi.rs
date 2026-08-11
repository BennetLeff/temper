//! EMI radiated-emissions kernels (Wave 4, Phase 4).
//!
//! Ports the pure scalar arithmetic of
//! `temper_placer/physics/emi.py` (`predict_radiated_emissions`,
//! `check_emi_compliance`) to Rust.  The Python module keeps its public
//! API and delegates the arithmetic here.
//!
//! ## Bit-exactness discipline (Wave 4 catalog entries)
//!
//! - **B1 (host libm via dlsym):** `math.log10` and `frequency_mhz ** 2`
//!   (CPython `float.__pow__` → host libm `pow(x, 2.0)`) come from the
//!   host Python runtime's libm via `hostmath` (`dlsym(RTLD_DEFAULT, ...)`,
//!   cached in `OnceLock`s; std-intrinsic fallback on wasm32 where there
//!   is no host libm to match).
//! - **B7 (f64 operation order):** `1.316e-14 * A * I * (f**2) / d` is
//!   the left-to-right chain `(((1.316e-14 * A) * I) * pow(f, 2.0)) / d`
//!   — NOT `A * I * f * f` and NOT a reassociated form.  `e_uv_per_m =
//!   e_v_per_m * 1e6` is a single multiply; the final `20 *
//!   math.log10(e_uv_per_m)` is `20.0 * log10(...)` (Python's int 20 is
//!   widened to float for the multiply — same bits as 20.0).
//! - **Branch parity:** the `<= 0` guards are IEEE comparisons — false
//!   for NaN (NaN inputs flow through to a NaN result, exactly as the
//!   reference).  The `e_uv_per_m <= 0` guard catches `0.0` (and
//!   negative values from signed-zero/negative inputs) and returns
//!   `0.0` instead of `log10(0) → -inf`, matching the reference.
//! - **B8 (denormal underflow):** default IEEE semantics (no fast-math,
//!   no FTZ/DAZ); denormal-band inputs pinned in the differential.
//!
//! R24 (physics-gated): N/A as a *constraint encoding* — these are
//! analysis estimators (metrics/physics.py EMI measurement), not CP-SAT
//! constraints that gate on a physics quantity; the applicable
//! correctness contract is bit-exact parity (R1a), recorded in
//! VERIFICATION.md.

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyAny, PyString};
#[cfg(feature = "python")]
use temper_py_bridge;

use crate::hostmath;

/// Predict the radiated electric field strength (dBµV/m) from a small
/// loop antenna.  Mirrors `predict_radiated_emissions` verbatim:
///
/// - `e_v_per_m = (1.316e-14 * A * I * pow(f, 2.0)) / d` — the
///   five-op left-to-right chain with the parenthesized `f**2` power
///   evaluated before the multiply (B7).
/// - `e_uv_per_m = e_v_per_m * 1e6`; guard `e_uv_per_m <= 0` returns
///   `0.0` (covers `0.0` and negative results; NaN flows through).
/// - `20 * math.log10(e_uv_per_m)` → `20.0 * log10(...)` (B1).
///
/// Guard parity: `A <= 0 || I <= 0 || f <= 0` returns `0.0`; NaN
/// comparisons are false, so NaN inputs reach the arithmetic (NaN out).
pub fn predict_radiated_emissions(
    loop_area_mm2: f64,
    current_peak_a: f64,
    frequency_mhz: f64,
    distance_m: f64,
) -> f64 {
    if loop_area_mm2 <= 0.0 || current_peak_a <= 0.0 || frequency_mhz <= 0.0 {
        return 0.0;
    }

    // (1.316e-14 * A * I * (f**2)) / d — left-to-right (B7), pow via
    // host libm (B1).
    let e_v_per_m =
        (1.316e-14 * loop_area_mm2 * current_peak_a * hostmath::pow(frequency_mhz, 2.0))
            / distance_m;

    let e_uv_per_m = e_v_per_m * 1e6;

    if e_uv_per_m <= 0.0 {
        return 0.0;
    }

    20.0 * hostmath::log10(e_uv_per_m)
}

/// Check predicted emissions against the CISPR limit.  Mirrors
/// `check_emi_compliance` verbatim: `"CISPR32_CLASS_A"` → 50.0,
/// anything else → 40.0; returns `field_strength_dbuv <= limit`
/// (IEEE comparison, false for NaN).
pub fn check_emi_compliance(field_strength_dbuv: f64, standard: &str) -> bool {
    let limit = if standard == "CISPR32_CLASS_A" { 50.0 } else { 40.0 };
    field_strength_dbuv <= limit
}

/// pyo3 bridge for [`predict_radiated_emissions`].
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (loop_area_mm2, current_peak_a, frequency_mhz, distance_m))]
pub fn predict_radiated_emissions_py(
    loop_area_mm2: f64,
    current_peak_a: f64,
    frequency_mhz: f64,
    distance_m: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        predict_radiated_emissions(loop_area_mm2, current_peak_a, frequency_mhz, distance_m)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge for [`check_emi_compliance`].
///
/// `standard` is accepted as any Python object: the reference compares
/// `standard == "CISPR32_CLASS_A"` at the Python level, so ANY object
/// (None, ints, lists, ...) is accepted and falls to the 40.0
/// else-branch unless it equals the string.  The previous `String`
/// extraction raised TypeError for non-str (pass 2 P2); `Bound<PyAny>`
/// `eq` reproduces the reference's duck-typed comparison (including a
/// custom `__eq__` on the standard object, via full rich-compare
/// semantics).
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (field_strength_dbuv, standard))]
pub fn check_emi_compliance_py(
    py: Python<'_>,
    field_strength_dbuv: f64,
    standard: Bound<'_, PyAny>,
) -> PyResult<bool> {
    use pyo3::types::PyAnyMethods;
    let is_class_a = standard.eq(PyString::new(py, "CISPR32_CLASS_A"))?;
    let limit = if is_class_a { 50.0 } else { 40.0 };
    Ok(field_strength_dbuv <= limit)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn zero_inputs_short_circuit() {
        assert_eq!(predict_radiated_emissions(0.0, 1.0, 1.0, 3.0), 0.0);
        assert_eq!(predict_radiated_emissions(1.0, 0.0, 1.0, 3.0), 0.0);
        assert_eq!(predict_radiated_emissions(1.0, 1.0, 0.0, 3.0), 0.0);
        assert_eq!(predict_radiated_emissions(1.0, 1.0, -2.0, 3.0), 0.0);
    }

    #[cfg_attr(test, test)]
    fn nan_flows_through() {
        let r = predict_radiated_emissions(f64::NAN, 1.0, 1.0, 3.0);
        assert!(r.is_nan());
    }

    #[cfg_attr(test, test)]
    fn known_value() {
        // A=100 mm², I=10 A, f=1 MHz, d=3 m:
        // e_v = 1.316e-14*100*10*1/3 = 4.3866...e-12
        // e_uv = 4.3866...e-6; 20*log10(...) ≈ -107.15
        let r = predict_radiated_emissions(100.0, 10.0, 1.0, 3.0);
        assert!((r - (-107.157)).abs() < 1e-3, "got {r}");
    }

    #[cfg_attr(test, test)]
    fn tiny_output_guards_zero() {
        // e_uv_per_m rounds to 0.0 (the field chain underflows through
        // the denormal band) → guard returns 0.0, not log10(0)=-inf.
        let r = predict_radiated_emissions(1e-300, 1e-300, 1e-300, 30.0);
        assert_eq!(r, 0.0);
    }

    #[cfg_attr(test, test)]
    fn compliance_limits() {
        assert!(check_emi_compliance(39.9, "CISPR32_CLASS_B"));
        assert!(!check_emi_compliance(40.1, "CISPR32_CLASS_B"));
        assert!(check_emi_compliance(49.9, "CISPR32_CLASS_A"));
        assert!(!check_emi_compliance(50.1, "CISPR32_CLASS_A"));
        assert!(!check_emi_compliance(45.0, "CISPR32_CLASS_B"));
        assert!(check_emi_compliance(45.0, "CISPR32_CLASS_A"));
        // Unknown standard → Class B (40.0) like the reference else-branch.
        assert!(!check_emi_compliance(41.0, "OTHER"));
        // NaN comparison is false.
        assert!(!check_emi_compliance(f64::NAN, "CISPR32_CLASS_B"));
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("emi::tests::zero_inputs_short_circuit", zero_inputs_short_circuit),
        ("emi::tests::nan_flows_through", nan_flows_through),
        ("emi::tests::known_value", known_value),
        ("emi::tests::tiny_output_guards_zero", tiny_output_guards_zero),
        ("emi::tests::compliance_limits", compliance_limits),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
