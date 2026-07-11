// =============================================================================
// Signed Distance Functions (SDF) for temper-geometry
// =============================================================================
//
// Ported from Python's `temper_placer/geometry/sdf.py`.
//
// An SDF returns:
// - Negative value: point is inside the shape (distance to nearest boundary)
// - Zero: point is on the boundary
// - Positive value: point is outside the shape (distance to nearest boundary)
//
// All functions take a query `Point` + shape parameters and return `f64`.

use temper_geometry_core::types::*;
use crate::polygon::*;

// =============================================================================
// Basic Shape SDFs
// =============================================================================

/// Signed distance function for a circle.
pub fn sdf_circle(p: &Point, cx: f64, cy: f64, r: f64) -> f64 {
    let dx = p.x - cx;
    let dy = p.y - cy;
    (dx * dx + dy * dy).sqrt() - r
}

/// Signed distance function for an axis-aligned rectangle.
pub fn sdf_rectangle(p: &Point, cx: f64, cy: f64, half_w: f64, half_h: f64) -> f64 {
    let dx = (p.x - cx).abs() - half_w;
    let dy = (p.y - cy).abs() - half_h;

    // Outside distance: sqrt of squared positive components
    let outside = (dx.max(0.0).powi(2) + dy.max(0.0).powi(2)).sqrt();

    // Inside distance: negative of min distance to edge
    let inside = dx.max(dy).min(0.0);

    outside + inside
}

/// SDF for an axis-aligned box centered at a given point.
pub fn sdf_box_2d(p: &Point, center: &Point, half_size: &Point) -> f64 {
    let dx = (p.x - center.x).abs() - half_size.x;
    let dy = (p.y - center.y).abs() - half_size.y;

    let outside = (dx.max(0.0).powi(2) + dy.max(0.0).powi(2)).sqrt();
    let inside = dx.max(dy).min(0.0);

    outside + inside
}

/// SDF for a rectangle with rounded corners.
pub fn sdf_rounded_rectangle(
    p: &Point,
    cx: f64,
    cy: f64,
    half_w: f64,
    half_h: f64,
    r: f64,
) -> f64 {
    // Clamp corner radius to valid range
    let r_clamped = r.min(half_w.min(half_h));

    // Shrink the rectangle by the corner radius, then round the corners
    let dx = (p.x - cx).abs() - (half_w - r_clamped);
    let dy = (p.y - cy).abs() - (half_h - r_clamped);

    // Distance to rounded edge
    let outside = (dx.max(0.0).powi(2) + dy.max(0.0).powi(2)).sqrt();
    let inside = dx.max(dy).min(0.0);

    outside + inside - r_clamped
}

/// SDF for a capsule (line segment with radius).
///
/// Useful for representing traces or elongated keepout zones.
pub fn sdf_capsule(p: &Point, a: &Point, b: &Point, r: f64) -> f64 {
    let abx = b.x - a.x;
    let aby = b.y - a.y;
    let apx = p.x - a.x;
    let apy = p.y - a.y;

    // Project point onto line, clamped to segment
    let ab_len_sq = abx * abx + aby * aby;
    let t = if ab_len_sq > 1e-15 {
        (apx * abx + apy * aby) / ab_len_sq
    } else {
        0.0
    };
    let t_clamped = t.clamp(0.0, 1.0);

    // Closest point on segment
    let closest_x = a.x + t_clamped * abx;
    let closest_y = a.y + t_clamped * aby;

    // Distance to closest point, minus radius
    let dx = p.x - closest_x;
    let dy = p.y - closest_y;
    (dx * dx + dy * dy).sqrt() - r
}

// =============================================================================
// Polygon SDF
// =============================================================================

