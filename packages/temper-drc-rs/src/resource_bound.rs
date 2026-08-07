//! `router_v6/resource_bound.py` — Resource Exhaustion Theorem for PCB
//! routing (bin-packing lower bound on simultaneously routable nets), Wave
//! 4. Pre-migration implementations pinned VERBATIM as the oracle in
//! `packages/temper-placer/tests/router_v6/_resource_bound_py_oracle.py`;
//! the differential lives in `test_resource_bound_rust_differential.py`.
//!
//! Ported (the oracle pins exactly these six):
//! - [`compute_conflict_clusters`] — `_compute_conflict_clusters`
//! - [`cluster_union_bbox`] — `_cluster_union_bbox`
//! - [`capacity_in_bbox`] — `_capacity_in_bbox`
//! - [`compute_fill_factor`] — `_compute_fill_factor`
//! - [`max_routable_nets`] — `max_routable_nets`
//! - [`demand_budget_summary`] — `demand_budget_summary`
//!
//! NOT ported: `_net_bboxes_from_pcb` (walks the rich `ParsedPCB` /
//! `Component` / `Pin` Python object graph via `pin_world_position` —
//! glue over Python objects with no numeric divergence risk of its own,
//! same shape as `clearance_check.py`'s `_route_to_rust_tuple` staying in
//! Python) and `max_routable_nets_from_pcb` (a thin wrapper: calls
//! `_net_bboxes_from_pcb` then `max_routable_nets`, so once
//! `max_routable_nets` is Rust-backed this wrapper needs no kernel of its
//! own).
//!
//! ## The three numpy calls, measured (not assumed)
//!
//! - `int(np.sum(region == 0))` (`_capacity_in_bbox`): the summand is a
//!   **boolean** array. Measured: `np.sum` on a `bool` array upcasts to an
//!   `int64` accumulator and produces an exact integer count — integer
//!   addition is associative, so there is no pairwise-vs-sequential
//!   summation-order divergence here (unlike a float64 accumulator, where
//!   it would matter). [`capacity_in_bbox`] counts matching cells with a
//!   plain Rust loop; the count is bit-for-bit identical to numpy's for
//!   every ordering.
//! - `float(np.sqrt(avg_area))` (`_compute_fill_factor`): `avg_area` is a
//!   **Python scalar float**, not an array element. `sqrt` is a correctly-
//!   rounded IEEE-754 operation (unlike `pow`/`sin`/`cos`, which have
//!   multiple valid roundings) — there is exactly one correctly-rounded
//!   answer, so scalar-vs-array and numpy-vs-libm distinctions do not
//!   apply. Routed through [`crate::pymath::sqrt`] anyway for consistency
//!   with the crate's host-libm-resolution convention, not because a
//!   divergence was measured.
//! - `float(np.clip(ff, 0.01, 1.0))` (`_compute_fill_factor`): measured
//!   against numpy 2.4.6 — `np.clip(x, lo, hi)` is
//!   `np.minimum(hi, np.maximum(x, lo))` with NaN-**propagating**
//!   `maximum`/`minimum` (NaN in *any* of the three positions yields NaN),
//!   which is a third, distinct behavior from both CPython's builtin
//!   `min`/`max` (keeps the first NaN) and `f64::max`/`f64::min` (discards
//!   NaN). [`np_clip`] here reproduces the measured numpy semantics; see
//!   `packages/temper-thermal/src/hostmath.rs::np_clip` for the same
//!   measurement and the same fix, ported independently rather than
//!   shared across crates (no existing dependency edge between them).
//!
//! No float32 array is constructed anywhere in this file (all grid/bbox
//! arithmetic is native Python `float` / numpy `float64`), so the NEP-50
//! narrowing hazard does not apply here.
//!
//! ## A FOURTH hazard, not on the numpy list: CPython 3.12's `sum()`
//!
//! `_compute_fill_factor`'s `sum(bbox_areas.values())` and
//! `demand_budget_summary`'s `total_demand = sum(demands.values())` are
//! plain CPython builtin `sum()` — no numpy involved — but CPython 3.12
//! (gh-100425) changed `sum()`'s float fast path to Neumaier compensated
//! summation, which is a *different function* from a naive sequential
//! fold. Measured while writing this port: a naive `bbox_areas.iter().sum()`
//! diverged from the oracle's `sum(bbox_areas.values())` in the last ULP on
//! the FIRST randomized differential trial (4-element `f64` sum). Both
//! summations here go through [`crate::pymath::py_sum`], not
//! `Iterator::sum`.
//!
//! ## NaN in bounding boxes: builtin `min`/`max` keep the FIRST NaN
//!
//! `_cluster_union_bbox`'s `min(bboxes[n][0] for n in cluster)` /
//! `max(...)` and `_compute_conflict_clusters`'s overlap-box arithmetic use
//! CPython's builtin `min`/`max`, which keep the **first** argument seen
//! unless a later one is strictly less/greater — reproduced via
//! [`crate::pymath::py_min`] / [`crate::pymath::py_max`], never
//! `f64::min`/`f64::max` (which discard NaN) nor `np.minimum`/`np.maximum`
//! (which propagate NaN from either operand — the *third* distinct
//! behavior, used deliberately only where §np.clip above measured it).
//!
//! ## Cluster grouping and HashMap/set iteration order
//!
//! The oracle's `_compute_conflict_clusters` visits each net's conflict
//! *set* (`for neighbor in conflict[n]`) — CPython `set` iteration order is
//! hash-bucket layout, and string hashing is `PYTHONHASHSEED`-randomized
//! per process by default, so the oracle's own *within-cluster* net order
//! is not itself a reproducible target (this codebase has hit exactly this
//! class of bug before — see `test_net_ordering.py`, `_astar_ordering.py`).
//! [`compute_conflict_clusters`] here sorts each net's neighbor list before
//! traversal, so the Rust output is deterministic on every run (an
//! improvement over the oracle, not a regression from it). This is safe to
//! diverge from the oracle bit-for-bit because within-cluster net order
//! does not otherwise affect the *numeric* outputs the oracle proves:
//! `_cluster_union_bbox`'s min/max is order-independent for the non-NaN
//! bounding boxes real board data produces, and `max_routable_nets` /
//! `demand_budget_summary` re-sort each cluster's demands
//! (`sorted(demands[n] for n in cluster)`) before consuming them. The
//! **outer** cluster order (which cluster is discovered first) is fully
//! deterministic in the oracle too — it follows `nets = list(bboxes.keys())`,
//! i.e. Python dict insertion order, not hash order — and
//! [`compute_conflict_clusters`] reproduces that order exactly by walking
//! the caller-supplied net order for the outer loop.

