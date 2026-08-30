// Wave 4: `temper_placer/requirements/validators/_geometry.py` — the shared
// geometry helpers for PCB layout validation (extracted from layout_review,
// switching_nodes, bypass_caps, and pick_and_place to eliminate duplicated
// implementations).
//
// The verbatim pre-migration copy this module must reproduce bit-identically
// is pinned in the `_oracle_*` block of
// `packages/temper-placer/tests/requirements/validators/
// test_geometry_rust_differential.py` (`git show 47349a50`).
//
// ---------------------------------------------------------------------------
// Why these are NOT `drc_constraints_geometry.rs`'s kernels
// ---------------------------------------------------------------------------
// This crate already carries a `point_to_segment_distance`,
// `segments_intersect` and `segment_to_segment_distance` for
// `router_v6/constraints_geometry.py` (drc_constraints_geometry.rs).  Those
// are DIFFERENT functions with DIFFERENT reference semantics, and reusing
// them here would be a silent behaviour change:
//
//   _geometry.py                     : degenerate when `len2 < 1e-12`
//   constraints_geometry.py          : degenerate when `seg_len_sq < 1e-10`
//
// A segment of length 1e-6 (squared 1e-12) takes the projection arm here
// and the degenerate arm in the DRC port.  And `_segments_intersect` here is
// a sign-based test (`(o1 > 0) != (o2 > 0)`) with a `1e-9` epsilon and
// epsilon-padded `_on_segment`, where the DRC port uses a 0/1/2 orientation
// code, a `1e-10` epsilon, and an un-padded box test.  The migration
// preserves each as written rather than unifying them.
//
// ---------------------------------------------------------------------------
// Numerical contract
// ---------------------------------------------------------------------------
// * `math.dist` / `math.hypot` -> `py_hypot` (CPython's compensated
//   `vector_norm`).  It is NOT `sqrt(x*x + y*y)` (measured, 17.1% of random
//   2-vectors disagree) and NOT libm `hypot` (differs in the last ulp).
//   `_distance(a, b)` is `math.dist(a, b)` = `py_hypot(a[0]-b[0], a[1]-b[1])`
//   — the same wiring the already-verified `audit.rs::dist_py` uses.
// * Builtin `min`/`max` -> `py_min` / `py_max` (creepage_check.rs): they
//   propagate NaN from the LEFT operand only and return the FIRST argument
//   on ties.  The reference's `t = max(0.0, min(1.0, t))` must be evaluated
//   as `(1.0_f64.min(t_raw)).max(0.0)` via py_min/py_max — NOT
//   `t_raw.max(0.0).min(1.0)`: for `t_raw = NaN` CPython's `min` keeps its
//   first argument and clamps to 1.0.
// * Multi-arg `min(a, b, c, d)` is a left-to-right strict-`<` fold seeded
//   with the first argument (leading NaN survives), composed via py_min.
// * Generator `min(...)` folds are the same strict-`<` fold seeded with the
//   first generated value.
// * Builtin `sum(...)` -> `py_sum_neumaier` (area_sufficiency.rs): CPython
//   3.12's `builtin_sum_impl` float fast path is a Neumaier-compensated
//   fold, NOT naive addition (B12).  Used only for `_polyline_length`; the
//   `+=` loops elsewhere stay naive folds.
// * `x ** 2` / `x ** 0.5` -> `host_math::pow` (dlsym-resolved host libm).
// * No `mul_add` fusion, no fast-math: default IEEE semantics so denormal
//   intermediates survive (B8).
// * `_rects_overlap` is implemented as the reference's negation of four
//   `<` comparisons rather than `AABB::intersects` because NaN coordinates
//   behave differently: in Python every NaN `<` is False so the negation is
//   True, while `AABB::intersects` would return False.

use crate::area_sufficiency::py_sum_neumaier;
use crate::creepage_check::{py_max, py_min};
use crate::pad_geometry::py_hypot;
use crate::types::{Point, Rect};

#[cfg(feature = "python")]
use pyo3::prelude::*;

// ---------------------------------------------------------------------------
// point / rect
// ---------------------------------------------------------------------------

/// `_distance`: `math.dist(a, b)` = CPython's Dekker double-double
/// compensated `vector_norm` over the two coordinate differences.
pub fn point_distance(ax: f64, ay: f64, bx: f64, by: f64) -> f64 {
    py_hypot(ax - bx, ay - by)
}