/// SDF for a convex or concave polygon using the winding number approach.
///
/// Returns the signed distance to the nearest edge, with sign determined by
/// the winding number (non-zero = inside).
pub fn sdf_polygon(p: &Point, vertices: &[Point]) -> f64 {
    let n = vertices.len();
    if n < 3 {
        return f64::INFINITY;
    }

    let mut min_dist_sq = f64::INFINITY;
    let mut winding: i32 = 0;

    for i in 0..n {
        let j = (i + 1) % n;
        let vi = &vertices[i];
        let vj = &vertices[j];

        let edge_x = vj.x - vi.x;
        let edge_y = vj.y - vi.y;
        let to_px = p.x - vi.x;
        let to_py = p.y - vi.y;

        // Project point onto edge line, clamped to edge
        let edge_len_sq = edge_x * edge_x + edge_y * edge_y;
        let t = if edge_len_sq > 1e-15 {
            ((to_px * edge_x + to_py * edge_y) / edge_len_sq).clamp(0.0, 1.0)
        } else {
            0.0
        };

        // Closest point on edge
        let closest_x = vi.x + t * edge_x;
        let closest_y = vi.y + t * edge_y;

        // Distance squared to closest point
        let d_sq = (p.x - closest_x).powi(2) + (p.y - closest_y).powi(2);
        if d_sq < min_dist_sq {
            min_dist_sq = d_sq;
        }

        // Winding number contribution
        let cross = edge_x * to_py - edge_y * to_px;

        if p.y >= vi.y && p.y < vj.y && cross > 0.0 {
            winding += 1;
        }
        if p.y < vi.y && p.y >= vj.y && cross < 0.0 {
            winding -= 1;
        }
    }

    // Sign based on winding number (non-zero = inside)
    let sign = if winding != 0 { -1.0 } else { 1.0 };
    sign * min_dist_sq.sqrt()
}

/// SDF for a convex polygon (simpler and faster than general polygon).
///
/// Uses the property that for a CCW polygon, a point is inside iff it is on
/// the same side (negative signed distance) of all edges.
pub fn sdf_convex_polygon(p: &Point, vertices: &[Point]) -> f64 {
    let n = vertices.len();
    if n < 3 {
        return f64::INFINITY;
    }

    let mut max_dist = f64::NEG_INFINITY;

    for i in 0..n {
        let j = (i + 1) % n;
        let vi = &vertices[i];
        let vj = &vertices[j];

        // Edge vector
        let edge_x = vj.x - vi.x;
        let edge_y = vj.y - vi.y;

        // Inward normal for CCW polygon (pointing inward: (edge.y, -edge.x))
        let nx = edge_y;
        let ny = -edge_x;

        let len = (nx * nx + ny * ny).sqrt();
        if len < 1e-15 {
            continue;
        }

        // Signed distance to infinite line (positive = outside)
        let d = ((p.x - vi.x) * nx + (p.y - vi.y) * ny) / len;

        if d > max_dist {
            max_dist = d;
        }
    }

    max_dist
}

// =============================================================================
// SDF Combination Operations
// =============================================================================

/// Union of two SDFs (combines shapes).
///
/// Point is inside result if inside either shape.
pub fn sdf_union(d1: f64, d2: f64) -> f64 {
    d1.min(d2)
}

/// Intersection of two SDFs.
///
/// Point is inside result if inside both shapes.
pub fn sdf_intersection(d1: f64, d2: f64) -> f64 {
    d1.max(d2)
}

/// Subtraction of SDFs (d1 minus d2).
///
/// Point is inside result if inside d1 and outside d2.
pub fn sdf_subtraction(d1: f64, d2: f64) -> f64 {
    d1.max(-d2)
}

/// Smooth union of two SDFs with blending.
///
/// Creates a smooth blend between shapes instead of sharp union.
/// `k` controls the blending radius (larger = smoother).
pub fn sdf_smooth_union(d1: f64, d2: f64, k: f64) -> f64 {
    let h = (0.5 + 0.5 * (d2 - d1) / k).clamp(0.0, 1.0);
    d2 * (1.0 - h) + d1 * h - k * h * (1.0 - h)
}

/// Smooth intersection of two SDFs with blending.
pub fn sdf_smooth_intersection(d1: f64, d2: f64, k: f64) -> f64 {
    let h = (0.5 - 0.5 * (d2 - d1) / k).clamp(0.0, 1.0);
    d2 * (1.0 - h) + d1 * h + k * h * (1.0 - h)
}

