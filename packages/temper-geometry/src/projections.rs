// =============================================================================
// Projection operators for geometric constraint satisfaction
// =============================================================================
//
// Ported from Python's `temper_placer/geometry/projections.py`.
//
// Each function projects a point onto a geometric constraint set, returning
// the nearest valid point (or the point itself if already valid).

use crate::types::*;

// =============================================================================
// Identity Projection
// =============================================================================

/// Pass-through for fixed positions — returns the point unchanged.
pub fn identity_projection(p: &Point) -> Point {
    *p
}

// =============================================================================
// Board Bounds Projection
// =============================================================================

/// Project a point onto the board interior with edge margin.
///
/// Clamps each coordinate independently to [margin, board_dim - margin].
pub fn project_onto_board(p: &Point, board_w: f64, board_h: f64, margin: f64) -> Point {
    let x = p.x.clamp(margin, board_w - margin);
    let y = p.y.clamp(margin, board_h - margin);
    Point::new(x, y)
}

// =============================================================================
// Zone Containment Projection
// =============================================================================

/// Project a point onto a rectangular zone interior.
///
/// If the point is inside the zone, returns it unchanged. Otherwise, clamps
/// to the nearest point on the zone boundary.
pub fn project_onto_zone(p: &Point, zone: &Rect) -> Point {
    if zone.contains_point(p) {
        return *p;
    }
    let x = p.x.clamp(zone.x, zone.x + zone.w);
    let y = p.y.clamp(zone.y, zone.y + zone.h);
    Point::new(x, y)
}

// =============================================================================
// Keepout Avoidance Projection
// =============================================================================

/// Project a point outside a keepout axis-aligned rectangle.
///
/// The keepout rect is expanded outward by the component half-size, so the
/// component body stays entirely outside. The nearest boundary point of the
/// expanded rect is found and the point is snapped there.
///
/// If the point is already outside the expanded keepout, returns it unchanged.
pub fn project_outside_keepout(p: &Point, keepout: &Rect, half_w: f64, half_h: f64) -> Point {
    // Expand keepout by component half-size
    let ex_min = keepout.x - half_w;
    let ex_max = keepout.x + keepout.w + half_w;
    let ey_min = keepout.y - half_h;
    let ey_max = keepout.y + keepout.h + half_h;

    // Is the point inside the expanded keepout?
    let inside = p.x >= ex_min && p.x <= ex_max && p.y >= ey_min && p.y <= ey_max;

    if !inside {
        return *p;
    }

    // Four candidate projection points (one per edge of expanded rect)
    let candidates = [
        Point::new(ex_min, p.y.clamp(ey_min, ey_max)), // left
        Point::new(ex_max, p.y.clamp(ey_min, ey_max)), // right
        Point::new(p.x.clamp(ex_min, ex_max), ey_min), // bottom
        Point::new(p.x.clamp(ex_min, ex_max), ey_max), // top
    ];

    let mut best_idx = 0;
    let mut best_dist_sq = candidates[0].distance_squared(p);
    for (i, candidate) in candidates.iter().enumerate().skip(1) {
        let d2 = candidate.distance_squared(p);
        if d2 < best_dist_sq {
            best_dist_sq = d2;
            best_idx = i;
        }
    }

    candidates[best_idx]
}

// =============================================================================
// Half-Plane Projection
// =============================================================================

/// Project a point onto a feasible half-plane.
///
/// The half-plane is defined as {q | (q - origin) · normal >= 0}. If the
/// point is on the violating side, it is projected orthogonally onto the
/// boundary line. A degenerate (zero-length) normal is treated as a no-op.
pub fn project_onto_half_plane(p: &Point, origin: &Point, normal: &Vec2) -> Point {
    let to_p = Vec2 {
        x: p.x - origin.x,
        y: p.y - origin.y,
    };
    let dot = normal.dot(&to_p);
    if dot >= 0.0 {
        return *p;
    }
    let denom = normal.length_squared();
    if denom < 1e-15 {
        return *p; // degenerate normal — no meaningful half-plane
    }
    // Project orthogonally onto the boundary line
    let t = dot / denom;
    Point::new(p.x - t * normal.x, p.y - t * normal.y)
}

// =============================================================================
// Edge Strip Projection
// =============================================================================

