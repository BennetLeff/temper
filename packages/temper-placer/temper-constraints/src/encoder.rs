//! CP-SAT encoder pure compute (Wave 3 #4).
//!
//! Python references: `temper_placer/placer/cp_sat/model.py`
//! (`CpSatModel.mm_to_units` / `units_to_mm`), `_encoder_solve.py`
//! (the courtyard τ margin, C1), `domain_clearance.py`
//! (`required_margin_mm`), and `handlers/keepout.py` (the
//! margin-expanded keepout bbox).
//!
//! This is the *pure numeric* surface of the CP-SAT constraint encoder
//! — everything the handlers do with board geometry before/around the
//! ortools calls: unit conversion (every handler's margin math funnels
//! through `mm_to_units`) and the margin parameters (courtyard τ, the
//! domain-classification margin, the keepout bbox).  The ortools
//! orchestration (CpModel/IntVar construction, handler dispatch, solver
//! calls) stays Python; only these functions move to Rust.
//!
//! Bit-exactness (the repo's hard-won notes, applied here):
//! - Python `round(x)` (no ndigits) is round-half-even on the float —
//!   Rust `round_ties_even()`, NOT `f64::round` (half away from zero).
//!   `int(round(±inf))` raises OverflowError and `int(round(nan))`
//!   raises ValueError in CPython; both are replicated.
//! - The even-parity adjustment `raw - (raw % 2)` uses Python's *floor*
//!   modulo, so a negative odd raw decrements by one (-15 -> -16).
//!   Rust's truncating `%` would give -14, so the port uses
//!   `rem_euclid` (see `mm_to_units`'s unit tests).
//! - `keepout_rect_units` converts the *difference* `zx_max - zx_min`
//!   (f64 subtraction first), never the difference of conversions —
//!   the two disagree at rounding boundaries and the reference's order
//!   is preserved exactly.
//! - `required_margin_mm` replicates Python builtin `max` (returns the
//!   first argument whenever `b > a` is false) — `f64::max` would
//!   discard a NaN, the builtin does not.
//!
//! Parity is pinned bit-exactly by
//! `tests/placer/cp_sat/test_encoder_rust_differential.py` and
//! `test_encoder_rust_pbt.py` (Wave 3 #4).

use pyo3::exceptions::{PyOverflowError, PyRuntimeError, PyValueError};
use pyo3::prelude::*;
use std::panic::{self};

fn catch_unwind<T>(f: impl FnOnce() -> PyResult<T>) -> PyResult<T> {
    match panic::catch_unwind(panic::AssertUnwindSafe(f)) {
        Ok(result) => result,
        Err(panic_info) => {
            let msg = if let Some(s) = panic_info.downcast_ref::<String>() {
                s.clone()
            } else if let Some(s) = panic_info.downcast_ref::<&str>() {
                s.to_string()
            } else {
                "unknown panic in temper_constraints::encoder".to_string()
            };
            Err(PyRuntimeError::new_err(format!("temper_constraints panic: {msg}")))
        }
    }
}

// ---------------------------------------------------------------------------
// Unit conversion (model.py::CpSatModel.mm_to_units / units_to_mm)
// ---------------------------------------------------------------------------

/// Mirrors `CpSatModel.mm_to_units`: `int(round(mm * units_per_mm))`
/// (Python round-half-even, no ndigits) then forced even parity.
///
/// The even parity is REQUIRED by the model's midpoint constraint
/// `x_start + x_end == 2 * x_center`: sizes must be even so
/// `2 * x_start + x_size` is even, matching `2 * x_center`.
fn mm_to_units(mm: f64, units_per_mm: i64) -> PyResult<i64> {
    if !mm.is_finite() {
        // CPython int(round(x)): inf -> OverflowError, NaN -> ValueError.
        if mm.is_nan() {
            return Err(PyValueError::new_err("cannot convert float NaN to integer"));
        }
        return Err(PyOverflowError::new_err(
            "cannot convert float infinity to integer",
        ));
    }
    let scaled = mm * units_per_mm as f64;
    let rounded = scaled.round_ties_even();
    // The scaled value is finite, so `rounded` is finite too; but an
    // extreme magnitude would exceed i64 (CPython would produce a big
    // int).  `i64::MAX as f64` is exactly 2^63, so the comparison is
    // precise at the boundary.
    if !(rounded >= i64::MIN as f64 && rounded < i64::MAX as f64) {
        return Err(PyOverflowError::new_err(
            "integer conversion resulted in overflow",
        ));
    }
    let raw = rounded as i64;
    // Python `raw - (raw % 2) if raw % 2 else raw`: `%` is *floor*
    // modulo, so a negative odd raw decrements by one.  rem_euclid(2)
    // is the exact replica (truncating `%` would give -1 for -3).
    let rem = raw.rem_euclid(2);
    Ok(if rem != 0 { raw - rem } else { raw })
}

