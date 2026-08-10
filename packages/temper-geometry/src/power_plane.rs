// Wave 4: `temper_placer/router_v6/power_plane.py` — the functional 4-layer
// power-plane geometry kernels (rect corners, isolated pour-strip partition,
// thermal-via NxN grid).  The Board/Component object access
// (`_board_bounds`, `_component_center`), the dataclasses, and the IGBT-ref
// filtering stay in Python; every pure-geometry computation crosses this
// boundary.
//
// The verbatim pre-migration copy this module must reproduce bit-identically
// is pinned in the `_oracle_*` block of
// `packages/temper-placer/tests/router_v6/
// test_spatial_drc_cluster_rust_differential.py`.
//
// ---------------------------------------------------------------------------
// Numerical contract
// ---------------------------------------------------------------------------
// * `_rect_polygon` is a 4-corner CCW vertex list — no arithmetic at all.
// * `generate_power_pours`: `total_gap = gap * (n-1)`, `strip_width =
//   (total_width - total_gap) / n`, then per strip `x_min + i * (strip_width
//   + gap)`, `x_max = x_min + strip_width`.  Ops are copied left-to-right
//   (class B7); no reassociation.  The two ValueError branches are raised
//   with CPython-exact messages (`py_float_str`, class B10 — Rust `{:?}`
//   differs from CPython `repr` for integer-valued floats and for the
//   exponent form).
// * `_thermal_via_positions`: `side = int(round(count**0.5))` — `count**0.5`
//   is CPython float `**` = host libm `pow` (class B1, resolved via
//   `host_math::pow`), and `round()` is round-half-EVEN (class B3, via
//   `host_math::py_round`).  The perfect-square check raises
//   `ValueError("count must be a perfect square, got {count}")` — the
//   message interpolates only an int, so it is constructed in Rust exactly.
// * `diameter_mm <= drill_mm` validation and its float-message ValueError
//   stay in the Python shim (the message interpolates floats; keeping the
//   check in Python makes the message exact by construction).

use crate::host_math::{pow as math_pow, py_round};

#[cfg(feature = "python")]
use pyo3::exceptions::PyValueError;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// CPython `repr(float)` for the ValueError messages: shortest round-trip
/// digits (Rust `{:?}` already produces those), with CPython's exponent
/// rendering (`1e+300`, `1e-05`) and a `.0` suffix for integer-valued
/// floats.  Class B10.
pub fn py_float_str(v: f64) -> String {
    if v.is_nan() {
        return "nan".into();
    }
    if v.is_infinite() {
        return if v > 0.0 { "inf".into() } else { "-inf".into() };
    }
    let s = format!("{v:?}");
    if let Some(exp_start) = s.find(['e', 'E']) {
        let (mant, _exp) = s.split_at(exp_start);
        let exp_digits = &s[exp_start + 1..];
        let (sign, digits) = match exp_digits.strip_prefix('-') {
            Some(rest) => ('-', rest),
            None => ('+', exp_digits),
        };
        let digits = if digits.len() < 2 {
            format!("0{digits}")
        } else {
            digits.to_string()
        };
        return format!("{mant}e{sign}{digits}");
    }
    // No exponent form: integer-valued floats must carry ".0".
    if s.bytes().all(|b| b.is_ascii_digit() || b == b'-') {
        return format!("{s}.0");
    }
    s
}

/// `_rect_polygon`: the 4 corners of an axis-aligned rectangle (CCW).
pub fn rect_polygon(x_min: f64, y_min: f64, x_max: f64, y_max: f64) -> Vec<(f64, f64)> {
    vec![(x_min, y_min), (x_max, y_min), (x_max, y_max), (x_min, y_max)]
}

/// Errors from `power_pour_strips`, mapped to CPython-exact ValueErrors at
/// the pyo3 boundary.
#[derive(Debug, Clone, PartialEq)]
pub enum PourError {
    NegativeGap(f64),
    NarrowBoard { total_width: f64, n: usize, gap: f64 },
}