/// Project a point onto an edge-adjacent mounting strip.
///
/// The strip extends ``strip_width`` perpendicularly from the edge segment
/// (edge_start → edge_end) on both sides. Points within the strip are
/// returned unchanged; points beyond are clamped perpendicularly to the
/// strip boundary.
///
/// For a degenerate segment (start == end), the strip becomes a disc of
/// radius ``strip_width`` around that point.
pub fn project_onto_edge_strip(
    p: &Point,
    edge_start: &Point,
    edge_end: &Point,
    strip_width: f64,
) -> Point {
    let seg = Segment::new(*edge_start, *edge_end);
    let nearest = seg.nearest_point(p);
    let offset = Vec2 {
        x: p.x - nearest.x,
        y: p.y - nearest.y,
    };
    let dist = offset.length();
    if dist <= strip_width {
        return *p;
    }
    if dist < 1e-15 {
        // Point is exactly on the edge (or degenerate segment).
        // Push perpendicularly by strip_width.
        let edge_dir = Vec2 {
            x: edge_end.x - edge_start.x,
            y: edge_end.y - edge_start.y,
        };
        let edge_len = edge_dir.length();
        if edge_len < 1e-15 {
            return *p; // point-like edge; keep as-is
        }
        // Perpendicular direction (90° CCW rotation of unit edge direction)
        let perp = Vec2 {
            x: -edge_dir.y / edge_len,
            y: edge_dir.x / edge_len,
        };
        return Point::new(
            nearest.x + perp.x * strip_width,
            nearest.y + perp.y * strip_width,
        );
    }
    // Clamp perpendicular distance to strip_width
    let scale = strip_width / dist;
    Point::new(
        nearest.x + offset.x * scale,
        nearest.y + offset.y * scale,
    )
}

// =============================================================================
// Manufacturing Side Projection
// =============================================================================