/// Mirrors `CpSatModel.units_to_mm`: `units / units_per_mm`.
fn units_to_mm(units: i64, units_per_mm: i64) -> f64 {
    units as f64 / units_per_mm as f64
}

// ---------------------------------------------------------------------------
// Courtyard clearance τ (C1, _encoder_solve.py)
// ---------------------------------------------------------------------------

/// Mirrors `_encoder_solve.py`'s courtyard τ:
/// `default_clearance_mm + 2 * MASK_EXPANSION_MM`.
///
/// Strict `+`, not `max()`: the mask-expansion term must *add* to the
/// default so mask apertures never touch at 0 (solder-mask bridging).
/// Operation order preserved: `2 * expansion` first, then the addition.
fn courtyard_clearance_mm(default_clearance_mm: f64, mask_expansion_mm: f64) -> f64 {
    default_clearance_mm + 2.0 * mask_expansion_mm
}

// ---------------------------------------------------------------------------
// Domain-classification margin (domain_clearance.py::required_margin_mm)
// ---------------------------------------------------------------------------

/// Python builtin `max(a, b)` for two args: returns `a` whenever
/// `b > a` is false (so max(NaN, x) == NaN but max(x, NaN) == x) —
/// `f64::max` would discard the NaN, the builtin does not.
fn py_max(a: f64, b: f64) -> f64 {
    if b > a {
        b
    } else {
        a
    }
}

/// Mirrors `domain_clearance.py::required_margin_mm`: `max` of the
/// clearance and creepage minimums so one SeparatedConstraint per pair
/// satisfies both IEC 60335-2-6 checks simultaneously.
fn required_margin_mm(clearance_mm: f64, creepage_mm: f64) -> f64 {
    py_max(clearance_mm, creepage_mm)
}

// ---------------------------------------------------------------------------
// Keepout bbox (handlers/keepout.py)
// ---------------------------------------------------------------------------

/// Mirrors `handlers/keepout.py`'s margin-expanded keepout rectangle in
/// model units, exact f64/i64 operation order:
///
/// ```text
/// margin_u = mm_to_units(margin_mm)
/// kx_s = mm_to_units(zx_min)      - margin_u
/// ky_s = mm_to_units(zy_min)      - margin_u
/// kx_w = mm_to_units(zx_max - zx_min) + 2 * margin_u   # span converted,
/// ky_h = mm_to_units(zy_max - zy_min) + 2 * margin_u   # not diff-of-convs
/// ```
fn keepout_rect_units(
    zx_min: f64,
    zy_min: f64,
    zx_max: f64,
    zy_max: f64,
    margin_mm: f64,
    units_per_mm: i64,
) -> PyResult<(i64, i64, i64, i64)> {
    let margin_u = mm_to_units(margin_mm, units_per_mm)?;
    let kx_s = mm_to_units(zx_min, units_per_mm)? - margin_u;
    let ky_s = mm_to_units(zy_min, units_per_mm)? - margin_u;
    let kx_w = mm_to_units(zx_max - zx_min, units_per_mm)? + 2 * margin_u;
    let ky_h = mm_to_units(zy_max - zy_min, units_per_mm)? + 2 * margin_u;
    Ok((kx_s, ky_s, kx_w, ky_h))
}

// ---------------------------------------------------------------------------
// PyO3 bridge
// ---------------------------------------------------------------------------

#[pyfunction]
pub fn mm_to_units_py(mm: f64, units_per_mm: i64) -> PyResult<i64> {
    catch_unwind(|| mm_to_units(mm, units_per_mm))
}

#[pyfunction]
pub fn units_to_mm_py(units: i64, units_per_mm: i64) -> PyResult<f64> {
    catch_unwind(|| Ok(units_to_mm(units, units_per_mm)))
}

#[pyfunction]
pub fn courtyard_clearance_mm_py(default_clearance_mm: f64, mask_expansion_mm: f64) -> PyResult<f64> {
    catch_unwind(|| Ok(courtyard_clearance_mm(default_clearance_mm, mask_expansion_mm)))
}

#[pyfunction]
pub fn required_margin_mm_py(clearance_mm: f64, creepage_mm: f64) -> PyResult<f64> {
    catch_unwind(|| Ok(required_margin_mm(clearance_mm, creepage_mm)))
}

#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn keepout_rect_units_py(
    zx_min: f64,
    zy_min: f64,
    zx_max: f64,
    zy_max: f64,
    margin_mm: f64,
    units_per_mm: i64,
) -> PyResult<(i64, i64, i64, i64)> {
    catch_unwind(|| keepout_rect_units(zx_min, zy_min, zx_max, zy_max, margin_mm, units_per_mm))
}

#[cfg(test)]
#[allow(clippy::unwrap_used)] // tests may unwrap; failures surface as test panics
mod tests {
    use super::*;

