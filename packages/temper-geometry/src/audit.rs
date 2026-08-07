// Placement-audit geometry (Wave 3 #5 — the R24 post-solve audit's pure
// compute) — the Chebyshev-gap recomputation behind
// temper_placer/placer/cp_sat/audit.py.
//
// Python reference: audit.py `_bbox` and `_chebyshev_gap`.  The auditor's
// per-constraint orchestration stays in Python; these two functions are
// the geometry every check (separated, enclosing, adjacent edge-to-edge,
// on_side, anchored-region, keepout, loop-area) is built from.
//
// Bit-exactness: identical f64 operation order (left-to-right,
// two-op chains stay two ops) and Python-builtin `max` semantics —
// CPython's builtin max(a, b) returns `a` whenever `b > a` is false,
// which makes max(NaN, x) == NaN but max(x, NaN) == x.  Rust's
// f64::max discards NaN, so `py_max` below is the exact replica.

use pyo3::prelude::*;
use temper_py_bridge;

use crate::types::AABB;

/// Python builtin `max(a, b)` for two args (see module docstring for why
/// this differs from `f64::max` on NaN arguments).
fn py_max(a: f64, b: f64) -> f64 {
    if b > a {
        b
    } else {
        a
    }
}

/// Mirrors audit.py `_bbox`: `(cx - sw/2, cy - sh/2, cx + sw/2, cy + sh/2)`.
/// Operation order preserved: `hw = sw / 2`, `hh = sh / 2`, then the four
/// subtractions/additions left-to-right.
fn bbox_from_center(cx: f64, cy: f64, sw: f64, sh: f64) -> AABB {
    let hw = sw / 2.0;
    let hh = sh / 2.0;
    AABB::new(cx - hw, cy - hh, cx + hw, cy + hh)
}

/// Mirrors audit.py `_chebyshev_gap`: the Chebyshev (L-inf) distance
/// between two axis-aligned rectangles.  Returns 0 when they touch or
/// overlap, negative when they overlap deeply, positive when separated.
///
/// `dx = max(ax1 - bx2, bx1 - ax2)` then `dy` analogously, then
/// `max(dx, dy)` — all via Python-builtin-max semantics.
fn chebyshev_gap(a: AABB, b: AABB) -> f64 {
    let dx = py_max(a.x_min - b.x_max, b.x_min - a.x_max);
    let dy = py_max(a.y_min - b.y_max, b.y_min - a.y_max);
    py_max(dx, dy)
}

// ---------------------------------------------------------------------------
// PyO3 bridge
// ---------------------------------------------------------------------------

#[pyfunction]
pub fn bbox_from_center_py(cx: f64, cy: f64, sw: f64, sh: f64) -> PyResult<(f64, f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| {
        let b = bbox_from_center(cx, cy, sw, sh);
        (b.x_min, b.y_min, b.x_max, b.y_max)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
#[allow(clippy::too_many_arguments)] // FFI surface mirrors the fixed Python API; the kernel takes two AABBs
pub fn chebyshev_gap_py(
    ax1: f64, ay1: f64, ax2: f64, ay2: f64,
    bx1: f64, by1: f64, bx2: f64, by2: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let a = AABB::new(ax1, ay1, ax2, ay2);
        let b = AABB::new(bx1, by1, bx2, by2);
        chebyshev_gap(a, b)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bbox_origin_centered() {
        assert_eq!(bbox_from_center(0.0, 0.0, 2.0, 4.0), AABB::new(-1.0, -2.0, 1.0, 2.0));
    }

    #[test]
    fn bbox_zero_size_collapses_to_point() {
        assert_eq!(bbox_from_center(3.0, -7.0, 0.0, 0.0), AABB::new(3.0, -7.0, 3.0, -7.0));
    }

    #[test]
    fn gap_separated_boxes() {
        // 2x2 boxes centered at (0,0) and (5,0): edge gap 3.
        let a = bbox_from_center(0.0, 0.0, 2.0, 2.0);
        let b = bbox_from_center(5.0, 0.0, 2.0, 2.0);
        assert_eq!(chebyshev_gap(a, b), 3.0);
    }

    #[test]
    fn gap_touching_and_overlapping() {
        let a = AABB::new(0.0, 0.0, 1.0, 1.0);
        let b = AABB::new(1.0, 0.0, 2.0, 1.0);
        assert_eq!(chebyshev_gap(a, b), 0.0);
        let big = AABB::new(0.0, 0.0, 10.0, 10.0);
        let small = AABB::new(4.0, 4.0, 6.0, 6.0);
        assert!(chebyshev_gap(big, small) < 0.0);
        // Identical boxes overlap deeply: gap = -width.
        assert_eq!(chebyshev_gap(a, a), -1.0);
    }

    #[test]
    fn gap_is_symmetric() {
        let a = AABB::new(1.0, 2.0, 3.0, 4.0);
        let b = AABB::new(5.0, 6.0, 7.0, 8.0);
        assert_eq!(chebyshev_gap(a, b), chebyshev_gap(b, a));
    }

    #[test]
    fn gap_nan_replicates_python_builtin_max() {
        // max(NaN, x) == NaN but max(x, NaN) == x under the builtin.
        let nan = f64::NAN;
        let a = AABB::new(nan, 0.0, 1.0, 1.0);
        let b = AABB::new(2.0, 0.0, 3.0, 1.0);
        assert!(chebyshev_gap(a, b).is_nan());
        let a2 = AABB::new(0.0, 0.0, 1.0, 1.0);
        let b2 = AABB::new(2.0, 0.0, 3.0, nan);
        // dx = max(-3, 1) = 1; dy = max(-nan, -1) = nan; max(1, nan) = 1.
        assert_eq!(chebyshev_gap(a2, b2), 1.0);
    }
}