/// `generate_power_pours` strip partition.  Returns `(strip_x_min,
/// strip_x_max)` per domain in domain order.  `n == 0` yields an empty list
/// (the shim returns `[]` for an empty domain list before calling).
pub fn power_pour_strips(
    x_min: f64,
    _y_min: f64,
    x_max: f64,
    _y_max: f64,
    n: usize,
    isolation_gap_mm: f64,
) -> Result<Vec<(f64, f64)>, PourError> {
    if n == 0 {
        return Ok(Vec::new());
    }
    if isolation_gap_mm < 0.0 {
        return Err(PourError::NegativeGap(isolation_gap_mm));
    }
    let total_width = x_max - x_min;
    let total_gap = isolation_gap_mm * (n - 1) as f64;
    let strip_width = (total_width - total_gap) / n as f64;
    if strip_width <= 0.0 {
        return Err(PourError::NarrowBoard {
            total_width,
            n,
            gap: isolation_gap_mm,
        });
    }
    let mut strips = Vec::with_capacity(n);
    for i in 0..n {
        let strip_x_min = x_min + i as f64 * (strip_width + isolation_gap_mm);
        let strip_x_max = strip_x_min + strip_width;
        strips.push((strip_x_min, strip_x_max));
    }
    Ok(strips)
}

/// Error from `thermal_via_positions`.
#[derive(Debug, Clone, PartialEq)]
pub enum ViaError {
    NotPerfectSquare(u32),
}

/// `_thermal_via_positions`: an NxN grid of via centres around `center`,
/// row-major (row outer, col inner), matching the reference's
/// `for row in range(side) for col in range(side)`.
pub fn thermal_via_positions(
    cx: f64,
    cy: f64,
    count: u32,
    pitch_mm: f64,
) -> Result<Vec<(f64, f64)>, ViaError> {
    let side = py_round(math_pow(count as f64, 0.5)) as i64;
    if side * side != count as i64 {
        return Err(ViaError::NotPerfectSquare(count));
    }
    let span = (side - 1) as f64 * pitch_mm;
    let x0 = cx - span / 2.0;
    let y0 = cy - span / 2.0;
    let mut out = Vec::with_capacity((side * side) as usize);
    for row in 0..side {
        for col in 0..side {
            out.push((x0 + col as f64 * pitch_mm, y0 + row as f64 * pitch_mm));
        }
    }
    Ok(out)
}

