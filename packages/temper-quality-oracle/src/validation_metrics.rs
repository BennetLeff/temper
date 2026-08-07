//! Validation placement-metric kernels (Wave 4) — the hot `O(n^2)`/`O(n)`
//! numeric loops of `temper_placer/validation/metrics.py`.
//!
//! The Python module keeps its public API (`compute_metrics`,
//! `PlacementMetrics`) and does the object plumbing: `Netlist`/`Board`
//! attribute reads, `pin_world_position_at` pin-geometry resolution,
//! dict/zone lookups, `KeyError` handling. It hands these functions flat
//! `f64`/`f32`/`bool` slices, already resolved in the oracle's own
//! iteration order (load-bearing for the order-sensitive folds below).
//!
//! Pinned bit-for-bit against
//! `packages/temper-placer/tests/validation/_validation_metrics_py_oracle.py`
//! (a verbatim copy of the pre-migration module) by
//! `test_validation_metrics_rust_differential.py`.
//!
//! ## Scope
//!
//! Ports `_compute_overlap_metrics`, `_compute_clearance_metrics`,
//! `_compute_wirelength_metrics`'s numeric fold, and
//! `_compute_distribution_metrics`. Deliberately NOT ported (see
//! `validation/metrics.py`'s module docstring for the full triage note):
//!
//! - `_compute_boundary_metrics` / `_compute_keepout_metrics`: both call
//!   `get_rotated_bounds` per component, already a Rust FFI crossing
//!   (`temper-geometry`); the remaining work per component is a handful of
//!   subtractions and a 4-way `max` — an `O(n)` loop, not worth a second
//!   FFI surface, and restructuring the call site to batch the rotated
//!   bounds first would touch `compute_metrics`' shared orchestration for
//!   marginal gain.
//! - `_compute_zone_metrics`: dominated by `board.get_zone(name)` dict
//!   lookup and `KeyError`-as-control-flow — domain glue, not compute.
//! - `_compute_wirelength_metrics`'s pin-position resolution
//!   (`pin_world_position_at`, `netlist.get_component_index`,
//!   `try/except (KeyError, IndexError)`) stays in Python; only the HPWL
//!   fold (given already-resolved per-net HPWL values and weights) is
//!   ported here.
//!
//! ## Bit-exactness discipline (Wave 4 catalog entries)
//!
//! - **B5 — CPython `max`/`min` keep the first argument on ties/NaN.**
//!   `worst_overlap = max(worst_overlap, overlap_amount)`,
//!   `min_hv_lv = min(min_hv_lv, dist)`,
//!   `max_net_length = max(max_net_length, hpwl)` all route through
//!   [`crate::placement_metrics::py_max2`] /
//!   [`crate::placement_metrics::py_min2`] — never `f64::max`/`min`, which
//!   follow IEEE `maxNum`/`minNum` and discard NaN unconditionally
//!   regardless of argument position.
//! - **B12 — CPython 3.12's compensated `sum()`.**
//!   `avg_net_length = sum(net_lengths) / len(net_lengths)` uses the
//!   *builtin* `sum()`, which CPython 3.12 implements as Neumaier
//!   (improved Kahan-Babuska) compensated summation, not naive
//!   left-to-right addition. Measured on this repo's CPython 3.12.12: a
//!   naive `+=` fold disagrees with `sum()` on 920/2000 random
//!   wirelength-shaped float lists. [`wirelength_metrics`] routes the
//!   average through [`crate::placement_metrics::py_builtin_sum`];
//!   `total_wirelength`'s accumulator is a literal `+=` loop in the
//!   oracle, so it stays naive here too — using the wrong strategy for
//!   either is a silent 1-ulp bug (same trap `placement_metrics.rs`
//!   documents for `metrics/quality.py`).
//! - **New class (recorded by this migration) — NEP-50 float32
//!   narrowing, not promotion.** `_compute_distribution_metrics` has no
//!   float64 array anchor: `state.positions` (every factory in
//!   `core/state.py` hardcodes `dtype=np.float32`) and
//!   `netlist.get_bounds_array()` (hardcodes `dtype=np.float32` too) are
//!   BOTH float32. So `np.sum(widths * heights)`, `np.mean(positions[:,
//!   k])`, and the final `np.mean(distances_from_com)` all run their
//!   pairwise-summation reduction in float32 arithmetic, not float64 —
//!   see [`numpy_pairwise_sum_f32`]. Measured: a naive whole-computation-
//!   in-float64 reimplementation disagrees with the real (narrowed)
//!   computation for every one of 13 tested `n` in `[1, 1000]` (0/13
//!   agree). This is the mirror image of `geometric_metrics.rs`'s finding
//!   (float64 widening) and the same shape as `thermal_edges.rs`'s
//!   (float32 narrowing) — this module's inputs are the
//!   `validation/metrics.py` ones, distinct from either.
//! - **Measured non-trap — array `** 2` IS `x * x` here.** Unlike the
//!   `x ** 2`-is-libm-`pow` trap documented for plain CPython float
//!   scalars elsewhere in this crate (`placement_metrics.rs`'s B1/B7),
//!   `(positions[:, k] - com) ** 2` is numpy ARRAY exponentiation — a
//!   ufunc call, not `float.__pow__`. Measured over 200,000 random
//!   float32 samples: `arr ** 2` and `arr * arr` are bit-identical (0
//!   mismatches), and `arr ** 0.5` and `np.sqrt(arr)` are bit-identical
//!   too (0/200,000 mismatches) — numpy's float ufunc loops special-case
//!   small integer/half exponents to multiplication/sqrt internally, so
//!   this kernel uses plain `*`/`.sqrt()`, not
//!   [`crate::placement_metrics::py_pow`]. Do not assume this
//!   generalizes to scalar `**` elsewhere in this codebase — it does not
//!   (see `placement_metrics.rs`, `geometric_metrics.rs`).
//! - **B5 (XOR simplification) — HV/LV classification.** The oracle's
//!   `is_hv_lv = (hv_i and not hv_j) or (hv_j and not hv_i)` is exactly
//!   `hv_i != hv_j` (XOR) — a boolean-algebra identity, not a
//!   floating-point concern, so [`clearance_metrics`] takes a precomputed
//!   `is_hv: &[bool]` and XORs directly.

