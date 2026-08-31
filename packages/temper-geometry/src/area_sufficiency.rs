//! Area-sufficiency aggregation — the Wave 4 Phase 4 analysis-surface
//! migration (plan `docs/plans/2026-08-01-001-feat-wave4-full-migration-program-plan.md`).
//!
//! Python reference: `temper_placer/analysis/_area_sufficiency.py`, pinned
//! VERBATIM in `packages/temper-placer/tests/analysis/_area_sufficiency_py_oracle.py`
//! (commit `c5875adad`). The pyo3 pyfunctions here must reproduce that
//! implementation bit-identically; the differential test
//! `packages/temper-placer/tests/analysis/test_area_sufficiency_rust_differential.py`
//! is the TDD oracle for this file.
//!
//! Boundary (argued in the delegation shim and in
//! `temper-geometry/VERIFICATION.md`): the per-courtyard areas
//! (shapely/GEOS polygon areas) and the kicad-metadata extraction stay
//! Python-side — GEOS is not bit-reproducible outside shapely, the guide's
//! "library semantics are not reimplementable" precedent.  This module owns
//! the aggregation math:
//!
//! - `py_sum` — CPython 3.12's builtin `sum()` float semantics verbatim:
//!   with the default int-0 start, the first item enters via
//!   `PyNumber_Add(0, x0)` (which normalises `-0.0` to `+0.0` under
//!   round-to-nearest), then Arnold Neumaier's compensated summation over
//!   the remainder, and a final `if (c && finite(c)) f_result += c`
//!   (mirroring `Python/bltinmodule.c`'s `builtin_sum_impl` fast path).
//!   An empty input returns `int 0`, not `float 0.0` (`sum([]) == 0`).
//! - `area_sufficiency_compute` — usable-area arithmetic
//!   (`(w - 2m) * (h - 2m)`), the non-positive-usable `ValueError` with a
//!   byte-identical message (CPython fixed-format floats via
//!   `py_float_fixed`; shortest-repr floats via `py_float_str`; int-or-float
//!   board dims rendered through their own `str()`), the ratio
//!   `(total / usable) * 100.0`, and pass-through of the original board
//!   dimension objects (an int board width stays an int in the result).
//! - `top_courtyards` — the oracle's `sorted(..., reverse=True)` stable
//!   descending sort (ties preserve input order) followed by Python's
//!   `list[:n]` slice semantics (negative `n` included).
//!
//! No recursion and no size-dependent iteration: per the plan's R1e a
//! **structural proof** is recorded in `temper-geometry/VERIFICATION.md`
//! (the summation kernel's bit-exactness is verified by the differential +
//! mutation campaign rather than by induction).

use pyo3::exceptions::PyValueError;
use pyo3::prelude::*;
use pyo3::types::PyTuple;

// ---------------------------------------------------------------------------
// CPython float-rendering replicas (per-module copies, per the established
// convention — see `priority.rs`'s helpers and `VERIFICATION.md`).
// ---------------------------------------------------------------------------

/// Render `v` exactly as CPython's `repr(float)` does.  Both languages use
/// shortest-round-trip digit selection, so the digits always agree; the
/// differences are in the exponent rendering only: CPython always writes
/// the exponent sign and pads to two digits (`1e+300`, `1e-05`), and writes
/// `nan`/`inf` where Rust's Debug writes `NaN`/`inf`.
fn py_float_str(v: f64) -> String {
    if v.is_nan() {
        return "nan".to_string();
    }
    if v.is_infinite() {
        return if v.is_sign_negative() { "-inf".to_string() } else { "inf".to_string() };
    }
    let rendered = format!("{v:?}");
    let Some(e_pos) = rendered.find(['e', 'E']) else {
        return rendered;
    };
    let (mantissa, exponent) = rendered.split_at(e_pos);
    let exponent = &exponent[1..]; // drop 'e'/'E'
    let (sign, digits) = match exponent.strip_prefix('-') {
        Some(rest) => ('-', rest),
        None => ('+', exponent),
    };
    let padded = if digits.len() < 2 {
        format!("0{digits}")
    } else {
        digits.to_string()
    };
    format!("{mantissa}e{sign}{padded}")
}

