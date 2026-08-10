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
pub(crate) fn ceil_to_int(v: f64) -> PyResult<i64> {
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
pub(crate) fn row_array<'py>(py: Python<'py>, row: &[f64]) -> PyResult<Bound<'py, PyAny>> {
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
    m.add_function(wrap_pyfunction!(congestion_estimate_net_demand_py, m)?)?;
    m.add_function(wrap_pyfunction!(congestion_bottleneck_to_coordinates_py, m)?)?;
    m.add_function(wrap_pyfunction!(congestion_result_overflow_ratio_py, m)?)?;
    m.add_function(wrap_pyfunction!(congestion_result_top_bottlenecks_py, m)?)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Slice 2: estimate_net_demand
// ---------------------------------------------------------------------------

/// CPython's `min` over a list: `acc = first; for x in rest { if x < acc { acc = x } }`.
///
/// A NaN comparison is false, so a NaN in the FIRST position sticks and a NaN
/// anywhere later is discarded. `f64::min` is the opposite (it discards NaN
/// entirely) and `np.min` propagates any NaN; both are wrong here. The corpus
/// carries a NaN coordinate for exactly this.
pub(crate) fn cpython_min(vals: &[f64]) -> f64 {
    let mut acc = vals[0];
    for &x in &vals[1..] {
        if x < acc {
            acc = x;
        }
    }
    acc
}

/// CPython's `max`, mirroring [`cpython_min`]'s asymmetry.
pub(crate) fn cpython_max(vals: &[f64]) -> f64 {
    let mut acc = vals[0];
    for &x in &vals[1..] {
        if x > acc {
            acc = x;
        }
    }
    acc
}

/// `int(x)` — truncation toward ZERO, and CPython's errors on non-finite.
///
/// Not `floor`: `int(-2.7)` is `-2`, while `(-2.7f64).floor()` is `-3`. That
/// difference is what lands a bounding box one cell off on the negative side
/// of the origin, which is the neighbourhood of defect D3.
pub(crate) fn int_trunc(v: f64) -> PyResult<i64> {
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
    Ok(v.trunc() as i64)
}

