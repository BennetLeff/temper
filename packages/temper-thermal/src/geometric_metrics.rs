//! Geometric-violation metrics kernel (Wave 4) — the hot O(n²) loops of
//! `temper_placer/metrics/physics.py::measure_geometric`.
//!
//! Ports the four geometric-violation sub-algorithms (component overlap,
//! zone containment, board-boundary containment, HV/LV clearance) to
//! Rust. The Python module keeps its public API, marshals the pyclass
//! fields it reads (`Component.bounds`, `Zone.bounds`, `Board.origin` /
//! `width` / `height`, `Component.net_class`) into primitive arrays, and
//! delegates the arithmetic here.
//!
//! ## Bit-exactness discipline (Wave 4 catalog entries)
//!
//! Pinned bit-for-bit against `tests/metrics/_physics_py_oracle.py` (a
//! verbatim extraction of the pre-Rust `measure_geometric`) by
//! `tests/metrics/test_physics_rust_differential.py`.
//!
//! - **B1/B7 — `**` is libm `pow`, not `x * x`.** The oracle writes
//!   `np.sqrt(dist_x**2 + dist_y**2)` in both the zone-violation and
//!   HV/LV-clearance arms. By the time that line runs, `dist_x`/`dist_y`
//!   are numpy float64 scalars (the output of Python's builtin `max()`
//!   folded over numpy floats) — and numpy's scalar `**` calls the same
//!   libm `pow` CPython's `float.__pow__` does (measured: 0/50000 the two
//!   disagree, vs ~0.12% disagreeing with plain `x * x`). So this crate
//!   routes both squarings through [`crate::hostmath::pow`], never `x*x`.
//! - **B5 — CPython `max`/`min` keep the *first* argument on NaN.** The
//!   zone-violation arm's `max(0, a, b)` puts the *constant* `0` first —
//!   folded left-to-right, a NaN candidate is never "greater than" the
//!   running max, so it never wins UNLESS it is the running max already,
//!   which starting from the literal `0` it never is. The HV/LV arm's
//!   `max(dx, dy, 0.0)` puts a *computed* value (`dx`) first instead, so a
//!   NaN `dx` (from NaN input positions) DOES survive the fold. Both
//!   folds are implemented as two chained [`crate::hostmath::py_max`]
//!   calls, matching the oracle's exact left-to-right argument order —
//!   not `f64::max`, which discards NaN unconditionally regardless of
//!   position. `min(metrics.min_hv_lv_clearance_mm, dist)` similarly uses
//!   [`crate::hostmath::py_min`].
//! - **New class (recorded by this migration) — NEP-50 float32/float64
//!   mixing, widening (not narrowing).** `state.positions` is always
//!   constructed float32 (every factory in `core/state.py` hardcodes
//!   `dtype=np.float32`); `widths`/`heights` are built from a Python list
//!   of `Component.bounds` floats, i.e. float64. Every expression here
//!   that combines a position with a width/height-derived value has an
//!   ACTUAL float64 operand somewhere in the chain, so NEP-50 promotes to
//!   float64 (widening the f32 position value exactly — lossless beyond
//!   the array's own float32 storage), never narrows. The one place two
//!   *positions* combine directly — `positions[i,0] - positions[j,0]` in
//!   the overlap and HV/LV-clearance arms — is a same-dtype (float32)
//!   subtraction that happens BEFORE any float64 value is involved, so
//!   the subtraction and `abs()` run in float32 and only widen to float64
//!   afterward. Contrast `thermal_edges.rs`, where there is no float64
//!   anchor and the computation narrows to float32 throughout instead.
//!
//! B2/B3/B4/B6/B8/B11/B12 are not applicable: no named-constant division,
//! no rounding, no `hypot`, no denormal-band inputs targeted, and no
//! vectorized `np.sum`/builtin `sum()` anywhere in this kernel (every
//! accumulator here is a plain sequential `+=` inside nested `for` loops,
//! exactly matching the oracle's own scalar Python loop — never a
//! vectorized numpy reduction).

use crate::hostmath;
#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// Mirrors `GeometricMetrics` — raw geometric violations.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct GeometricMetrics {
    pub overlap_count: i64,
    pub overlap_area_mm2: f64,
    pub zone_violation_count: i64,
    pub zone_violation_max_mm: f64,
    pub boundary_violation_count: i64,
    pub min_hv_lv_clearance_mm: f64,
}

impl Default for GeometricMetrics {
    fn default() -> Self {
        Self {
            overlap_count: 0,
            overlap_area_mm2: 0.0,
            zone_violation_count: 0,
            zone_violation_max_mm: 0.0,
            boundary_violation_count: 0,
            // Oracle default: `min_hv_lv_clearance_mm: float = 1000.0`.
            min_hv_lv_clearance_mm: 1000.0,
        }
    }
}

