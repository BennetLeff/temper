// The D3 `_grid_fence` checks of the Rust Orchestration Engine plan
// (2026-08-09-001, Phase D batch D3): the U3 conservatism-fence
// orchestration and the perf-budget check, as Rust kernels the Python shims
// delegate to (`_grid_fence.check_clearance_grid_conservatism` ->
// `run_grid_fence_check`, `_grid_fence.check_clearance_grid_perf_budget` ->
// `run_grid_perf_budget`).
//
// `run_grid_fence_check` iterates the expansion log, unpacks each entry,
// computes the sample points via the already-Rust
// `temper_geometry.fence_samples_py` kernel (with `shape_code` from
// `temper_placer.core.pad_geometry`), checks the per-sample availability via
// the `temper_geometry.grid_cell_available_py` kernel (`grid_leaf.rs`, the
// ported `ClearanceGrid.is_available` leaf) and assembles the violation
// dicts. The `reason` f-string's `:.3f` leaves
// are formatted by calling CPython's `__format__(".3f")` on the ORIGINAL
// sample floats, so the rendered text is identical by construction (David
// Gay dtoa is not reproducible from Rust's `{:.3}`).
//
// `run_grid_perf_budget` reproduces the floor exemption, the `(fence /
// stage) * 100.0` overhead and the `:.1f` warning message (again rendered
// via CPython `__format__` on exact f64 -> PyFloat round-trips).
//
// What stays Python: the `FenceViolation` exception class (raised by the
// stage, not here) and the module-level `_EXPANSION_LOG` (the stage writes
// it; this kernel only reads the passed-in list).

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyDict, PyList, PyTuple};

#[cfg(feature = "python")]
/// FFI entry for the Python shim: `run_grid_fence_check(grid, log, count)`.
/// Returns the list of violation dicts (empty == conservative).
#[pyfunction]
pub fn run_grid_fence_check(
    py: Python<'_>,
    grid: Py<PyAny>,
    expansion_log: Py<PyAny>,
    sample_count_circle: i64,
) -> PyResult<Py<PyAny>> {
    let cell: f64 = grid.bind(py).getattr("cell_size_mm")?.extract()?;
    let inset = cell / 2.0; // ±0.5 cell tolerance per R8
    let layer_count: i64 = grid.bind(py).getattr("layer_count")?.extract()?;
    let fence_samples = py.import("temper_geometry")?.getattr("fence_samples_py")?;
    let shape_code = py
        .import("temper_placer.core.pad_geometry")?
        .getattr("shape_code")?;
    // The per-sample availability check (`grid.is_available`) is a
    // temper-geometry kernel (`grid_leaf.rs`); fetch the per-layer arrays
    // and dimensions once instead of round-tripping through the Python
    // method per sample.
    let avail_kernel = py
        .import("temper_geometry")?
        .getattr("grid_cell_available_py")?;
    let trace_arrays = grid.bind(py).getattr("_trace_net_ids")?;
    let pad_arrays = grid.bind(py).getattr("_pad_net_ids")?;
    let rows: usize = grid.bind(py).getattr("rows")?.extract()?;
    let cols: usize = grid.bind(py).getattr("cols")?.extract()?;

    let violations = PyList::empty(py);
    for entry in expansion_log.bind(py).try_iter()? {
        let entry = entry?;
        // (ref, pin_name, layer_idx, pos, shape, pad_radius, pad_size,
        //  eff_creep, _cells_added)
        let ref_val = entry.get_item(0)?;
        let pin_name = entry.get_item(1)?;
        let layer_idx: i64 = entry.get_item(2)?.extract()?;
        if layer_idx < 0 || layer_idx >= layer_count {
            continue;
        }
        let pos = entry.get_item(3)?;
        let shape: String = entry.get_item(4)?.extract()?;
        let pad_radius: f64 = entry.get_item(5)?.extract()?;
        let pad_size = entry.get_item(6)?;
        let eff_creep: f64 = entry.get_item(7)?.extract()?;

        let code: i64 = shape_code.call1((&shape,))?.extract()?;
        let px: f64 = pos.get_item(0)?.extract()?;
        let pyy: f64 = pos.get_item(1)?.extract()?;
        let w: f64 = pad_size.get_item(0)?.extract()?;
        let h: f64 = pad_size.get_item(1)?.extract()?;
        let raw = fence_samples.call1((
            code, px, pyy, pad_radius, w, h, eff_creep, inset, sample_count_circle,
        ))?;

        // samples = [(raw[i], raw[i+1]) for i in range(0, len(raw), 2)]
        let raw_len = raw.len()?;
        let mut i = 0;
        while i + 1 < raw_len {
            let x = raw.get_item(i)?;
            let y = raw.get_item(i + 1)?;
            let avail: bool = avail_kernel
                .call1((
                    trace_arrays.get_item(layer_idx)?,
                    pad_arrays.get_item(layer_idx)?,
                    rows,
                    cols,
                    cell,
                    &x,
                    &y,
                    py.None(),
                ))?
                .extract()?;
            if avail {
                let x_fmt: String = x.call_method1("__format__", (".3f",))?.extract()?;
                let y_fmt: String = y.call_method1("__format__", (".3f",))?.extract()?;
                let ref_s = crate::grid_hv::str_of(&ref_val)?;
                let pin_s = crate::grid_hv::str_of(&pin_name)?;
                let reason = format!(
                    "cell at ({}, {}) on layer {} is unblocked but should be \
                     inside the expanded creepage boundary for pad {}.{}",
                    x_fmt, y_fmt, layer_idx, ref_s, pin_s
                );
                let d = PyDict::new(py);
                d.set_item("ref", &ref_val)?;
                d.set_item("pin_name", &pin_name)?;
                d.set_item("layer", layer_idx)?;
                d.set_item("xy", PyTuple::new(py, [&x, &y])?)?;
                d.set_item("reason", reason)?;
                violations.append(d)?;
            }
            i += 2;
        }
    }
    Ok(violations.into_any().unbind())
}

