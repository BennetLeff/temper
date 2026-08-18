//! Pyo3 binding for the Tier-3 N-layer, via-aware A*
//! (`temper_rust_router_core::astar_nlayer`, the port of
//! `router_v6/astar_core.py`'s `_astar_search_3d` / `_route_segment_3d`).
//!
//! Occupancy planes cross the FFI as one concatenated little-endian int8 blob
//! of `n_layers * height * width` bytes, layer-major. That mirrors the byte
//! convention `astar_kernel_3d_py` / `line_of_sight_py` already use (this repo
//! has no `numpy` crate, so there is no zero-copy array path to follow), while
//! keeping it to a single buffer per call rather than one per layer.
//!
//! Via *marking* is deliberately not done here — see the core module's docs.
//! The caller receives `via_cells` and applies the existing, already-Rust
//! `OccupancyGrid.mark_via_blocked`, exactly as the Python did.

use pyo3::prelude::*;
use temper_rust_router_core::astar_nlayer::{route_segment_3d, LayerGrid};

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(route_segment_3d_py, m)?)?;
    Ok(())
}

/// Python-callable `_route_segment_3d`.
///
/// Returns `(world_path, via_world, via_cells, found, iterations)` where
/// `world_path` is a list of `(x_mm, y_mm, layer_index)`.
#[pyfunction]
#[pyo3(signature = (
    start_world, goal_world, start_layer, goal_layer,
    planes, name_ranks, width, height, available_layers,
    via_cost, max_iter, origin, cell_size,
))]
#[expect(
    clippy::too_many_arguments,
    reason = "Pyo3 boundary mirrors the Python signature 1:1; a config struct would change the FFI"
)]
#[allow(clippy::type_complexity)]
fn route_segment_3d_py(
    start_world: (f64, f64),
    goal_world: (f64, f64),
    start_layer: usize,
    goal_layer: usize,
    planes: Vec<u8>,
    name_ranks: Vec<u32>,
    width: i64,
    height: i64,
    available_layers: Vec<usize>,
    via_cost: f64,
    max_iter: Option<u64>,
    origin: (f64, f64),
    cell_size: f64,
) -> PyResult<(
    Vec<(f64, f64, usize)>,
    Vec<(f64, f64)>,
    Vec<(i64, i64)>,
    bool,
    u64,
)> {
    let n_layers = name_ranks.len();
    let plane_len = (width * height) as usize;
    if n_layers == 0 || planes.len() != n_layers * plane_len {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "planes blob is {} bytes; expected n_layers({n_layers}) * width({width}) * height({height}) = {}",
            planes.len(),
            n_layers * plane_len
        )));
    }

    // Reinterpret the u8 blob as i8 — both single-byte, no alignment concern,
    // and `planes` is a contiguous Vec owned by this frame. Same pattern as
    // `astar_kernel_3d_py`'s `grid_bytes`.
    let signed: &[i8] =
        unsafe { std::slice::from_raw_parts(planes.as_ptr() as *const i8, planes.len()) };

    let grids: Vec<LayerGrid<'_>> = (0..n_layers)
        .map(|i| LayerGrid {
            name_rank: name_ranks[i],
            cells: &signed[i * plane_len..(i + 1) * plane_len],
            width,
            height,
        })
        .collect();

    let out = route_segment_3d(
        start_world,
        goal_world,
        start_layer,
        goal_layer,
        &grids,
        &available_layers,
        via_cost,
        max_iter,
        origin,
        cell_size,
    );

    Ok((
        out.world_path,
        out.via_world,
        out.via_cells,
        out.found,
        out.iterations,
    ))
}