// =============================================================================
// SDF Modifications
// =============================================================================

/// Offset (dilate/erode) an SDF.
///
/// Positive offset makes shape larger (dilation).
/// Negative offset makes shape smaller (erosion).
pub fn sdf_offset(d: f64, offset: f64) -> f64 {
    d - offset
}

/// Round the corners of an SDF shape.
///
/// Equivalent to Minkowski sum with a circle of given radius.
pub fn sdf_round(d: f64, r: f64) -> f64 {
    d - r
}

/// Create a shell (hollow version) of an SDF shape.
pub fn sdf_shell(d: f64, thickness: f64) -> f64 {
    d.abs() - thickness * 0.5
}

// =============================================================================
// Utility Functions
// =============================================================================

/// Convert SDF distances to a soft mask (0 outside, 1 inside).
///
/// Uses sigmoid for smooth transition. `threshold` controls the width of
/// the transition region (smaller = sharper).
pub fn sdf_to_mask(distances: &[f64], threshold: f64) -> Vec<f64> {
    distances
        .iter()
        .map(|&d| 1.0 / (1.0 + (d / threshold).exp()))
        .collect()
}

/// Convert SDF distances to a penalty value for being inside a shape.
///
/// Returns positive penalty when inside (d < 0), zero when outside.
/// Uses softplus for smooth ReLU transition. `alpha` controls the
/// sharpness of the transition.
pub fn sdf_to_penalty(distances: &[f64], alpha: f64) -> Vec<f64> {
    distances
        .iter()
        .map(|&d| (1.0 + (-alpha * d).exp()).ln() / alpha)
        .collect()
}