#[cfg(feature = "python")]
/// FFI entry for the Python shim: `run_grid_perf_budget(...)`. Returns the
/// `(over_budget, warning_message | None)` tuple.
#[pyfunction]
pub fn run_grid_perf_budget(
    py: Python<'_>,
    fence_elapsed_ms: f64,
    stage_elapsed_ms: f64,
    budget_pct: f64,
    floor_ms: f64,
) -> PyResult<Py<PyAny>> {
    // `if stage_elapsed_ms < floor_ms: return False, None`
    if stage_elapsed_ms < floor_ms {
        return fence_tuple(py, false, None);
    }
    let overhead_pct = (fence_elapsed_ms / stage_elapsed_ms) * 100.0;
    if overhead_pct > budget_pct {
        let fmt = |v: f64| -> PyResult<String> {
            pyo3::types::PyFloat::new(py, v)
                .call_method1("__format__", (".1f",))?
                .extract()
        };
        let message = format!(
            "fence overhead {}% exceeds budget {}% (fence={}ms, stage={}ms)",
            fmt(overhead_pct)?,
            fmt(budget_pct)?,
            fmt(fence_elapsed_ms)?,
            fmt(stage_elapsed_ms)?,
        );
        return fence_tuple(py, true, Some(message));
    }
    fence_tuple(py, false, None)
}

#[cfg(feature = "python")]
fn fence_tuple(
    py: Python<'_>,
    over_budget: bool,
    message: Option<String>,
) -> PyResult<Py<PyAny>> {
    let builtins = py.import("builtins")?;
    let over: Py<PyAny> = builtins
        .getattr(if over_budget { "True" } else { "False" })?
        .into_any()
        .unbind();
    let msg: Py<PyAny> = match message {
        Some(m) => pyo3::types::PyString::new(py, &m).into_any().unbind(),
        None => py.None(),
    };
    Ok(PyTuple::new(py, [over, msg])?.into_any().unbind())
}