use pyo3::prelude::*;
use pyo3::types::{PyDict, PyModule};

use crate::pymath::{py_max, py_min, py_sum, sqrt};

const OVERLAP_THRESHOLD: f64 = 0.1;

// ---------------------------------------------------------------------------
// np.clip (measured semantics — see module docs)
// ---------------------------------------------------------------------------

/// `np.maximum(a, b)` — NaN-propagating elementwise maximum (distinct from
/// both `f64::max`, which discards NaN, and `pymath::py_max`, which keeps
/// only the *first* NaN).
#[inline]
fn np_maximum(a: f64, b: f64) -> f64 {
    if a.is_nan() || b.is_nan() {
        f64::NAN
    } else if b > a {
        b
    } else {
        a
    }
}

/// `np.clip(x, lo, hi)`, measured against numpy 2.4.6 (see module docs).
#[inline]
fn np_clip(x: f64, lo: f64, hi: f64) -> f64 {
    let upper = np_maximum(x, lo);
    if upper.is_nan() || hi.is_nan() {
        f64::NAN
    } else if hi < upper {
        hi
    } else {
        upper
    }
}

// ---------------------------------------------------------------------------
// _compute_conflict_clusters
// ---------------------------------------------------------------------------

/// `_compute_conflict_clusters`: builds the overlap-conflict graph over
/// `nets` (in caller-supplied — i.e. Python dict insertion — order) and
/// returns its connected components.
///
/// See the module docs for the deliberate divergence from the oracle's
/// within-cluster net order (hash-randomized in CPython, sorted here for
/// determinism) and why that divergence cannot change any numeric output.
pub fn compute_conflict_clusters(
    nets: &[(String, (f64, f64, f64, f64))],
    overlap_threshold: f64,
) -> Vec<Vec<String>> {
    let n = nets.len();
    if n <= 1 {
        return if n == 1 { vec![vec![nets[0].0.clone()]] } else { Vec::new() };
    }

    let areas: Vec<f64> = nets
        .iter()
        .map(|(_, (x1, y1, x2, y2))| py_max((x2 - x1) * (y2 - y1), 0.0))
        .collect();

    let mut adjacency: Vec<Vec<usize>> = vec![Vec::new(); n];
    for i in 0..n {
        let area_a = areas[i];
        if area_a <= 0.0 {
            continue;
        }
        let (ax1, ay1, ax2, ay2) = nets[i].1;
        for j in (i + 1)..n {
            let area_b = areas[j];
            if area_b <= 0.0 {
                continue;
            }
            let (bx1, by1, bx2, by2) = nets[j].1;
            let ox = py_max(0.0, py_min(ax2, bx2) - py_max(ax1, bx1));
            let oy = py_max(0.0, py_min(ay2, by2) - py_max(ay1, by1));
            let overlap = ox * oy;
            let min_area = py_min(area_a, area_b);
            if min_area > 0.0 && overlap / min_area > overlap_threshold {
                adjacency[i].push(j);
                adjacency[j].push(i);
            }
        }
    }

    let mut visited = vec![false; n];
    let mut clusters: Vec<Vec<String>> = Vec::new();
    for start in 0..n {
        if visited[start] {
            continue;
        }
        let mut stack = vec![start];
        let mut cluster_idx: Vec<usize> = Vec::new();
        while let Some(idx) = stack.pop() {
            if visited[idx] {
                continue;
            }
            visited[idx] = true;
            cluster_idx.push(idx);
            let mut neighbors = adjacency[idx].clone();
            neighbors.sort_unstable();
            for nb in neighbors {
                if !visited[nb] {
                    stack.push(nb);
                }
            }
        }
        clusters.push(cluster_idx.into_iter().map(|i| nets[i].0.clone()).collect());
    }
    clusters
}

