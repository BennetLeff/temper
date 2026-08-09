// Wave 4: `temper_placer/router_v6/resource_bound.py` — the resource-
// exhaustion kernels (bin-packing lower bound on simultaneously routable
// nets).  The ParsedPCB-driven orchestration (`_net_bboxes_from_pcb`,
// `max_routable_nets_from_pcb`) and the logging stay in Python; every
// computation that turns bboxes + a grid into a bound crosses this boundary.
//
// The verbatim pre-migration copy this module must reproduce bit-identically
// is pinned in the `_oracle_*` block of
// `packages/temper-placer/tests/router_v6/
// test_spatial_drc_cluster_rust_differential.py`.
//
// ---------------------------------------------------------------------------
// Numerical contract
// ---------------------------------------------------------------------------
// * Per-net area is `max((x2-x1)*(y2-y1), 0.0)` — a Python *builtin* `max`
//   with the product as its FIRST argument (position-dependent NaN
//   semantics, class B5), so it is `py_max(product, 0.0)`, not `f64::max`.
// * Conflict overlap is `max(0.0, min(ax2,bx2) - max(ax1,bx1))` — builtin
//   `min`/`max`/`max` in that nesting order; the outer `max` has `0.0` as
//   its first argument.  Replicated with `py_min`/`py_max` from
//   `creepage_check.rs`.
// * `_compute_fill_factor`: `sum(bbox_areas.values())` is CPython builtin
//   `sum()` = Neumaier-compensated (class B12) over dict insertion order;
//   `np.sqrt` and `np.clip(x, 0.01, 1.0)` are numpy ufuncs — `np.clip`
//   expands to `np.minimum(np.maximum(x, lo), hi)` (class B12), NaN
//   propagating from either operand, implemented here as `np_minimum`/
//   `np_maximum`.
// * `world_to_grid` is `int((x - origin)/cell_size)` — truncation toward
//   zero (`as i64`), and the clamp is Python builtin `max(0, min(g, W-1))`
//   on ints (plain i64 min/max, no NaN class involved).
// * The conflict clusters are connected components of the overlap graph.
//   Cluster *membership* and outer discovery order (first member in input
//   order) are deterministic.  The reference's *intra*-cluster order is
//   Python-set-iteration dependent (hash-seed-dependent); every downstream
//   consumer either sorts (`sorted(demands ...)`) or aggregates (min/max),
//   so this kernel returns each cluster's indices sorted ascending and the
//   differential compares the normalized form.  `total_capacity` in
//   `demand_budget` is a per-cluster float `+=` over clusters in the
//   deterministic outer order, matching the reference bit-for-bit.
// * The bin-packing greedy step is `if running + d > capacity: break` with
//   a naive left-to-right `+=` fold; the demand sort is Python's stable
//   `<`-order sort (Rust `sort_by` with `partial_cmp`, unordered→Equal so
//   NaN/-0.0 ties keep input order).

use crate::creepage_check::{py_max, py_min};

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// CPython 3.12 builtin `sum()` over floats: the improved Kahan-Babuska
/// (Neumaier) algorithm (class B12).  Duplicated from
/// `area_sufficiency.rs::py_sum_neumaier` (which is python-feature-gated;
/// this kernel must also build under `--no-default-features`).  The
/// differential suite pins it directly against CPython `sum()`.
pub(crate) fn py_sum_neumaier(items: &[f64]) -> f64 {
    debug_assert!(!items.is_empty(), "empty input is handled by the caller");
    let mut f_result = 0.0f64 + items[0];
    let mut c = 0.0f64;
    for &x in &items[1..] {
        let t = f_result + x;
        if f_result.abs() >= x.abs() {
            c += (f_result - t) + x;
        } else {
            c += (x - t) + f_result;
        }
        f_result = t;
    }
    if c != 0.0 && c.is_finite() {
        f_result += c;
    }
    f_result
}

/// `np.maximum(a, b)`: NaN propagates from EITHER operand (differs from
/// both `f64::max` and the builtin `py_max`).
fn np_maximum(a: f64, b: f64) -> f64 {
    if a.is_nan() || b.is_nan() {
        f64::NAN
    } else if a > b {
        a
    } else {
        b
    }
}