use crate::placement_metrics::{py_builtin_sum, py_max2, py_min2};

/// numpy's `PW_BLOCKSIZE` — identical across dtypes.
const PW_BLOCKSIZE: usize = 128;

/// Replicates `numpy.sum`/`numpy.mean`'s reduction over a contiguous
/// float32 array, bit-for-bit — the float32 sibling of
/// [`crate::placement_metrics::numpy_pairwise_sum`] (float64). See this
/// module's doc comment for why `validation/metrics.py`'s distribution
/// metrics need the float32 variant specifically (no float64 anchor —
/// narrows, doesn't promote).
pub fn numpy_pairwise_sum_f32(a: &[f32]) -> f32 {
    let n = a.len();
    if n < 8 {
        let mut res = 0.0_f32;
        for &v in a {
            res += v;
        }
        res
    } else if n <= PW_BLOCKSIZE {
        let mut r = [a[0], a[1], a[2], a[3], a[4], a[5], a[6], a[7]];
        let mut i = 8;
        let body_end = n - (n % 8);
        while i < body_end {
            for (j, acc) in r.iter_mut().enumerate() {
                *acc += a[i + j];
            }
            i += 8;
        }
        let mut res = ((r[0] + r[1]) + (r[2] + r[3])) + ((r[4] + r[5]) + (r[6] + r[7]));
        while i < n {
            res += a[i];
            i += 1;
        }
        res
    } else {
        let mut n2 = n / 2;
        n2 -= n2 % 8;
        numpy_pairwise_sum_f32(&a[..n2]) + numpy_pairwise_sum_f32(&a[n2..])
    }
}

/// Ports `_compute_overlap_metrics`.
///
/// `distances` is the flattened row-major `n x n` pairwise-distance
/// matrix (from `compute_pairwise_distances`, already Rust); only the
/// upper triangle (`i < j`) is read, matching the oracle's loop bounds.
///
/// Returns `(overlap_count, total_overlap_area, worst_overlap)`.
pub fn overlap_metrics(distances: &[f64], n: usize) -> (i64, f64, f64) {
    let mut overlap_count: i64 = 0;
    let mut total_overlap = 0.0_f64;
    let mut worst_overlap = 0.0_f64;

    for i in 0..n {
        for j in (i + 1)..n {
            let dist = distances[i * n + j];
            if dist < 0.0 {
                let overlap_amount = -dist;
                overlap_count += 1;
                total_overlap += overlap_amount;
                worst_overlap = py_max2(worst_overlap, overlap_amount);
            }
        }
    }

    (overlap_count, total_overlap, worst_overlap)
}