#[pyfunction]
#[pyo3(name = "resource_bound_compute_conflict_clusters")]
#[pyo3(signature = (nets, overlap_threshold=OVERLAP_THRESHOLD))]
pub fn compute_conflict_clusters_py(
    nets: Vec<(String, (f64, f64, f64, f64))>,
    overlap_threshold: f64,
) -> Vec<Vec<String>> {
    compute_conflict_clusters(&nets, overlap_threshold)
}

// ---------------------------------------------------------------------------
// _cluster_union_bbox
// ---------------------------------------------------------------------------

/// `_cluster_union_bbox`: union bounding box over `bboxes`, in the exact
/// order supplied (matters only for the NaN edge case — see module docs).
pub fn cluster_union_bbox(bboxes: &[(f64, f64, f64, f64)]) -> (f64, f64, f64, f64) {
    let Some(&(fx1, fy1, fx2, fy2)) = bboxes.first() else {
        return (0.0, 0.0, 0.0, 0.0);
    };
    let mut x1 = fx1;
    let mut y1 = fy1;
    let mut x2 = fx2;
    let mut y2 = fy2;
    for &(bx1, by1, bx2, by2) in &bboxes[1..] {
        x1 = py_min(x1, bx1);
        y1 = py_min(y1, by1);
        x2 = py_max(x2, bx2);
        y2 = py_max(y2, by2);
    }
    (x1, y1, x2, y2)
}

#[pyfunction]
#[pyo3(name = "resource_bound_cluster_union_bbox")]
pub fn cluster_union_bbox_py(bboxes: Vec<(f64, f64, f64, f64)>) -> (f64, f64, f64, f64) {
    cluster_union_bbox(&bboxes)
}

// ---------------------------------------------------------------------------
// _capacity_in_bbox
// ---------------------------------------------------------------------------

/// Error raised only when a grid coordinate is non-finite (e.g. `cell_size
/// == 0.0` making `world_to_grid` divide by zero) — CPython's `int(nan)` /
/// `int(inf)` raise `ValueError`/`OverflowError` there; this crate does not
/// attempt to match the exact exception type or message (no pre-migration
/// test exercises this path — it is not one of the three measured numpy
/// hazards), only that the kernel fails closed rather than silently
/// returning a wrong capacity.
#[derive(Debug)]
pub struct NonFiniteGridCoordinate;