/// `_point_in_rect`: `rx <= x <= rx + rw and ry <= y <= ry + rh` (inclusive
/// bounds).  Wires `Rect::contains_point`, whose comparisons and arithmetic
/// (`x + w` added inside the comparison) are identical to the reference's
/// chained comparison.
pub fn point_in_rect(x: f64, y: f64, rx: f64, ry: f64, rw: f64, rh: f64) -> bool {
    Rect::new(rx, ry, rw, rh).contains_point(&Point::new(x, y))
}

/// `_rects_overlap`: `not (x1 + w1 < x2 or x2 + w2 < x1 or y1 + h1 < y2 or
/// y2 + h2 < y1)`.  Implemented as the reference's exact negation (see the
/// module docstring for why this is not `AABB::intersects`).
#[allow(clippy::too_many_arguments)]
pub fn rects_overlap(x1: f64, y1: f64, w1: f64, h1: f64, x2: f64, y2: f64, w2: f64, h2: f64) -> bool {
    !(x1 + w1 < x2 || x2 + w2 < x1 || y1 + h1 < y2 || y2 + h2 < y1)
}

// ---------------------------------------------------------------------------
// point / segment
// ---------------------------------------------------------------------------

/// `_point_to_segment_distance`: closest (perpendicular, clamped) distance
/// from point `p` to segment `a`-`b`.  Degenerate (returns the point-to-point
/// distance) when `len2 < 1e-12`; the projection arm's clamp is the
/// min-then-max `py_min(1.0, t)` / `py_max(0.0, ...)` NaN-safe nesting.
#[allow(clippy::too_many_arguments)]
pub fn point_to_segment_distance(
    px: f64,
    py: f64,
    ax: f64,
    ay: f64,
    bx: f64,
    by: f64,
) -> f64 {
    let abx = bx - ax;
    let aby = by - ay;
    let len2 = abx * abx + aby * aby;
    // NaN takes the projection arm here exactly as Python's `<` does.
    if len2 < 1e-12 {
        return point_distance(px, py, ax, ay);
    }
    let t = py_max(0.0, py_min(1.0, ((px - ax) * abx + (py - ay) * aby) / len2));
    let cx = ax + t * abx;
    let cy = ay + t * aby;
    point_distance(px, py, cx, cy)
}

/// `_point_to_polyline_distance`: minimum distance from a point to any
/// segment of a polyline, to the single point of a one-point polyline, or
/// `+inf` for an empty polyline.  `pts` is a flat `[x0, y0, x1, y1, ...]`.
/// The multi-segment minimum is the generator `min(...)` strict-`<` fold
/// seeded with the first segment distance.
pub fn point_to_polyline_distance(px: f64, py: f64, pts: &[f64]) -> f64 {
    let n = pts.len() / 2;
    match n {
        0 => f64::INFINITY,
        1 => point_distance(px, py, pts[0], pts[1]),
        _ => {
            let mut best = point_to_segment_distance(px, py, pts[0], pts[1], pts[2], pts[3]);
            for i in 1..n - 1 {
                let d = point_to_segment_distance(
                    px,
                    py,
                    pts[2 * i],
                    pts[2 * i + 1],
                    pts[2 * i + 2],
                    pts[2 * i + 3],
                );
                if d < best {
                    best = d;
                }
            }
            best
        }
    }
}