// ---------------------------------------------------------------------------
// pyo3 boundary
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
#[pyfunction]
pub fn rect_polygon_py(x_min: f64, y_min: f64, x_max: f64, y_max: f64) -> PyResult<Vec<(f64, f64)>> {
    temper_py_bridge::catch_unwind(|| rect_polygon(x_min, y_min, x_max, y_max))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn power_pour_strips_py(
    x_min: f64,
    y_min: f64,
    x_max: f64,
    y_max: f64,
    n: usize,
    isolation_gap_mm: f64,
) -> PyResult<Vec<(f64, f64)>> {
    temper_py_bridge::catch_unwind(|| {
        power_pour_strips(x_min, y_min, x_max, y_max, n, isolation_gap_mm)
    })
    .map_err(temper_py_bridge::panic_to_err)?
    .map_err(|e| match e {
        PourError::NegativeGap(g) => PyValueError::new_err(format!(
            "isolation_gap_mm must be >= 0, got {}",
            py_float_str(g)
        )),
        PourError::NarrowBoard { total_width, n, gap } => PyValueError::new_err(format!(
            "Board too narrow ({}mm) for {} isolated pours with {}mm gaps",
            py_float_str(total_width),
            n,
            py_float_str(gap)
        )),
    })
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn thermal_via_positions_py(
    cx: f64,
    cy: f64,
    count: u32,
    pitch_mm: f64,
) -> PyResult<Vec<(f64, f64)>> {
    temper_py_bridge::catch_unwind(|| thermal_via_positions(cx, cy, count, pitch_mm))
        .map_err(temper_py_bridge::panic_to_err)?
        .map_err(|e| match e {
            ViaError::NotPerfectSquare(count) => {
                PyValueError::new_err(format!("count must be a perfect square, got {count}"))
            }
        })
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(rect_polygon_py, m)?)?;
    m.add_function(wrap_pyfunction!(power_pour_strips_py, m)?)?;
    m.add_function(wrap_pyfunction!(thermal_via_positions_py, m)?)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// tests
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn rect_polygon_corners_ccw() {
        assert_eq!(
            rect_polygon(0.0, 0.0, 10.0, 5.0),
            vec![(0.0, 0.0), (10.0, 0.0), (10.0, 5.0), (0.0, 5.0)]
        );
    }

    #[cfg_attr(test, test)]
    fn power_pour_strips_partition_exact() {
        // (10 - 2*0.5)/3 = 3.0; strips at [0,3),[3.5,6.5),[7,10)
        assert_eq!(
            power_pour_strips(0.0, 0.0, 10.0, 20.0, 3, 0.5),
            Ok(vec![(0.0, 3.0), (3.5, 6.5), (7.0, 10.0)])
        );
    }

    #[cfg_attr(test, test)]
    fn power_pour_strips_empty_and_errors() {
        assert_eq!(power_pour_strips(0.0, 0.0, 10.0, 10.0, 0, 0.5), Ok(vec![]));
        assert_eq!(
            power_pour_strips(0.0, 0.0, 10.0, 10.0, 3, -0.3),
            Err(PourError::NegativeGap(-0.3))
        );
        // total_width = 0.5 < 2*gap -> negative strip width
        assert!(matches!(
            power_pour_strips(0.0, 0.0, 0.5, 10.0, 3, 0.3),
            Err(PourError::NarrowBoard { .. })
        ));
    }

    #[cfg_attr(test, test)]
    fn thermal_via_positions_3x3_grid() {
        let vias = thermal_via_positions(0.0, 0.0, 9, 1.0);
        assert_eq!(vias, Ok(vec![
            (-1.0, -1.0), (0.0, -1.0), (1.0, -1.0),
            (-1.0, 0.0), (0.0, 0.0), (1.0, 0.0),
            (-1.0, 1.0), (0.0, 1.0), (1.0, 1.0),
        ]));
    }

    #[cfg_attr(test, test)]
    fn thermal_via_positions_error_and_edges() {
        assert_eq!(thermal_via_positions(0.0, 0.0, 2, 1.0), Err(ViaError::NotPerfectSquare(2)));
        assert_eq!(thermal_via_positions(0.0, 0.0, 1, 1.0), Ok(vec![(0.0, 0.0)]));
        assert_eq!(thermal_via_positions(0.0, 0.0, 0, 1.0), Ok(vec![]));
    }

    #[cfg_attr(test, test)]
    fn py_float_str_matches_cpython_repr() {
        assert_eq!(py_float_str(0.5), "0.5");
        assert_eq!(py_float_str(1.0), "1.0");
        assert_eq!(py_float_str(-0.3), "-0.3");
        assert_eq!(py_float_str(-0.0), "-0.0");
        assert_eq!(py_float_str(1e20), "1e+20");
        assert_eq!(py_float_str(1.5e20), "1.5e+20");
        assert_eq!(py_float_str(1e-5), "1e-05");
        assert_eq!(py_float_str(f64::NAN), "nan");
        assert_eq!(py_float_str(f64::INFINITY), "inf");
        assert_eq!(py_float_str(f64::NEG_INFINITY), "-inf");
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("power_plane::tests::rect_polygon_corners_ccw", rect_polygon_corners_ccw),
        ("power_plane::tests::power_pour_strips_partition_exact", power_pour_strips_partition_exact),
        ("power_plane::tests::power_pour_strips_empty_and_errors", power_pour_strips_empty_and_errors),
        ("power_plane::tests::thermal_via_positions_3x3_grid", thermal_via_positions_3x3_grid),
        ("power_plane::tests::thermal_via_positions_error_and_edges", thermal_via_positions_error_and_edges),
        ("power_plane::tests::py_float_str_matches_cpython_repr", py_float_str_matches_cpython_repr),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