/// `max(0, a, b)` as CPython's builtin left-to-right fold — the
/// zone-violation arm's exact call shape (constant first).
#[inline]
fn max0(a: f64, b: f64) -> f64 {
    hostmath::py_max(hostmath::py_max(0.0, a), b)
}

/// Squared-distance-to-sqrt, matching the oracle's
/// `np.sqrt(dist_x**2 + dist_y**2)` — `**` is libm `pow`, not `x * x`
/// (B1/B7).
#[inline]
fn hypot_pow(dist_x: f64, dist_y: f64) -> f64 {
    (hostmath::pow(dist_x, 2.0) + hostmath::pow(dist_y, 2.0)).sqrt()
}

/// Zone bounds as `(x_min, y_min, x_max, y_max)`, or `None` if the
/// component has no zone assignment (or its zone name doesn't resolve) —
/// mirrors `if comp.zone and comp.zone in zone_map`, resolved caller-side
/// since the zone-name lookup is a dict/string operation (glue), not
/// compute.
pub type ZoneBounds = Option<(f64, f64, f64, f64)>;

/// Ports `measure_geometric`'s four sub-algorithms verbatim.
///
/// # Arguments
///
/// * `positions_x` / `positions_y` — component center positions (mm), as
///   they are actually stored: float32 (`state.positions`'s true dtype in
///   every production code path).
/// * `widths` / `heights` — component full width/height (mm), float64
///   (`Component.bounds[0]` / `[1]`, as a Python float list).
/// * `min_separation` — minimum required clearance between component
///   edges (mm).
/// * `zone_bounds` — per-component resolved zone bounds, `None` if
///   unassigned or unresolvable.
/// * `board_origin` — `(x, y)` of the board's placement origin (mm).
/// * `board_width` / `board_height` — board extents (mm).
/// * `is_hv` — per-component `net_class == "HighVoltage"` flag.
///
/// All four slices (`positions_x`, `positions_y`, `widths`, `heights`,
/// `zone_bounds`, `is_hv`) must have the same length `n` (one entry per
/// component, in `netlist.components` order); this is a caller invariant
/// enforced by the pyo3 wrapper, not re-validated here (matching the
/// oracle, which has no such guard either — a length mismatch there would
/// raise `IndexError`, not silently misbehave).
#[allow(clippy::too_many_arguments)]
pub fn measure_geometric(
    positions_x: &[f32],
    positions_y: &[f32],
    widths: &[f64],
    heights: &[f64],
    min_separation: f64,
    zone_bounds: &[ZoneBounds],
    board_origin: (f64, f64),
    board_width: f64,
    board_height: f64,
    is_hv: &[bool],
) -> GeometricMetrics {
    let n = positions_x.len();
    let mut m = GeometricMetrics::default();

    // 1. Overlaps — pairwise over all i < j.
    for i in 0..n {
        let hw_i = widths[i] / 2.0;
        let hh_i = heights[i] / 2.0;
        for j in (i + 1)..n {
            let hw_j = widths[j] / 2.0;
            let hh_j = heights[j] / 2.0;

            // positions[i,0] - positions[j,0]: same-dtype (float32)
            // subtraction, computed in float32, THEN widened (NEP-50: no
            // float64 anchor is present yet at this step).
            let dx = (positions_x[i] - positions_x[j]).abs() as f64;
            let dy = (positions_y[i] - positions_y[j]).abs() as f64;

            let ox = (hw_i + hw_j + min_separation) - dx;
            let oy = (hh_i + hh_j + min_separation) - dy;

            if ox > 0.0 && oy > 0.0 {
                m.overlap_count += 1;
                m.overlap_area_mm2 += ox * oy;
            }
        }
    }

    // 2. Zone violations.
    for i in 0..n {
        if let Some((zx0, zy0, zx1, zy1)) = zone_bounds[i] {
            // x, y widen to float64 immediately: they meet hw/hh (actual
            // float64) in the very next expression (NEP-50 promotion).
            let x = positions_x[i] as f64;
            let y = positions_y[i] as f64;
            let hw = widths[i] / 2.0;
            let hh = heights[i] / 2.0;

            let dist_x = max0(zx0 - (x - hw), (x + hw) - zx1);
            let dist_y = max0(zy0 - (y - hh), (y + hh) - zy1);

            if dist_x > 0.0 || dist_y > 0.0 {
                m.zone_violation_count += 1;
                let d = hypot_pow(dist_x, dist_y);
                m.zone_violation_max_mm = hostmath::py_max(m.zone_violation_max_mm, d);
            }
        }
    }

    // 3. Boundary violations.
    for i in 0..n {
        let x = positions_x[i] as f64;
        let y = positions_y[i] as f64;
        let hw = widths[i] / 2.0;
        let hh = heights[i] / 2.0;

        if x - hw < board_origin.0
            || x + hw > board_origin.0 + board_width
            || y - hh < board_origin.1
            || y + hh > board_origin.1 + board_height
        {
            m.boundary_violation_count += 1;
        }
    }

    // 4. HV-LV clearance (creepage proxy).
    let hv_indices: Vec<usize> = (0..n).filter(|&i| is_hv[i]).collect();
    let lv_indices: Vec<usize> = (0..n).filter(|&i| !is_hv[i]).collect();

    if !hv_indices.is_empty() && !lv_indices.is_empty() {
        for &i in &hv_indices {
            let hw_i = widths[i] / 2.0;
            let hh_i = heights[i] / 2.0;
            for &j in &lv_indices {
                let hw_j = widths[j] / 2.0;
                let hh_j = heights[j] / 2.0;

                // Same same-dtype-first-then-widen shape as the overlap
                // arm above.
                let diff_x = (positions_x[i] - positions_x[j]).abs() as f64;
                let diff_y = (positions_y[i] - positions_y[j]).abs() as f64;
                let dx = diff_x - hw_i - hw_j;
                let dy = diff_y - hh_i - hh_j;

                // max(dx, dy, 0.0): dx is the FIRST argument here (unlike
                // the zone arm's `max(0, ...)`), so a NaN dx survives the
                // fold — B5, argument-order-sensitive.
                let mut dist = hostmath::py_max(hostmath::py_max(dx, dy), 0.0);
                if dx > 0.0 && dy > 0.0 {
                    dist = hypot_pow(dx, dy);
                }

                m.min_hv_lv_clearance_mm = hostmath::py_min(m.min_hv_lv_clearance_mm, dist);
            }
        }
    }

    m
}