/// `estimate_net_demand`, projected as the differential signs it:
/// `(demand, out is grid)`.
///
/// The identity flag is part of the contract, not a convenience. Both early
/// returns hand back the INPUT grid — fewer than two pins, and D3's
/// "bounding box does not intersect the grid" guard. Before #760 that guard
/// clamped from one side only, so a net entirely left of or above the board
/// left `col_max`/`row_max` negative and
/// `demand[0 : -3 + 1, 0 : -3 + 1]` wrote a real block of demand at the board
/// ORIGIN. A mirror that returns a fresh copy carrying an empty write is
/// indistinguishable from the repair unless the identity is signed.
///
/// # The accumulator form (`demand` is not `None`)
///
/// The fresh-grid form builds the demand as `np.zeros` from the board
/// scalars, which is the contract the single-net differential pins
/// (`test_estimate_net_demand_bit_exact` / `_random_sweep`). But
/// `analyze_congestion`'s per-net loop accumulates onto the SAME grid across
/// many nets — delegating the fresh form there would silently drop every
/// net's demand but the first (the module docstring's first gap). When
/// `demand` is passed, it IS the accumulator: the grid dims come from the
/// array's own shape (so `width`/`height`/`cell_size_mm` are pass-throughs
/// for that form), the function adds `demand_per_cell` into the region in
/// place, and `0.0 + demand_per_cell` is exact for every finite, infinite
/// and NaN `demand_per_cell`, so the rectangle can be filled directly rather
/// than copy-then-add. The identity flag still distinguishes the two early
/// returns, so the shipped wrapper can hand back the input grid object.
#[pyfunction]
#[pyo3(signature = (width, height, cell_size_mm, origin, pins, layer, demand_per_cell, num_layers, demand=None))]
#[allow(clippy::too_many_arguments)]
pub fn congestion_estimate_net_demand_py<'py>(
    py: Python<'py>,
    width: f64,
    height: f64,
    cell_size_mm: f64,
    origin: (f64, f64),
    pins: Vec<(f64, f64)>,
    layer: i64,
    demand_per_cell: f64,
    num_layers: i64,
    demand: Option<Bound<'py, PyAny>>,
) -> PyResult<Bound<'py, PyAny>> {
    let np = py.import("numpy")?;

    let (width_cells, height_cells, zeros) = match &demand {
        Some(arr) => {
            // Accumulator form: the array's shape is the grid. `num_layers`
            // picks the branch exactly as the fresh form does (`== 1` is the
            // 2-D test, not `<= 1`), so the shape indexing below matches the
            // arrays `np.zeros` would have built.
            if num_layers == 1 {
                let (h, w): (i64, i64) = arr.getattr("shape")?.extract()?;
                (w, h, arr.clone())
            } else {
                let (l, h, w): (i64, i64, i64) = arr.getattr("shape")?.extract()?;
                debug_assert_eq!(l, num_layers);
                (w, h, arr.clone())
            }
        }
        None => {
            let wc = ceil_to_int(width / cell_size_mm)?;
            let hc = ceil_to_int(height / cell_size_mm)?;
            let shape_2d = (hc, wc);
            let shape_3d = (num_layers, hc, wc);
            let z = if num_layers == 1 {
                np.call_method1("zeros", (shape_2d,))?
            } else {
                np.call_method1("zeros", (shape_3d,))?
            };
            (wc, hc, z)
        }
    };

    // `len(pin_positions) < 2` -- identity return, before any arithmetic, so a
    // NaN coordinate in a one-pin net never reaches `int()` and never raises.
    if pins.len() < 2 {
        return Ok((zeros, true).into_pyobject(py)?.into_any());
    }

    let xs: Vec<f64> = pins.iter().map(|p| p.0).collect();
    let ys: Vec<f64> = pins.iter().map(|p| p.1).collect();
    let (min_x, max_x) = (cpython_min(&xs), cpython_max(&xs));
    let (min_y, max_y) = (cpython_min(&ys), cpython_max(&ys));

    let col_min = 0.max(int_trunc((min_x - origin.0) / cell_size_mm)?);
    let col_max = (width_cells - 1).min(int_trunc((max_x - origin.0) / cell_size_mm)?);
    let row_min = 0.max(int_trunc((min_y - origin.1) / cell_size_mm)?);
    let row_max = (height_cells - 1).min(int_trunc((max_y - origin.1) / cell_size_mm)?);

    // D3's repaired guard: BOTH pairs, not one side.
    if col_max < col_min || row_max < row_min {
        return Ok((zeros, true).into_pyobject(py)?.into_any());
    }

    // Fill the rectangle. In the fresh form `zeros` is this function's own
    // array, so mutating it in place is equivalent to the reference's
    // `demand.copy()` then `+=`; in the accumulator form the caller's array
    // is the working array and `set_item` accumulates into it in place.
    let py_slice = py
        .import("builtins")?
        .getattr("slice")?;
    let rows = py_slice.call1((row_min, row_max + 1))?;
    let cols = py_slice.call1((col_min, col_max + 1))?;
    let current = if num_layers == 1 {
        zeros.get_item((&rows, &cols))?
    } else {
        zeros.get_item((layer, &rows, &cols))?
    };
    let updated = current.add(demand_per_cell)?;
    if num_layers == 1 {
        zeros.set_item((&rows, &cols), updated)?;
    } else {
        zeros.set_item((layer, &rows, &cols), updated)?;
    }

    Ok((zeros, false).into_pyobject(py)?.into_any())
}

// ---------------------------------------------------------------------------
// Slice 3: Bottleneck / CongestionResult
// ---------------------------------------------------------------------------

/// `min(a, b)` as CPython evaluates it: `acc = a; if b < acc { acc = b }`.
///
/// A NaN in the FIRST position survives, because `b < NaN` is false. The
/// corpus pins `overflow_ratio` with a NaN `total_overflow` for this (B5);
/// `f64::min` would return the other operand instead.
pub(crate) fn cpython_min2(a: f64, b: f64) -> f64 {
    if b < a { b } else { a }
}