/// Project a point onto a manufacturing side of the board.
///
/// "top" side constrains y <= board_h / 2, "bottom" side constrains
/// y >= board_h / 2.
///
/// # Panics
///
/// Panics if ``side`` is not "top" or "bottom".
pub fn project_onto_side(p: &Point, _board_w: f64, board_h: f64, side: &str) -> Point {
    let midline = board_h / 2.0;
    match side {
        "top" => Point::new(p.x, p.y.min(midline)),
        "bottom" => Point::new(p.x, p.y.max(midline)),
        _ => panic!("Invalid side '{side}'. Must be 'top' or 'bottom'."),
    }
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    const EPS: f64 = 1e-12;

    // -----------------------------------------------------------------
    // Identity projection
    // -----------------------------------------------------------------
    #[test]
    fn test_identity_projection_returns_same_point() {
        let p = Point::new(3.0, 4.0);
        let result = identity_projection(&p);
        assert!((result.x - 3.0).abs() < EPS);
        assert!((result.y - 4.0).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // project_onto_board
    // -----------------------------------------------------------------
    #[test]
    fn test_project_onto_board_outside_clamped() {
        // Point outside board — should clamp to margin-bounded edge
        let result = project_onto_board(&Point::new(-10.0, 50.0), 100.0, 100.0, 5.0);
        assert!((result.x - 5.0).abs() < EPS, "expected x=5.0, got {}", result.x);
        assert!((result.y - 50.0).abs() < EPS);
    }

    #[test]
    fn test_project_onto_board_inside_unchanged() {
        // Point inside board — should remain unchanged
        let result = project_onto_board(&Point::new(50.0, 50.0), 100.0, 100.0, 5.0);
        assert!((result.x - 50.0).abs() < EPS);
        assert!((result.y - 50.0).abs() < EPS);
    }

    #[test]
    fn test_project_onto_board_clamps_both_axes() {
        let result = project_onto_board(&Point::new(-20.0, 200.0), 100.0, 100.0, 10.0);
        assert!((result.x - 10.0).abs() < EPS);
        assert!((result.y - 90.0).abs() < EPS, "expected y=90.0, got {}", result.y);
    }

    // -----------------------------------------------------------------
    // project_onto_zone
    // -----------------------------------------------------------------
    #[test]
    fn test_project_onto_zone_outside_projected() {
        let zone = Rect::new(0.0, 0.0, 10.0, 10.0);
        // Point outside to the right — should clamp to right edge
        let result = project_onto_zone(&Point::new(15.0, 5.0), &zone);
        assert!((result.x - 10.0).abs() < EPS);
        assert!((result.y - 5.0).abs() < EPS);
    }

    #[test]
    fn test_project_onto_zone_inside_unchanged() {
        let zone = Rect::new(0.0, 0.0, 10.0, 10.0);
        let result = project_onto_zone(&Point::new(5.0, 5.0), &zone);
        assert!((result.x - 5.0).abs() < EPS);
        assert!((result.y - 5.0).abs() < EPS);
    }

    #[test]
    fn test_project_onto_zone_outside_both_axes() {
        let zone = Rect::new(0.0, 0.0, 10.0, 10.0);
        let result = project_onto_zone(&Point::new(15.0, 15.0), &zone);
        assert!((result.x - 10.0).abs() < EPS);
        assert!((result.y - 10.0).abs() < EPS);
    }

    #[test]
    fn test_project_onto_zone_outside_left() {
        let zone = Rect::new(0.0, 0.0, 10.0, 10.0);
        let result = project_onto_zone(&Point::new(-5.0, 5.0), &zone);
        assert!((result.x - 0.0).abs() < EPS);
        assert!((result.y - 5.0).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // project_outside_keepout
    // -----------------------------------------------------------------
    #[test]
    fn test_project_outside_keepout_already_outside() {
        let keepout = Rect::new(0.0, 0.0, 10.0, 10.0);
        let result = project_outside_keepout(&Point::new(50.0, 50.0), &keepout, 0.0, 0.0);
        assert!((result.x - 50.0).abs() < EPS);
        assert!((result.y - 50.0).abs() < EPS);
    }

    #[test]
    fn test_project_outside_keepout_inside_snapped() {
        let keepout = Rect::new(0.0, 0.0, 10.0, 10.0);
        // Point at center of keepout — nearest edge is left or bottom (both at 0)
        let result = project_outside_keepout(&Point::new(5.0, 5.0), &keepout, 0.0, 0.0);
        // The nearest candidate is either left (0, 5) or bottom (5, 0), both at dist=5
        // Check that it's exactly on one of the expanded rect edges
        let on_edge = (result.x - 0.0).abs() < EPS
            || (result.x - 10.0).abs() < EPS
            || (result.y - 0.0).abs() < EPS
            || (result.y - 10.0).abs() < EPS;
        assert!(on_edge, "result ({}, {}) not on keepout edge", result.x, result.y);
    }

    #[test]
    fn test_project_outside_keepout_with_half_size() {
        let keepout = Rect::new(0.0, 0.0, 10.0, 10.0);
        // With half_w=1, half_h=1, the expanded rect is (-1, -1, 11, 11)
        // Point (0, 0) is inside expanded rect. Nearest candidate should be (-1, 0) or (0, -1)
        let result = project_outside_keepout(&Point::new(0.0, 0.0), &keepout, 1.0, 1.0);
        let on_edge = (result.x - (-1.0)).abs() < EPS
            || (result.x - 11.0).abs() < EPS
            || (result.y - (-1.0)).abs() < EPS
            || (result.y - 11.0).abs() < EPS;
        assert!(on_edge, "result ({}, {}) not on expanded keepout edge", result.x, result.y);
    }

    // -----------------------------------------------------------------
    // project_onto_half_plane
    // -----------------------------------------------------------------
    #[test]
    fn test_project_onto_half_plane_already_feasible() {
        // Half-plane: y >= 5 (normal=(0,1), origin=(0,5))
        let origin = Point::new(0.0, 5.0);
        let normal = Vec2 { x: 0.0, y: 1.0 };
        let result = project_onto_half_plane(&Point::new(10.0, 10.0), &origin, &normal);
        assert!((result.x - 10.0).abs() < EPS);
        assert!((result.y - 10.0).abs() < EPS);
    }

    #[test]
    fn test_project_onto_half_plane_violating_reflected() {
        // Half-plane: y >= 5, point at y=0 — should project to y=5
        let origin = Point::new(0.0, 5.0);
        let normal = Vec2 { x: 0.0, y: 1.0 };
        let result = project_onto_half_plane(&Point::new(10.0, 0.0), &origin, &normal);
        assert!((result.x - 10.0).abs() < EPS, "expected x=10.0, got {}", result.x);
        assert!((result.y - 5.0).abs() < EPS, "expected y=5.0, got {}", result.y);
    }

    #[test]
    fn test_project_onto_half_plane_diagonal_normal() {
        // Half-plane: x >= y (normal=(1,-1), origin=(0,0))
        // Boundary line: x - y = 0. Feasible: x - y >= 0.
        let origin = Point::new(0.0, 0.0);
        let normal = Vec2 { x: 1.0, y: -1.0 };
        // Point (-5, -3): dot = (-5, -3)·(1,-1) = -5 + 3 = -2 < 0 → violating
        let result = project_onto_half_plane(&Point::new(-5.0, -3.0), &origin, &normal);
        // Project onto x - y = 0 via the line: param t = dot/|n|² = -2/2 = -1
        // p' = p - t * normal = (-5, -3) - (-1)*(1,-1) = (-5, -3) + (1,-1) = (-4, -4)
        // Check: -4 - (-4) = 0 ✓. Distance from p: |(-4)-(-5), (-4)-(-3)| = |1, -1| = sqrt(2)
        assert!((result.x - (-4.0)).abs() < EPS, "expected x=-4.0, got {}", result.x);
        assert!((result.y - (-4.0)).abs() < EPS, "expected y=-4.0, got {}", result.y);
    }

    #[test]
    fn test_project_onto_half_plane_degenerate_normal() {
        let origin = Point::new(0.0, 5.0);
        let normal = Vec2 { x: 0.0, y: 0.0 };
        let result = project_onto_half_plane(&Point::new(10.0, 0.0), &origin, &normal);
        assert!((result.x - 10.0).abs() < EPS);
        assert!((result.y - 0.0).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // project_onto_edge_strip
    // -----------------------------------------------------------------
    #[test]
    fn test_project_onto_edge_strip_inside_unchanged() {
        // Edge from (0, 0) to (0, 10), strip_width = 5
        // Point at (2, 5) is within the strip — should be unchanged
        let result = project_onto_edge_strip(
            &Point::new(2.0, 5.0),
            &Point::new(0.0, 0.0),
            &Point::new(0.0, 10.0),
            5.0,
        );
        assert!((result.x - 2.0).abs() < EPS);
        assert!((result.y - 5.0).abs() < EPS);
    }

    #[test]
    fn test_project_onto_edge_strip_outside_clamped() {
        // Edge from (0, 0) to (0, 10), strip_width = 5
        // Point at (10, 5) is beyond strip_width — should clamp to (5, 5)
        let result = project_onto_edge_strip(
            &Point::new(10.0, 5.0),
            &Point::new(0.0, 0.0),
            &Point::new(0.0, 10.0),
            5.0,
        );
        assert!((result.x - 5.0).abs() < EPS, "expected x=5.0, got {}", result.x);
        assert!((result.y - 5.0).abs() < EPS);
    }

    #[test]
    fn test_project_onto_edge_strip_beyond_endpoint() {
        // Edge from (0, 0) to (10, 0), strip_width = 3
        // Point at (5, 10) — nearest on edge is (5, 0), dist=10 > 3, clamp to (5, 3)
        let result = project_onto_edge_strip(
            &Point::new(5.0, 10.0),
            &Point::new(0.0, 0.0),
            &Point::new(10.0, 0.0),
            3.0,
        );
        assert!((result.x - 5.0).abs() < EPS);
        assert!((result.y - 3.0).abs() < EPS, "expected y=3.0, got {}", result.y);
    }

    // -----------------------------------------------------------------
    // project_onto_side
    // -----------------------------------------------------------------
    #[test]
    fn test_project_onto_side_top_inside() {
        let result = project_onto_side(&Point::new(10.0, 20.0), 100.0, 100.0, "top");
        assert!((result.x - 10.0).abs() < EPS);
        assert!((result.y - 20.0).abs() < EPS);
    }

    #[test]
    fn test_project_onto_side_bottom_inside() {
        let result = project_onto_side(&Point::new(10.0, 80.0), 100.0, 100.0, "bottom");
        assert!((result.x - 10.0).abs() < EPS);
        assert!((result.y - 80.0).abs() < EPS);
    }

    #[test]
    fn test_project_onto_side_top_from_bottom() {
        let result = project_onto_side(&Point::new(10.0, 80.0), 100.0, 100.0, "top");
        // midline = 50, clamp y to max 50
        assert!((result.x - 10.0).abs() < EPS);
        assert!((result.y - 50.0).abs() < EPS, "expected y=50.0, got {}", result.y);
    }

    #[test]
    fn test_project_onto_side_bottom_from_top() {
        let result = project_onto_side(&Point::new(10.0, 20.0), 100.0, 100.0, "bottom");
        // midline = 50, clamp y to min 50
        assert!((result.x - 10.0).abs() < EPS);
        assert!((result.y - 50.0).abs() < EPS, "expected y=50.0, got {}", result.y);
    }

    #[test]
    #[should_panic(expected = "Invalid side")]
    fn test_project_onto_side_invalid_panics() {
        project_onto_side(&Point::new(0.0, 0.0), 100.0, 100.0, "invalid");
    }
}
