//! `router_v6/resource_bound.py` — the bin-packing resource-exhaustion
//! kernels, ported from the pinned oracle
//! `packages/temper-placer/tests/router_v6/_resource_bound_py_oracle.py`
//! (verbatim copy of lines 36-390 of commit `da7708e55753c4271385d49d915bab4d186f641d`,
//! origin/main).
//!
//! Ported (4 of the module's 8 functions — see the oracle docstring for the
//! full worth-porting rationale):
//! - [`conflict_clusters`] — `_compute_conflict_clusters`
//! - [`cluster_union_bbox`] — `_cluster_union_bbox`
//! - [`capacity_in_bbox`] — `_capacity_in_bbox`
//! - [`compute_fill_factor`] — `_compute_fill_factor`
//!
//! `max_routable_nets` and `demand_budget_summary` are NOT re-implemented
//! here: their Python bodies are unchanged and now execute entirely through
//! the four kernels above (transitive delegation) except for their own
//! outer bin-packing loop (`sorted(...)` + a running-sum `for` loop over a
//! per-cluster demand list), which is plain float/int arithmetic with no
//! numpy call and no O(n^2) shape — not part of this crate's port.
//! `_net_bboxes_from_pcb` (PCB/Component/Pin object-graph traversal, zero
//! numpy) and `max_routable_nets_from_pcb` (a 2-line, zero-caller
//! convenience wrapper) stay pure Python glue.
//!
//! ## The `np.clip` NaN trap
//!
//! `_compute_fill_factor`'s `np.clip(ff, 0.01, 1.0)` propagates NaN from
//! *either* operand (like `np.maximum`/`np.minimum`), which is NEITHER
//! CPython's builtin `max`/`min` (keeps whichever argument a NaN
//! comparison failed to unseat — see [`crate::pymath::py_max`]) NOR
//! `f64::max`/`f64::min` (IEEE-754-minimum-propagating: discards NaN).
//! Measured directly against this repo's numpy (2.4.6):
//! `np.clip(nan, 0.01, 1.0)` is `nan`; a naive `max(0.01, min(1.0, nan))`
//! chain built from `py_max`/`py_min` is `1.0`. [`np_clip`] below
//! implements the either-operand-propagating shape via local
//! `np_maximum`/`np_minimum` helpers, not `py_max`/`py_min`.
//!
//! `ff` can genuinely be NaN in production: `avg_area <= 0` (the guard
//! meant to short-circuit before `sqrt`/`clip`) is `False` when `avg_area`
//! is NaN, so a NaN average bbox area falls through to `sqrt`/`clip`
//! rather than the `0.5` early return, in both the oracle and this port.
//!
//! ## `np.sum` on the capacity region — measured NOT to need pairwise care
//!
//! `_capacity_in_bbox`'s `np.sum(region == 0)` reduces a **boolean/int8**
//! array, not a float array. Blocked-pairwise summation only changes a
//! result when float rounding is order-sensitive; boolean/integer addition
//! is exact and order-invariant. Measured directly: `np.sum(bool_array)`
//! vs a plain sequential Python `sum()` over the same array, sizes
//! 1/2/10/100/1000/10000/100000 — 0/7 mismatches. [`capacity_in_bbox`]
//! below sums a `&[i64]` sequentially with no pairwise-blocking logic.
//!
//! ## `world_to_grid` / clamp / degenerate-region check stay in Python
//!
//! `OccupancyGrid.world_to_grid` is a widely-used general-purpose method
//! (like `router_v6/occupancy_grid.py`'s own precedent for
//! `world_to_grid`/`grid_to_world` — see that module's Rust port notes);
//! it, the two per-axis clamps, the swap, and the degenerate-bbox check are
//! plain integer arithmetic with zero numpy involvement and are called only
//! twice per invocation (not a hot inner loop), so the Python wrapper keeps
//! them and hands this kernel only the already-clamped, already-sliced
//! region plus `cell_size` — the actual reduction that carries the
//! `np.sum` trap above.
//!
//! ## Cluster order is intentionally NOT bit-replicated
//!
//! The oracle's `_compute_conflict_clusters` traverses a `set[str]`
//! (`for neighbor in conflict[n]`), whose CPython iteration order is
//! salted per process (PEP 456) — the within-cluster element order is not
//! reproducible even against a second run of the *same* oracle. This
//! kernel instead builds clusters via a deterministic index-ascending
//! adjacency traversal (reproducible within and across processes — an
//! improvement over the status quo). The only place this could matter is
//! [`cluster_union_bbox`]'s NaN-poisoning fold (CPython/[`py_min`]/
//! [`py_max`] keep whichever operand a NaN comparison failed to unseat,
//! and that's order-dependent for the very first element only) — a case
//! that requires a NaN bbox coordinate, which `_net_bboxes_from_pcb` never
//! produces (see the oracle docstring). Every other observable output
//! (cluster count, cluster membership as a set, `max_routable_nets`'s
//! returned int, and every `demand_budget_summary` field except
//! `total_capacity_mm2`/`utilization`) is order-invariant by construction.

