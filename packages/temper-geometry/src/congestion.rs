//! Wave-4 Phase B: the `router_v6` congestion cluster in Rust.
//!
//! Mirrors, bit for bit, the pinned Python oracle
//! `packages/temper-placer/tests/router_v6/_congestion_py_oracle.py`,
//! re-pinned by #801 onto post-#760 source (defects **D1**, **D2**, **D3**
//! repaired).
//!
//! # Slice 1 of the cluster: `CongestionGrid`
//!
//! `congestion_grid_from_board_py`, `congestion_grid_utilization_py` and
//! `congestion_grid_overflow_py`. The remaining entry points in
//! `REQUIRED_RUST_SYMBOLS` (analysis, routing demand, placement suggestions,
//! heatmap) are not implemented yet; their differentials stay RED by design
//! until they are.
//!
//! # Why this calls numpy instead of computing in Rust
//!
//! The reference computes with numpy, and the differential compares through
//! `_signature.sig`, which carries **dtype and shape** alongside every
//! element's `float.hex()`. Re-deriving numpy's elementwise semantics in Rust
//! would have to reproduce, exactly:
//!
//! * **B12** — `np.maximum` propagates NaN from *either* operand.
//!   `f64::max` DISCARDS NaN and CPython's `max` keeps only the first
//!   operand's; both are wrong here, and the corpus carries one NaN per
//!   position independently (`[NAN, 1.0] / [10.0, 10.0]` and its mirror)
//!   precisely to catch a mirror that picks either.
//! * `inf - inf -> NaN` in `get_overflow`, signed zeros through
//!   `np.maximum(supply, 1e-6)`, and the denormal band (B8).
//!
//! Calling numpy inherits all of that by construction rather than by
//! re-implementation, which is the only way the "no tolerance anywhere" bar
//! is reachable for these three functions.

use pyo3::exceptions::{PyOverflowError, PyValueError};
use pyo3::prelude::*;
use pyo3::types::PyAnyMethods;

/// `int(math.ceil(v))`.
///
/// `math.ceil` is not `f64::ceil`: on a non-finite argument CPython raises
/// rather than saturating, and the corpus exercises both edges — an `inf`
/// board width (from `1e300 / 1e-300` as well as a literal) and NaN.
/// A bare `v.ceil() as i64` saturates silently at `i64::MAX`, which would
/// turn a raising case into a gigantic allocation.
fn ceil_to_int(v: f64) -> PyResult<i64> {
    if v.is_nan() {
        return Err(PyValueError::new_err(
            "cannot convert float NaN to integer",
        ));
    }
    if v.is_infinite() {
        return Err(PyOverflowError::new_err(
            "cannot convert float infinity to integer",
        ));
    }
    Ok(v.ceil() as i64)
}

/// `CongestionGrid.from_board`.
///
/// Returns the 7-tuple the differential projects:
/// `(demand, supply, cell_size_mm, width_cells, height_cells, num_layers,
/// origin)`.
///
/// The `num_layers == 1` branch is 2-D and every other value is 3-D — that is
/// the reference's own test, not `<= 1`, so `num_layers=0` takes the 3-D path
/// and yields a leading zero dimension.
#[pyfunction]
#[pyo3(signature = (width, height, origin, cell_size_mm, num_layers, default_supply))]
pub fn congestion_grid_from_board_py<'py>(
    py: Python<'py>,
    width: f64,
    height: f64,
    origin: (f64, f64),
    cell_size_mm: f64,
    num_layers: i64,
    default_supply: f64,
) -> PyResult<Bound<'py, PyAny>> {
    let width_cells = ceil_to_int(width / cell_size_mm)?;
    let height_cells = ceil_to_int(height / cell_size_mm)?;

    let np = py.import("numpy")?;
    let (demand, supply) = if num_layers == 1 {
        let shape = (height_cells, width_cells);
        (
            np.call_method1("zeros", (shape,))?,
            np.call_method1("full", (shape, default_supply))?,
        )
    } else {
        let shape = (num_layers, height_cells, width_cells);
        (
            np.call_method1("zeros", (shape,))?,
            np.call_method1("full", (shape, default_supply))?,
        )
    };

    let out = (
        demand,
        supply,
        cell_size_mm,
        width_cells,
        height_cells,
        num_layers,
        origin,
    );
    Ok(out.into_pyobject(py)?.into_any())
}

/// Build the 1 x N f64 array `_congestion_builders.build_grid` builds, so the
/// two arms start from an identical object.
fn row_array<'py>(py: Python<'py>, row: &[f64]) -> PyResult<Bound<'py, PyAny>> {
    let np = py.import("numpy")?;
    let dtype = np.getattr("float64")?;
    let kwargs = pyo3::types::PyDict::new(py);
    kwargs.set_item("dtype", dtype)?;
    np.call_method("array", (vec![row.to_vec()],), Some(&kwargs))
}

/// `CongestionGrid.get_utilization` — `demand / np.maximum(supply, 1e-6)`.
#[pyfunction]
pub fn congestion_grid_utilization_py<'py>(
    py: Python<'py>,
    demand: Vec<f64>,
    supply: Vec<f64>,
) -> PyResult<Bound<'py, PyAny>> {
    let np = py.import("numpy")?;
    let d = row_array(py, &demand)?;
    let s = row_array(py, &supply)?;
    // `np.maximum(supply, 1e-6)` -- NOT `f64::max`, which discards NaN (B12).
    let floored = np.call_method1("maximum", (s, 1e-6f64))?;
    d.div(floored)
}

/// `CongestionGrid.get_overflow` — `np.maximum(demand - supply, 0.0)`.
///
/// `inf - inf` is NaN here, and `np.maximum(NaN, 0.0)` is NaN, so an overflow
/// of NaN is a reachable result rather than an error.
#[pyfunction]
pub fn congestion_grid_overflow_py<'py>(
    py: Python<'py>,
    demand: Vec<f64>,
    supply: Vec<f64>,
) -> PyResult<Bound<'py, PyAny>> {
    let np = py.import("numpy")?;
    let d = row_array(py, &demand)?;
    let s = row_array(py, &supply)?;
    let diff = d.sub(s)?;
    np.call_method1("maximum", (diff, 0.0f64))
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(congestion_grid_from_board_py, m)?)?;
    m.add_function(wrap_pyfunction!(congestion_grid_utilization_py, m)?)?;
    m.add_function(wrap_pyfunction!(congestion_grid_overflow_py, m)?)?;
    Ok(())
}
