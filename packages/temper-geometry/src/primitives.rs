use crate::types::*;

// =============================================================================
// Point Operations
// =============================================================================

/// Euclidean distance between two points with an epsilon guard for numerical
/// stability. Without this guard, grad of sqrt(0) would be undefined.
pub fn point_distance(p1: &Point, p2: &Point) -> f64 {
    let dx = p2.x - p1.x;
    let dy = p2.y - p1.y;
    (dx * dx + dy * dy + 1e-12).sqrt()
}

/// Squared Euclidean distance between two points. Avoids the sqrt — more
/// efficient when comparing distances.
pub fn point_distance_squared(p1: &Point, p2: &Point) -> f64 {
    let dx = p2.x - p1.x;
    let dy = p2.y - p1.y;
    dx * dx + dy * dy
}

/// Midpoint between two points.
pub fn point_midpoint(p1: &Point, p2: &Point) -> Point {
    Point::new((p1.x + p2.x) * 0.5, (p1.y + p2.y) * 0.5)
}

/// Centroid (mean position) of a set of points. Returns (0, 0) for an empty
/// slice.
pub fn points_centroid(points: &[Point]) -> Point {
    let n = points.len();
    if n == 0 {
        return Point::zero();
    }
    let mut cx = 0.0;
    let mut cy = 0.0;
    for p in points {
        cx += p.x;
        cy += p.y;
    }
    Point::new(cx / n as f64, cy / n as f64)
}

/// Shortest distance from a point to a line segment.
pub fn point_to_line_distance(p: &Point, a: &Point, b: &Point) -> f64 {
    let seg = Segment::new(*a, *b);
    let nearest = seg.nearest_point(p);
    point_distance(p, &nearest)
}

// =============================================================================
// Rectangle Operations
// =============================================================================

/// Create a [`Rect`] from center point and half-dimensions.
pub fn rect_from_center(cx: f64, cy: f64, half_w: f64, half_h: f64) -> Rect {
    Rect::from_center(cx, cy, half_w, half_h)
}

/// Compute the center of a rectangle.
pub fn rect_center(r: &Rect) -> Point {
    r.center()
}

/// Compute (width, height) of a rectangle.
pub fn rect_dimensions(r: &Rect) -> (f64, f64) {
    (r.w, r.h)
}

/// Compute area of a rectangle.
pub fn rect_area(r: &Rect) -> f64 {
    r.area()
}

/// Check whether a point is inside a rectangle.
pub fn rect_contains_point(r: &Rect, p: &Point) -> bool {
    r.contains_point(p)
}

/// Return all four corners of a rectangle as `[bottom-left, bottom-right,
/// top-right, top-left]`.
pub fn rect_corners(r: &Rect) -> Vec<Point> {
    r.corners().into_iter().collect()
}

// =============================================================================
// Axis-Aligned Bounding Box (AABB) Operations
// =============================================================================

/// Compute the axis-aligned bounding box for a set of points.
pub fn aabb_from_points(points: &[Point]) -> AABB {
    AABB::from_points(points)
}

/// Check whether two AABBs intersect.
pub fn aabb_intersects(a: &AABB, b: &AABB) -> bool {
    a.intersects(b)
}

/// Compute the overlap area between two AABBs (0.0 if no overlap).
pub fn aabb_overlap_area(a: &AABB, b: &AABB) -> f64 {
    a.overlap_area(b)
}

/// Compute the union bounding box of two AABBs.
pub fn aabb_union(a: &AABB, b: &AABB) -> AABB {
    a.union(b)
}

/// Expand an AABB by a margin in all directions.
pub fn aabb_expand(a: &AABB, margin: f64) -> AABB {
    a.expand(margin)
}

// =============================================================================
// Distance to Rectangle / Board Edge
// =============================================================================

/// Signed distance from point to the nearest edge of a rectangle.
///
/// Positive when the point is inside, negative when outside.
pub fn distance_to_rect_edge(p: &Point, r: &Rect) -> f64 {
    let dist_left = p.x - r.x;
    let dist_right = (r.x + r.w) - p.x;
    let dist_bottom = p.y - r.y;
    let dist_top = (r.y + r.h) - p.y;
    dist_left
        .min(dist_right)
        .min(dist_bottom.min(dist_top))
}