use std::collections::HashMap;

use pyo3::prelude::*;
use pyo3::types::PyModule;

use crate::pymath::{py_max, py_min};

// ---------------------------------------------------------------------------
// CPython 3.12 builtin `sum()` float path — Neumaier-compensated, NOT a
// naive left fold. Measured directly (this differential): a naive
// `areas.iter().sum()` diverges from Python's `sum(bbox_areas.values())`
// in the last ULP on ordinary random inputs (not just adversarial
// cancellation cases) -- e.g. `sum([23.02..., 477.16..., 340.30...,
// 402.55..., 406.99..., 128.24...])` is `296.3788240378778` via CPython's
// `sum()` vs `296.37882403787773` via naive left-to-right `+=`. Same
// algorithm as `physics_oracle.rs::overall_score` and
// `temper-geometry/area_sufficiency.rs::py_sum_neumaier`; transcribed
// locally rather than shared because both of those are `pub(crate)`/
// module-private by the same convention this crate already uses for
// `py_max2`/`py_min2`-shaped helpers (see `router_clearance.rs`).
// ---------------------------------------------------------------------------

fn py_sum_neumaier(values: &[f64]) -> f64 {
    let mut sum = 0.0_f64;
    let mut c = 0.0_f64;
    for &x in values {
        let t = sum + x;
        if sum.abs() >= x.abs() {
            c += (sum - t) + x;
        } else {
            c += (x - t) + sum;
        }
        sum = t;
    }
    sum + c
}

// ---------------------------------------------------------------------------
// np.clip — either-operand NaN-propagating min/max, NOT py_max/py_min
// ---------------------------------------------------------------------------

/// `np.maximum(a, b)`: NaN in *either* position poisons the result.
/// Different from [`py_max`], which keeps whichever argument a NaN
/// comparison failed to unseat (never poisons unconditionally).
#[inline]
fn np_maximum(a: f64, b: f64) -> f64 {
    if a.is_nan() || b.is_nan() {
        f64::NAN
    } else if a > b {
        a
    } else {
        b
    }
}

#[inline]
fn np_minimum(a: f64, b: f64) -> f64 {
    if a.is_nan() || b.is_nan() {
        f64::NAN
    } else if a < b {
        a
    } else {
        b
    }
}

/// `np.clip(x, lo, hi)`, implemented as `np.minimum(np.maximum(x, lo), hi)`
/// (numpy's own definition) — propagates NaN from `x`, `lo`, or `hi`.
#[inline]
fn np_clip(x: f64, lo: f64, hi: f64) -> f64 {
    np_minimum(np_maximum(x, lo), hi)
}

// ---------------------------------------------------------------------------
// _compute_conflict_clusters
// ---------------------------------------------------------------------------