/// `OccupancyGrid.world_to_grid`: `int((coord - origin) / cell_size)`.
/// Python's `int()` truncates toward zero, matching Rust's `as i64` float
/// cast (also truncates toward zero) for finite inputs.
fn world_to_grid(
    x_mm: f64,
    y_mm: f64,
    origin: (f64, f64),
    cell_size: f64,
) -> Result<(i64, i64), NonFiniteGridCoordinate> {
    let gx = (x_mm - origin.0) / cell_size;
    let gy = (y_mm - origin.1) / cell_size;
    if !gx.is_finite() || !gy.is_finite() {
        return Err(NonFiniteGridCoordinate);
    }
    Ok((gx as i64, gy as i64))
}

/// `_capacity_in_bbox`: total free-cell area (mm^2) within `bbox`.
///
/// `grid_cells` is the flattened row-major grid (`height_cells` rows of
/// `width_cells` bytes each — a byte's value is the `OccupancyGrid.grid`
/// int8 cell state, reinterpreted bit-for-bit from Python's
/// `array.tobytes()`). Indexing is defensively bounds-checked against the
/// *actual* slice length rather than trusting `width_cells`/`height_cells`
/// to match it exactly — mirrors numpy's own never-raises slicing (a
/// declared-vs-actual mismatch degrades to counting fewer cells, never a
/// panic), which matters for the `width_cells == 0` / `height_cells == 0`
/// edge case the oracle's redundant post-swap guard defends against.
#[allow(clippy::too_many_arguments)]
pub fn capacity_in_bbox(
    grid_cells: &[i8],
    width_cells: i64,
    height_cells: i64,
    origin: (f64, f64),
    cell_size: f64,
    bbox: (f64, f64, f64, f64),
) -> Result<f64, NonFiniteGridCoordinate> {
    let (min_x, min_y, max_x, max_y) = bbox;

    let (gx1_raw, gy1_raw) = world_to_grid(min_x, min_y, origin, cell_size)?;
    let (gx2_raw, gy2_raw) = world_to_grid(max_x, max_y, origin, cell_size)?;

    // Python: gx1 = max(0, min(gx1, width_cells - 1)) — replicate exactly
    // (including the width_cells == 0 => width_cells - 1 == -1 case,
    // where max(0, min(v, -1)) == 0 for any v).
    let clamp_axis = |v: i64, dim: i64| -> i64 {
        let hi = dim - 1;
        0_i64.max(v.min(hi))
    };

    let mut gx1 = clamp_axis(gx1_raw, width_cells);
    let mut gx2 = clamp_axis(gx2_raw, width_cells);
    let mut gy1 = clamp_axis(gy1_raw, height_cells);
    let mut gy2 = clamp_axis(gy2_raw, height_cells);

    if gx1 > gx2 {
        std::mem::swap(&mut gx1, &mut gx2);
    }
    if gy1 > gy2 {
        std::mem::swap(&mut gy1, &mut gy2);
    }
    if gx1 > gx2 || gy1 > gy2 {
        return Ok(0.0);
    }

    let cols = width_cells.max(0) as usize;
    let rows = height_cells.max(0) as usize;
    let mut free_cells: i64 = 0;
    for row in gy1..=gy2 {
        if row < 0 || row as usize >= rows {
            continue;
        }
        let row_base = row as usize * cols;
        for col in gx1..=gx2 {
            if col < 0 || col as usize >= cols {
                continue;
            }
            let idx = row_base + col as usize;
            if let Some(&v) = grid_cells.get(idx) {
                if v == 0 {
                    free_cells += 1;
                }
            }
        }
    }

    let cell_area = cell_size * cell_size;
    Ok(free_cells as f64 * cell_area)
}

#[pyfunction]
#[pyo3(name = "resource_bound_capacity_in_bbox")]
#[allow(clippy::too_many_arguments)]
pub fn capacity_in_bbox_py(
    grid_bytes: Vec<u8>,
    width_cells: i64,
    height_cells: i64,
    origin: (f64, f64),
    cell_size: f64,
    bbox: (f64, f64, f64, f64),
) -> PyResult<f64> {
    let cells: Vec<i8> = grid_bytes.into_iter().map(|b| b as i8).collect();
    capacity_in_bbox(&cells, width_cells, height_cells, origin, cell_size, bbox)
        .map_err(|_| pyo3::exceptions::PyValueError::new_err("non-finite grid coordinate"))
}

// ---------------------------------------------------------------------------
// _compute_fill_factor
// ---------------------------------------------------------------------------

