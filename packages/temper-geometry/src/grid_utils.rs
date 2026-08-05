// Deterministic grid-utils kernels (Wave 4, Phase 5, first slice).
//
// Python reference:
//   temper_placer/deterministic/geometry/grid_utils.py  — `snap_to_grid`
//     and `add_endpoint_nudge` (the pure compute; the Python module is now
//     a delegation shim).
//
// Bit-exactness (see the differential
// tests/deterministic/test_grid_utils_rust_differential.py):
//
// 1. `snap_to_grid` is `round(pos / grid_size) * grid_size`. CPython's
//    `round()` without ndigits is round-half-to-EVEN (its `_Py_double_round`
//    ties to the nearest even integer), and the rounded value is an `int`
//    before the multiplication — so `int(-0.0)` becomes `0` and the product
//    carries `+0.0`, never `-0.0`. `host_math::py_round` reproduces this
//    exactly (`f64::round` is half-away-from-zero and would drift on every
//    `.5` tick; `f64::round_ties_even` is the IEEE roundTiesToEven that
//    `_Py_double_round` implements, with the `-0.0 → +0.0` correction).
// 2. `** 2` / `** 0.5` are libm `pow` (CPython's float_pow), resolved via
//    `host_math::pow` through `dlsym` to the host Python runtime's libm —
//    NOT `x * x` / `sqrt` (see host_math.rs and the Wave-4 guide's
//    numerical traps).
// 3. `add_endpoint_nudge` keeps the oracle's exact iteration: threshold
//    `dist > 1e-4` is strict, and an empty path returns `[]` (asserted
//    explicitly in the differential so vacuity cannot hide there).

use crate::host_math::{pow, py_round};

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// `round(pos / grid_size) * grid_size` — CPython `round` is half-to-even
/// and the `int * float` product normalises `-0.0` away, per the module
/// doc above. Non-finite division results raise the exact CPython errors:
/// `OverflowError` for `±inf` ("cannot convert float infinity to integer"),
/// `ValueError` for `NaN` ("cannot convert float NaN to integer").
pub fn snap_to_grid(px: f64, py: f64, grid_size: f64) -> Result<(f64, f64), SnapError> {
    let rx = px / grid_size;
    let ry = py / grid_size;
    // CPython evaluates the tuple elements left-to-right; the FIRST
    // round() that fails determines the error, so check rx before ry.
    if !rx.is_finite() {
        return Err(if rx.is_nan() {
            SnapError::Nan
        } else {
            SnapError::Infinity
        });
    }
    if !ry.is_finite() {
        return Err(if ry.is_nan() {
            SnapError::Nan
        } else {
            SnapError::Infinity
        });
    }
    Ok((py_round(rx) * grid_size, py_round(ry) * grid_size))
}

/// Why `snap_to_grid` failed to produce a result — the two cases CPython
/// raises for non-finite division results.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum SnapError {
    Infinity,
    Nan,
}

impl SnapError {
    /// The CPython exception type name for this failure mode.
    pub fn py_exception_name(&self) -> &'static str {
        match self {
            SnapError::Infinity => "OverflowError",
            SnapError::Nan => "ValueError",
        }
    }

    /// The CPython exception message for this failure mode.
    pub fn py_exception_message(&self) -> &'static str {
        match self {
            SnapError::Infinity => "cannot convert float infinity to integer",
            SnapError::Nan => "cannot convert float NaN to integer",
        }
    }
}

/// `add_endpoint_nudge` — prepend `actual_start` when it is more than
/// 1e-4 mm from the first path point, append `actual_end` when it is more
/// than 1e-4 mm from the last, preserving the path in between. An empty
/// path returns `[]`.
///
/// `path` is a flattened `[x0, y0, x1, y1, ...]`; the result is flattened
/// the same way.
pub fn add_endpoint_nudge(
    path: &[f64],
    actual_start_x: f64,
    actual_start_y: f64,
    actual_end_x: f64,
    actual_end_y: f64,
) -> Vec<f64> {
    if path.is_empty() {
        return Vec::new();
    }
    let mut result = Vec::with_capacity(path.len() + 4);

    // Nudge from actual start to first grid point. Threshold 1e-4, strict.
    let dist_start = pow(pow(path[0] - actual_start_x, 2.0) + pow(path[1] - actual_start_y, 2.0), 0.5);
    if dist_start > 1e-4 {
        result.push(actual_start_x);
        result.push(actual_start_y);
    }

    result.extend_from_slice(path);

    // Nudge from last grid point to actual end.
    let n = path.len();
    let dist_end = pow(pow(path[n - 2] - actual_end_x, 2.0) + pow(path[n - 1] - actual_end_y, 2.0), 0.5);
    if dist_end > 1e-4 {
        result.push(actual_end_x);
        result.push(actual_end_y);
    }

    result
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "snap_to_grid")]
#[pyo3(signature = (px, py, grid_size=0.25))]
pub fn snap_to_grid_py(px: f64, py: f64, grid_size: f64) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| crate::grid_utils::snap_to_grid(px, py, grid_size))
        .map_err(temper_py_bridge::panic_to_err)
        .and_then(|res| match res {
            Ok(v) => Ok(v),
            Err(e) => {
                let exc = if e == SnapError::Nan {
                    pyo3::exceptions::PyValueError::new_err(e.py_exception_message())
                } else {
                    pyo3::exceptions::PyOverflowError::new_err(e.py_exception_message())
                };
                Err(exc)
            }
        })
}