/// `_compute_conflict_clusters`: pairwise bbox-overlap conflict graph,
/// connected components via DFS (a stack-based `queue.pop()` from the
/// oracle, despite its own comment calling it "BFS").
///
/// `names`/`bboxes` are parallel arrays in the caller's original dict
/// order (Python dict iteration is insertion-ordered, never hash-salted —
/// only the *within-cluster* traversal below touches a hash-salted `set`,
/// see the module doc).
pub fn conflict_clusters(
    names: &[String],
    bboxes: &[(f64, f64, f64, f64)],
    overlap_threshold: f64,
) -> Vec<Vec<String>> {
    let n = names.len();
    if n <= 1 {
        return if n == 1 { vec![vec![names[0].clone()]] } else { vec![] };
    }

    // Per-net area, `max((x2-x1)*(y2-y1), 0.0)` via py_max (area first,
    // 0.0 second — a NaN area survives, matching `max(area, 0.0)`).
    let areas: Vec<f64> = bboxes.iter().map(|&(x1, y1, x2, y2)| py_max((x2 - x1) * (y2 - y1), 0.0)).collect();

    // Adjacency built in ascending (i, j) discovery order — deterministic,
    // unlike the oracle's `set[str]`.
    let mut adjacency: Vec<Vec<usize>> = vec![Vec::new(); n];
    for i in 0..n {
        let (ax1, ay1, ax2, ay2) = bboxes[i];
        let area_a = areas[i];
        if area_a <= 0.0 {
            continue;
        }
        for j in (i + 1)..n {
            let (bx1, by1, bx2, by2) = bboxes[j];
            let area_b = areas[j];
            if area_b <= 0.0 {
                continue;
            }
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

    // DFS connected components, index-ascending outer scan (mirrors the
    // oracle's `for net in nets:` — dict/list order, already deterministic).
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
            for &neighbor in &adjacency[idx] {
                if !visited[neighbor] {
                    stack.push(neighbor);
                }
            }
        }
        clusters.push(cluster_idx.into_iter().map(|i| names[i].clone()).collect());
    }

    clusters
}

#[pyfunction]
pub fn resource_bound_conflict_clusters_py(
    net_names: Vec<String>,
    bboxes: Vec<(f64, f64, f64, f64)>,
    overlap_threshold: f64,
) -> Vec<Vec<String>> {
    conflict_clusters(&net_names, &bboxes, overlap_threshold)
}

// ---------------------------------------------------------------------------
// _cluster_union_bbox
// ---------------------------------------------------------------------------

/// `_cluster_union_bbox`: 4 independent `min`/`max` folds (one per bbox
/// coordinate) over the cluster's member bboxes, each starting from the
/// FIRST element in `cluster` order and updating on a strict `<`/`>` win
/// only — CPython's builtin `min(iterable)`/`max(iterable)` semantics,
/// replicated by folding [`py_min`]/[`py_max`] left-to-right.
pub fn cluster_union_bbox(
    cluster: &[String],
    names: &[String],
    bboxes: &[(f64, f64, f64, f64)],
) -> (f64, f64, f64, f64) {
    if cluster.is_empty() {
        return (0.0, 0.0, 0.0, 0.0);
    }
    let lookup: HashMap<&str, (f64, f64, f64, f64)> =
        names.iter().map(|s| s.as_str()).zip(bboxes.iter().copied()).collect();

    let member_bboxes: Vec<(f64, f64, f64, f64)> =
        cluster.iter().map(|n| *lookup.get(n.as_str()).unwrap_or(&(0.0, 0.0, 0.0, 0.0))).collect();

    let x1 = member_bboxes[1..].iter().fold(member_bboxes[0].0, |acc, b| py_min(acc, b.0));
    let y1 = member_bboxes[1..].iter().fold(member_bboxes[0].1, |acc, b| py_min(acc, b.1));
    let x2 = member_bboxes[1..].iter().fold(member_bboxes[0].2, |acc, b| py_max(acc, b.2));
    let y2 = member_bboxes[1..].iter().fold(member_bboxes[0].3, |acc, b| py_max(acc, b.3));
    (x1, y1, x2, y2)
}