/// `_orientation`: the signed cross product `(b - a) x (c - a)`.
#[allow(clippy::too_many_arguments)]
pub fn orientation(ax: f64, ay: f64, bx: f64, by: f64, cx: f64, cy: f64) -> f64 {
    (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
}

/// `_on_segment`: whether `p` lies in the `1e-9`-padded axis-aligned box of
/// segment `a`-`b` (builtin `min`/`max` semantics via `py_min`/`py_max`).
#[allow(clippy::too_many_arguments)]
pub fn on_segment(ax: f64, ay: f64, bx: f64, by: f64, px: f64, py: f64) -> bool {
    (py_min(ax, bx) - 1e-9 <= px && px <= py_max(ax, bx) + 1e-9)
        && (py_min(ay, by) - 1e-9 <= py && py <= py_max(ay, by) + 1e-9)
}

/// `_segments_intersect`: sign-based orientation test with a `1e-9` epsilon
/// for the collinear arms.  See the module docstring for why this is not the
/// `drc_constraints_geometry.rs` version.
#[allow(clippy::too_many_arguments)]
pub fn segments_intersect(
    a1x: f64,
    a1y: f64,
    a2x: f64,
    a2y: f64,
    b1x: f64,
    b1y: f64,
    b2x: f64,
    b2y: f64,
) -> bool {
    let o1 = orientation(a1x, a1y, a2x, a2y, b1x, b1y);
    let o2 = orientation(a1x, a1y, a2x, a2y, b2x, b2y);
    let o3 = orientation(b1x, b1y, b2x, b2y, a1x, a1y);
    let o4 = orientation(b1x, b1y, b2x, b2y, a2x, a2y);

    if ((o1 > 0.0) != (o2 > 0.0)) && ((o3 > 0.0) != (o4 > 0.0)) {
        return true;
    }

    let eps = 1e-9;
    if o1.abs() < eps && on_segment(a1x, a1y, a2x, a2y, b1x, b1y) {
        return true;
    }
    if o2.abs() < eps && on_segment(a1x, a1y, a2x, a2y, b2x, b2y) {
        return true;
    }
    if o3.abs() < eps && on_segment(b1x, b1y, b2x, b2y, a1x, a1y) {
        return true;
    }
    o4.abs() < eps && on_segment(b1x, b1y, b2x, b2y, a2x, a2y)
}

/// `_segment_to_segment_distance`: minimum distance between two segments
/// (0.0 if they intersect, including touching/collinear-overlap).  The
/// four-point `min(d1, d2, d3, d4)` is the reference's left-to-right
/// strict-`<` fold.
#[allow(clippy::too_many_arguments)]
pub fn segment_to_segment_distance(
    a1x: f64,
    a1y: f64,
    a2x: f64,
    a2y: f64,
    b1x: f64,
    b1y: f64,
    b2x: f64,
    b2y: f64,
) -> f64 {
    if segments_intersect(a1x, a1y, a2x, a2y, b1x, b1y, b2x, b2y) {
        return 0.0;
    }
    let d1 = point_to_segment_distance(a1x, a1y, b1x, b1y, b2x, b2y);
    let d2 = point_to_segment_distance(a2x, a2y, b1x, b1y, b2x, b2y);
    let d3 = point_to_segment_distance(b1x, b1y, a1x, a1y, a2x, a2y);
    let d4 = point_to_segment_distance(b2x, b2y, a1x, a1y, a2x, a2y);
    py_min(py_min(py_min(d1, d2), d3), d4)
}

// ---------------------------------------------------------------------------
// polyline / polyline
// ---------------------------------------------------------------------------

/// `_polyline_min_distance`: minimum distance between two polylines (0.0 if
/// any segment pair crosses, `+inf` if either is empty, reduced to the
/// point-to-polyline distance when either has a single point).  The loop's
/// strict-`<` update with the early `best <= 0.0` exit matches the reference
/// exactly (a NaN `d` never displaces a finite best).
pub fn polyline_min_distance(poly1: &[f64], poly2: &[f64]) -> f64 {
    let n1 = poly1.len() / 2;
    let n2 = poly2.len() / 2;
    if n1 == 0 || n2 == 0 {
        return f64::INFINITY;
    }
    if n1 == 1 {
        return point_to_polyline_distance(poly1[0], poly1[1], poly2);
    }
    if n2 == 1 {
        return point_to_polyline_distance(poly2[0], poly2[1], poly1);
    }
    let mut best = f64::INFINITY;
    for i in 0..n1 - 1 {
        for j in 0..n2 - 1 {
            let d = segment_to_segment_distance(
                poly1[2 * i],
                poly1[2 * i + 1],
                poly1[2 * i + 2],
                poly1[2 * i + 3],
                poly2[2 * j],
                poly2[2 * j + 1],
                poly2[2 * j + 2],
                poly2[2 * j + 3],
            );
            if d < best {
                best = d;
            }
            if best <= 0.0 {
                return 0.0;
            }
        }
    }
    best
}

/// `_polylines_intersect`: whether any segment of poly1 crosses any segment
/// of poly2 (False when either has fewer than 2 points).
pub fn polylines_intersect(poly1: &[f64], poly2: &[f64]) -> bool {
    let n1 = poly1.len() / 2;
    let n2 = poly2.len() / 2;
    if n1 < 2 || n2 < 2 {
        return false;
    }
    for i in 0..n1 - 1 {
        for j in 0..n2 - 1 {
            if segments_intersect(
                poly1[2 * i],
                poly1[2 * i + 1],
                poly1[2 * i + 2],
                poly1[2 * i + 3],
                poly2[2 * j],
                poly2[2 * j + 1],
                poly2[2 * j + 2],
                poly2[2 * j + 3],
            ) {
                return true;
            }
        }
    }
    false
}

/// `_polyline_length`: builtin `sum()` over the segment `math.dist` lengths —
/// CPython's Neumaier-compensated fold (NOT naive addition), shared with
/// `area_sufficiency.rs`.  The reference guards `< 2` points with `0.0`
/// (float), so this kernel returns `0.0` for that case and matches
/// bit-exactly throughout.
pub fn polyline_length(polyline: &[f64]) -> f64 {
    let n = polyline.len() / 2;
    if n < 2 {
        return 0.0;
    }
    let mut items = Vec::with_capacity(n - 1);
    for i in 0..n - 1 {
        items.push(point_distance(
            polyline[2 * i],
            polyline[2 * i + 1],
            polyline[2 * i + 2],
            polyline[2 * i + 3],
        ));
    }
    py_sum_neumaier(&items)
}

// ---------------------------------------------------------------------------
// pyo3 boundary
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
#[pyfunction]
pub fn geom_point_distance_py(ax: f64, ay: f64, bx: f64, by: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| point_distance(ax, ay, bx, by))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn geom_point_in_rect_py(x: f64, y: f64, rx: f64, ry: f64, rw: f64, rh: f64) -> PyResult<bool> {
    temper_py_bridge::catch_unwind(|| point_in_rect(x, y, rx, ry, rw, rh))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn geom_rects_overlap_py(
    x1: f64,
    y1: f64,
    w1: f64,
    h1: f64,
    x2: f64,
    y2: f64,
    w2: f64,
    h2: f64,
) -> PyResult<bool> {
    temper_py_bridge::catch_unwind(|| rects_overlap(x1, y1, w1, h1, x2, y2, w2, h2))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn geom_point_to_segment_distance_py(
    px: f64,
    py: f64,
    ax: f64,
    ay: f64,
    bx: f64,
    by: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| point_to_segment_distance(px, py, ax, ay, bx, by))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn geom_point_to_polyline_distance_py(px: f64, py: f64, pts: Vec<f64>) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| point_to_polyline_distance(px, py, &pts))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn geom_orientation_py(
    ax: f64,
    ay: f64,
    bx: f64,
    by: f64,
    cx: f64,
    cy: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| orientation(ax, ay, bx, by, cx, cy))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn geom_on_segment_py(
    ax: f64,
    ay: f64,
    bx: f64,
    by: f64,
    px: f64,
    py: f64,
) -> PyResult<bool> {
    temper_py_bridge::catch_unwind(|| on_segment(ax, ay, bx, by, px, py))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn geom_segments_intersect_py(
    a1x: f64,
    a1y: f64,
    a2x: f64,
    a2y: f64,
    b1x: f64,
    b1y: f64,
    b2x: f64,
    b2y: f64,
) -> PyResult<bool> {
    temper_py_bridge::catch_unwind(|| {
        segments_intersect(a1x, a1y, a2x, a2y, b1x, b1y, b2x, b2y)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
#[allow(clippy::too_many_arguments)]
pub fn geom_segment_to_segment_distance_py(
    a1x: f64,
    a1y: f64,
    a2x: f64,
    a2y: f64,
    b1x: f64,
    b1y: f64,
    b2x: f64,
    b2y: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        segment_to_segment_distance(a1x, a1y, a2x, a2y, b1x, b1y, b2x, b2y)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn geom_polyline_min_distance_py(poly1: Vec<f64>, poly2: Vec<f64>) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| polyline_min_distance(&poly1, &poly2))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn geom_polylines_intersect_py(poly1: Vec<f64>, poly2: Vec<f64>) -> PyResult<bool> {
    temper_py_bridge::catch_unwind(|| polylines_intersect(&poly1, &poly2))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
#[pyfunction]
pub fn geom_polyline_length_py(polyline: Vec<f64>) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| polyline_length(&polyline))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(geom_point_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(geom_point_in_rect_py, m)?)?;
    m.add_function(wrap_pyfunction!(geom_rects_overlap_py, m)?)?;
    m.add_function(wrap_pyfunction!(geom_point_to_segment_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(geom_point_to_polyline_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(geom_orientation_py, m)?)?;
    m.add_function(wrap_pyfunction!(geom_on_segment_py, m)?)?;
    m.add_function(wrap_pyfunction!(geom_segments_intersect_py, m)?)?;
    m.add_function(wrap_pyfunction!(geom_segment_to_segment_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(geom_polyline_min_distance_py, m)?)?;
    m.add_function(wrap_pyfunction!(geom_polylines_intersect_py, m)?)?;
    m.add_function(wrap_pyfunction!(geom_polyline_length_py, m)?)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// tests
// ---------------------------------------------------------------------------

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn point_distance_three_four_five() {
        assert_eq!(point_distance(0.0, 0.0, 3.0, 4.0), 5.0);
    }

    #[test]
    fn point_in_rect_wires_the_rect_primitive() {
        assert!(point_in_rect(5.0, 5.0, 0.0, 0.0, 10.0, 10.0));
        assert!(!point_in_rect(10.5, 5.0, 0.0, 0.0, 10.0, 10.0));
        assert!(point_in_rect(10.0, 10.0, 0.0, 0.0, 10.0, 10.0)); // on edge
    }

    #[test]
    fn rects_overlap_nan_is_true_like_python() {
        // Python: every NaN `<` is False, so the negation is True.
        assert!(rects_overlap(f64::NAN, 0.0, 10.0, 10.0, 0.0, 0.0, 5.0, 5.0));
        assert!(rects_overlap(0.0, 0.0, 10.0, 10.0, 0.0, 0.0, 5.0, f64::NAN));
    }

    #[test]
    fn point_to_segment_degenerate_threshold_is_1e_12() {
        // len2 == 1e-12 -> projection arm; len2 == 0.81e-12 -> degenerate arm.
        let a = point_to_segment_distance(1.0, 0.0, 0.0, 0.0, 1e-6, 0.0);
        let b = point_to_segment_distance(1.0, 0.0, 0.0, 0.0, 0.9e-6, 0.0);
        assert_ne!(a.to_bits(), b.to_bits());
    }

    #[test]
    fn point_to_segment_nan_clamp_is_min_then_max() {
        // For a NaN projection the reference clamps t to 1.0 (min keeps its
        // first argument), giving the endpoint distance -- matching the
        // grid-raster B5 note, not t.max(0.0).min(1.0).
        let r = point_to_segment_distance(5.0, 5.0, 0.0, 0.0, f64::NAN, 0.0);
        assert!(r.is_nan());
        let finite = point_to_segment_distance(5.0, 5.0, 0.0, 0.0, 10.0, 0.0);
        assert_eq!(finite, 5.0);
    }

    #[test]
    fn segments_intersect_covers_the_sign_based_arms() {
        assert!(segments_intersect(0.0, 0.0, 10.0, 10.0, 0.0, 10.0, 10.0, 0.0));
        assert!(segments_intersect(0.0, 0.0, 10.0, 0.0, 5.0, 0.0, 15.0, 0.0));
        assert!(!segments_intersect(0.0, 0.0, 10.0, 0.0, 15.0, 0.0, 25.0, 0.0));
        assert!(segments_intersect(0.0, 0.0, 10.0, 0.0, 10.0, 0.0, 20.0, 0.0));
        assert!(!segments_intersect(0.0, 0.0, 10.0, 0.0, 0.0, 3.0, 10.0, 3.0));
    }

    #[test]
    fn segment_to_segment_distance_arms() {
        assert_eq!(
            segment_to_segment_distance(0.0, 0.0, 10.0, 10.0, 0.0, 10.0, 10.0, 0.0),
            0.0
        );
        assert_eq!(
            segment_to_segment_distance(0.0, 0.0, 10.0, 0.0, 0.0, 3.0, 10.0, 3.0),
            3.0
        );
    }

    #[test]
    fn polyline_length_is_compensated_not_naive() {
        // Neumaier discriminator: a naive fold collapses the 1.0.
        let flat = [0.0, 0.0, 1e16, 0.0, 1e16, 1.0];
        let v = polyline_length(&flat);
        // lengths: 1e16, 1.0 -> compensated sum 1e16 + 1.0
        let expected = py_sum_neumaier(&[py_hypot(1e16, 0.0), py_hypot(0.0, 1.0)]);
        assert_eq!(v, expected);
        assert_eq!(v, 1e16 + 1.0);
    }

    #[test]
    fn polylines_intersect_guards_short_polylines() {
        assert!(!polylines_intersect(&[], &[0.0, 0.0, 1.0, 1.0]));
        assert!(!polylines_intersect(&[0.0, 0.0], &[0.0, 5.0]));
        assert!(polylines_intersect(
            &[0.0, 0.0, 10.0, 10.0],
            &[0.0, 10.0, 10.0, 0.0]
        ));
    }
}
