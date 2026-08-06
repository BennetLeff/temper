//! Wave-4 Phase B, congestion cluster E: `router_v6/congestion_heatmap.py`.
//!
//! Mirrors, bit for bit, `CongestionHeatmap` from the pinned Python oracle
//! `packages/temper-placer/tests/router_v6/_congestion_py_oracle.py`
//! (re-pinned by #801 onto post-#760 source). Four entry points:
//! `congestion_heatmap_from_router_py`, `congestion_heatmap_at_py`,
//! `congestion_heatmap_total_py`, `congestion_heatmap_hotspots_py`.
//!
//! # Why this calls numpy instead of computing in Rust
//!
//! `from_router` reduces two 3-D arrays with `np.max(..., axis=2)`, combines
//! them, conditionally normalizes by `np.max`, and downcasts to `float32`.
//! `get_total_congestion` sums with `np.sum`, which is a **blocked-pairwise**
//! reduction rather than a left fold — measured to diverge from
//! `iter().sum()` on the corpus's own grids in
//! `test_trap_np_sum_is_not_a_left_fold`. `get_hotspots` sorts with Python's
//! `sorted(key=..., reverse=True)` — timsort, stable, and previously measured
//! at 624/2400 disagreements against a Rust stable merge on NaN keys
//! elsewhere in this cluster (`congestion.rs`) — and slices with a real
//! `slice` object, because `[:n]` with a negative `n` is `[:-1]`, not empty.
//! Delegating every one of these to Python/numpy inherits the exact
//! semantics by construction; re-deriving any of them in Rust is exactly the
//! pattern that has already produced mutation-provable divergences in this
//! cluster (see `congestion.rs`'s module doc).
//!
//! `get_hotspots` also returns tuples that mix a Python `float`
//! (`world_x`/`world_y`, computed as `gx * cell_size + origin[0]`) with a
//! `numpy.float32` (the grid value, read back with `__getitem__` and never
//! cast). The differential's `sig()` tells those apart even though `==`
//! cannot, so the grid element is kept as the exact `Bound<PyAny>` numpy
//! scalar `__getitem__` hands back, never `extract`-ed to `f64` for the
//! output — only for internal threshold comparisons.

use pyo3::exceptions::PyKeyError;
use pyo3::prelude::*;
use pyo3::types::{PyAnyMethods, PyDict};

use crate::congestion::int_trunc;

/// `np.array(data, dtype=float64)` for a 3-D nested `Vec`, mirroring
/// `congestion.rs`'s `row_array` for the 3-D `present_congestion` /
/// `history_cost` inputs this module consumes.
fn array3_f64<'py>(py: Python<'py>, data: Vec<Vec<Vec<f64>>>) -> PyResult<Bound<'py, PyAny>> {
    let np = py.import("numpy")?;
    let dtype = np.getattr("float64")?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("dtype", dtype)?;
    np.call_method("array", (data,), Some(&kwargs))
}

/// `np.max(arr, axis=2)`, called as the reference calls it (the free
/// function with an `axis` keyword), not the `.max(2)` method form.
fn np_max_axis2<'py>(
    np: &Bound<'py, PyModule>,
    arr: &Bound<'py, PyAny>,
) -> PyResult<Bound<'py, PyAny>> {
    let kwargs = PyDict::new(np.py());
    kwargs.set_item("axis", 2i64)?;
    np.call_method("max", (arr,), Some(&kwargs))
}

/// The 5-tuple `CongestionHeatmap.from_router` consumes, projected from the
/// `RouterStub` the differential builds: `(present_congestion, history_cost,
/// conflict_locations, cell_size, origin)`. `get_congestion_at` and
/// `get_hotspots` are signed by the differential as taking this whole tuple
/// as one argument rather than splatted, so it is named here to be threaded
/// through unchanged.
type RouterCase<'py> = (
    Vec<Vec<Vec<f64>>>,
    Vec<Vec<Vec<f64>>>,
    Vec<Bound<'py, PyDict>>,
    f64,
    (f64, f64),
);

