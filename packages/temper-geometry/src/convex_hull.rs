//! Convex-hull *area* — `scipy.spatial.ConvexHull` replacement for
//! `physics/loop_area.py`'s `_convex_hull_area` and
//! `validation/trace_analyzer.py`'s `calculate_actual_loop_area`.
//!
//! ## Contract, verified against the actual call sites before writing this
//!
//! Both Python call sites do exactly this and nothing else:
//!
//! ```python
//! hull = ConvexHull(pts)
//! return float(hull.volume)  # "volume" of a 2-D hull == area
//! ```
//!
//! Neither reads `hull.points`, `.vertices`, `.simplices`, or `.equations` —
//! confirmed by re-grepping both files at port time (`loop_area.py:227-240`,
//! `trace_analyzer.py:69-75`), the same re-check
//! `docs/evidence/2026-08-07-scipy-keeps-re-triage.md` Sec 5 calls for before
//! trusting its own PORTABLE verdict. Hull *area* is a scalar geometric
//! invariant: any correct convex-hull algorithm run on the same point set
//! produces the same real-valued area (mod ordinary floating-point
//! summation-order noise), unlike hull *vertex ordering*, which nothing here
//! consumes — so Qhull's specific tie-breaking on nearly-collinear or
//! nearly-duplicate boundary points is not load-bearing for this port. See
//! that doc's Sec 2 for the full argument and Sec 6 for why this was the
//! recommended port-first surface.
//!
//! ## Degenerate inputs
//!
//! `_convex_hull_area` and `calculate_actual_loop_area` both wrap the scipy
//! call in `except Exception: return 0.0` — scipy's Qhull *raises*
//! (`QhullError`) on inputs that can't form a full-dimensional hull (all
//! points collinear, or fewer than 3 distinct points), and both call sites
//! treat that as "no measurable loop area", not a hard failure. `geo`'s
//! QuickHull does not raise on these inputs; it degrades gracefully to a
//! hull with zero enclosed area (see `trivial_hull`/`quick_hull` in
//! `geo::algorithm::convex_hull`), so [`convex_hull_area`] returns `0.0`
//! directly for every one of these cases rather than needing a try/except
//! translation layer on the Python side:
//! - fewer than 3 points (including 0 and 1)
//! - all points collinear
//! - all points coincident (duplicates only)
//!
//! This is checked directly in this module's `#[cfg(test)]` suite, and
//! cross-checked against the live scipy behavior in the Python differential
//! harness (`tests/geometry/test_convex_hull_area_rust_differential.py`).

use geo::{Area, ConvexHull as GeoConvexHull, MultiPoint, Point as GeoPoint};

/// Convex-hull area of `points` (same units as the input coordinates —
/// mm² for this crate's callers).
///
/// Degenerate inputs (see module doc) return `0.0` rather than erroring,
/// matching both Python call sites' existing `except Exception: return 0.0`
/// fallback around `scipy.spatial.ConvexHull`.
pub fn convex_hull_area(points: &[[f64; 2]]) -> f64 {
    if points.len() < 3 {
        return 0.0;
    }
    let multi_point: MultiPoint<f64> = points.iter().map(|p| GeoPoint::new(p[0], p[1])).collect();
    let hull = multi_point.convex_hull();
    hull.unsigned_area()
}

#[cfg(feature = "python")]
use pyo3::prelude::*;

#[cfg(feature = "python")]
#[pyfunction]
/// Pyo3 boundary: `points` is a flat `(x0, y0, x1, y1, ...)` array, mirroring
/// this crate's existing `polygon_area`/`points_centroid` convention (see
/// `bridge.rs`'s `vec_to_points`) rather than `radius_pairs.rs`'s raw-bytes
/// convention — this is a one-shot, small-N (tens of points per net) call,
/// not a hot loop, so the bytes-marshalling optimization that convention
/// exists for isn't earning its complexity here.
pub fn convex_hull_area_py(points: Vec<f64>) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let pts: Vec<[f64; 2]> = points.chunks(2).map(|c| [c[0], c[1]]).collect();
        convex_hull_area(&pts)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(test)]