/// Distance from point to a specific edge of a rectangle.
///
/// Edge identifiers (case-insensitive): `"TOP"`, `"BOTTOM"`, `"LEFT"`,
/// `"RIGHT"`.  An unrecognised side falls back to the nearest-edge distance.
pub fn distance_to_specific_edge(p: &Point, r: &Rect, side: &str) -> f64 {
    match side {
        s if s.eq_ignore_ascii_case("TOP") => (r.y + r.h) - p.y,
        s if s.eq_ignore_ascii_case("BOTTOM") => p.y - r.y,
        s if s.eq_ignore_ascii_case("LEFT") => p.x - r.x,
        s if s.eq_ignore_ascii_case("RIGHT") => (r.x + r.w) - p.x,
        _ => distance_to_rect_edge(p, r),
    }
}

/// Signed distance from point to the board boundary with a margin applied
/// inward from every edge.
///
/// The board is assumed to span `[0, 0]` to `[board_w, board_h]`.  Return
/// value is positive when the point lies inside the margined region and
/// negative when outside.
pub fn distance_to_board_boundary(
    p: &Point,
    board_w: f64,
    board_h: f64,
    margin: f64,
) -> f64 {
    let inner = Rect::new(margin, margin, board_w - 2.0 * margin, board_h - 2.0 * margin);
    distance_to_rect_edge(p, &inner)
}

// =============================================================================
// Batch Operations
// =============================================================================

/// Pairwise Euclidean distances between all points.
///
/// Returns a flattened N×N matrix in row-major order where element
/// `[i * N + j]` = distance between `points[i]` and `points[j]`.
pub fn pairwise_distances(points: &[Point]) -> Vec<f64> {
    let n = points.len();
    // Upper triangle + mirror: `point_distance` is deterministic, so
    // `d[i][j] == d[j][i]` bit-for-bit — mirrored entries are copied, the
    // diagonal is computed once per element.
    let mut out = vec![0.0; n * n];
    for i in 0..n {
        out[i * n + i] = point_distance(&points[i], &points[i]);
        for j in (i + 1)..n {
            let d = point_distance(&points[i], &points[j]);
            out[i * n + j] = d;
            out[j * n + i] = d;
        }
    }
    out
}

/// Pairwise squared Euclidean distances between all points.
///
/// Returns a flattened N×N matrix in row-major order where element
/// `[i * N + j]` = squared distance between `points[i]` and `points[j]`.
pub fn pairwise_distances_squared(points: &[Point]) -> Vec<f64> {
    let n = points.len();
    let mut out = Vec::with_capacity(n * n);
    for i in 0..n {
        for j in 0..n {
            out.push(point_distance_squared(&points[i], &points[j]));
        }
    }
    out
}