/// Render `v` exactly as CPython's `f"{v:.{precision}f}"` (fixed notation,
/// correctly rounded).  Rust's `{:.precision$}` is also correctly rounded
/// and agrees with CPython's dtoa for every finite double; the divergences
/// are the specials: CPython renders `nan`/`inf` where Rust's Debug renders
/// `NaN`/`inf` (verified against a 1,221-sample corpus in the differential).
fn py_float_fixed(v: f64, precision: usize) -> String {
    if v.is_nan() {
        return "nan".to_string();
    }
    if v.is_infinite() {
        return if v.is_sign_negative() { "-inf".to_string() } else { "inf".to_string() };
    }
    format!("{v:.precision$}")
}

#[cfg(test)]
mod py_float_tests {
    use super::{py_float_fixed, py_float_str};

    #[test]
    fn str_repr_divergence_classes() {
        assert_eq!(py_float_str(1e300), "1e+300");
        assert_eq!(py_float_str(1e-5), "1e-05");
        assert_eq!(py_float_str(f64::NAN), "nan");
        assert_eq!(py_float_str(f64::INFINITY), "inf");
        assert_eq!(py_float_str(f64::NEG_INFINITY), "-inf");
    }

    #[test]
    fn str_repr_ordinary_values() {
        assert_eq!(py_float_str(5.0), "5.0");
        assert_eq!(py_float_str(0.1), "0.1");
        assert_eq!(py_float_str(-2.25), "-2.25");
    }

    #[test]
    fn fixed_matches_cpython_on_rounding_classes() {
        // CPython 3.12: f"{2.675:.2f}" == "2.67", f"{123.456:.1f}" == "123.5"
        assert_eq!(py_float_fixed(2.675, 2), "2.67");
        assert_eq!(py_float_fixed(123.456, 1), "123.5");
        assert_eq!(py_float_fixed(-0.05, 1), "-0.1");
        assert_eq!(py_float_fixed(1.005, 2), "1.00");
        assert_eq!(py_float_fixed(5e-324, 1), "0.0");
        assert_eq!(py_float_fixed(-0.0, 1), "-0.0");
        assert_eq!(py_float_fixed(f64::NAN, 2), "nan");
        assert_eq!(py_float_fixed(f64::INFINITY, 1), "inf");
    }
}

// ---------------------------------------------------------------------------
// CPython 3.12 sum() float kernel
// ---------------------------------------------------------------------------

/// Replicate CPython 3.12's `builtin_sum_impl` float fast path over an
/// all-float iterable with the default (int 0) start:
///
/// ```c
/// result = 0 + x0;                       // PyNumber_Add: -0.0 -> +0.0
/// f_result = result; c = 0.0;
/// for x in rest:
///     t = f_result + x;
///     if (fabs(f_result) >= fabs(x)) c += (f_result - t) + x;
///     else                            c += (x - t) + f_result;
///     f_result = t;
/// if (c && Py_IS_FINITE(c)) f_result += c;
/// ```
///
/// `Neumaier, A. (1974), Rundungsfehleranalyse einiger Verfahren zur
/// Summation endlicher Summen`, exactly as CPython comments it.  The
/// `fabs`/`>=`/NaN branch structure is replicated so NaN inputs take the
/// same compensation path as CPython (NaN propagates into `c`, which then
/// fails the finite check and leaves `f_result` NaN).
pub(crate) fn py_sum_neumaier(items: &[f64]) -> f64 {
    debug_assert!(!items.is_empty(), "empty input is handled by the caller");
    let mut f_result = 0.0f64 + items[0]; // CPython: 0 (int) + x0
    let mut c = 0.0f64;
    for &x in &items[1..] {
        let t = f_result + x;
        if f_result.abs() >= x.abs() {
            c += (f_result - t) + x;
        } else {
            c += (x - t) + f_result;
        }
        f_result = t;
    }
    if c != 0.0 && c.is_finite() {
        f_result += c;
    }
    f_result
}

#[cfg(test)]
mod py_sum_tests {
    use super::py_sum_neumaier;

    #[test]
    fn neumaier_discriminator() {
        // Naive accumulation gives 0.0; compensated gives 1.0 (CPython 3.12
        // agrees with the compensated value — measured on 3.12.12).
        assert_eq!(py_sum_neumaier(&[1e16, 1.0, -1e16]), 1.0);
    }