/// `_compute_fill_factor`. `bbox_areas` must be in the same order as the
/// Python `dict.values()` the oracle sums over (a plain builtin `sum()`,
/// sequential, not `np.sum` — see module docs) for bit-exact float
/// rounding parity.
pub fn compute_fill_factor(trace_width: f64, bbox_areas: &[f64]) -> f64 {
    if bbox_areas.is_empty() {
        return 0.5;
    }
    let avg_area = py_sum(bbox_areas) / bbox_areas.len() as f64;
    if avg_area <= 0.0 {
        return 0.5;
    }
    let sqrt_area = sqrt(avg_area);
    let ff = trace_width / sqrt_area;
    np_clip(ff, 0.01, 1.0)
}

#[pyfunction]
#[pyo3(name = "resource_bound_compute_fill_factor")]
pub fn compute_fill_factor_py(trace_width: f64, bbox_areas: Vec<f64>) -> f64 {
    compute_fill_factor(trace_width, &bbox_areas)
}

// ---------------------------------------------------------------------------
// max_routable_nets / demand_budget_summary — shared orchestration
// ---------------------------------------------------------------------------

struct GridArgs<'a> {
    cells: &'a [i8],
    width_cells: i64,
    height_cells: i64,
    origin: (f64, f64),
    cell_size: f64,
}

struct BoundResult {
    total_routable: i64,
    total_capacity: f64,
    total_demand: f64,
    fill_factor: f64,
    cluster_count: usize,
}

/// Shared core of `max_routable_nets` / `demand_budget_summary`: both
/// oracle functions are the identical per-cluster bin-packing loop, only
/// their return shape differs.
fn resource_bound_core(
    grid: &GridArgs<'_>,
    nets: &[(String, (f64, f64, f64, f64))],
    trace_width: f64,
    fill_factor: Option<f64>,
) -> Result<BoundResult, NonFiniteGridCoordinate> {
    if nets.is_empty() {
        return Ok(BoundResult {
            total_routable: 0,
            total_capacity: 0.0,
            total_demand: 0.0,
            fill_factor: fill_factor.unwrap_or(0.5),
            cluster_count: 0,
        });
    }

    let bbox_areas: Vec<f64> = nets
        .iter()
        .map(|(_, (x1, y1, x2, y2))| py_max((x2 - x1) * (y2 - y1), 0.0))
        .collect();

    let fill_factor_used = match fill_factor {
        Some(f) => f,
        None => compute_fill_factor(trace_width, &bbox_areas),
    };

    let demands: Vec<f64> = bbox_areas.iter().map(|a| a * fill_factor_used).collect();
    let bbox_by_name: std::collections::HashMap<&str, (f64, f64, f64, f64)> =
        nets.iter().map(|(n, b)| (n.as_str(), *b)).collect();
    let demand_by_name: std::collections::HashMap<&str, f64> =
        nets.iter().zip(demands.iter()).map(|((n, _), d)| (n.as_str(), *d)).collect();

    let clusters = compute_conflict_clusters(nets, OVERLAP_THRESHOLD);

    let mut total_capacity = 0.0_f64;
    let mut total_routable: i64 = 0;

    for cluster in &clusters {
        let cluster_bboxes: Vec<(f64, f64, f64, f64)> =
            cluster.iter().map(|n| bbox_by_name[n.as_str()]).collect();
        let union_bbox = cluster_union_bbox(&cluster_bboxes);
        let capacity = capacity_in_bbox(
            grid.cells,
            grid.width_cells,
            grid.height_cells,
            grid.origin,
            grid.cell_size,
            union_bbox,
        )?;
        total_capacity += capacity;

        let mut cluster_demands: Vec<f64> =
            cluster.iter().map(|n| demand_by_name[n.as_str()]).collect();
        cluster_demands.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));

        let mut running = 0.0_f64;
        let mut k: i64 = 0;
        for d in cluster_demands {
            if running + d > capacity {
                break;
            }
            running += d;
            k += 1;
        }
        total_routable += k;
    }

    // total_demand: `sum(demands.values())` over the FULL demand map, not
    // an accumulation across clusters — matches the oracle exactly (every
    // net belongs to exactly one cluster, so the two are mathematically
    // equal, but this mirrors the oracle's own computation path rather
    // than relying on that equivalence for bit-exact float rounding).
    // CPython 3.12's builtin `sum()` on floats is Neumaier-compensated,
    // not a naive fold — see `pymath::py_sum` and the module docs.
    let total_demand: f64 = py_sum(&demands);

    Ok(BoundResult {
        total_routable,
        total_capacity,
        total_demand,
        fill_factor: fill_factor_used,
        cluster_count: clusters.len(),
    })
}

