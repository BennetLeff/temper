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

use crate::pad_geometry::py_hypot;

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
fn bbox_from_center(cx: f64, cy: f64, sw: f64, sh: f64) -> (f64, f64, f64, f64) {
    let hw = sw / 2.0;
    let hh = sh / 2.0;
    (cx - hw, cy - hh, cx + hw, cy + hh)
}

/// Mirrors audit.py `_chebyshev_gap`: the Chebyshev (L-inf) distance
/// between two axis-aligned rectangles.  Returns 0 when they touch or
/// overlap, negative when they overlap deeply, positive when separated.
///
/// `dx = max(ax1 - bx2, bx1 - ax2)` then `dy` analogously, then
/// `max(dx, dy)` — all via Python-builtin-max semantics.
#[expect(clippy::too_many_arguments, reason = "audit.py port mirrors _chebyshev_gap's 2-rect signature 1:1; a config struct would change the ported shape")]
fn chebyshev_gap(
    ax1: f64, ay1: f64, ax2: f64, ay2: f64,
    bx1: f64, by1: f64, bx2: f64, by2: f64,
) -> f64 {
    let dx = py_max(ax1 - bx2, bx1 - ax2);
    let dy = py_max(ay1 - by2, by1 - ay2);
    py_max(dx, dy)
}

// ---------------------------------------------------------------------------
// PyO3 bridge
// ---------------------------------------------------------------------------

#[pyfunction]
pub fn bbox_from_center_py(cx: f64, cy: f64, sw: f64, sh: f64) -> PyResult<(f64, f64, f64, f64)> {
    temper_py_bridge::catch_unwind(|| bbox_from_center(cx, cy, sw, sh))
        .map_err(temper_py_bridge::panic_to_err)
}

#[pyfunction]
#[expect(clippy::too_many_arguments, reason = "PyO3 boundary mirrors the Python signature 1:1; a config struct would change the FFI")]
pub fn chebyshev_gap_py(
    ax1: f64, ay1: f64, ax2: f64, ay2: f64,
    bx1: f64, by1: f64, bx2: f64, by2: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| chebyshev_gap(ax1, ay1, ax2, ay2, bx1, by1, bx2, by2))
        .map_err(temper_py_bridge::panic_to_err)
}

// ---------------------------------------------------------------------------
// Euclidean point distance (Wave 3 #4 — domain_clearance.py's R24
// audit recompute)
// ---------------------------------------------------------------------------

/// Mirrors `domain_clearance.py::audit_domain_clearance`'s
/// `math.dist(pos_a, pos_b)` — the R24 item-3 recomputation of the real
/// Euclidean center-to-center distance of every generated
/// `domain_clearance_*` constraint from the *solved* coordinates.
///
/// `math.dist` is CPython's Dekker double-double compensated
/// `vector_norm` over the per-coordinate differences
/// (`vec[i] = p[i] - q[i]`) — the same algorithm `py_hypot` replicates
/// exactly (pad_geometry.rs, with CPython's NaN/±inf up-front guards),
/// so this delegates to it with the differences computed first,
/// mirroring `math.dist`'s subtraction order.
fn dist(ax: f64, ay: f64, bx: f64, by: f64) -> f64 {
    py_hypot(ax - bx, ay - by)
}

#[pyfunction]
pub fn dist_py(ax: f64, ay: f64, bx: f64, by: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| dist(ax, ay, bx, by))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn bbox_origin_centered() {
        assert_eq!(bbox_from_center(0.0, 0.0, 2.0, 4.0), (-1.0, -2.0, 1.0, 2.0));
    }

    #[test]
    fn bbox_zero_size_collapses_to_point() {
        assert_eq!(bbox_from_center(3.0, -7.0, 0.0, 0.0), (3.0, -7.0, 3.0, -7.0));
    }

    #[test]
    fn gap_separated_boxes() {
        // 2x2 boxes centered at (0,0) and (5,0): edge gap 3.
        let a = bbox_from_center(0.0, 0.0, 2.0, 2.0);
        let b = bbox_from_center(5.0, 0.0, 2.0, 2.0);
        assert_eq!(chebyshev_gap(a.0, a.1, a.2, a.3, b.0, b.1, b.2, b.3), 3.0);
    }

    #[test]
    fn gap_touching_and_overlapping() {
        let a = (0.0, 0.0, 1.0, 1.0);
        let b = (1.0, 0.0, 2.0, 1.0);
        assert_eq!(chebyshev_gap(a.0, a.1, a.2, a.3, b.0, b.1, b.2, b.3), 0.0);
        let big = (0.0, 0.0, 10.0, 10.0);
        let small = (4.0, 4.0, 6.0, 6.0);
        assert!(chebyshev_gap(big.0, big.1, big.2, big.3, small.0, small.1, small.2, small.3) < 0.0);
        // Identical boxes overlap deeply: gap = -width.
        assert_eq!(chebyshev_gap(a.0, a.1, a.2, a.3, a.0, a.1, a.2, a.3), -1.0);
    }

    #[test]
    fn gap_is_symmetric() {
        let a = (1.0, 2.0, 3.0, 4.0);
        let b = (5.0, 6.0, 7.0, 8.0);
        let ab = chebyshev_gap(a.0, a.1, a.2, a.3, b.0, b.1, b.2, b.3);
        let ba = chebyshev_gap(b.0, b.1, b.2, b.3, a.0, a.1, a.2, a.3);
        assert_eq!(ab, ba);
    }

    #[test]
    fn gap_nan_replicates_python_builtin_max() {
        // max(NaN, x) == NaN but max(x, NaN) == x under the builtin.
        let nan = f64::NAN;
        let a = (nan, 0.0, 1.0, 1.0);
        let b = (2.0, 0.0, 3.0, 1.0);
        assert!(chebyshev_gap(a.0, a.1, a.2, a.3, b.0, b.1, b.2, b.3).is_nan());
        let a2 = (0.0, 0.0, 1.0, 1.0);
        let b2 = (2.0, 0.0, 3.0, nan);
        // dx = max(-3, 1) = 1; dy = max(-nan, -1) = nan; max(1, nan) = 1.
        assert_eq!(chebyshev_gap(a2.0, a2.1, a2.2, a2.3, b2.0, b2.1, b2.2, b2.3), 1.0);
    }

    #[test]
    fn dist_known_points() {
        assert_eq!(dist(0.0, 0.0, 3.0, 4.0), 5.0);
        assert_eq!(dist(0.0, 0.0, 0.0, 0.0), 0.0);
        assert_eq!(dist(1.0, 2.0, 1.0, 2.0), 0.0);
        assert_eq!(dist(0.0, 0.0, 1.0, 0.0), 1.0);
        assert_eq!(dist(0.0, 0.0, 3000.0, 4000.0), 5000.0);
    }

    #[test]
    fn dist_is_symmetric() {
        assert_eq!(dist(1.0, -2.0, 5.0, 6.0), dist(5.0, 6.0, 1.0, -2.0));
    }

    #[test]
    fn dist_non_finite_matches_math_dist() {
        // math.dist semantics: any NaN diff -> NaN, any inf diff -> inf;
        // inf - inf is NaN, so a coincident-inf pair is NaN, not inf.
        assert!(dist(f64::NAN, 0.0, 0.0, 0.0).is_nan());
        assert_eq!(dist(f64::INFINITY, 0.0, 0.0, 0.0), f64::INFINITY);
        assert!(dist(f64::INFINITY, 0.0, f64::INFINITY, 0.0).is_nan());
    }
}