/// `Bottleneck.to_coordinates` — the cell centre.
///
/// Op order and grouping are the reference's: `origin + (idx + 0.5) * cell`,
/// not `origin + idx * cell + 0.5 * cell`, which reassociates and can differ
/// in the last ulp.
#[pyfunction]
pub fn congestion_bottleneck_to_coordinates_py(
    x: i64,
    y: i64,
    cell_size_mm: f64,
    origin: (f64, f64),
) -> (f64, f64) {
    let center_x = origin.0 + (x as f64 + 0.5) * cell_size_mm;
    let center_y = origin.1 + (y as f64 + 0.5) * cell_size_mm;
    (center_x, center_y)
}

/// `CongestionResult.overflow_ratio`.
///
/// `float(self.grid.demand.sum())` is **numpy's** sum, which is
/// blocked-pairwise rather than naive left-to-right, so it is delegated to
/// numpy instead of accumulated in Rust. The corpus reaches the cases where
/// that matters: cancellation to exactly 0.0, overflow of `1e308 + 1e308` to
/// inf, a NaN element, and the denormal band (B8).
///
/// `total_demand == 0` is a float compare, so it catches `-0.0` too, and it
/// is FALSE for NaN — a NaN total_demand skips the early return and divides.
#[pyfunction]
pub fn congestion_result_overflow_ratio_py(
    py: Python<'_>,
    demand: Vec<f64>,
    total_overflow: f64,
) -> PyResult<f64> {
    let arr = row_array(py, &demand)?;
    let total_demand: f64 = arr.call_method0("sum")?.extract()?;
    if total_demand == 0.0 {
        return Ok(0.0);
    }
    Ok(cpython_min2(total_overflow / total_demand, 1.0))
}

/// `CongestionResult.get_top_bottlenecks`.
///
/// Sorts REAL bottleneck records — `(x, y, utilization, overflow, layer)`,
/// the flattened `Bottleneck` dataclass — by `overflow` descending and
/// returns the top `n`. This is the module docstring's second gap: the
/// kernel used to accept only a list of `overflow` floats and reconstruct
/// synthetic `Bottleneck(x=i, y=0, utilization=i, layer=0)` rows to match
/// the differential's own fixture; it could not sort real records (arbitrary
/// `x`/`y`/`utilization`/`layer`) without discarding their true fields.
///
/// Delegates to Python's `sorted` and to a real slice object rather than
/// re-deriving either:
///
/// * `sorted(key=..., reverse=True)` is **timsort**, and stable. A plain
///   stable merge in Rust has already been measured disagreeing with it on
///   624 of 2400 NaN cases elsewhere in this repo. The corpus pins a full
///   tie, a NaN sort key, and `[0.0, -0.0]` (which compare equal, so only
///   stability decides the order).
/// * `[:n]` with a NEGATIVE n is `[:-1]` — it drops the last element. It is
///   NOT an empty list, which is what a naive `take(n.max(0))` would give.
#[pyfunction]
#[pyo3(signature = (records, n))]
pub fn congestion_result_top_bottlenecks_py<'py>(
    py: Python<'py>,
    records: Vec<(i64, i64, f64, f64, i64)>,
    n: i64,
) -> PyResult<Bound<'py, PyAny>> {
    let builtins = py.import("builtins")?;
    let list = records.into_pyobject(py)?;

    let operator = py.import("operator")?;
    let key = operator.call_method1("itemgetter", (3i64,))?;
    let kwargs = pyo3::types::PyDict::new(py);
    kwargs.set_item("key", key)?;
    kwargs.set_item("reverse", true)?;
    let sorted = builtins.call_method("sorted", (list,), Some(&kwargs))?;

    let slice = builtins.getattr("slice")?.call1((py.None(), n))?;
    sorted.get_item(slice)
}