/// Ports `_compute_clearance_metrics`.
///
/// `is_hv[i]` mirrors `netlist.components[i].net_class == "HighVoltage"`
/// (a string comparison — resolved caller-side, glue not compute).
///
/// `min_clearance = 0.2` is the oracle's own hardcoded constant (not a
/// caller parameter) — kept hardcoded here to match.
///
/// Returns `(clearance_violations, hv_lv_violations, min_hv_lv_clearance)`.
pub fn clearance_metrics(
    distances: &[f64],
    n: usize,
    is_hv: &[bool],
    hv_lv_clearance: f64,
) -> (i64, i64, f64) {
    const MIN_CLEARANCE: f64 = 0.2;

    let mut clearance_violations: i64 = 0;
    let mut hv_lv_violations: i64 = 0;
    let mut min_hv_lv = f64::INFINITY;

    for i in 0..n {
        for j in (i + 1)..n {
            let dist = distances[i * n + j];
            let is_hv_lv = is_hv[i] != is_hv[j];

            if is_hv_lv {
                min_hv_lv = py_min2(min_hv_lv, dist);
                if dist < hv_lv_clearance {
                    hv_lv_violations += 1;
                    clearance_violations += 1;
                }
            } else if dist < MIN_CLEARANCE {
                clearance_violations += 1;
            }
        }
    }

    (clearance_violations, hv_lv_violations, min_hv_lv)
}

/// Ports `_compute_wirelength_metrics`'s numeric fold.
///
/// `hpwl[k]` / `weights[k]` are the already-resolved per-net HPWL value
/// (`(max(xs)-min(xs)) + (max(ys)-min(ys))`) and `net.weight`, in
/// `netlist.nets` iteration order, for every net that survived the
/// oracle's `len(pin_positions) < 2` filter. Pin-position resolution is
/// domain geometry (glue), resolved Python-side before this call.
///
/// Returns `(total_wirelength, max_net_length, avg_net_length)`.
pub fn wirelength_metrics(hpwl: &[f64], weights: &[f64]) -> (f64, f64, f64) {
    let mut total_wirelength = 0.0_f64;
    let mut max_net_length = 0.0_f64;

    for (i, &h) in hpwl.iter().enumerate() {
        let weighted_hpwl = h * weights[i];
        total_wirelength += weighted_hpwl;
        max_net_length = py_max2(max_net_length, h);
    }

    let avg_net_length = if hpwl.is_empty() {
        0.0
    } else {
        py_builtin_sum(hpwl) / (hpwl.len() as f64)
    };

    (total_wirelength, max_net_length, avg_net_length)
}