#[pyfunction]
#[pyo3(name = "resource_bound_max_routable_nets")]
#[pyo3(signature = (grid_bytes, width_cells, height_cells, origin, cell_size, nets, trace_width, fill_factor=None))]
#[allow(clippy::too_many_arguments)]
pub fn max_routable_nets_py(
    grid_bytes: Vec<u8>,
    width_cells: i64,
    height_cells: i64,
    origin: (f64, f64),
    cell_size: f64,
    nets: Vec<(String, (f64, f64, f64, f64))>,
    trace_width: f64,
    fill_factor: Option<f64>,
) -> PyResult<i64> {
    let cells: Vec<i8> = grid_bytes.into_iter().map(|b| b as i8).collect();
    let grid = GridArgs { cells: &cells, width_cells, height_cells, origin, cell_size };
    let result = resource_bound_core(&grid, &nets, trace_width, fill_factor)
        .map_err(|_| pyo3::exceptions::PyValueError::new_err("non-finite grid coordinate"))?;
    Ok(result.total_routable)
}

#[pyfunction]
#[pyo3(name = "resource_bound_demand_budget_summary")]
#[pyo3(signature = (grid_bytes, width_cells, height_cells, origin, cell_size, nets, trace_width, fill_factor=None))]
#[allow(clippy::too_many_arguments)]
pub fn demand_budget_summary_py<'py>(
    py: Python<'py>,
    grid_bytes: Vec<u8>,
    width_cells: i64,
    height_cells: i64,
    origin: (f64, f64),
    cell_size: f64,
    nets: Vec<(String, (f64, f64, f64, f64))>,
    trace_width: f64,
    fill_factor: Option<f64>,
) -> PyResult<Bound<'py, PyDict>> {
    let cells: Vec<i8> = grid_bytes.into_iter().map(|b| b as i8).collect();
    let grid = GridArgs { cells: &cells, width_cells, height_cells, origin, cell_size };
    let total_nets = nets.len();
    let result = resource_bound_core(&grid, &nets, trace_width, fill_factor)
        .map_err(|_| pyo3::exceptions::PyValueError::new_err("non-finite grid coordinate"))?;

    let d = PyDict::new(py);
    d.set_item("max_routable", result.total_routable)?;
    d.set_item("total_nets", total_nets)?;
    d.set_item("fill_factor", result.fill_factor)?;
    d.set_item("cluster_count", result.cluster_count)?;
    d.set_item("total_capacity_mm2", result.total_capacity)?;
    d.set_item("total_demand_mm2", result.total_demand)?;
    d.set_item("utilization", result.total_demand / py_max(result.total_capacity, 1e-6))?;
    Ok(d)
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------

pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(compute_conflict_clusters_py, m)?)?;
    m.add_function(wrap_pyfunction!(cluster_union_bbox_py, m)?)?;
    m.add_function(wrap_pyfunction!(capacity_in_bbox_py, m)?)?;
    m.add_function(wrap_pyfunction!(compute_fill_factor_py, m)?)?;
    m.add_function(wrap_pyfunction!(max_routable_nets_py, m)?)?;
    m.add_function(wrap_pyfunction!(demand_budget_summary_py, m)?)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Unit tests