/// `CongestionHeatmap.from_router`, minus the dataclass wrapper: builds and
/// returns the normalized `float32` grid plus the row/col extents (equal to
/// `grid.shape`, since `astype` does not change shape), so callers that only
/// need a bounds-checked index don't pay for a second `getattr("shape")`
/// round-trip.
///
/// Op order mirrors the reference exactly:
/// `combined = congestion_2d + 0.5 * history_2d` (addition on the LEFT
/// operand `congestion_2d`, scaling on `history_2d` first) then the
/// conflict-location loop mutates `combined` in place, in list order, before
/// `max_val = np.max(combined)` decides whether to normalize. `max_val > 0`
/// is a float compare (false for NaN, so a NaN max skips normalization same
/// as the reference), and division by a Python `float` (not another array)
/// matches `combined / max_val`.
#[allow(clippy::too_many_arguments)]
fn build_heatmap<'py>(
    py: Python<'py>,
    present: Vec<Vec<Vec<f64>>>,
    history: Vec<Vec<Vec<f64>>>,
    conflicts: Vec<Bound<'py, PyDict>>,
    cell_size: f64,
    origin: (f64, f64),
) -> PyResult<(Bound<'py, PyAny>, i64, i64)> {
    let np = py.import("numpy")?;

    let present_arr = array3_f64(py, present)?;
    let history_arr = array3_f64(py, history)?;

    let congestion_2d = np_max_axis2(&np, &present_arr)?;
    let history_2d = np_max_axis2(&np, &history_arr)?.sub(1.0f64)?;
    let scaled_history = history_2d.mul(0.5f64)?;
    let combined = congestion_2d.add(scaled_history)?;

    let (rows, cols): (i64, i64) = combined.getattr("shape")?.extract()?;

    for loc in &conflicts {
        let world_x: f64 = loc
            .get_item("world_x")?
            .ok_or_else(|| PyKeyError::new_err("world_x"))?
            .extract()?;
        let world_y: f64 = loc
            .get_item("world_y")?
            .ok_or_else(|| PyKeyError::new_err("world_y"))?
            .extract()?;
        let nets = loc
            .get_item("nets")?
            .ok_or_else(|| PyKeyError::new_err("nets"))?;
        let nets_len = nets.len()? as i64;

        let gx = int_trunc((world_x - origin.0) / cell_size)?;
        let gy = int_trunc((world_y - origin.1) / cell_size)?;

        if 0 <= gx && gx < rows && 0 <= gy && gy < cols {
            let current = combined.get_item((gx, gy))?;
            let updated = current.add(nets_len)?;
            combined.set_item((gx, gy), updated)?;
        }
    }

    let max_val_obj = np.call_method1("max", (&combined,))?;
    let max_val: f64 = max_val_obj.extract()?;

    let normalized = if max_val > 0.0 {
        combined.div(max_val)?
    } else {
        combined
    };

    let dtype_f32 = np.getattr("float32")?;
    let grid = normalized.call_method1("astype", (dtype_f32,))?;

    Ok((grid, rows, cols))
}

/// `CongestionHeatmap.from_router`, projected as the differential signs it:
/// `(grid, cell_size, origin)`. `cell_size` and `origin` are handed back
/// exactly as received — the dataclass assigns them straight from
/// `router.cell_size` / `router.origin` with no arithmetic in between.
#[pyfunction]
#[pyo3(signature = (present, history, conflicts, cell_size, origin))]
pub fn congestion_heatmap_from_router_py<'py>(
    py: Python<'py>,
    present: Vec<Vec<Vec<f64>>>,
    history: Vec<Vec<Vec<f64>>>,
    conflicts: Vec<Bound<'py, PyDict>>,
    cell_size: f64,
    origin: (f64, f64),
) -> PyResult<Bound<'py, PyAny>> {
    let (grid, _rows, _cols) = build_heatmap(py, present, history, conflicts, cell_size, origin)?;
    let out = (grid, cell_size, origin);
    Ok(out.into_pyobject(py)?.into_any())
}

/// `CongestionHeatmap.get_congestion_at` — `int()` truncates toward zero and
/// raises on non-finite input (`int_trunc`, shared with `congestion.rs`);
/// the subsequent `max(0, min(gx, shape - 1))` clamp operates on plain
/// integers, so no NaN-ordering concern applies there.
#[pyfunction]
pub fn congestion_heatmap_at_py<'py>(
    py: Python<'py>,
    router: RouterCase<'py>,
    x: f64,
    y: f64,
) -> PyResult<f64> {
    let (present, history, conflicts, cell_size, origin) = router;
    let (grid, rows, cols) = build_heatmap(py, present, history, conflicts, cell_size, origin)?;

    let gx = int_trunc((x - origin.0) / cell_size)?;
    let gy = int_trunc((y - origin.1) / cell_size)?;

    let gx = 0i64.max(gx.min(rows - 1));
    let gy = 0i64.max(gy.min(cols - 1));

    let val = grid.get_item((gx, gy))?;
    val.extract()
}

