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
    LayerGrid, NlayerInput, RouteSegment3dOutput, astar_search_3d, foreign_obstacle_halo_inflation,
    route_segment_3d,
};

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(foreign_obstacle_halo_inflation_py, m)?)?;
    m.add_function(wrap_pyfunction!(route_segment_3d_py, m)?)?;
    m.add_function(wrap_pyfunction!(route_segment_3d_diagnostic_py, m)?)?;
    m.add_function(wrap_pyfunction!(astar_search_3d_py, m)?)?;
    Ok(())
}

/// Compute one foreign-obstacle C-space inflation in the Rust core.
#[pyfunction]
fn foreign_obstacle_halo_inflation_py(
    trace_width_mm: f64,
    clearance_mm: f64,
    pair_creepage_mm: f64,
) -> PyResult<f64> {
    foreign_obstacle_halo_inflation(trace_width_mm, clearance_mm, pair_creepage_mm).ok_or_else(
        || pyo3::exceptions::PyValueError::new_err("invalid foreign-obstacle halo spacing"),
    )
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
    widths: &[i64],
    heights: &[i64],
    origins: &[(f64, f64)],
    cell_sizes: &[f64],
) -> PyResult<Vec<LayerGrid<'a>>> {
    let n = name_ranks.len();
    if n == 0
        || widths.len() != n
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
    let mut expected = 0usize;
    for i in 0..n {
        if widths[i] <= 0 || heights[i] <= 0 {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "layer {i} has non-positive dimensions: {}x{}",
                widths[i], heights[i]
            )));
        }
        if !cell_sizes[i].is_finite() || cell_sizes[i] <= 0.0 {
            return Err(pyo3::exceptions::PyValueError::new_err(format!(
                "layer {i} has invalid cell_size: {}",
                cell_sizes[i]
            )));
        }
        let width = usize::try_from(widths[i]).map_err(|_| {
            pyo3::exceptions::PyValueError::new_err(format!(
                "layer {i} width does not fit in usize: {}",
                widths[i]
            ))
        })?;
        let height = usize::try_from(heights[i]).map_err(|_| {
            pyo3::exceptions::PyValueError::new_err(format!(
                "layer {i} height does not fit in usize: {}",
                heights[i]
            ))
        })?;
        let cells = width.checked_mul(height).ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err(format!(
                "layer {i} dimensions overflow width*height: {}x{}",
                widths[i], heights[i]
            ))
        })?;
        expected = expected.checked_add(cells).ok_or_else(|| {
            pyo3::exceptions::PyValueError::new_err("total layer dimensions overflow usize")
        })?;
    }
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
        let len = usize::try_from(widths[i])
            .ok()
            .and_then(|width| {
                usize::try_from(heights[i])
                    .ok()
                    .and_then(|height| width.checked_mul(height))
            })
            // The checked calculation above already validated these values;
            // keep this branch defensive if the decoder is edited later.
            .ok_or_else(|| {
                pyo3::exceptions::PyValueError::new_err(format!(
                    "layer {i} dimensions cannot be represented"
                ))
            })?;
        out.push(LayerGrid {
            name_rank: name_ranks[i],
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
    start, goal, planes, name_ranks, widths, heights, origins, cell_sizes,
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
        max_iter,
    });
    Ok((out.path, out.vias, out.found, out.iterations))
}

/// Python-callable `_route_segment_3d`.
///
/// Returns `(world_path, via_world, via_cells, found, iterations)` where
/// `world_path` is a list of `(x_mm, y_mm, layer_index)`.
#[pyfunction]
#[pyo3(signature = (
    start_world, goal_world, start_layer, goal_layer,
    planes, name_ranks, widths, heights, origins, cell_sizes,
    available_layers, via_cost, max_iter,
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
    widths: Vec<i64>,
    heights: Vec<i64>,
    origins: Vec<(f64, f64)>,
    cell_sizes: Vec<f64>,
    available_layers: Vec<usize>,
    via_cost: f64,
    max_iter: Option<u64>,
) -> PyResult<(
    Vec<(f64, f64, usize)>,
    Vec<(f64, f64)>,
    Vec<(i64, i64)>,
    bool,
    u64,
)> {
    let out = route_segment_3d_decoded(
        &planes,
        &name_ranks,
        &widths,
        &heights,
        &origins,
        &cell_sizes,
        start_world,
        goal_world,
        start_layer,
        goal_layer,
        &available_layers,
        via_cost,
        max_iter,
    )?;

    Ok((
        out.world_path,
        out.via_world,
        out.via_cells,
        out.found,
        out.iterations,
    ))
}

/// Diagnostic form of [`route_segment_3d_py`].
///
/// The extra final value is a deterministic `[(net_id, frontier_contacts)]`
/// list. It is deliberately named as contact evidence rather than blockers:
/// encountering committed copper on the explored frontier does not prove
/// that removing it makes the route possible.
#[pyfunction]
#[pyo3(signature = (
    start_world, goal_world, start_layer, goal_layer,
    planes, name_ranks, widths, heights, origins, cell_sizes,
    available_layers, via_cost, max_iter,
))]
#[expect(
    clippy::too_many_arguments,
    reason = "Pyo3 boundary mirrors the route-segment signature and adds only diagnostics"
)]
#[allow(clippy::type_complexity)]
fn route_segment_3d_diagnostic_py(
    start_world: (f64, f64),
    goal_world: (f64, f64),
    start_layer: usize,
    goal_layer: usize,
    planes: Vec<u8>,
    name_ranks: Vec<u32>,
    widths: Vec<i64>,
    heights: Vec<i64>,
    origins: Vec<(f64, f64)>,
    cell_sizes: Vec<f64>,
    available_layers: Vec<usize>,
    via_cost: f64,
    max_iter: Option<u64>,
) -> PyResult<(
    Vec<(f64, f64, usize)>,
    Vec<(f64, f64)>,
    Vec<(i64, i64)>,
    bool,
    u64,
    Vec<(i64, u64)>,
)> {
    let out = route_segment_3d_decoded(
        &planes,
        &name_ranks,
        &widths,
        &heights,
        &origins,
        &cell_sizes,
        start_world,
        goal_world,
        start_layer,
        goal_layer,
        &available_layers,
        via_cost,
        max_iter,
    )?;

    Ok((
        out.world_path,
        out.via_world,
        out.via_cells,
        out.found,
        out.iterations,
        out.blocker_contacts,
    ))
}

#[expect(
    clippy::too_many_arguments,
    reason = "shared decoder for two pyo3 signatures with exact parity inputs"
)]
fn route_segment_3d_decoded(
    planes: &[u8],
    name_ranks: &[u32],
    widths: &[i64],
    heights: &[i64],
    origins: &[(f64, f64)],
    cell_sizes: &[f64],
    start_world: (f64, f64),
    goal_world: (f64, f64),
    start_layer: usize,
    goal_layer: usize,
    available_layers: &[usize],
    via_cost: f64,
    max_iter: Option<u64>,
) -> PyResult<RouteSegment3dOutput> {
    let grids = decode_planes(planes, name_ranks, widths, heights, origins, cell_sizes)?;
    Ok(route_segment_3d(
        start_world,
        goal_world,
        start_layer,
        goal_layer,
        &grids,
        available_layers,
        via_cost,
        max_iter,
    ))
}