/// Element-wise distances between corresponding points in two arrays.
pub fn batch_point_distance(points_a: &[Point], points_b: &[Point]) -> Vec<f64> {
    let n = points_a.len().min(points_b.len());
    let mut out = Vec::with_capacity(n);
    for i in 0..n {
        out.push(point_distance(&points_a[i], &points_b[i]));
    }
    out
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    // -----------------------------------------------------------------
    // point_distance
    // -----------------------------------------------------------------
    #[test]
    fn test_point_distance_zero() {
        let p = Point::new(3.0, 4.0);
        let d = point_distance(&p, &p);
        assert!(d <= 1e-6, "self-distance should be ~sqrt(eps), got {d}");
    }

    #[test]
    fn test_point_distance_basic() {
        let a = Point::new(0.0, 0.0);
        let b = Point::new(3.0, 4.0);
        let d = point_distance(&a, &b);
        assert!((d - 5.0).abs() < 1e-9, "expected 5.0, got {d}");
    }

    #[test]
    fn test_point_distance_negative_coords() {
        let a = Point::new(-1.0, -1.0);
        let b = Point::new(2.0, 3.0);
        let d = point_distance(&a, &b);
        assert!((d - 5.0).abs() < 1e-9, "expected 5.0, got {d}");
    }

    // -----------------------------------------------------------------
    // point_distance_squared
    // -----------------------------------------------------------------
    #[test]
    fn test_point_distance_squared() {
        let a = Point::new(0.0, 0.0);
        let b = Point::new(3.0, 4.0);
        let ds = point_distance_squared(&a, &b);
        assert!((ds - 25.0).abs() < 1e-9, "expected 25.0, got {ds}");
    }

    // -----------------------------------------------------------------
    // point_midpoint
    // -----------------------------------------------------------------
    #[test]
    fn test_point_midpoint() {
        let a = Point::new(2.0, 4.0);
        let b = Point::new(6.0, 8.0);
        let m = point_midpoint(&a, &b);
        assert!((m.x - 4.0).abs() < 1e-9);
        assert!((m.y - 6.0).abs() < 1e-9);
    }

    // -----------------------------------------------------------------
    // points_centroid
    // -----------------------------------------------------------------
    #[test]
    fn test_points_centroid_empty() {
        let c = points_centroid(&[]);
        assert!((c.x - 0.0).abs() < 1e-9);
        assert!((c.y - 0.0).abs() < 1e-9);
    }

    #[test]
    fn test_points_centroid() {
        let pts = vec![
            Point::new(0.0, 0.0),
            Point::new(2.0, 4.0),
            Point::new(4.0, 2.0),
        ];
        let c = points_centroid(&pts);
        assert!((c.x - 2.0).abs() < 1e-9, "expected 2.0, got {}", c.x);
        assert!((c.y - 2.0).abs() < 1e-9, "expected 2.0, got {}", c.y);
    }

    // -----------------------------------------------------------------
    // point_to_line_distance
    // -----------------------------------------------------------------
    #[test]
    fn test_point_to_line_distance_perpendicular() {
        let p = Point::new(5.0, 3.0);
        let a = Point::new(5.0, 0.0);
        let b = Point::new(5.0, 10.0);
        let d = point_to_line_distance(&p, &a, &b);
        assert!(d <= 1e-6, "point on the line, expected ~sqrt(eps), got {d}");
    }

    #[test]
    fn test_point_to_line_distance_offset() {
        let p = Point::new(0.0, 5.0);
        let a = Point::new(0.0, 0.0);
        let b = Point::new(10.0, 0.0);
        let d = point_to_line_distance(&p, &a, &b);
        assert!((d - 5.0).abs() < 1e-9, "expected 5.0, got {d}");
    }

    #[test]
    fn test_point_to_line_distance_clamped() {
        // Point is "before" segment start — distance should be to start point
        let p = Point::new(-5.0, 0.0);
        let a = Point::new(0.0, 0.0);
        let b = Point::new(10.0, 0.0);
        let d = point_to_line_distance(&p, &a, &b);
        assert!((d - 5.0).abs() < 1e-9, "expected 5.0, got {d}");
    }

    // -----------------------------------------------------------------
    // rect_from_center / rect_center / rect_dimensions / rect_area
    // -----------------------------------------------------------------
    #[test]
    fn test_rect_from_center_and_center() {
        let r = rect_from_center(10.0, 20.0, 30.0, 40.0);
        assert!((r.x - (-20.0)).abs() < 1e-9, "x mismatch: {}", r.x);
        assert!((r.y - (-20.0)).abs() < 1e-9, "y mismatch: {}", r.y);
        assert!((r.w - 60.0).abs() < 1e-9, "w mismatch: {}", r.w);
        assert!((r.h - 80.0).abs() < 1e-9, "h mismatch: {}", r.h);

        let c = rect_center(&r);
        assert!((c.x - 10.0).abs() < 1e-9);
        assert!((c.y - 20.0).abs() < 1e-9);
    }

    #[test]
    fn test_rect_dimensions_and_area() {
        let r = Rect::new(0.0, 0.0, 10.0, 5.0);
        let (w, h) = rect_dimensions(&r);
        assert!((w - 10.0).abs() < 1e-9);
        assert!((h - 5.0).abs() < 1e-9);
        assert!((rect_area(&r) - 50.0).abs() < 1e-9);
    }

    // -----------------------------------------------------------------
    // rect_contains_point
    // -----------------------------------------------------------------
    #[test]
    fn test_rect_contains_point_inside() {
        let r = Rect::new(0.0, 0.0, 100.0, 100.0);
        let p = Point::new(50.0, 50.0);
        assert!(rect_contains_point(&r, &p));
    }

    #[test]
    fn test_rect_contains_point_outside() {
        let r = Rect::new(0.0, 0.0, 100.0, 100.0);
        let p = Point::new(200.0, 50.0);
        assert!(!rect_contains_point(&r, &p));
    }

    #[test]
    fn test_rect_contains_point_on_edge() {
        let r = Rect::new(0.0, 0.0, 100.0, 100.0);
        let p = Point::new(100.0, 50.0);
        assert!(rect_contains_point(&r, &p));
    }

    // -----------------------------------------------------------------
    // rect_corners
    // -----------------------------------------------------------------
    #[test]
    fn test_rect_corners_ordered() {
        let r = Rect::new(10.0, 20.0, 30.0, 40.0);
        let corners = rect_corners(&r);
        assert_eq!(corners.len(), 4);
        // bottom-left
        assert!((corners[0].x - 10.0).abs() < 1e-9);
        assert!((corners[0].y - 20.0).abs() < 1e-9);
        // bottom-right
        assert!((corners[1].x - 40.0).abs() < 1e-9);
        assert!((corners[1].y - 20.0).abs() < 1e-9);
        // top-right
        assert!((corners[2].x - 40.0).abs() < 1e-9);
        assert!((corners[2].y - 60.0).abs() < 1e-9);
        // top-left
        assert!((corners[3].x - 10.0).abs() < 1e-9);
        assert!((corners[3].y - 60.0).abs() < 1e-9);
    }

    // -----------------------------------------------------------------
    // aabb_from_points
    // -----------------------------------------------------------------
    #[test]
    fn test_aabb_from_points() {
        let pts = vec![
            Point::new(5.0, 10.0),
            Point::new(20.0, 3.0),
            Point::new(15.0, 25.0),
            Point::new(-5.0, 8.0),
        ];
        let bb = aabb_from_points(&pts);
        assert!((bb.x_min - (-5.0)).abs() < 1e-9);
        assert!((bb.y_min - 3.0).abs() < 1e-9);
        assert!((bb.x_max - 20.0).abs() < 1e-9);
        assert!((bb.y_max - 25.0).abs() < 1e-9);
    }

    #[test]
    fn test_aabb_from_points_single() {
        let pts = vec![Point::new(7.0, 8.0)];
        let bb = aabb_from_points(&pts);
        assert!((bb.x_min - 7.0).abs() < 1e-9);
        assert!((bb.x_max - 7.0).abs() < 1e-9);
        assert!((bb.y_min - 8.0).abs() < 1e-9);
        assert!((bb.y_max - 8.0).abs() < 1e-9);
    }

    // -----------------------------------------------------------------
    // aabb_intersects
    // -----------------------------------------------------------------
    #[test]
    fn test_aabb_intersects_overlap() {
        let a = AABB::new(0.0, 0.0, 10.0, 10.0);
        let b = AABB::new(5.0, 5.0, 15.0, 15.0);
        assert!(aabb_intersects(&a, &b));
    }

    #[test]
    fn test_aabb_intersects_disjoint() {
        let a = AABB::new(0.0, 0.0, 10.0, 10.0);
        let b = AABB::new(20.0, 20.0, 30.0, 30.0);
        assert!(!aabb_intersects(&a, &b));
    }

    #[test]
    fn test_aabb_intersects_touching() {
        let a = AABB::new(0.0, 0.0, 10.0, 10.0);
        let b = AABB::new(10.0, 0.0, 20.0, 10.0);
        assert!(aabb_intersects(&a, &b),
                "touching edges should intersect per AABB convention");
    }

    #[test]
    fn test_aabb_intersects_contained() {
        let a = AABB::new(0.0, 0.0, 20.0, 20.0);
        let b = AABB::new(5.0, 5.0, 15.0, 15.0);
        assert!(aabb_intersects(&a, &b));
    }

    // -----------------------------------------------------------------
    // aabb_overlap_area
    // -----------------------------------------------------------------
    #[test]
    fn test_aabb_overlap_area_partial() {
        let a = AABB::new(0.0, 0.0, 10.0, 10.0);
        let b = AABB::new(5.0, 5.0, 15.0, 15.0);
        let area = aabb_overlap_area(&a, &b);
        assert!((area - 25.0).abs() < 1e-9, "expected 25.0, got {area}");
    }

    #[test]
    fn test_aabb_overlap_area_none() {
        let a = AABB::new(0.0, 0.0, 10.0, 10.0);
        let b = AABB::new(20.0, 20.0, 30.0, 30.0);
        let area = aabb_overlap_area(&a, &b);
        assert!((area - 0.0).abs() < 1e-9, "expected 0.0, got {area}");
    }

    #[test]
    fn test_aabb_overlap_area_contained() {
        let a = AABB::new(0.0, 0.0, 20.0, 20.0);
        let b = AABB::new(5.0, 5.0, 15.0, 15.0);
        let area = aabb_overlap_area(&a, &b);
        assert!((area - 100.0).abs() < 1e-9, "expected 100.0, got {area}");
    }

    // -----------------------------------------------------------------
    // aabb_union
    // -----------------------------------------------------------------
    #[test]
    fn test_aabb_union() {
        let a = AABB::new(0.0, 0.0, 10.0, 10.0);
        let b = AABB::new(5.0, 5.0, 15.0, 15.0);
        let u = aabb_union(&a, &b);
        assert!((u.x_min - 0.0).abs() < 1e-9);
        assert!((u.y_min - 0.0).abs() < 1e-9);
        assert!((u.x_max - 15.0).abs() < 1e-9);
        assert!((u.y_max - 15.0).abs() < 1e-9);
    }

    // -----------------------------------------------------------------
    // aabb_expand
    // -----------------------------------------------------------------
    #[test]
    fn test_aabb_expand() {
        let a = AABB::new(5.0, 5.0, 15.0, 15.0);
        let e = aabb_expand(&a, 2.0);
        assert!((e.x_min - 3.0).abs() < 1e-9);
        assert!((e.y_min - 3.0).abs() < 1e-9);
        assert!((e.x_max - 17.0).abs() < 1e-9);
        assert!((e.y_max - 17.0).abs() < 1e-9);
    }

    // -----------------------------------------------------------------
    // distance_to_rect_edge
    // -----------------------------------------------------------------
    #[test]
    fn test_distance_to_rect_edge_inside() {
        let r = Rect::new(0.0, 0.0, 100.0, 100.0);
        let p = Point::new(50.0, 50.0);
        let d = distance_to_rect_edge(&p, &r);
        assert!((d - 50.0).abs() < 1e-9, "expected 50.0, got {d}");
    }

    #[test]
    fn test_distance_to_rect_edge_center() {
        let r = Rect::new(0.0, 0.0, 100.0, 200.0);
        // center is (50, 100); nearest edge is left/right at 50
        let p = r.center();
        let d = distance_to_rect_edge(&p, &r);
        assert!((d - 50.0).abs() < 1e-9, "expected 50.0, got {d}");
    }

    #[test]
    fn test_distance_to_rect_edge_outside() {
        let r = Rect::new(0.0, 0.0, 100.0, 100.0);
        let p = Point::new(200.0, 50.0);
        let d = distance_to_rect_edge(&p, &r);
        assert!(d < 0.0, "outside should be negative, got {d}");
    }

    // -----------------------------------------------------------------
    // distance_to_specific_edge
    // -----------------------------------------------------------------
    #[test]
    fn test_distance_to_specific_edge_left() {
        let r = Rect::new(10.0, 20.0, 100.0, 50.0);
        let p = Point::new(30.0, 40.0);
        let d = distance_to_specific_edge(&p, &r, "LEFT");
        assert!((d - 20.0).abs() < 1e-9, "expected 20.0, got {d}");
    }

    #[test]
    fn test_distance_to_specific_edge_case_insensitive() {
        let r = Rect::new(0.0, 0.0, 100.0, 100.0);
        let p = Point::new(50.0, 50.0);
        let d = distance_to_specific_edge(&p, &r, "top");
        assert!((d - 50.0).abs() < 1e-9, "expected 50.0, got {d}");
    }

    #[test]
    fn test_distance_to_specific_edge_fallback() {
        let r = Rect::new(0.0, 0.0, 100.0, 100.0);
        let p = Point::new(50.0, 50.0);
        let d = distance_to_specific_edge(&p, &r, "BOGUS");
        assert!((d - 50.0).abs() < 1e-9, "expected nearest edge 50.0, got {d}");
    }

    // -----------------------------------------------------------------
    // distance_to_board_boundary
    // -----------------------------------------------------------------
    #[test]
    fn test_distance_to_board_boundary_inside() {
        let p = Point::new(50.0, 50.0);
        let d = distance_to_board_boundary(&p, 100.0, 100.0, 10.0);
        // effective region: (10,10) – (90,90); nearest edge is 40 away
        assert!((d - 40.0).abs() < 1e-9, "expected 40.0, got {d}");
    }

    #[test]
    fn test_distance_to_board_boundary_on_margin() {
        let p = Point::new(10.0, 50.0);
        let d = distance_to_board_boundary(&p, 100.0, 100.0, 10.0);
        assert!(d.abs() < 1e-9, "expected 0.0 on margin edge, got {d}");
    }

    #[test]
    fn test_distance_to_board_boundary_outside() {
        let p = Point::new(0.0, 50.0);
        let d = distance_to_board_boundary(&p, 100.0, 100.0, 10.0);
        assert!(d < 0.0, "outside should be negative, got {d}");
    }

    #[test]
    fn test_distance_to_board_boundary_zero_margin() {
        let p = Point::new(50.0, 50.0);
        let d = distance_to_board_boundary(&p, 100.0, 100.0, 0.0);
        // effective region is full board (0,0)–(100,100); nearest edge is 50
        assert!((d - 50.0).abs() < 1e-9, "expected 50.0, got {d}");
    }

    // -----------------------------------------------------------------
    // pairwise_distances
    // -----------------------------------------------------------------
    #[test]
    fn test_pairwise_distances_empty() {
        let d = pairwise_distances(&[]);
        assert!(d.is_empty());
    }

    #[test]
    fn test_pairwise_distances_single() {
        let pts = vec![Point::new(3.0, 4.0)];
        let d = pairwise_distances(&pts);
        assert_eq!(d.len(), 1);
        assert!(d[0] <= 1e-6, "self-distance should be ~sqrt(eps)");
    }

    #[test]
    fn test_pairwise_distances_two_points() {
        let pts = vec![Point::new(0.0, 0.0), Point::new(3.0, 4.0)];
        let d = pairwise_distances(&pts);
        assert_eq!(d.len(), 4);
        // d[0,0]
        assert!(d[0] <= 1e-6, "self-distance 0");
        // d[0,1]
        assert!((d[1] - 5.0).abs() < 1e-9, "expected 5.0, got {}", d[1]);
        // d[1,0]
        assert!((d[2] - 5.0).abs() < 1e-9, "expected 5.0, got {}", d[2]);
        // d[1,1]
        assert!(d[3] <= 1e-6, "self-distance 1");
    }

    #[test]
    fn test_pairwise_distances_symmetry() {
        let pts = vec![
            Point::new(0.0, 0.0),
            Point::new(1.0, 2.0),
            Point::new(4.0, 6.0),
        ];
        let d = pairwise_distances(&pts);
        let n = 3;
        for i in 0..n {
            for j in 0..n {
                let ij = d[i * n + j];
                let ji = d[j * n + i];
                assert!(
                    (ij - ji).abs() < 1e-12,
                    "not symmetric at ({i},{j}): {ij} vs {ji}"
                );
            }
        }
    }

    // -----------------------------------------------------------------
    // pairwise_distances_squared
    // -----------------------------------------------------------------
    #[test]
    fn test_pairwise_distances_squared() {
        let pts = vec![Point::new(0.0, 0.0), Point::new(3.0, 4.0)];
        let d = pairwise_distances_squared(&pts);
        assert_eq!(d.len(), 4);
        assert!(d[0] < 1e-12);
        assert!((d[1] - 25.0).abs() < 1e-9);
        assert!((d[2] - 25.0).abs() < 1e-9);
        assert!(d[3] < 1e-12);
    }

    // -----------------------------------------------------------------
    // batch_point_distance
    // -----------------------------------------------------------------
    #[test]
    fn test_batch_point_distance() {
        let a = vec![Point::new(0.0, 0.0), Point::new(1.0, 1.0)];
        let b = vec![Point::new(3.0, 4.0), Point::new(4.0, 5.0)];
        let d = batch_point_distance(&a, &b);
        assert_eq!(d.len(), 2);
        assert!((d[0] - 5.0).abs() < 1e-9);
        assert!((d[1] - 5.0).abs() < 1e-9);
    }

    #[test]
    fn test_batch_point_distance_unequal_lengths() {
        let a = vec![Point::new(0.0, 0.0), Point::new(1.0, 1.0), Point::new(2.0, 2.0)];
        let b = vec![Point::new(3.0, 4.0)];
        let d = batch_point_distance(&a, &b);
        assert_eq!(d.len(), 1);
        assert!((d[0] - 5.0).abs() < 1e-9);
    }
}