/// `CongestionHeatmap.get_total_congestion` — `float(np.sum(self.grid))`.
/// Delegated to numpy's own `sum`, a blocked-pairwise reduction on the
/// `float32` grid; see the module doc for why a Rust fold diverges.
#[pyfunction]
#[pyo3(signature = (present, history, conflicts, cell_size, origin))]
pub fn congestion_heatmap_total_py<'py>(
    py: Python<'py>,
    present: Vec<Vec<Vec<f64>>>,
    history: Vec<Vec<Vec<f64>>>,
    conflicts: Vec<Bound<'py, PyDict>>,
    cell_size: f64,
    origin: (f64, f64),
) -> PyResult<f64> {
    let (grid, _rows, _cols) = build_heatmap(py, present, history, conflicts, cell_size, origin)?;
    let np = py.import("numpy")?;
    let total = np.call_method1("sum", (grid,))?;
    total.extract()
}

/// `CongestionHeatmap.get_hotspots`. Builds candidates in the reference's
/// own iteration order (`gx` outer, `gy` inner) so a stable sort on tied
/// keys reproduces the same tie-break, then delegates the sort itself to
/// Python's `sorted(key=operator.itemgetter(2), reverse=True)` and the
/// truncation to a real `slice` object — both for the reasons the module doc
/// gives (timsort stability on NaN/`-0.0` keys; `[:n]` with negative `n`).
///
/// The stored congestion value is the exact `Bound<PyAny>` `__getitem__`
/// returns from the `float32` grid — never widened to `f64` — so the output
/// tuple mixes Python `float` (`world_x`, `world_y`) with `numpy.float32`
/// (the third element), matching the type the reference actually returns.
#[pyfunction]
pub fn congestion_heatmap_hotspots_py<'py>(
    py: Python<'py>,
    router: RouterCase<'py>,
    threshold: f64,
    max_count: i64,
) -> PyResult<Bound<'py, PyAny>> {
    let (present, history, conflicts, cell_size, origin) = router;
    let (grid, rows, cols) = build_heatmap(py, present, history, conflicts, cell_size, origin)?;

    // `val >= threshold` compares a numpy.float32 scalar (the grid element)
    // against a Python float. Under NEP 50, a Python float is a "weak"
    // scalar in a binary op against a numpy scalar: it adopts the OTHER
    // operand's dtype rather than promoting the numpy scalar to float64, so
    // the comparison happens at float32 precision -- `threshold` is narrowed
    // first. `np.float32(1.0) >= 1.0000000000000002` is therefore `True`
    // (the narrowed threshold rounds down to exactly `1.0f32`), which a
    // straight `f64` comparison of the widened grid value would miss.
    // Measured directly against this numpy build (2.3.5) before relying on
    // it here.
    let threshold_f32 = threshold as f32;
    let mut candidates: Vec<(f64, f64, Bound<'py, PyAny>)> = Vec::new();
    for gx in 0..rows {
        for gy in 0..cols {
            let val = grid.get_item((gx, gy))?;
            let val_f32: f32 = val.extract()?;
            if val_f32 >= threshold_f32 {
                let world_x = gx as f64 * cell_size + origin.0;
                let world_y = gy as f64 * cell_size + origin.1;
                candidates.push((world_x, world_y, val));
            }
        }
    }

    let builtins = py.import("builtins")?;
    let list = candidates.into_pyobject(py)?;

    let operator = py.import("operator")?;
    let key = operator.call_method1("itemgetter", (2i64,))?;
    let kwargs = PyDict::new(py);
    kwargs.set_item("key", key)?;
    kwargs.set_item("reverse", true)?;
    let sorted = builtins.call_method("sorted", (list,), Some(&kwargs))?;

    let slice = builtins.getattr("slice")?.call1((py.None(), max_count))?;
    sorted.get_item(slice)
}

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(congestion_heatmap_from_router_py, m)?)?;
    m.add_function(wrap_pyfunction!(congestion_heatmap_at_py, m)?)?;
    m.add_function(wrap_pyfunction!(congestion_heatmap_total_py, m)?)?;
    m.add_function(wrap_pyfunction!(congestion_heatmap_hotspots_py, m)?)?;
    Ok(())
}