#[pyfunction]
pub fn resource_bound_cluster_union_bbox_py(
    cluster: Vec<String>,
    net_names: Vec<String>,
    bboxes: Vec<(f64, f64, f64, f64)>,
) -> (f64, f64, f64, f64) {
    cluster_union_bbox(&cluster, &net_names, &bboxes)
}

// ---------------------------------------------------------------------------
// _capacity_in_bbox — just the np.sum reduction (see module doc)
// ---------------------------------------------------------------------------

/// `int(np.sum(region == 0)) * cell_size * cell_size`, where `region` is
/// the already-clamped, already-sliced sub-array the Python wrapper
/// extracts via `grid.grid[gy1:gy2+1, gx1:gx2+1]`.
pub fn capacity_in_bbox(region: &[i64], cell_size: f64) -> f64 {
    let free_cells = region.iter().filter(|&&v| v == 0).count() as f64;
    // Oracle computes `cell_area = cell_size * cell_size` FIRST, then
    // `free_cells * cell_area` -- grouping matters for f64 (non-associative);
    // `free_cells * cell_size * cell_size` (left-to-right) is a DIFFERENT,
    // measured-diverging computation in the last ULP.
    let cell_area = cell_size * cell_size;
    free_cells * cell_area
}

#[pyfunction]
pub fn resource_bound_capacity_in_bbox_py(region: Vec<i64>, cell_size: f64) -> f64 {
    capacity_in_bbox(&region, cell_size)
}

// ---------------------------------------------------------------------------
// _compute_fill_factor
// ---------------------------------------------------------------------------

/// `_compute_fill_factor`: `trace_width / sqrt(mean(areas))`, clamped to
/// `[0.01, 1.0]` via `np.clip` (see module doc for the NaN trap).
/// `areas` must be in the caller's original dict-value order: the mean's
/// `sum()` is CPython 3.12's Neumaier-compensated float summation
/// ([`py_sum_neumaier`], NOT a naive left fold — measured to diverge in
/// the last ULP on ordinary random inputs, see that function's doc), which
/// is still order-sensitive; dict iteration order is deterministic
/// (insertion order), so this is a bit-exact reproduction, not merely a
/// value-equivalent one.
pub fn compute_fill_factor(trace_width: f64, areas: &[f64]) -> f64 {
    if areas.is_empty() {
        return 0.5;
    }
    let sum = py_sum_neumaier(areas);
    let avg_area = sum / (areas.len() as f64);
    if avg_area <= 0.0 {
        return 0.5;
    }
    let sqrt_area = avg_area.sqrt();
    let ff = trace_width / sqrt_area;
    np_clip(ff, 0.01, 1.0)
}

#[pyfunction]
pub fn resource_bound_compute_fill_factor_py(trace_width: f64, areas: Vec<f64>) -> f64 {
    compute_fill_factor(trace_width, &areas)
}

// ---------------------------------------------------------------------------
// Module registration
// ---------------------------------------------------------------------------

