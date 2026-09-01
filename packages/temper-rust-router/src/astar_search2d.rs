//! Pyo3 binding for [`temper_rust_router_core::astar_search2d`] — the faithful
//! f64 port of `router_v6/astar_core.py`'s `_astar_search`.
//!
//! Deliberately a **separate entry point from `astar_kernel_3d_py`**: that
//! kernel is f32, keeps a closed set, and has no `DIAGONAL_COST_FACTOR`, so it
//! is not a drop-in for this function (see the core module's docs). It is left
//! untouched.
//!
//! Buffers cross the FFI as little-endian byte blobs, the same convention
//! `astar_kernel_3d_py` and `line_of_sight_py` already use — this repo has no
//! `numpy` crate, so there is no zero-copy array path to follow.
//!
//! The path is returned as a flat `Vec<i64>` of `x0, y0, x1, y1, …` and
//! **`None` for "no path"**, mirroring the Python's `None` return. An empty
//! list would be indistinguishable from a zero-length path, and the Python's
//! caller (`route_edge_astar`) branches on truthiness.

use pyo3::prelude::*;
use temper_rust_router_core::astar_search2d::{Astar2dInput, astar_search_2d};

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(astar_search_2d_py, m)?)?;
    Ok(())
}

/// Python-callable faithful port of `astar_core._astar_search`.
///
/// * `grid_bytes` — row-major `(height_cells, width_cells)` int8 occupancy.
/// * `neighbor_tensor_bytes` — row-major `(height_cells, width_cells, 8)` u8
///   validity bits; consulted only when `net_id < 0`.
/// * `thermal_bytes` — little-endian float32 `(height_cells*width_cells,)`.
/// * `corridor_mask_bytes` — row-major `(height_cells, width_cells)` u8.
/// * `diagonal_cost_factor` — the live value of
///   `astar_core.DIAGONAL_COST_FACTOR`, read per call rather than baked in.
///
/// Returns a flat `[x0, y0, x1, y1, …]` path, or `None` when no path exists.
#[pyfunction]
#[pyo3(signature = (
    start_x, start_y, goal_x, goal_y, width_cells, height_cells, grid_bytes,
    neighbor_tensor_bytes=None, thermal_bytes=None, thermal_weight=0.0,
    net_id=-1i64, corridor_mask_bytes=None, diagonal_cost_factor=1.0,
))]
#[expect(
    clippy::too_many_arguments,
    reason = "Pyo3 boundary mirrors the Python signature 1:1; a config struct would change the FFI"
)]
fn astar_search_2d_py(
    start_x: i64,
    start_y: i64,
    goal_x: i64,
    goal_y: i64,
    width_cells: i64,
    height_cells: i64,
    grid_bytes: Vec<u8>,
    neighbor_tensor_bytes: Option<Vec<u8>>,
    thermal_bytes: Option<Vec<u8>>,
    thermal_weight: f64,
    net_id: i64,
    corridor_mask_bytes: Option<Vec<u8>>,
    diagonal_cost_factor: f64,
) -> PyResult<Option<Vec<i64>>> {
    let n_cells = (width_cells.max(0) as usize) * (height_cells.max(0) as usize);
    if grid_bytes.len() != n_cells {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "grid_bytes has {} bytes, expected width_cells*height_cells = {}",
            grid_bytes.len(),
            n_cells
        )));
    }
    if let Some(m) = corridor_mask_bytes.as_ref()
        && m.len() != n_cells
    {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "corridor_mask_bytes has {} bytes, expected {}",
            m.len(),
            n_cells
        )));
    }
    if let Some(t) = neighbor_tensor_bytes.as_ref()
        && t.len() != n_cells * 8
    {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "neighbor_tensor_bytes has {} bytes, expected {}",
            t.len(),
            n_cells * 8
        )));
    }

    let thermal = thermal_bytes.map(|b| crate::f32s_from_le_bytes(&b, n_cells));

    // SAFETY: reinterprets the owned `Vec<u8>` as `i8` — both single-byte, no
    // alignment concern, and the buffer outlives the borrow. Same pattern
    // `astar_kernel_3d_py` / `line_of_sight_py` already use.
    let grid_slice: &[i8] =
        unsafe { std::slice::from_raw_parts(grid_bytes.as_ptr() as *const i8, grid_bytes.len()) };

    let out = astar_search_2d(&Astar2dInput {
        start: (start_x, start_y),
        goal: (goal_x, goal_y),
        width_cells,
        height_cells,
        grid: grid_slice,
        neighbor_tensor: neighbor_tensor_bytes.as_deref(),
        thermal_flat: thermal.as_deref(),
        thermal_weight,
        net_id,
        corridor_mask: corridor_mask_bytes.as_deref(),
        diagonal_cost_factor,
    });

    Ok(out.map(|path| {
        let mut flat = Vec::with_capacity(path.len() * 2);
        for (x, y) in path {
            flat.push(x);
            flat.push(y);
        }
        flat
    }))
}