    #[test]
    fn mm_to_units_known_points() {
        assert_eq!(mm_to_units(10.0, 100).unwrap(), 1000);
        assert_eq!(mm_to_units(0.1, 100).unwrap(), 10);
        assert_eq!(mm_to_units(5.0, 100).unwrap(), 500);
        assert_eq!(mm_to_units(0.0, 100).unwrap(), 0);
        assert_eq!(mm_to_units(-3.0, 100).unwrap(), -300);
    }

    #[test]
    fn mm_to_units_ties_round_half_even() {
        // mm*u exactly k+0.5 (mm = m/8, m odd): 12.5 -> 12, 37.5 -> 38.
        assert_eq!(mm_to_units(0.125, 100).unwrap(), 12);
        assert_eq!(mm_to_units(0.375, 100).unwrap(), 38);
        assert_eq!(mm_to_units(0.625, 100).unwrap(), 62);
    }

    #[test]
    fn mm_to_units_odd_raw_even_adjusted() {
        // 31.25 -> round 31 -> odd -> 30; 0.155*100 = 15.5 exactly
        // (0.155 is stored just above 0.155, the product rounds to 15.5)
        // -> tie to even -> 16, no adjustment needed.
        assert_eq!(mm_to_units(0.3125, 100).unwrap(), 30);
        assert_eq!(mm_to_units(0.155, 100).unwrap(), 16);
    }

    #[test]
    fn mm_to_units_negative_uses_floor_modulo() {
        // Python floor-mod: -15 % 2 == 1, so -15 -> -16 (truncating %
        // would give -15 - (-1) = -14).
        assert_eq!(mm_to_units(-0.155, 100).unwrap(), -16);
        assert_eq!(mm_to_units(-0.125, 100).unwrap(), -12);
    }

    #[test]
    fn mm_to_units_non_finite_errors() {
        assert!(mm_to_units(f64::NAN, 100).is_err());
        assert!(mm_to_units(f64::INFINITY, 100).is_err());
        assert!(mm_to_units(f64::NEG_INFINITY, 100).is_err());
    }

    #[test]
    fn units_to_mm_known_points() {
        assert_eq!(units_to_mm(1000, 100), 10.0);
        assert_eq!(units_to_mm(0, 100), 0.0);
        assert_eq!(units_to_mm(-1000, 100), -10.0);
        assert_eq!(units_to_mm(1, 100), 0.01);
        assert_eq!(units_to_mm(100, 100), 1.0);
    }

    #[test]
    fn courtyard_clearance_known_points() {
        assert_eq!(courtyard_clearance_mm(0.2, 0.1), 0.4);
        assert_eq!(courtyard_clearance_mm(0.0, 0.0), 0.0);
        assert_eq!(courtyard_clearance_mm(1.0, 0.25), 1.5);
        // Strict plus, not max: zero default still yields positive τ.
        assert_eq!(courtyard_clearance_mm(0.0, 0.1), 0.2);
    }

    #[test]
    fn required_margin_known_points() {
        assert_eq!(required_margin_mm(6.0, 8.0), 8.0);
        assert_eq!(required_margin_mm(8.0, 6.0), 8.0);
        assert_eq!(required_margin_mm(6.0, 6.0), 6.0);
        // Builtin max(NaN, x) == NaN; max(x, NaN) == x.
        assert!(required_margin_mm(f64::NAN, 8.0).is_nan());
        assert_eq!(required_margin_mm(8.0, f64::NAN), 8.0);
    }

    #[test]
    fn keepout_rect_known_points() {
        // Zone (10,10)-(20,20)mm, margin 0.5mm, u=100.
        assert_eq!(
            keepout_rect_units(10.0, 10.0, 20.0, 20.0, 0.5, 100).unwrap(),
            (950, 950, 1100, 1100)
        );
        // Zero margin: converted zone itself.
        assert_eq!(
            keepout_rect_units(10.0, 10.0, 20.0, 20.0, 0.0, 100).unwrap(),
            (1000, 1000, 1000, 1000)
        );
    }

    #[test]
    fn keepout_rect_converts_span_not_diff_of_conversions() {
        // zx_min=0.11599784954941361, zx_max=1.0148714663788405:
        // span-first gives +90, difference-of-conversions gives 88 — the
        // reference order (span converted first) wins.
        assert_eq!(
            keepout_rect_units(0.11599784954941361, 0.0, 1.0148714663788405, 0.0, 0.0, 100).unwrap(),
            (12, 0, 90, 0)
        );
        // The difference-of-conversions order genuinely disagrees.
        let conv = |mm: f64| mm_to_units(mm, 100).unwrap_or(i64::MIN);
        assert_ne!(conv(1.0148714663788405) - conv(0.11599784954941361), 90);
    }
}