#[allow(clippy::unwrap_used)]
mod tests {
    use super::*;

    fn approx_eq(a: f64, b: f64, tol: f64) -> bool {
        (a - b).abs() <= tol
    }

    #[test]
    fn test_empty_input() {
        assert_eq!(convex_hull_area(&[]), 0.0);
    }

    #[test]
    fn test_single_point() {
        assert_eq!(convex_hull_area(&[[1.0, 1.0]]), 0.0);
    }

    #[test]
    fn test_two_points() {
        assert_eq!(convex_hull_area(&[[0.0, 0.0], [1.0, 1.0]]), 0.0);
    }

    #[test]
    fn test_two_distinct_plus_duplicates() {
        // Duplicates don't add a third distinct direction -- still degenerate.
        let pts = [[0.0, 0.0], [0.0, 0.0], [1.0, 1.0], [1.0, 1.0]];
        assert_eq!(convex_hull_area(&pts), 0.0);
    }

    #[test]
    fn test_all_duplicate_points() {
        let pts = [[3.0, 3.0]; 5];
        assert_eq!(convex_hull_area(&pts), 0.0);
    }

    #[test]
    fn test_collinear_points() {
        // All on the line y = x -- zero-width hull, zero area.
        let pts = [[0.0, 0.0], [1.0, 1.0], [2.0, 2.0], [3.0, 3.0], [0.5, 0.5]];
        assert_eq!(convex_hull_area(&pts), 0.0);
    }

    #[test]
    fn test_collinear_axis_aligned() {
        let pts = [[0.0, 5.0], [1.0, 5.0], [2.0, 5.0], [10.0, 5.0]];
        assert_eq!(convex_hull_area(&pts), 0.0);
    }

    #[test]
    fn test_unit_right_triangle() {
        let pts = [[0.0, 0.0], [1.0, 0.0], [0.0, 1.0]];
        assert!(approx_eq(convex_hull_area(&pts), 0.5, 1e-12));
    }

    #[test]
    fn test_unit_square() {
        let pts = [[0.0, 0.0], [1.0, 0.0], [1.0, 1.0], [0.0, 1.0]];
        assert!(approx_eq(convex_hull_area(&pts), 1.0, 1e-12));
    }

    #[test]
    fn test_square_with_interior_point() {
        // Interior points must not affect the hull area.
        let pts = [
            [0.0, 0.0],
            [4.0, 0.0],
            [4.0, 4.0],
            [0.0, 4.0],
            [2.0, 2.0],
            [1.0, 1.0],
            [3.0, 3.0],
        ];
        assert!(approx_eq(convex_hull_area(&pts), 16.0, 1e-9));
    }

    #[test]
    fn test_square_with_duplicate_corners() {
        let pts = [
            [0.0, 0.0],
            [0.0, 0.0],
            [4.0, 0.0],
            [4.0, 4.0],
            [4.0, 4.0],
            [0.0, 4.0],
        ];
        assert!(approx_eq(convex_hull_area(&pts), 16.0, 1e-9));
    }

    #[test]
    fn test_regular_hexagon_shoelace_cross_check() {
        // Independent shoelace reference on the hexagon's own vertices
        // (already known convex + already in order), cross-checked against
        // the hull area computed from the same points in scrambled order.
        let r = 2.0_f64;
        let mut hex = Vec::new();
        for i in 0..6 {
            let theta = std::f64::consts::PI / 3.0 * i as f64;
            hex.push([r * theta.cos(), r * theta.sin()]);
        }
        let shoelace = {
            let mut acc = 0.0;
            for i in 0..hex.len() {
                let (x1, y1) = (hex[i][0], hex[i][1]);
                let (x2, y2) = (hex[(i + 1) % hex.len()][0], hex[(i + 1) % hex.len()][1]);
                acc += x1 * y2 - x2 * y1;
            }
            (acc / 2.0).abs()
        };
        // Scramble order and duplicate one vertex to exercise robustness.
        let mut scrambled = vec![hex[3], hex[0], hex[5], hex[1], hex[1], hex[4], hex[2]];
        scrambled.push(hex[0]);
        let got = convex_hull_area(&scrambled);
        assert!(
            approx_eq(got, shoelace, 1e-9),
            "got {got}, want {shoelace}"
        );
    }

