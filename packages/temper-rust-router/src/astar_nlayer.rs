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
use temper_rust_router_core::astar_nlayer::{
    astar_search_3d, route_segment_3d, via_spacing_is_legal, LayerGrid, NlayerInput,
};

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(route_segment_3d_py, m)?)?;
    m.add_function(wrap_pyfunction!(astar_search_3d_py, m)?)?;
    m.add_function(wrap_pyfunction!(via_spacing_is_legal_py, m)?)?;
    Ok(())
}

/// Decode the concatenated int8 plane blob into per-layer [`LayerGrid`]s.
///
/// Layers may differ in size and coordinate frame (the Python consults each
/// grid's own frame — see the core module's `LayerGrid` docs), so planes are
/// laid out back-to-back at per-layer `width*height` strides rather than a
/// uniform one.
///
/// SAFETY: reinterprets the `u8` blob as `i8` — both single-byte, no alignment
/// concern, and the blob is a contiguous `Vec` owned by the caller's frame.
/// Same pattern `astar_kernel_3d_py`'s `grid_bytes` uses.
#[allow(clippy::too_many_arguments)]
fn decode_planes<'a>(
    planes: &'a [u8],
    name_ranks: &[u32],
    stack_ranks: &[u32],
    widths: &[i64],
    heights: &[i64],
    origins: &[(f64, f64)],
    cell_sizes: &[f64],
) -> PyResult<Vec<LayerGrid<'a>>> {
    let n = name_ranks.len();
    if n == 0
        || widths.len() != n
        || stack_ranks.len() != n
        || heights.len() != n
        || origins.len() != n
        || cell_sizes.len() != n
    {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "per-layer arrays disagree: name_ranks={n}, widths={}, heights={}, \
             origins={}, cell_sizes={}",
            widths.len(),
            heights.len(),
            origins.len(),
            cell_sizes.len()
        )));
    }
    let expected: usize = (0..n).map(|i| (widths[i] * heights[i]) as usize).sum();
    if planes.len() != expected {
        return Err(pyo3::exceptions::PyValueError::new_err(format!(
            "planes blob is {} bytes; expected sum(width*height) over {n} layers = {expected}",
            planes.len()
        )));
    }
    let signed: &[i8] =
        unsafe { std::slice::from_raw_parts(planes.as_ptr() as *const i8, planes.len()) };

    let mut out = Vec::with_capacity(n);
    let mut offset = 0usize;
    for i in 0..n {
        let len = (widths[i] * heights[i]) as usize;
        out.push(LayerGrid {
            name_rank: name_ranks[i],
            stack_rank: stack_ranks[i],
            cells: &signed[offset..offset + len],
            width: widths[i],
            height: heights[i],
            origin: origins[i],
            cell_size: cell_sizes[i],
        });
        offset += len;
    }
    Ok(out)
}

/// Python-callable `_astar_search_3d` — the raw cell-level search, for callers
/// that work in grid coordinates rather than world millimetres.
///
/// Returns `(path_cells, via_cells, found, iterations)` where `path_cells` is
/// a list of `(x, y, layer_index)`.
#[pyfunction]
#[pyo3(signature = (
    start, goal, planes, name_ranks, stack_ranks, widths, heights, origins, cell_sizes,
    available_layers, via_cost, max_iter,
))]
#[expect(
    clippy::too_many_arguments,
    reason = "Pyo3 boundary mirrors the Python signature 1:1; a config struct would change the FFI"
)]
#[allow(clippy::type_complexity)]
fn astar_search_3d_py(
    start: (i64, i64, usize),
    goal: (i64, i64, usize),
    planes: Vec<u8>,
    name_ranks: Vec<u32>,
    stack_ranks: Vec<u32>,
    widths: Vec<i64>,
    heights: Vec<i64>,
    origins: Vec<(f64, f64)>,
    cell_sizes: Vec<f64>,
    available_layers: Vec<usize>,
    via_cost: f64,
    max_iter: Option<u64>,
) -> PyResult<(Vec<(i64, i64, usize)>, Vec<(i64, i64)>, bool, u64)> {
    let grids = decode_planes(
        &planes,
        &name_ranks,
        &stack_ranks,
        &widths,
        &heights,
        &origins,
        &cell_sizes,
    )?;
    let out = astar_search_3d(&NlayerInput {
        start,
        goal,
        grids: &grids,
        available_layers: &available_layers,
        via_cost,
        via_extra_radius_mm: 0.0,
        prior_vias_world: &[],
        min_prior_via_spacing_mm: 0.0,
        max_iter,
    });
    Ok((out.path, out.vias, out.found, out.iterations))
}

/// Python-callable `_route_segment_3d`.
///
/// Returns `(world_path, via_world, via_cells, found, iterations,
/// hit_iteration_cap)` where `world_path` is a list of
/// `(x_mm, y_mm, layer_index)`. The final flag is computed here from the
/// kernel's own bail convention (`iterations > cap`), not inferred from a
/// missing path by Python.
#[pyfunction]
#[pyo3(signature = (
    start_world, goal_world, start_layer, goal_layer,
    planes, name_ranks, stack_ranks, widths, heights, origins, cell_sizes,
    available_layers, via_cost, via_extra_radius_mm,
    prior_vias_world, min_prior_via_spacing_mm, max_iter,
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
    stack_ranks: Vec<u32>,
    widths: Vec<i64>,
    heights: Vec<i64>,
    origins: Vec<(f64, f64)>,
    cell_sizes: Vec<f64>,
    available_layers: Vec<usize>,
    via_cost: f64,
    via_extra_radius_mm: f64,
    prior_vias_world: Vec<(f64, f64)>,
    min_prior_via_spacing_mm: f64,
    max_iter: Option<u64>,
) -> PyResult<(
    Vec<(f64, f64, usize)>,
    Vec<(f64, f64)>,
    Vec<(i64, i64)>,
    bool,
    u64,
    bool,
)> {
    let grids = decode_planes(
        &planes,
        &name_ranks,
        &stack_ranks,
        &widths,
        &heights,
        &origins,
        &cell_sizes,
    )?;

    let out = route_segment_3d(
        start_world,
        goal_world,
        start_layer,
        goal_layer,
        &grids,
        &available_layers,
        via_cost,
        via_extra_radius_mm,
        &prior_vias_world,
        min_prior_via_spacing_mm,
        max_iter,
    );

    let hit_iteration_cap = !out.found && max_iter.is_some_and(|cap| out.iterations > cap);
    Ok((
        out.world_path,
        out.via_world,
        out.via_cells,
        out.found,
        out.iterations,
        hit_iteration_cap,
    ))
}

#[pyfunction]
fn via_spacing_is_legal_py(
    candidate: (f64, f64),
    prior_vias: Vec<(f64, f64)>,
    min_spacing_mm: f64,
) -> bool {
    via_spacing_is_legal(candidate, &prior_vias, min_spacing_mm)
}