#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(name = "add_endpoint_nudge")]
pub fn add_endpoint_nudge_py(
    path: Vec<f64>,
    actual_start_x: f64,
    actual_start_y: f64,
    actual_end_x: f64,
    actual_end_y: f64,
) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| {
        crate::grid_utils::add_endpoint_nudge(&path, actual_start_x, actual_start_y, actual_end_x, actual_end_y)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;

    #[test]
    fn snap_half_even() {
        // 0.125 / 0.25 = 0.5 -> rounds to 0; 0.375 / 0.25 = 1.5 -> 2.
        assert_eq!(snap_to_grid(0.125, 0.125, 0.25).unwrap(), (0.0, 0.0));
        assert_eq!(snap_to_grid(0.375, 0.375, 0.25).unwrap(), (0.5, 0.5));
        assert_eq!(snap_to_grid(-0.125, -0.125, 0.25).unwrap(), (0.0, 0.0));
        assert_eq!(snap_to_grid(-0.375, -0.375, 0.25).unwrap(), (-0.5, -0.5));
    }

    #[test]
    fn snap_negative_zero_normalised() {
        // -0.125 / 0.25 = -0.5 -> tie -> round(-0.5) = int 0 -> +0.0 * 0.25.
        let (sx, sy) = snap_to_grid(-0.125, 0.0, 0.25).unwrap();
        assert_eq!(sx, 0.0);
        assert!(!sx.is_sign_negative());
        assert_eq!(sy, 0.0);
        // -0.5 / 0.25 = -2.0 -> not a tie -> -0.5 stays negative.
        let (sx, sy) = snap_to_grid(-0.0, -0.5, 0.25).unwrap();
        assert_eq!(sy, -0.5);
        assert!(sx == 0.0 && !sx.is_sign_negative());
    }

    #[test]
    fn snap_non_finite_errors() {
        assert!(snap_to_grid(f64::INFINITY, 0.0, 0.25).is_err());
        assert!(snap_to_grid(f64::NAN, 0.0, 0.25).is_err());
        assert!(snap_to_grid(0.0, 1.0, 0.0).is_err()); // div by zero -> inf
    }

    #[test]
    fn nudge_empty() {
        assert!(add_endpoint_nudge(&[], 1.0, 2.0, 3.0, 4.0).is_empty());
    }

    #[test]
    fn nudge_both_ends() {
        // path[0] == start -> no leading nudge; end far -> trailing nudge.
        let out = add_endpoint_nudge(&[0.0, 0.0], 0.0, 0.0, 1.0, 1.0);
        assert_eq!(out, vec![0.0, 0.0, 1.0, 1.0]);
        // start far -> leading nudge prepended.
        let out = add_endpoint_nudge(&[0.0, 0.0], -1.0, -1.0, 1.0, 1.0);
        assert_eq!(out, vec![-1.0, -1.0, 0.0, 0.0, 1.0, 1.0]);
    }

    #[test]
    fn nudge_threshold_is_strict() {
        // Exactly 1e-4 away -> NOT nudged; 1e-4 + 1e-9 -> nudged.
        let out = add_endpoint_nudge(&[1.0, 1.0], 1.0 + 1e-4, 1.0, 1.0, 1.0);
        assert_eq!(out, vec![1.0, 1.0]);
        let out = add_endpoint_nudge(&[1.0, 1.0], 1.0 + 1e-4 + 1e-9, 1.0, 1.0, 1.0);
        assert_eq!(out.len(), 4);
    }
}