pub fn register(module: &Bound<'_, PyModule>) -> PyResult<()> {
    module.add_function(wrap_pyfunction!(resource_bound_conflict_clusters_py, module)?)?;
    module.add_function(wrap_pyfunction!(resource_bound_cluster_union_bbox_py, module)?)?;
    module.add_function(wrap_pyfunction!(resource_bound_capacity_in_bbox_py, module)?)?;
    module.add_function(wrap_pyfunction!(resource_bound_compute_fill_factor_py, module)?)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// Unit tests (Rust-side; the Python differential is the primary proof)
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn np_clip_propagates_nan_from_either_operand() {
        assert!(np_clip(f64::NAN, 0.01, 1.0).is_nan());
        assert!(np_clip(0.5, f64::NAN, 1.0).is_nan());
        assert!(np_clip(0.5, 0.01, f64::NAN).is_nan());
    }

    #[test]
    fn np_clip_matches_measured_values() {
        assert_eq!(np_clip(0.005, 0.01, 1.0), 0.01);
        assert_eq!(np_clip(0.5, 0.01, 1.0), 0.5);
        assert_eq!(np_clip(1.5, 0.01, 1.0), 1.0);
        assert_eq!(np_clip(-1.0, 0.01, 1.0), 0.01);
    }

    #[test]
    fn conflict_clusters_empty_and_single() {
        assert_eq!(conflict_clusters(&[], &[], 0.1), Vec::<Vec<String>>::new());
        let names = vec!["A".to_string()];
        let bboxes = vec![(0.0, 0.0, 1.0, 1.0)];
        assert_eq!(conflict_clusters(&names, &bboxes, 0.1), vec![vec!["A".to_string()]]);
    }

    #[test]
    fn conflict_clusters_no_overlap_are_singleton_clusters() {
        let names = vec!["A".to_string(), "B".to_string(), "C".to_string()];
        let bboxes = vec![(0.0, 0.0, 5.0, 5.0), (10.0, 10.0, 15.0, 15.0), (20.0, 20.0, 25.0, 25.0)];
        let clusters = conflict_clusters(&names, &bboxes, 0.1);
        assert_eq!(clusters.len(), 3);
    }

    #[test]
    fn conflict_clusters_full_overlap_is_one_cluster() {
        let names = vec!["A".to_string(), "B".to_string(), "C".to_string()];
        let bboxes = vec![(0.0, 0.0, 10.0, 10.0), (1.0, 1.0, 9.0, 9.0), (2.0, 2.0, 8.0, 8.0)];
        let clusters = conflict_clusters(&names, &bboxes, 0.1);
        assert_eq!(clusters.len(), 1);
        let mut members = clusters[0].clone();
        members.sort();
        assert_eq!(members, vec!["A".to_string(), "B".to_string(), "C".to_string()]);
    }

    #[test]
    fn conflict_clusters_chain_merges() {
        let names = vec!["A".to_string(), "B".to_string(), "C".to_string()];
        let bboxes = vec![(0.0, 0.0, 5.0, 5.0), (3.0, 3.0, 8.0, 8.0), (6.0, 6.0, 11.0, 11.0)];
        let clusters = conflict_clusters(&names, &bboxes, 0.1);
        assert_eq!(clusters.len(), 1);
    }

    #[test]
    fn conflict_clusters_area_nan_keeps_first_arg_via_py_max() {
        // area = NaN (a degenerate NaN bbox): max(NaN, 0.0) keeps NaN, so
        // area_a <= 0.0 is False (NaN <= 0.0 is False) -- the net still
        // participates rather than being skipped like a truly-zero-area net.
        let names = vec!["A".to_string(), "B".to_string()];
        let bboxes = vec![(f64::NAN, 0.0, f64::NAN, 1.0), (0.0, 0.0, 1.0, 1.0)];
        // Must not panic.
        let _ = conflict_clusters(&names, &bboxes, 0.1);
    }

    #[test]
    fn cluster_union_bbox_empty_cluster_is_zero_bbox() {
        assert_eq!(cluster_union_bbox(&[], &[], &[]), (0.0, 0.0, 0.0, 0.0));
    }

    #[test]
    fn cluster_union_bbox_matches_manual_min_max() {
        let names = vec!["A".to_string(), "B".to_string(), "C".to_string()];
        let bboxes = vec![(0.0, 5.0, 10.0, 15.0), (-5.0, 2.0, 3.0, 20.0), (1.0, -1.0, 8.0, 9.0)];
        let cluster = names.clone();
        let got = cluster_union_bbox(&cluster, &names, &bboxes);
        assert_eq!(got, (-5.0, -1.0, 10.0, 20.0));
    }

    #[test]
    fn cluster_union_bbox_first_nan_poisons_like_python_min() {
        // Cluster order [A, B]; A's x1 is NaN and A is FIRST -> x1 result
        // must stay NaN (py_min keeps the running best unless the new
        // value is strictly less, and NaN comparisons are always False).
        let names = vec!["A".to_string(), "B".to_string()];
        let bboxes = vec![(f64::NAN, 0.0, 1.0, 1.0), (2.0, 2.0, 3.0, 3.0)];
        let cluster = vec!["A".to_string(), "B".to_string()];
        let got = cluster_union_bbox(&cluster, &names, &bboxes);
        assert!(got.0.is_nan(), "expected x1 to stay NaN, got {}", got.0);

        // Reversed cluster order [B, A]: B is first (not NaN), A's NaN
        // comes second and never dislodges B's finite x1.
        let cluster_rev = vec!["B".to_string(), "A".to_string()];
        let got_rev = cluster_union_bbox(&cluster_rev, &names, &bboxes);
        assert_eq!(got_rev.0, 2.0, "expected x1=2.0 (NaN arrives second, ignored)");
    }

    #[test]
    fn capacity_in_bbox_counts_zero_cells() {
        let region = vec![0, 1, 0, 0, -1, 0];
        // 4 zeros * cell_size^2 (2.0^2 = 4.0) = 16.0
        assert_eq!(capacity_in_bbox(&region, 2.0), 16.0);
    }

    #[test]
    fn capacity_in_bbox_empty_region_is_zero() {
        assert_eq!(capacity_in_bbox(&[], 1.0), 0.0);
    }

    #[test]
    fn capacity_in_bbox_all_free() {
        let region = vec![0; 121];
        assert_eq!(capacity_in_bbox(&region, 1.0), 121.0);
    }

    #[test]
    fn compute_fill_factor_empty_returns_half() {
        assert_eq!(compute_fill_factor(0.2, &[]), 0.5);
    }

    #[test]
    fn py_sum_neumaier_matches_measured_cpython_312_value() {
        // Measured against this repo's CPython 3.12.12: sum() on this
        // exact sequence is 296.3788240378778, while a naive left-to-right
        // fold gives 296.37882403787773 -- a real, not hypothetical,
        // divergence on ordinary (non-adversarial) random floats.
        let vals = [
            23.025289715282675,
            477.1625760836891,
            340.3015468079908,
            402.54761019435176,
            406.99931766284374,
            128.23660376310846,
        ];
        assert_eq!(py_sum_neumaier(&vals), 296.3788240378778);
        let naive: f64 = vals.iter().sum();
        assert_ne!(naive, 296.3788240378778, "naive fold should NOT match -- otherwise this test proves nothing");
    }

    #[test]
    fn py_sum_neumaier_classic_discriminator() {
        // Naive accumulation gives 0.0 (the 1.0 is lost to rounding once
        // added to 1e16, then the -1e16 cancels the big term exactly);
        // compensated summation recovers the 1.0.
        assert_eq!(py_sum_neumaier(&[1e16, 1.0, -1e16]), 1.0);
    }

    #[test]
    fn compute_fill_factor_matches_formula() {
        // areas = [100.0, 400.0] -> avg=250.0, sqrt=15.8113883...,
        // ff = 0.1 / sqrt(250) = 0.0063245553... -> clipped to 0.01.
        let got = compute_fill_factor(0.1, &[100.0, 400.0]);
        assert!((got - 0.01).abs() < 1e-12, "got {got}");
    }

    #[test]
    fn compute_fill_factor_increases_with_trace_width() {
        let areas = [100.0, 400.0];
        let small = compute_fill_factor(0.1, &areas);
        let large = compute_fill_factor(0.5, &areas);
        assert!(large > small);
        assert!((0.01..=1.0).contains(&small));
        assert!((0.01..=1.0).contains(&large));
    }

    #[test]
    fn compute_fill_factor_nan_avg_area_falls_through_to_nan_clip() {
        // avg_area = NaN -> `avg_area <= 0.0` is False (does NOT
        // short-circuit to 0.5) -> sqrt(NaN)=NaN -> ff=NaN -> np_clip(NaN,..)=NaN.
        let got = compute_fill_factor(0.2, &[f64::NAN]);
        assert!(got.is_nan(), "expected NaN to survive the fall-through, got {got}");
    }
}