/// Compute the gradient of an SDF at a point using finite differences.
///
/// Returns a normalized gradient `(gx, gy)`. The gradient of an exact SDF
/// has magnitude 1 and points away from the shape.
pub fn sdf_gradient(p: &Point, sdf_fn: fn(&Point) -> f64, eps: f64) -> (f64, f64) {
    let f0 = sdf_fn(p);
    let gx = (sdf_fn(&Point::new(p.x + eps, p.y)) - f0) / eps;
    let gy = (sdf_fn(&Point::new(p.x, p.y + eps)) - f0) / eps;
    let mag = (gx * gx + gy * gy).sqrt().max(1e-15);
    (gx / mag, gy / mag)
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    const EPS: f64 = 1e-9;

    // -----------------------------------------------------------------
    // sdf_circle
    // -----------------------------------------------------------------
    #[test]
    fn test_sdf_circle_center() {
        let p = Point::new(0.0, 0.0);
        let d = sdf_circle(&p, 0.0, 0.0, 5.0);
        assert!((d - (-5.0)).abs() < EPS, "center should be -r, got {d}");
    }

    #[test]
    fn test_sdf_circle_at_radius() {
        let p = Point::new(5.0, 0.0);
        let d = sdf_circle(&p, 0.0, 0.0, 5.0);
        assert!(d.abs() < EPS, "on boundary should be ~0, got {d}");
    }

    #[test]
    fn test_sdf_circle_far() {
        let p = Point::new(10.0, 0.0);
        let d = sdf_circle(&p, 0.0, 0.0, 5.0);
        assert!((d - 5.0).abs() < EPS, "outside by 5 should be 5, got {d}");
    }

    // -----------------------------------------------------------------
    // sdf_rectangle
    // -----------------------------------------------------------------
    #[test]
    fn test_sdf_rectangle_center() {
        // 10x6 rectangle centered at origin: nearest edge is 3 away
        let p = Point::new(0.0, 0.0);
        let d = sdf_rectangle(&p, 0.0, 0.0, 5.0, 3.0);
        assert!(d < 0.0, "center should be negative, got {d}");
        assert!((d - (-3.0)).abs() < EPS, "expected -3.0, got {d}");
    }

    #[test]
    fn test_sdf_rectangle_corner() {
        // 10x6 rect at origin, point just outside top-right corner
        let p = Point::new(6.0, 4.0);
        let d = sdf_rectangle(&p, 0.0, 0.0, 5.0, 3.0);
        assert!(d > 0.0, "outside corner should be positive, got {d}");
        let expected = (1.0f64.powi(2) + 1.0f64.powi(2)).sqrt();
        assert!((d - expected).abs() < EPS, "expected {expected}, got {d}");
    }

    // -----------------------------------------------------------------
    // sdf_union
    // -----------------------------------------------------------------
    #[test]
    fn test_sdf_union_two_circles() {
        // Two overlapping circles at (-2,0) and (2,0), each r=3
        // Point (0,0) is distance 2 from each center → SDF = 2-3 = -1 for each
        let p = Point::new(0.0, 0.0);
        let d1 = sdf_circle(&p, -2.0, 0.0, 3.0);
        let d2 = sdf_circle(&p, 2.0, 0.0, 3.0);
        let d = sdf_union(d1, d2);
        assert!((d - (-1.0)).abs() < EPS, "union should be min of distances, got {d}");
    }

    // -----------------------------------------------------------------
    // sdf_to_mask
    // -----------------------------------------------------------------
    #[test]
    fn test_sdf_to_mask_all_inside() {
        // All well-inside (negative) distances → mask should be ~1.0
        // With threshold=0.1, d=-1 → 1/(1+exp(-10)) ≈ 0.99995
        let distances = vec![-5.0, -3.0, -1.0];
        let mask = sdf_to_mask(&distances, 0.1);
        assert_eq!(mask.len(), 3);
        for &m in &mask {
            assert!(
                (m - 1.0).abs() < 0.01,
                "expected ~1.0 for inside, got {m}"
            );
        }
    }

    #[test]
    fn test_sdf_to_mask_all_outside() {
        // All outside (positive) distances → mask should be ~0.0
        let distances = vec![1.0, 3.0, 5.0];
        let mask = sdf_to_mask(&distances, 0.1);
        for &m in &mask {
            assert!(
                (m - 0.0).abs() < 0.01,
                "expected ~0.0 for outside, got {m}"
            );
        }
    }

    // -----------------------------------------------------------------
    // sdf_box_2d
    // -----------------------------------------------------------------
    #[test]
    fn test_sdf_box_2d_center() {
        let center = Point::new(2.0, 3.0);
        let half = Point::new(5.0, 4.0);
        let p = Point::new(2.0, 3.0);
        let d = sdf_box_2d(&p, &center, &half);
        assert!((d - (-4.0)).abs() < EPS, "expected -4.0, got {d}");
    }

    #[test]
    fn test_sdf_box_2d_outside() {
        let center = Point::new(0.0, 0.0);
        let half = Point::new(3.0, 3.0);
        let p = Point::new(5.0, 0.0);
        let d = sdf_box_2d(&p, &center, &half);
        assert!((d - 2.0).abs() < EPS, "expected 2.0, got {d}");
    }

    // -----------------------------------------------------------------
    // sdf_rounded_rectangle
    // -----------------------------------------------------------------
    #[test]
    fn test_sdf_rounded_rectangle_center() {
        let p = Point::new(0.0, 0.0);
        let d = sdf_rounded_rectangle(&p, 0.0, 0.0, 5.0, 3.0, 1.0);
        // At center: should be -min(5,3) = -3 (same as unrounded at center)
        assert!((d - (-3.0)).abs() < EPS, "expected -3.0, got {d}");
    }

    // -----------------------------------------------------------------
    // sdf_capsule
    // -----------------------------------------------------------------
    #[test]
    fn test_sdf_capsule_midpoint() {
        // Capsule from (0,0) to (0,10), radius 1
        // Point at (2, 5) should be distance 2-1 = 1 from capsule
        let a = Point::new(0.0, 0.0);
        let b = Point::new(0.0, 10.0);
        let p = Point::new(2.0, 5.0);
        let d = sdf_capsule(&p, &a, &b, 1.0);
        assert!((d - 1.0).abs() < EPS, "expected 1.0, got {d}");
    }

    #[test]
    fn test_sdf_capsule_on_surface() {
        let a = Point::new(0.0, 0.0);
        let b = Point::new(0.0, 10.0);
        let p = Point::new(1.0, 5.0);
        let d = sdf_capsule(&p, &a, &b, 1.0);
        assert!(d.abs() < EPS, "on surface should be ~0, got {d}");
    }

    // -----------------------------------------------------------------
    // sdf_polygon (triangle)
    // -----------------------------------------------------------------
    #[test]
    fn test_sdf_polygon_inside() {
        let tri = vec![
            Point::new(0.0, 0.0),
            Point::new(4.0, 0.0),
            Point::new(2.0, 3.0),
        ];
        let p = Point::new(2.0, 1.0);
        let d = sdf_polygon(&p, &tri);
        assert!(d < 0.0, "inside should be negative, got {d}");
    }

    #[test]
    fn test_sdf_polygon_outside() {
        let tri = vec![
            Point::new(0.0, 0.0),
            Point::new(4.0, 0.0),
            Point::new(2.0, 3.0),
        ];
        let p = Point::new(10.0, 10.0);
        let d = sdf_polygon(&p, &tri);
        assert!(d > 0.0, "outside should be positive, got {d}");
    }

    // -----------------------------------------------------------------
    // sdf_convex_polygon
    // -----------------------------------------------------------------
    #[test]
    fn test_sdf_convex_polygon_inside() {
        let sq = vec![
            Point::new(0.0, 0.0),
            Point::new(2.0, 0.0),
            Point::new(2.0, 2.0),
            Point::new(0.0, 2.0),
        ];
        let p = Point::new(1.0, 1.0);
        let d = sdf_convex_polygon(&p, &sq);
        assert!(d < 0.0, "inside should be negative, got {d}");
        // Nearest edge is at distance 1
        assert!((d - (-1.0)).abs() < EPS, "expected -1.0, got {d}");
    }

    #[test]
    fn test_sdf_convex_polygon_outside() {
        let sq = vec![
            Point::new(0.0, 0.0),
            Point::new(2.0, 0.0),
            Point::new(2.0, 2.0),
            Point::new(0.0, 2.0),
        ];
        let p = Point::new(3.0, 1.0);
        let d = sdf_convex_polygon(&p, &sq);
        assert!(d > 0.0, "outside should be positive, got {d}");
        assert!((d - 1.0).abs() < EPS, "expected 1.0, got {d}");
    }

    // -----------------------------------------------------------------
    // Boolean operations
    // -----------------------------------------------------------------
    #[test]
    fn test_sdf_intersection() {
        let d = sdf_intersection(-3.0, -1.0);
        assert!((d - (-1.0)).abs() < EPS);
    }

    #[test]
    fn test_sdf_subtraction() {
        // d1 - d2: inside d1 but outside d2
        let d = sdf_subtraction(-2.0, 3.0);
        assert!((d - (-2.0)).abs() < EPS, "expected -2.0, got {d}");
    }

    #[test]
    fn test_sdf_subtraction_clipped() {
        // If d2 is inside (negative), -d2 is positive, so max(d1, -d2) > d1
        let d = sdf_subtraction(-2.0, -1.0);
        assert!((d - 1.0).abs() < EPS, "expected 1.0, got {d}");
    }

    // -----------------------------------------------------------------
    // Smooth operations
    // -----------------------------------------------------------------
    #[test]
    fn test_sdf_smooth_union_sharp_limit() {
        // As k → 0, smooth union → sharp union (min)
        let d = sdf_smooth_union(-3.0, -1.0, 0.001);
        assert!((d - (-3.0)).abs() < 0.01, "expected ~-3.0, got {d}");
    }

    #[test]
    fn test_sdf_smooth_intersection_sharp_limit() {
        let d = sdf_smooth_intersection(-3.0, -1.0, 0.001);
        assert!((d - (-1.0)).abs() < 0.01, "expected ~-1.0, got {d}");
    }

    // -----------------------------------------------------------------
    // Modifications
    // -----------------------------------------------------------------
    #[test]
    fn test_sdf_offset_dilate() {
        let d = sdf_offset(-5.0, 2.0);
        assert!((d - (-7.0)).abs() < EPS, "offset dilate: expected -7.0, got {d}");
    }

    #[test]
    fn test_sdf_offset_erode() {
        let d = sdf_offset(-5.0, -2.0);
        assert!((d - (-3.0)).abs() < EPS, "offset erode: expected -3.0, got {d}");
    }

    #[test]
    fn test_sdf_round() {
        let d = sdf_round(-5.0, 1.0);
        assert!((d - (-6.0)).abs() < EPS, "expected -6.0, got {d}");
    }

    #[test]
    fn test_sdf_shell_inside() {
        // Inside a shape: shell thickness material centered at boundary
        // |-3| - 2/2 = 3 - 1 = 2 (still positive = inside shell material)
        let d = sdf_shell(-3.0, 2.0);
        assert!((d - 2.0).abs() < EPS, "expected 2.0, got {d}");
    }

    #[test]
    fn test_sdf_shell_outside() {
        let d = sdf_shell(5.0, 2.0);
        assert!((d - 4.0).abs() < EPS, "expected 4.0, got {d}");
    }

    // -----------------------------------------------------------------
    // sdf_to_penalty
    // -----------------------------------------------------------------
    #[test]
    fn test_sdf_to_penalty_inside() {
        let distances = vec![-1.0, -5.0];
        let penalty = sdf_to_penalty(&distances, 10.0);
        assert!(penalty[0] > 0.0, "inside should have positive penalty");
        assert!(penalty[1] > penalty[0], "deeper inside = larger penalty");
    }

    #[test]
    fn test_sdf_to_penalty_outside() {
        let distances = vec![1.0, 5.0];
        let penalty = sdf_to_penalty(&distances, 10.0);
        for &p in &penalty {
            assert!(p < 0.001, "outside should be ~0 penalty, got {p}");
        }
    }

    // -----------------------------------------------------------------
    // sdf_gradient
    // -----------------------------------------------------------------
    #[test]
    fn test_sdf_gradient_circle() {
        // Gradient of sdf_circle at (3, 4) from origin should point radially outward
        let sdf_circle_at_origin = |p: &Point| sdf_circle(p, 0.0, 0.0, 5.0);
        let (gx, gy) = sdf_gradient(&Point::new(3.0, 4.0), sdf_circle_at_origin, 1e-4);
        // Gradient should point in direction (3,4) normalized
        let mag = (3.0f64 * 3.0 + 4.0 * 4.0).sqrt();
        assert!((gx - 3.0 / mag).abs() < 0.01, "gx expected {:.4}, got {gx}", 3.0 / mag);
        assert!((gy - 4.0 / mag).abs() < 0.01, "gy expected {:.4}, got {gy}", 4.0 / mag);
    }

    // -----------------------------------------------------------------
    // Edge cases
    // -----------------------------------------------------------------
    #[test]
    fn test_sdf_polygon_empty() {
        let d = sdf_polygon(&Point::new(0.0, 0.0), &[]);
        assert!(d.is_infinite() && d > 0.0, "empty vertices should be INF");
    }

    #[test]
    fn test_sdf_convex_polygon_empty() {
        let d = sdf_convex_polygon(&Point::new(0.0, 0.0), &[]);
        assert!(d.is_infinite() && d > 0.0, "empty vertices should be INF");
    }

    #[test]
    fn test_sdf_capsule_degenerate() {
        // Degenerate capsule (start == end) should behave like a circle
        let a = Point::new(0.0, 0.0);
        let b = Point::new(0.0, 0.0);
        let p = Point::new(3.0, 0.0);
        let d = sdf_capsule(&p, &a, &b, 1.0);
        assert!((d - 2.0).abs() < EPS, "expected 2.0, got {d}");
    }

    #[test]
    fn test_sdf_rounded_rectangle_zero_radius() {
        let p = Point::new(0.0, 0.0);
        let d_round = sdf_rounded_rectangle(&p, 0.0, 0.0, 5.0, 3.0, 0.0);
        let d_rect = sdf_rectangle(&p, 0.0, 0.0, 5.0, 3.0);
        assert!((d_round - d_rect).abs() < EPS, "zero radius should match rect");
    }
}