    #[test]
    fn single_negative_zero_normalises_to_positive() {
        // CPython: 0 (int) + -0.0 == +0.0 under round-to-nearest.
        let v = py_sum_neumaier(&[-0.0]);
        assert_eq!(v, 0.0);
        assert!(v.is_sign_positive());
    }

    #[test]
    fn nan_propagates() {
        assert!(py_sum_neumaier(&[f64::NAN, 1.0]).is_nan());
        assert!(py_sum_neumaier(&[1.0, f64::NAN]).is_nan());
    }

    #[test]
    fn all_negative_zeros_stay_positive() {
        let v = py_sum_neumaier(&[-0.0, -0.0, -0.0]);
        assert!(v.is_sign_positive());
    }
}

// ---------------------------------------------------------------------------
// pyo3 surface
// ---------------------------------------------------------------------------

/// Compute the area-sufficiency aggregate for a board whose dimensions and
/// per-courtyard areas have already been extracted Python-side.
///
/// Returns `(total, usable, ratio_pct, board_width, board_height,
/// component_count)`.  `total` is `int 0` for an empty area list (CPython
/// `sum([])`), else the Neumaier-compensated float.  `board_width` /
/// `board_height` are passed through unchanged (int boards stay int).
///
/// Raises `ValueError` with the oracle's byte-identical message when the
/// usable region is non-positive.
#[pyfunction]
#[pyo3(signature = (board_width, board_height, margin_mm, areas))]
fn area_sufficiency_compute(
    py: Python<'_>,
    board_width: &Bound<'_, PyAny>,
    board_height: &Bound<'_, PyAny>,
    margin_mm: f64,
    areas: Vec<f64>,
) -> PyResult<Py<PyAny>> {
    let bw = board_width.extract::<f64>()?;
    let bh = board_height.extract::<f64>()?;
    let used_w = bw - 2.0 * margin_mm;
    let used_h = bh - 2.0 * margin_mm;
    let usable = used_w * used_h;
    if used_w <= 0.0 || used_h <= 0.0 || usable <= 0.0 {
        let message = format!(
            "Usable board area is non-positive ({} mm^2) with {}mm margin on {}x{}mm board (usable region: {}x{} mm).",
            py_float_fixed(usable, 1),
            py_float_str(margin_mm),
            board_width.str()?.to_str()?,
            board_height.str()?.to_str()?,
            py_float_fixed(used_w, 1),
            py_float_fixed(used_h, 1),
        );
        return Err(PyValueError::new_err(message));
    }
    let total: Py<PyAny> = if areas.is_empty() {
        0i64.into_pyobject(py)?.unbind().into_any()
    } else {
        py_sum_neumaier(&areas).into_pyobject(py)?.unbind().into_any()
    };
    let total_f64: f64 = if areas.is_empty() { 0.0 } else { total.extract(py)? };
    let ratio = (total_f64 / usable) * 100.0;
    let tuple = PyTuple::new(
        py,
        [
            total,
            usable.into_pyobject(py)?.unbind().into_any(),
            ratio.into_pyobject(py)?.unbind().into_any(),
            board_width.clone().unbind().into_any(),
            board_height.clone().unbind().into_any(),
            (areas.len() as i64).into_pyobject(py)?.unbind().into_any(),
        ],
    )?;
    Ok(tuple.into_any().unbind())
}

/// Stable descending sort of `(ref, area)` pairs by area, then Python's
/// `list[:n]` slice semantics.  Ties preserve input order (the oracle's
/// `sorted(..., reverse=True)` is stable; `slice::sort_by` is stable).
#[pyfunction]
fn top_courtyards(pairs: Vec<(String, f64)>, n: i64) -> Vec<(String, f64)> {
    let mut pairs = pairs;
    pairs.sort_by(|a, b| b.1.partial_cmp(&a.1).unwrap_or(std::cmp::Ordering::Equal));
    let len = pairs.len() as i64;
    let take: usize = if n >= len {
        len as usize
    } else if n < 0 {
        (len + n).max(0) as usize
    } else {
        n as usize
    };
    pairs.truncate(take);
    pairs
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(area_sufficiency_compute, m)?)?;
    m.add_function(wrap_pyfunction!(top_courtyards, m)?)?;
    Ok(())
}