    #[test]
    fn test_point_order_does_not_matter() {
        let pts_a = [[0.0, 0.0], [4.0, 0.0], [4.0, 4.0], [0.0, 4.0]];
        let mut pts_b = pts_a;
        pts_b.reverse();
        assert_eq!(convex_hull_area(&pts_a), convex_hull_area(&pts_b));
    }

    #[test]
    fn test_negative_coordinates() {
        let pts = [[-2.0, -2.0], [2.0, -2.0], [2.0, 2.0], [-2.0, 2.0]];
        assert!(approx_eq(convex_hull_area(&pts), 16.0, 1e-9));
    }

    #[test]
    fn test_large_random_point_cloud_matches_independent_reference() {
        // Independent O(n^2) gift-wrapping reference, structurally unrelated
        // to `geo`'s QuickHull, cross-checked before ever comparing against
        // scipy (that comparison is the separate Python differential
        // harness) -- same discipline as radius_pairs.rs's brute-force
        // cross-check.
        let mut state: u64 = 0xD1B54A32D192ED03;
        let mut next_f64 = move || {
            state ^= state << 13;
            state ^= state >> 7;
            state ^= state << 17;
            (state >> 11) as f64 / (1u64 << 53) as f64
        };
        for trial in 0..6 {
            let n = 20 + trial * 10;
            let pts: Vec<[f64; 2]> = (0..n)
                .map(|_| [next_f64() * 50.0 - 25.0, next_f64() * 50.0 - 25.0])
                .collect();
            let got = convex_hull_area(&pts);
            let want = gift_wrap_area(&pts);
            assert!(
                approx_eq(got, want, 1e-6 * want.max(1.0)),
                "trial {trial}: got {got}, want {want}"
            );
        }
    }

    /// Independent O(n^2 log n) gift-wrapping convex hull + shoelace area,
    /// used only inside this test module as a cross-check oracle.
    fn gift_wrap_area(points: &[[f64; 2]]) -> f64 {
        let mut unique: Vec<[f64; 2]> = Vec::new();
        for &p in points {
            if !unique.iter().any(|&q| q == p) {
                unique.push(p);
            }
        }
        if unique.len() < 3 {
            return 0.0;
        }
        // Start from the lowest-y (then lowest-x) point.
        let start_idx = (0..unique.len())
            .min_by(|&a, &b| {
                unique[a][1]
                    .partial_cmp(&unique[b][1])
                    .unwrap()
                    .then(unique[a][0].partial_cmp(&unique[b][0]).unwrap())
            })
            .unwrap();

        let mut hull = vec![unique[start_idx]];
        let mut current = start_idx;
        loop {
            let mut candidate = if current == 0 { 1 % unique.len() } else { 0 };
            if candidate == current {
                candidate = (candidate + 1) % unique.len();
            }
            for i in 0..unique.len() {
                if i == current {
                    continue;
                }
                let cross = cross_product(unique[current], unique[candidate], unique[i]);
                if cross < 0.0 {
                    candidate = i;
                }
            }
            if candidate == start_idx {
                break;
            }
            hull.push(unique[candidate]);
            current = candidate;
            if hull.len() > unique.len() {
                // Degenerate (e.g. all collinear) -- bail with zero area.
                return 0.0;
            }
        }

        if hull.len() < 3 {
            return 0.0;
        }
        let mut acc = 0.0;
        for i in 0..hull.len() {
            let (x1, y1) = (hull[i][0], hull[i][1]);
            let (x2, y2) = (hull[(i + 1) % hull.len()][0], hull[(i + 1) % hull.len()][1]);
            acc += x1 * y2 - x2 * y1;
        }
        (acc / 2.0).abs()
    }

    fn cross_product(o: [f64; 2], a: [f64; 2], b: [f64; 2]) -> f64 {
        (a[0] - o[0]) * (b[1] - o[1]) - (a[1] - o[1]) * (b[0] - o[0])
    }
}