/// `np.minimum(a, b)`: NaN propagates from either operand.
fn np_minimum(a: f64, b: f64) -> f64 {
    if a.is_nan() || b.is_nan() {
        f64::NAN
    } else if a < b {
        a
    } else {
        b
    }
}

/// `np.clip(x, lo, hi)` = `np.minimum(np.maximum(x, lo), hi)`.
fn np_clip(x: f64, lo: f64, hi: f64) -> f64 {
    np_minimum(np_maximum(x, lo), hi)
}

/// Per-net bbox area: `max((x2-x1)*(y2-y1), 0.0)` — the product is the
/// FIRST argument of the builtin `max`.
fn bbox_area(bbox: &[f64]) -> f64 {
    let product = (bbox[2] - bbox[0]) * (bbox[3] - bbox[1]);
    py_max(product, 0.0)
}

/// `_compute_conflict_clusters`: connected components of the overlap
/// graph, where two nets conflict when the smaller net's area is overlapped
/// by more than `overlap_threshold`.  `bboxes` is a flat
/// `[x0,y0,x1,y1, x2,y2,x3,y3, ...]` array in dict-insertion order.
///
/// Returns clusters of INDICES; each cluster is sorted ascending; clusters
/// appear in the reference's outer discovery order (first member in input
/// order).
pub fn conflict_clusters(bboxes: &[f64], overlap_threshold: f64) -> Vec<Vec<usize>> {
    let n = bboxes.len() / 4;
    if n == 0 {
        return Vec::new();
    }
    let mut areas = vec![0.0f64; n];
    for (i, a) in areas.iter_mut().enumerate() {
        *a = bbox_area(&bboxes[4 * i..4 * i + 4]);
    }
    let mut adjacency: Vec<Vec<usize>> = vec![Vec::new(); n];
    for i in 0..n {
        let area_a = areas[i];
        if area_a <= 0.0 {
            continue;
        }
        let (ax1, ay1, ax2, ay2) = (bboxes[4 * i], bboxes[4 * i + 1], bboxes[4 * i + 2], bboxes[4 * i + 3]);
        for j in (i + 1)..n {
            let area_b = areas[j];
            if area_b <= 0.0 {
                continue;
            }
            let (bx1, by1, bx2, by2) = (bboxes[4 * j], bboxes[4 * j + 1], bboxes[4 * j + 2], bboxes[4 * j + 3]);
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
    // DFS in input order, exactly the reference's `queue.pop()` (LIFO)
    // traversal over the neighbor set.
    let mut visited = vec![false; n];
    let mut clusters: Vec<Vec<usize>> = Vec::new();
    for start in 0..n {
        if visited[start] {
            continue;
        }
        let mut stack = vec![start];
        let mut cluster: Vec<usize> = Vec::new();
        while let Some(node) = stack.pop() {
            if visited[node] {
                continue;
            }
            visited[node] = true;
            cluster.push(node);
            for &nb in &adjacency[node] {
                if !visited[nb] {
                    stack.push(nb);
                }
            }
        }
        cluster.sort_unstable();
        clusters.push(cluster);
    }
    clusters
}

/// `_cluster_union_bbox`: `(min_x, min_y, max_x, max_y)` over a cluster's
/// nets, using builtin `min`/`max` chains (py semantics).  Finite-coordinate
/// contract — with a NaN bbox the reference itself is iteration-order
/// dependent, so NaN inputs are outside the pinned differential.
pub fn cluster_union_bbox(cluster: &[usize], bboxes: &[f64]) -> [f64; 4] {
    if cluster.is_empty() {
        return [0.0, 0.0, 0.0, 0.0];
    }
    let mut x1 = bboxes[4 * cluster[0]];
    let mut y1 = bboxes[4 * cluster[0] + 1];
    let mut x2 = bboxes[4 * cluster[0] + 2];
    let mut y2 = bboxes[4 * cluster[0] + 3];
    for &i in &cluster[1..] {
        x1 = py_min(x1, bboxes[4 * i]);
        y1 = py_min(y1, bboxes[4 * i + 1]);
        x2 = py_max(x2, bboxes[4 * i + 2]);
        y2 = py_max(y2, bboxes[4 * i + 3]);
    }
    [x1, y1, x2, y2]
}

/// `_capacity_in_bbox`: free (value == 0) cell count within a world-coordinate
/// bbox, times cell area.  `grid` is the flat row-major grid (index
/// `row * width_cells + col`); `world_to_grid` truncates toward zero.
pub fn capacity_in_bbox(
    grid: &[i64],
    width_cells: usize,
    height_cells: usize,
    cell_size: f64,
    origin_x: f64,
    origin_y: f64,
    bbox: [f64; 4],
) -> f64 {
    let [min_x, min_y, max_x, max_y] = bbox;
    if width_cells == 0 || height_cells == 0 {
        return 0.0;
    }
    let mut gx1 = ((min_x - origin_x) / cell_size) as i64;
    let mut gy1 = ((min_y - origin_y) / cell_size) as i64;
    let mut gx2 = ((max_x - origin_x) / cell_size) as i64;
    let mut gy2 = ((max_y - origin_y) / cell_size) as i64;

    let w = width_cells as i64;
    let h = height_cells as i64;
    // max(0, min(g, W-1)) — ints, builtin order preserved.
    gx1 = gx1.min(w - 1).max(0);
    gx2 = gx2.min(w - 1).max(0);
    gy1 = gy1.min(h - 1).max(0);
    gy2 = gy2.min(h - 1).max(0);

    if gx1 > gx2 {
        std::mem::swap(&mut gx1, &mut gx2);
    }
    if gy1 > gy2 {
        std::mem::swap(&mut gy1, &mut gy2);
    }

    let mut free_cells: i64 = 0;
    for r in gy1..=gy2 {
        for c in gx1..=gx2 {
            let idx = r * width_cells as i64 + c;
            if grid[idx as usize] == 0 {
                free_cells += 1;
            }
        }
    }
    let cell_area = cell_size * cell_size;
    free_cells as f64 * cell_area
}

/// `_compute_fill_factor`: `trace_width / sqrt(avg bbox area)`, clamped to
/// `[0.01, 1.0]` via `np.clip`.  `areas` must be in dict-insertion order
/// (builtin `sum` is Neumaier, not naive).
pub fn fill_factor(trace_width: f64, areas: &[f64]) -> f64 {
    if areas.is_empty() {
        return 0.5;
    }
    let avg_area = py_sum_neumaier(areas) / areas.len() as f64;
    if avg_area <= 0.0 {
        return 0.5;
    }
    let sqrt_area = avg_area.sqrt();
    let ff = trace_width / sqrt_area;
    np_clip(ff, 0.01, 1.0)
}

/// `max_routable_nets` computation, shared by `max_routable` and
/// `demand_budget`.  Returns `(total_routable, resolved_fill_factor,
/// cluster_count, cluster_capacities)` where `cluster_capacities` is one
/// float per cluster in outer discovery order (the reference's
/// `total_capacity` fold order).
struct BoundResult {
    total: i64,
    fill_factor: f64,
    cluster_count: i64,
    capacities: Vec<f64>,
}

#[allow(clippy::too_many_arguments)]
fn compute_bound(
    bboxes: &[f64],
    grid: &[i64],
    width_cells: usize,
    height_cells: usize,
    cell_size: f64,
    origin_x: f64,
    origin_y: f64,
    trace_width: f64,
    fill_factor_opt: Option<f64>,
) -> BoundResult {
    let n = bboxes.len() / 4;
    if n == 0 {
        return BoundResult {
            total: 0,
            fill_factor: fill_factor_opt.unwrap_or(0.5),
            cluster_count: 0,
            capacities: Vec::new(),
        };
    }
    let mut areas = vec![0.0f64; n];
    for (i, a) in areas.iter_mut().enumerate() {
        *a = bbox_area(&bboxes[4 * i..4 * i + 4]);
    }
    let fill = match fill_factor_opt {
        Some(f) => f,
        None => fill_factor(trace_width, &areas),
    };
    let mut demands = vec![0.0f64; n];
    for (d, &a) in demands.iter_mut().zip(areas.iter()) {
        *d = a * fill;
    }
    let clusters = conflict_clusters(bboxes, 0.1);
    let mut total: i64 = 0;
    let mut capacities: Vec<f64> = Vec::with_capacity(clusters.len());
    for cluster in &clusters {
        let union_bbox = cluster_union_bbox(cluster, bboxes);
        let capacity = capacity_in_bbox(
            grid,
            width_cells,
            height_cells,
            cell_size,
            origin_x,
            origin_y,
            union_bbox,
        );
        capacities.push(capacity);
        let mut cluster_demands: Vec<f64> = cluster.iter().map(|&i| demands[i]).collect();
        // Python sorted(): stable, `<`-ordered; unordered (NaN) ties keep
        // input order via partial_cmp().unwrap_or(Ordering::Equal).
        cluster_demands.sort_by(|a, b| a.partial_cmp(b).unwrap_or(std::cmp::Ordering::Equal));
        let mut running = 0.0;
        let mut k: i64 = 0;
        for d in &cluster_demands {
            if running + d > capacity {
                break;
            }
            running += d;
            k += 1;
        }
        total += k;
    }
    BoundResult {
        total,
        fill_factor: fill,
        cluster_count: clusters.len() as i64,
        capacities,
    }
}

/// `max_routable_nets`: the bin-packing upper bound over conflict clusters.
#[allow(clippy::too_many_arguments)]
pub fn max_routable(
    bboxes: &[f64],
    grid: &[i64],
    width_cells: usize,
    height_cells: usize,
    cell_size: f64,
    origin_x: f64,
    origin_y: f64,
    trace_width: f64,
    fill_factor_opt: Option<f64>,
) -> (i64, f64, i64) {
    let r = compute_bound(
        bboxes,
        grid,
        width_cells,
        height_cells,
        cell_size,
        origin_x,
        origin_y,
        trace_width,
        fill_factor_opt,
    );
    (r.total, r.fill_factor, r.cluster_count)
}

/// `demand_budget_summary`: (max_routable, total_nets, fill_factor,
/// cluster_count, total_capacity_mm2, total_demand_mm2, utilization).
/// `total_capacity` is a per-cluster `+=` fold over the deterministic outer
/// cluster order; `total_demand` is builtin `sum()` (Neumaier) over input
/// order; `utilization` divides by `max(total_capacity, 1e-6)` (builtin max,
/// total_capacity first).
#[allow(clippy::too_many_arguments)]
pub fn demand_budget(
    bboxes: &[f64],
    grid: &[i64],
    width_cells: usize,
    height_cells: usize,
    cell_size: f64,
    origin_x: f64,
    origin_y: f64,
    trace_width: f64,
    fill_factor_opt: Option<f64>,
) -> (i64, i64, f64, i64, f64, f64, f64) {
    let n = bboxes.len() / 4;
    if n == 0 {
        return (
            0,
            0,
            fill_factor_opt.unwrap_or(0.5),
            0,
            0.0,
            0.0,
            0.0,
        );
    }
    let r = compute_bound(
        bboxes,
        grid,
        width_cells,
        height_cells,
        cell_size,
        origin_x,
        origin_y,
        trace_width,
        fill_factor_opt,
    );
    let mut total_capacity = 0.0;
    for &c in &r.capacities {
        total_capacity += c;
    }
    let mut areas = vec![0.0f64; n];
    for (i, a) in areas.iter_mut().enumerate() {
        *a = bbox_area(&bboxes[4 * i..4 * i + 4]);
    }
    let mut demands = vec![0.0f64; n];
    for (d, &a) in demands.iter_mut().zip(areas.iter()) {
        *d = a * r.fill_factor;
    }
    let total_demand = py_sum_neumaier(&demands);
    let utilization = total_demand / py_max(total_capacity, 1e-6);
    (
        r.total,
        n as i64,
        r.fill_factor,
        r.cluster_count,
        total_capacity,
        total_demand,
        utilization,
    )
}

// ---------------------------------------------------------------------------
// pyo3 boundary
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
#[pyfunction]
pub fn conflict_clusters_py(bboxes: Vec<f64>, overlap_threshold: f64) -> PyResult<Vec<Vec<usize>>> {
    temper_py_bridge::catch_unwind(|| conflict_clusters(&bboxes, overlap_threshold))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn cluster_union_bbox_py(cluster: Vec<usize>, bboxes: Vec<f64>) -> PyResult<(f64, f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let b = cluster_union_bbox(&cluster, &bboxes);
        (b[0], b[1], b[2], b[3])
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[allow(clippy::too_many_arguments)]
#[cfg(feature = "python")]
#[pyfunction]
pub fn capacity_in_bbox_py(
    grid: Vec<i64>,
    width_cells: usize,
    height_cells: usize,
    cell_size: f64,
    origin_x: f64,
    origin_y: f64,
    x1: f64,
    y1: f64,
    x2: f64,
    y2: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        capacity_in_bbox(
            &grid,
            width_cells,
            height_cells,
            cell_size,
            origin_x,
            origin_y,
            [x1, y1, x2, y2],
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn fill_factor_py(trace_width: f64, areas: Vec<f64>) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| fill_factor(trace_width, &areas))
        .map_err(temper_py_bridge::panic_to_err)
}

#[allow(clippy::too_many_arguments)]
#[cfg(feature = "python")]
#[pyfunction]
pub fn max_routable_py(
    bboxes: Vec<f64>,
    grid: Vec<i64>,
    width_cells: usize,
    height_cells: usize,
    cell_size: f64,
    origin_x: f64,
    origin_y: f64,
    trace_width: f64,
    fill_factor: Option<f64>,
) -> PyResult<(i64, f64, i64)> {
    temper_py_bridge::catch_unwind(|| {
        max_routable(
            &bboxes,
            &grid,
            width_cells,
            height_cells,
            cell_size,
            origin_x,
            origin_y,
            trace_width,
            fill_factor,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[allow(clippy::too_many_arguments)]
#[cfg(feature = "python")]
#[pyfunction]
pub fn demand_budget_py(
    bboxes: Vec<f64>,
    grid: Vec<i64>,
    width_cells: usize,
    height_cells: usize,
    cell_size: f64,
    origin_x: f64,
    origin_y: f64,
    trace_width: f64,
    fill_factor: Option<f64>,
) -> PyResult<(i64, i64, f64, i64, f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        demand_budget(
            &bboxes,
            &grid,
            width_cells,
            height_cells,
            cell_size,
            origin_x,
            origin_y,
            trace_width,
            fill_factor,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(conflict_clusters_py, m)?)?;
    m.add_function(wrap_pyfunction!(cluster_union_bbox_py, m)?)?;
    m.add_function(wrap_pyfunction!(capacity_in_bbox_py, m)?)?;
    m.add_function(wrap_pyfunction!(fill_factor_py, m)?)?;
    m.add_function(wrap_pyfunction!(max_routable_py, m)?)?;
    m.add_function(wrap_pyfunction!(demand_budget_py, m)?)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn conflict_clusters_empty_and_single() {
        assert_eq!(conflict_clusters(&[], 0.1), Vec::<Vec<usize>>::new());
        assert_eq!(conflict_clusters(&[0.0, 0.0, 1.0, 1.0], 0.1), vec![vec![0]]);
    }

    #[test]
    fn conflict_clusters_disjoint_and_overlapping() {
        // disjoint: three separate clusters
        let bboxes = vec![0.0, 0.0, 1.0, 1.0, 10.0, 10.0, 11.0, 11.0, 20.0, 20.0, 21.0, 21.0];
        assert_eq!(conflict_clusters(&bboxes, 0.1), vec![vec![0], vec![1], vec![2]]);
        // nested overlap -> single cluster
        let bboxes = vec![0.0, 0.0, 10.0, 10.0, 1.0, 1.0, 9.0, 9.0, 2.0, 2.0, 8.0, 8.0];
        assert_eq!(conflict_clusters(&bboxes, 0.1), vec![vec![0, 1, 2]]);
    }

    #[test]
    fn conflict_clusters_chain_merges() {
        // A-B and B-C overlap, A-C do not -> one cluster
        let bboxes = vec![0.0, 0.0, 5.0, 5.0, 3.0, 3.0, 8.0, 8.0, 6.0, 6.0, 11.0, 11.0];
        assert_eq!(conflict_clusters(&bboxes, 0.1), vec![vec![0, 1, 2]]);
    }

    #[test]
    fn cluster_union_bbox_basic_and_empty() {
        let bboxes = vec![0.0, 0.0, 2.0, 2.0, 1.0, 1.0, 3.0, 3.0, 5.0, 5.0, 6.0, 6.0];
        assert_eq!(cluster_union_bbox(&[0, 1], &bboxes), [0.0, 0.0, 3.0, 3.0]);
        assert_eq!(cluster_union_bbox(&[], &bboxes), [0.0, 0.0, 0.0, 0.0]);
    }

    #[test]
    fn capacity_in_bbox_all_free_and_out_of_bounds() {
        // 3x3 free grid, cell 1mm: bbox covering the whole board -> 9 free
        let grid = vec![0i64; 9];
        let c = capacity_in_bbox(&grid, 3, 3, 1.0, 0.0, 0.0, [0.0, 0.0, 3.0, 3.0]);
        assert_eq!(c, 9.0);
        // bbox entirely outside -> clamps to the single corner cell
        let c2 = capacity_in_bbox(&grid, 3, 3, 1.0, 0.0, 0.0, [100.0, 100.0, 200.0, 200.0]);
        assert_eq!(c2, 1.0);
        // blocked grid -> 0
        let blocked = vec![1i64; 9];
        assert_eq!(capacity_in_bbox(&blocked, 3, 3, 1.0, 0.0, 0.0, [0.0, 0.0, 3.0, 3.0]), 0.0);
    }

    #[test]
    fn fill_factor_bounds_and_empty() {
        assert_eq!(fill_factor(0.2, &[]), 0.5);
        let f = fill_factor(0.2, &[100.0, 400.0]);
        assert!((0.01..=1.0).contains(&f));
        // larger trace width -> larger fill factor
        let f2 = fill_factor(0.5, &[100.0, 400.0]);
        assert!(f2 > f);
    }

    #[test]
    fn max_routable_empty_and_single() {
        assert_eq!(max_routable(&[], &[0i64], 1, 1, 1.0, 0.0, 0.0, 0.2, None), (0, 0.5, 0));
        // single net with capacity -> 1
        let r = max_routable(
            &[0.0, 0.0, 5.0, 5.0],
            &[0i64; 100],
            10,
            10,
            1.0,
            0.0,
            0.0,
            0.2,
            None,
        );
        assert_eq!(r.0, 1);
    }

    #[test]
    fn max_routable_respects_capacity_limit() {
        // 10x10 free grid; 50 nets packed in the corner form one cluster;
        // fill_factor=1.0 caps how many fit (strictly < 50).
        let grid = vec![0i64; 100];
        let mut bboxes: Vec<f64> = Vec::new();
        for i in 0..50 {
            let o = i as f64 * 0.05;
            bboxes.extend([o, o, o + 2.0, o + 2.0]);
        }
        let r = max_routable(&bboxes, &grid, 10, 10, 1.0, 0.0, 0.0, 0.2, Some(1.0));
        assert!(r.0 < 50);
    }

    #[test]
    fn demand_budget_empty_and_utilization() {
        let d = demand_budget(&[], &[0i64], 1, 1, 1.0, 0.0, 0.0, 0.2, None);
        assert_eq!(d, (0, 0, 0.5, 0, 0.0, 0.0, 0.0));
        let d2 = demand_budget(
            &[0.0, 0.0, 1.0, 1.0],
            &[0i64; 100],
            10,
            10,
            1.0,
            0.0,
            0.0,
            0.2,
            Some(0.5),
        );
        assert_eq!(d2.0, 1);
        assert_eq!(d2.1, 1);
        assert_eq!(d2.4, 4.0); // bbox [0,1]x[0,1] -> 2x2 = 4 free cells
        assert!(d2.6 >= 0.0);
    }
}