/// Ports `_compute_distribution_metrics`.
///
/// `positions_x`/`positions_y`/`widths`/`heights` are float32 (see this
/// module's doc comment — NEP-50 narrowing, not promotion).
/// `board_width`/`board_height` are `Board.width`/`.height`, plain Python
/// floats (float64) — `board_area` is a genuine float64 multiplication.
///
/// Returns `(utilization, com_x, com_y, spread_score)`.
pub fn distribution_metrics(
    positions_x: &[f32],
    positions_y: &[f32],
    widths: &[f32],
    heights: &[f32],
    board_width: f64,
    board_height: f64,
) -> (f64, f64, f64, f64) {
    let n = positions_x.len();

    // Utilization: np.sum(widths * heights) — float32 elementwise
    // product, then float32 pairwise sum, widened only at the end.
    let areas: Vec<f32> = widths.iter().zip(heights).map(|(&w, &h)| w * h).collect();
    let total_component_area = numpy_pairwise_sum_f32(&areas) as f64;
    let board_area = board_width * board_height;
    let utilization = total_component_area / board_area;

    // Center of mass: np.mean over a float32 array — pairwise sum divided
    // by n, both in float32.
    let com_x_f32 = numpy_pairwise_sum_f32(positions_x) / (n as f32);
    let com_y_f32 = numpy_pairwise_sum_f32(positions_y) / (n as f32);
    let com_x = com_x_f32 as f64;
    let com_y = com_y_f32 as f64;

    // Spread score: `positions[:, k] - com_x` — com_x is a weak NEP-50
    // Python float meeting an ACTUAL float32 array, so it narrows to
    // float32 FIRST, then the subtraction (and everything after) runs in
    // float32. `** 2` is `x * x` here (measured — see module doc); sqrt
    // is IEEE-correctly-rounded, bit-identical to `np.sqrt`.
    let mut dists: Vec<f32> = Vec::with_capacity(n);
    for i in 0..n {
        let dx = positions_x[i] - com_x_f32;
        let dy = positions_y[i] - com_y_f32;
        dists.push((dx * dx + dy * dy).sqrt());
    }
    let spread_score = (numpy_pairwise_sum_f32(&dists) / (n as f32)) as f64;

    (utilization, com_x, com_y, spread_score)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn overlap_metrics_no_overlap_is_zero() {
        let (count, total, worst) = overlap_metrics(&[0.0], 1);
        assert_eq!(count, 0);
        assert_eq!(total, 0.0);
        assert_eq!(worst, 0.0);
    }

    #[test]
    fn overlap_metrics_counts_and_sums() {
        // 3 components: (0,1) overlaps -1.5, (0,2) no overlap 2.0,
        // (1,2) overlaps -0.5. Row-major n=3.
        #[rustfmt::skip]
        let d = [
            0.0, -1.5, 2.0,
            0.0, 0.0, -0.5,
            0.0, 0.0, 0.0,
        ];
        let (count, total, worst) = overlap_metrics(&d, 3);
        assert_eq!(count, 2);
        assert!((total - 2.0).abs() < 1e-12);
        assert!((worst - 1.5).abs() < 1e-12);
    }

    #[test]
    fn overlap_metrics_exact_zero_is_not_overlap() {
        // `dist < 0` strictly — a touching pair (dist == 0.0) must not count.
        let (count, total, worst) = overlap_metrics(&[0.0, 0.0, 0.0, 0.0], 2);
        assert_eq!(count, 0);
        assert_eq!(total, 0.0);
        assert_eq!(worst, 0.0);
    }

    #[test]
    fn clearance_metrics_xor_classification() {
        #[rustfmt::skip]
        let d = [0.0, 5.0, 0.0, 0.0];
        let (clearance_v, hv_lv_v, min_hv_lv) = clearance_metrics(&d, 2, &[true, false], 10.0);
        assert_eq!(clearance_v, 1);
        assert_eq!(hv_lv_v, 1);
        assert_eq!(min_hv_lv, 5.0);
    }

    #[test]
    fn clearance_metrics_both_hv_uses_min_clearance_not_hv_lv() {
        // Both HV -> not is_hv_lv -> falls to `elif dist < min_clearance`.
        #[rustfmt::skip]
        let d = [0.0, 0.1, 0.0, 0.0];
        let (clearance_v, hv_lv_v, min_hv_lv) = clearance_metrics(&d, 2, &[true, true], 10.0);
        assert_eq!(clearance_v, 1); // 0.1 < 0.2 default min_clearance
        assert_eq!(hv_lv_v, 0);
        assert_eq!(min_hv_lv, f64::INFINITY);
    }

    #[test]
    fn wirelength_metrics_empty_is_all_zero() {
        let (total, max_len, avg) = wirelength_metrics(&[], &[]);
        assert_eq!(total, 0.0);
        assert_eq!(max_len, 0.0);
        assert_eq!(avg, 0.0);
    }

    #[test]
    fn wirelength_metrics_weighted_total_and_avg() {
        let (total, max_len, avg) = wirelength_metrics(&[10.0, 20.0], &[1.0, 2.0]);
        assert!((total - 50.0).abs() < 1e-12); // 10*1 + 20*2
        assert_eq!(max_len, 20.0);
        assert!((avg - 15.0).abs() < 1e-12);
    }

    #[test]
    fn distribution_metrics_single_component() {
        let (util, com_x, com_y, spread) =
            distribution_metrics(&[10.0], &[20.0], &[4.0], &[2.0], 100.0, 100.0);
        assert!((util - 8.0 / 10000.0).abs() < 1e-12);
        assert_eq!(com_x, 10.0);
        assert_eq!(com_y, 20.0);
        assert_eq!(spread, 0.0); // single point is its own center of mass
    }

    #[test]
    fn pairwise_sum_f32_matches_naive_below_eight() {
        let a: Vec<f32> = vec![1.5, 2.25, 3.75, 0.125];
        let mut naive = 0.0_f32;
        for &v in &a {
            naive += v;
        }
        assert_eq!(numpy_pairwise_sum_f32(&a).to_bits(), naive.to_bits());
    }

    #[test]
    fn pairwise_sum_f32_recurses_above_blocksize() {
        let a: Vec<f32> = (0..300).map(|i| (i as f32) * 0.37 - 12.0).collect();
        let mut n2 = a.len() / 2;
        n2 -= n2 % 8;
        let expected = numpy_pairwise_sum_f32(&a[..n2]) + numpy_pairwise_sum_f32(&a[n2..]);
        assert_eq!(numpy_pairwise_sum_f32(&a).to_bits(), expected.to_bits());
    }

    #[test]
    fn pairwise_sum_f32_empty_is_zero() {
        assert_eq!(numpy_pairwise_sum_f32(&[]), 0.0);
    }
}