// ---------------------------------------------------------------------------

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;

    #[test]
    fn np_clip_matches_measured_numpy_semantics() {
        assert_eq!(np_clip(0.5, 0.01, 1.0), 0.5);
        assert_eq!(np_clip(-1.0, 0.01, 1.0), 0.01);
        assert_eq!(np_clip(2.0, 0.01, 1.0), 1.0);
        assert!(np_clip(f64::NAN, 0.01, 1.0).is_nan());
        assert!(np_clip(0.01, f64::NAN, 1.0).is_nan());
        assert!(np_clip(0.01, 0.01, f64::NAN).is_nan());
    }

    #[test]
    fn conflict_clusters_empty_and_single() {
        assert_eq!(compute_conflict_clusters(&[], OVERLAP_THRESHOLD), Vec::<Vec<String>>::new());
        let one = vec![("A".to_string(), (0.0, 0.0, 1.0, 1.0))];
        assert_eq!(compute_conflict_clusters(&one, OVERLAP_THRESHOLD), vec![vec!["A".to_string()]]);
    }

    #[test]
    fn conflict_clusters_no_overlap_separate() {
        let nets = vec![
            ("A".to_string(), (0.0, 0.0, 5.0, 5.0)),
            ("B".to_string(), (10.0, 10.0, 15.0, 15.0)),
        ];
        let clusters = compute_conflict_clusters(&nets, OVERLAP_THRESHOLD);
        assert_eq!(clusters.len(), 2);
    }

    #[test]
    fn conflict_clusters_full_overlap_merges() {
        let nets = vec![
            ("A".to_string(), (0.0, 0.0, 10.0, 10.0)),
            ("B".to_string(), (1.0, 1.0, 9.0, 9.0)),
        ];
        let clusters = compute_conflict_clusters(&nets, OVERLAP_THRESHOLD);
        assert_eq!(clusters.len(), 1);
        let mut names = clusters[0].clone();
        names.sort();
        assert_eq!(names, vec!["A".to_string(), "B".to_string()]);
    }

    #[test]
    fn cluster_union_bbox_basic() {
        let bboxes = vec![(0.0, 0.0, 5.0, 5.0), (2.0, 2.0, 8.0, 8.0)];
        assert_eq!(cluster_union_bbox(&bboxes), (0.0, 0.0, 8.0, 8.0));
        assert_eq!(cluster_union_bbox(&[]), (0.0, 0.0, 0.0, 0.0));
    }

    #[test]
    fn capacity_in_bbox_all_free() {
        let cells = vec![0_i8; 50 * 50];
        let cap = capacity_in_bbox(&cells, 50, 50, (0.0, 0.0), 1.0, (0.0, 0.0, 10.0, 10.0)).unwrap();
        assert!((100.0..=130.0).contains(&cap));
    }

    #[test]
    fn capacity_in_bbox_fully_blocked() {
        let cells = vec![1_i8; 10 * 10];
        let cap = capacity_in_bbox(&cells, 10, 10, (0.0, 0.0), 1.0, (1.0, 1.0, 4.0, 4.0)).unwrap();
        assert_eq!(cap, 0.0);
    }

    #[test]
    fn capacity_in_bbox_zero_size_grid_never_panics() {
        let cells: Vec<i8> = vec![];
        let cap = capacity_in_bbox(&cells, 0, 0, (0.0, 0.0), 1.0, (0.0, 0.0, 10.0, 10.0)).unwrap();
        assert_eq!(cap, 0.0);
    }

    #[test]
    fn compute_fill_factor_bounds() {
        let areas = vec![100.0, 400.0];
        let ff_small = compute_fill_factor(0.1, &areas);
        let ff_large = compute_fill_factor(0.5, &areas);
        assert!((0.01..=1.0).contains(&ff_small));
        assert!((0.01..=1.0).contains(&ff_large));
        assert!(ff_large > ff_small);
        assert_eq!(compute_fill_factor(0.1, &[]), 0.5);
    }

    #[test]
    fn compute_fill_factor_uses_neumaier_sum_not_naive_fold() {
        // Pinned regression: CPython 3.12's `sum()` on floats is
        // Neumaier-compensated (see module docs) -- this exact 4-element
        // vector diverges by 1 ULP between a naive sequential fold and the
        // oracle's `sum()`. `compute_fill_factor` must match the oracle.
        let areas = [4671.917981058251, 2274.697238796103, 3849.4502398234745, 3324.755168764735];
        let trace_width = f64::from_bits(0x3ff719750feb72f7);
        let naive_avg = areas.iter().sum::<f64>() / areas.len() as f64;
        let compensated_avg = py_sum(&areas) / areas.len() as f64;
        assert_ne!(
            naive_avg.to_bits(),
            compensated_avg.to_bits(),
            "fixture no longer exhibits the 1-ULP divergence -- pin a new one"
        );
        let got = compute_fill_factor(trace_width, &areas);
        let expected_bits = 0x3f98e1bc891336e3_u64; // oracle: float(np.clip(...)).hex()
        assert_eq!(got.to_bits(), expected_bits);
    }
}