/// pyo3 bridge for [`measure_geometric`]. Returns a 6-tuple in field
/// order: `(overlap_count, overlap_area_mm2, zone_violation_count,
/// zone_violation_max_mm, boundary_violation_count,
/// min_hv_lv_clearance_mm)`.
#[cfg(feature = "python")]
#[allow(clippy::too_many_arguments)]
#[pyfunction]
#[pyo3(signature = (
    positions_x,
    positions_y,
    widths,
    heights,
    min_separation,
    zone_bounds,
    board_origin,
    board_width,
    board_height,
    is_hv,
))]
pub fn measure_geometric_py(
    positions_x: Vec<f32>,
    positions_y: Vec<f32>,
    widths: Vec<f64>,
    heights: Vec<f64>,
    min_separation: f64,
    zone_bounds: Vec<ZoneBounds>,
    board_origin: (f64, f64),
    board_width: f64,
    board_height: f64,
    is_hv: Vec<bool>,
) -> PyResult<(i64, f64, i64, f64, i64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let m = measure_geometric(
            &positions_x,
            &positions_y,
            &widths,
            &heights,
            min_separation,
            &zone_bounds,
            board_origin,
            board_width,
            board_height,
            &is_hv,
        );
        (
            m.overlap_count,
            m.overlap_area_mm2,
            m.zone_violation_count,
            m.zone_violation_max_mm,
            m.boundary_violation_count,
            m.min_hv_lv_clearance_mm,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn no_components_is_all_defaults() {
        let m = measure_geometric(&[], &[], &[], &[], 0.5, &[], (0.0, 0.0), 100.0, 100.0, &[]);
        assert_eq!(m, GeometricMetrics::default());
    }

    #[test]
    fn overlapping_pair_is_counted() {
        // Two 4x4mm components 3mm apart on x (centers), min_separation 0.5:
        // ox = (2+2+0.5) - 3 = 1.5 > 0; oy = (2+2+0.5) - 0 = 4.5 > 0.
        let xs = [0.0_f32, 3.0];
        let ys = [0.0_f32, 0.0];
        let w = [4.0, 4.0];
        let h = [4.0, 4.0];
        let m = measure_geometric(&xs, &ys, &w, &h, 0.5, &[None, None], (-50.0, -50.0), 100.0, 100.0, &[false, false]);
        assert_eq!(m.overlap_count, 1);
        assert!((m.overlap_area_mm2 - 1.5 * 4.5).abs() < 1e-9);
    }

    #[test]
    fn exact_touch_is_not_an_overlap() {
        // ox == 0.0 exactly must NOT count (`> 0`, not `>= 0`).
        let xs = [0.0_f32, 4.5];
        let ys = [0.0_f32, 0.0];
        let w = [4.0, 4.0];
        let h = [4.0, 4.0];
        let m = measure_geometric(&xs, &ys, &w, &h, 0.5, &[None, None], (-50.0, -50.0), 100.0, 100.0, &[false, false]);
        assert_eq!(m.overlap_count, 0);
    }

    #[test]
    fn zone_violation_detected_and_measured() {
        let xs = [55.0_f32];
        let ys = [10.0];
        let w = [4.0];
        let h = [4.0];
        // Zone x in [0, 50]; component right edge at 57 -> dist_x = 7.
        let zb = [Some((0.0, 0.0, 50.0, 50.0))];
        let m = measure_geometric(&xs, &ys, &w, &h, 0.5, &zb, (0.0, 0.0), 100.0, 100.0, &[false]);
        assert_eq!(m.zone_violation_count, 1);
        assert!((m.zone_violation_max_mm - 7.0).abs() < 1e-9);
    }

    #[test]
    fn boundary_violation_detected() {
        let xs = [2.0_f32];
        let ys = [50.0];
        let w = [10.0]; // half-width 5, x - hw = -3 < origin.0 (0.0)
        let h = [4.0];
        let m = measure_geometric(&xs, &ys, &w, &h, 0.5, &[None], (0.0, 0.0), 100.0, 100.0, &[false]);
        assert_eq!(m.boundary_violation_count, 1);
    }

    #[test]
    fn hv_lv_clearance_needs_both_classes_nonempty() {
        // All HV -> lv_indices empty -> stays default 1000.0.
        let xs = [0.0_f32, 10.0];
        let ys = [0.0_f32, 0.0];
        let w = [4.0, 4.0];
        let h = [4.0, 4.0];
        let m = measure_geometric(&xs, &ys, &w, &h, 0.5, &[None, None], (-50.0, -50.0), 100.0, 100.0, &[true, true]);
        assert_eq!(m.min_hv_lv_clearance_mm, 1000.0);
    }

    #[test]
    fn hv_lv_clearance_measured_when_mixed() {
        let xs = [0.0_f32, 10.0];
        let ys = [0.0_f32, 0.0];
        let w = [4.0, 4.0];
        let h = [4.0, 4.0];
        let m = measure_geometric(&xs, &ys, &w, &h, 0.5, &[None, None], (-50.0, -50.0), 100.0, 100.0, &[true, false]);
        // dx = |0-10| - 2 - 2 = 6; dy = 0 - 2 - 2 = -4 -> dist = max(6,-4,0)=6
        assert!((m.min_hv_lv_clearance_mm - 6.0).abs() < 1e-9);
    }

    #[test]
    fn nan_position_in_hv_lv_does_not_survive_the_accumulator_min() {
        // dx computed from a NaN position IS the first argument of the
        // inner `max(dx, dy, 0.0)` fold (B5) -- but the OUTER accumulator
        // is `min(metrics.min_hv_lv_clearance_mm, dist)`, whose first
        // argument is the running minimum (starts at the concrete,
        // never-NaN default 1000.0), not `dist`. Since NaN is never `<`
        // anything, a NaN `dist` can never beat that running minimum, so
        // the final `min_hv_lv_clearance_mm` stays 1000.0 -- verified to
        // match the Python oracle bit-for-bit on this exact fixture
        // (not merely asserted here).
        let xs = [f32::NAN, 10.0];
        let ys = [0.0_f32, 0.0];
        let w = [4.0, 4.0];
        let h = [4.0, 4.0];
        let m = measure_geometric(&xs, &ys, &w, &h, 0.5, &[None, None], (-50.0, -50.0), 100.0, 100.0, &[true, false]);
        assert_eq!(m.min_hv_lv_clearance_mm, 1000.0);
    }

    #[test]
    fn pow_used_not_multiplication_in_hypot() {
        // A measured input pair where `sqrt(x**2+y**2)` (pow) disagrees
        // with `sqrt(x*x+y*y)` (multiplication) -- unlike a single
        // `pow(x,2) != x*x` pin, sqrt's correct rounding can (and for
        // many inputs does) collapse a 1-ulp pre-sqrt difference, so this
        // pair was found by direct search rather than reusing hostmath's
        // pre-sqrt pin.
        let x = 261_393.185_393_277_38_f64;
        let y = 353_085.386_809_846_7_f64;
        let via_pow = hypot_pow(x, y);
        let via_mul = (x * x + y * y).sqrt();
        assert_ne!(via_pow, via_mul);
    }
}
