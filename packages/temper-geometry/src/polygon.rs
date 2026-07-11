// =============================================================================
// Polygon operations for temper-geometry
// =============================================================================
//
// Ported from Python's `temper_placer/geometry/polygon.py`.
//
// Key algorithms:
// - Shoelace formula for polygon area
// - Winding number for point-in-polygon (soft version for smooth transitions)
// - Centroid, bounding box, bounding circle, perimeter
// - Convexity and orientation checks
// - Nearest point on polygon boundary
// - Polygon transformations (translate, scale, rotate)

use temper_geometry_core::types::*;
use crate::primitives;

// =============================================================================
// Helpers
// =============================================================================

/// Logistic sigmoid: `1 / (1 + exp(-alpha * x))`.
fn sigmoid(x: f64, alpha: f64) -> f64 {
    1.0 / (1.0 + (-alpha * x).exp())
}

// =============================================================================
// Polygon Area (Shoelace Formula)
// =============================================================================

/// Compute the signed area of a polygon using the shoelace formula.
///
/// Returns a positive value for CCW winding, negative for CW.
/// Returns 0.0 for polygons with fewer than 3 vertices.
pub fn polygon_signed_area(vertices: &[Point]) -> f64 {
    let n = vertices.len();
    if n < 3 {
        return 0.0;
    }
    let mut area = 0.0;
    for i in 0..n {
        let j = (i + 1) % n;
        area += vertices[i].x * vertices[j].y;
        area -= vertices[j].x * vertices[i].y;
    }
    area * 0.5
}

/// Compute the area of a polygon (always positive).
///
/// Uses the shoelace formula. Returns 0.0 for polygons with fewer than 3
/// vertices.
pub fn polygon_area(vertices: &[Point]) -> f64 {
    polygon_signed_area(vertices).abs()
}

/// Compute the area of a triangle from three points.
///
/// Uses the cross-product formula: `0.5 * |(b-a) × (c-a)|`.
pub fn triangle_area(a: &Point, b: &Point, c: &Point) -> f64 {
    let v1 = *b - *a;
    let v2 = *c - *a;
    let cross = v1.x * v2.y - v1.y * v2.x;
    cross.abs() * 0.5
}

// =============================================================================
// Polygon Centroid
// =============================================================================

/// Compute the centroid (center of mass) of a polygon using the shoelace
/// formula.
///
/// The centroid is the centre of mass assuming uniform density. For degenerate
/// polygons (collinear points, zero area), falls back to the arithmetic mean of
/// the vertices to avoid division by zero.
pub fn polygon_centroid(vertices: &[Point]) -> Point {
    let n = vertices.len();
    if n == 0 {
        return Point::zero();
    }
    if n < 3 {
        return primitives::points_centroid(vertices);
    }

    let mut signed_area = 0.0;
    let mut cx = 0.0;
    let mut cy = 0.0;

    for i in 0..n {
        let j = (i + 1) % n;
        let cross = vertices[i].x * vertices[j].y - vertices[j].x * vertices[i].y;
        signed_area += cross;
        cx += (vertices[i].x + vertices[j].x) * cross;
        cy += (vertices[i].y + vertices[j].y) * cross;
    }

    signed_area *= 0.5;

    if signed_area.abs() < 1e-10 {
        return primitives::points_centroid(vertices);
    }

    let denom = 6.0 * signed_area;
    Point::new(cx / denom, cy / denom)
}

/// Compute the centroid of a set of points weighted by edge contribution
/// (winding centroid).
///
/// This is equivalent to [`polygon_centroid`] – it uses the shoelace formula
/// and is the proper centre of mass for a polygon. The name distinguishes it
/// from [`primitives::points_centroid`], which is the unweighted arithmetic
/// mean.
pub fn points_centroid_winding(vertices: &[Point]) -> Point {
    polygon_centroid(vertices)
}

// =============================================================================
// Point-in-Polygon Tests
// =============================================================================

/// Check if a point is inside a polygon using the winding number algorithm.
///
/// Returns `true` if the point is inside the polygon (or on the boundary),
/// `false` otherwise. This is a hard-boundary test (not differentiable at the
/// boundary).
pub fn point_in_polygon_winding(p: &Point, vertices: &[Point]) -> bool {
    let n = vertices.len();
    if n < 3 {
        return false;
    }

    // First pass: check if the point lies exactly on any edge boundary.
    // This handles the degenerate case where the winding-number ray passes
    // through a vertex or lies flush along an edge.
    for i in 0..n {
        let j = (i + 1) % n;
        let vi = &vertices[i];
        let vj = &vertices[j];

        // AABB check first (cheap reject)
        let min_x = vi.x.min(vj.x) - 1e-12;
        let max_x = vi.x.max(vj.x) + 1e-12;
        let min_y = vi.y.min(vj.y) - 1e-12;
        let max_y = vi.y.max(vj.y) + 1e-12;
        if p.x >= min_x && p.x <= max_x && p.y >= min_y && p.y <= max_y {
            // Check collinearity via cross product
            let edge_dx = vj.x - vi.x;
            let edge_dy = vj.y - vi.y;
            let to_px = p.x - vi.x;
            let to_py = p.y - vi.y;
            let cross = edge_dx * to_py - edge_dy * to_px;
            if cross.abs() < 1e-12 {
                return true;
            }
        }
    }

    // Second pass: winding number.
    let mut winding = 0i32;
    for i in 0..n {
        let j = (i + 1) % n;
        let vi = &vertices[i];
        let vj = &vertices[j];

        let edge_dx = vj.x - vi.x;
        let edge_dy = vj.y - vi.y;

        let to_px = p.x - vi.x;
        let to_py = p.y - vi.y;

        // Cross product determines side
        let cross = edge_dx * to_py - edge_dy * to_px;

        // Upward crossing (edge crosses horizontal ray going right)
        if p.y >= vi.y && p.y < vj.y && cross > 0.0 {
            winding += 1;
        }
        // Downward crossing
        if p.y < vi.y && p.y >= vj.y && cross < 0.0 {
            winding -= 1;
        }
    }

    winding != 0
}

/// Soft point-in-polygon test using signed distance to the nearest edge.
///
/// Returns a value close to 1.0 for points well inside, close to 0.0 for
/// points well outside, with a smooth transition at the boundary controlled
/// by `alpha` (larger `alpha` = sharper transition).
///
/// Uses the outward-facing normal of each edge. For a CCW polygon, interior
/// points have negative signed distances; the sigmoid of `-max_dist / alpha`
/// produces a smooth indicator in (0, 1).
pub fn point_in_polygon_soft(p: &Point, vertices: &[Point], alpha: f64) -> f64 {
    let n = vertices.len();
    if n < 3 {
        return 0.0;
    }

    let mut max_dist = f64::NEG_INFINITY;

    for i in 0..n {
        let j = (i + 1) % n;
        let vi = &vertices[i];
        let vj = &vertices[j];

        // Outward normal (right of edge direction)
        let nx = vj.y - vi.y;
        let ny = vi.x - vj.x; // -(vj.x - vi.x)

        let len = (nx * nx + ny * ny).sqrt();
        if len < 1e-12 {
            continue;
        }

        let to_px = p.x - vi.x;
        let to_py = p.y - vi.y;

        // Signed distance: positive = outside (in normal direction)
        let dist = (to_px * nx + to_py * ny) / len;
        if dist > max_dist {
            max_dist = dist;
        }
    }

    if max_dist.is_infinite() {
        return 0.0;
    }

    sigmoid(-max_dist, alpha)
}

/// Check if a point is inside an axis-aligned rectangle.
///
/// Returns `true` if the point lies within the rectangle (including on the
/// boundary).
pub fn point_in_rect(p: &Point, r: &Rect) -> bool {
    r.contains_point(p)
}

/// Soft point-in-rectangle test.
///
/// Returns a value close to 1.0 for points well inside, close to 0.0 for
/// points well outside, with a smooth transition at the boundary controlled
/// by `alpha`.
pub fn point_in_rect_soft(p: &Point, r: &Rect, alpha: f64) -> f64 {
    let dist_left = r.x - p.x;
    let dist_right = p.x - (r.x + r.w);
    let dist_bottom = r.y - p.y;
    let dist_top = p.y - (r.y + r.h);
    let max_dist = dist_left
        .max(dist_right)
        .max(dist_bottom.max(dist_top));
    sigmoid(-max_dist, alpha)
}

// =============================================================================
// Polygon Perimeter
// =============================================================================

/// Compute the perimeter of a polygon (sum of edge lengths).
///
/// Returns 0.0 for polygons with fewer than 2 vertices.
pub fn polygon_perimeter(vertices: &[Point]) -> f64 {
    let n = vertices.len();
    if n < 2 {
        return 0.0;
    }
    let mut perim = 0.0;
    for i in 0..n {
        let j = (i + 1) % n;
        perim += vertices[i].distance(&vertices[j]);
    }
    perim
}

// =============================================================================
// Loop Area for PCB Design
// =============================================================================

/// Compute the area of a current loop formed by pins.
///
/// Delegates to [`polygon_area`]. The pin positions should be ordered around
/// the loop.
pub fn compute_loop_area(vertices: &[Point]) -> f64 {
    polygon_area(vertices)
}

/// Compute the perimeter of a current loop.
///
/// Delegates to [`polygon_perimeter`].
pub fn compute_loop_perimeter(vertices: &[Point]) -> f64 {
    polygon_perimeter(vertices)
}

/// Compute a squared penalty for loop area exceeding a maximum.
///
/// Returns `weight * max(0, area - max_area_mm2)^2`.
pub fn loop_area_penalty(vertices: &[Point], max_area_mm2: f64, weight: f64) -> f64 {
    let area = compute_loop_area(vertices);
    let violation = (area - max_area_mm2).max(0.0);
    weight * violation * violation
}

// =============================================================================
// Bounding Box and Circle
// =============================================================================

/// Compute the axis-aligned bounding box of a polygon.
///
/// Returns `AABB { x_min, y_min, x_max, y_max }`.
/// If the vertex list is empty the returned AABB will have infinities.
pub fn polygon_bounding_box(vertices: &[Point]) -> AABB {
    AABB::from_points(vertices)
}

/// Compute an approximate bounding circle of a polygon.
///
/// Uses the arithmetic mean centroid as the centre and the maximum distance
/// from the centre to any vertex as the radius. This is *not* the minimum
/// bounding circle but is efficient to compute.
///
/// Returns `(center, radius)`. For an empty vertex list the center is `(0, 0)`
/// and the radius is 0.
pub fn polygon_bounding_circle(vertices: &[Point]) -> (Point, f64) {
    let center = primitives::points_centroid(vertices);
    let mut max_dist_sq = 0.0;
    for v in vertices {
        let d2 = center.distance_squared(v);
        if d2 > max_dist_sq {
            max_dist_sq = d2;
        }
    }
    (center, max_dist_sq.sqrt())
}

// =============================================================================
// Polygon Validation & Classification
// =============================================================================

/// Check if a polygon is convex.
///
/// A polygon is convex if all cross products of consecutive edges have the
/// same sign (with a small tolerance for collinear edges). Returns `false`
/// for polygons with fewer than 3 vertices.
pub fn is_convex(vertices: &[Point]) -> bool {
    let n = vertices.len();
    if n < 3 {
        return false;
    }

    let mut sign: Option<bool> = None;

    for i in 0..n {
        let j = (i + 1) % n;
        let k = (i + 2) % n;

        let edge1_x = vertices[j].x - vertices[i].x;
        let edge1_y = vertices[j].y - vertices[i].y;
        let edge2_x = vertices[k].x - vertices[j].x;
        let edge2_y = vertices[k].y - vertices[j].y;

        let cross = edge1_x * edge2_y - edge1_y * edge2_x;

        if cross.abs() > 1e-12 {
            let is_positive = cross > 0.0;
            match sign {
                None => sign = Some(is_positive),
                Some(s) if s != is_positive => return false,
                _ => {}
            }
        }
    }

    true
}

/// Determine the orientation of a polygon.
///
/// Returns:
/// - `1` for CCW (counter-clockwise, positive signed area)
/// - `-1` for CW (clockwise, negative signed area)
/// - `0` for degenerate (collinear or fewer than 3 vertices)
pub fn polygon_orientation(vertices: &[Point]) -> i32 {
    let signed_area = polygon_signed_area(vertices);
    if signed_area > 1e-12 {
        1
    } else if signed_area < -1e-12 {
        -1
    } else {
        0
    }
}

// =============================================================================
// Nearest Point on Polygon / Segment
// =============================================================================

/// Find the nearest point on a line segment to a query point.
///
/// Projects the point onto the infinite line through the segment, then clamps
/// the parameter to [0, 1]. Degenerate segments (zero length) return the
/// start point.
pub fn nearest_point_on_segment(p: &Point, seg: &Segment) -> Point {
    seg.nearest_point(p)
}

/// Find the nearest point on a polygon boundary to a query point.
///
/// Sweeps all polygon edges and returns the nearest boundary point.
/// For an empty vertex list returns the query point itself.
pub fn nearest_point_on_polygon(p: &Point, vertices: &[Point]) -> Point {
    let n = vertices.len();
    if n == 0 {
        return *p;
    }
    if n == 1 {
        return vertices[0];
    }

    let mut best_dist_sq = f64::INFINITY;
    let mut best_point = *p;

    for i in 0..n {
        let j = (i + 1) % n;
        let seg = Segment::new(vertices[i], vertices[j]);
        let np = seg.nearest_point(p);
        let d2 = np.distance_squared(p);
        if d2 < best_dist_sq {
            best_dist_sq = d2;
            best_point = np;
        }
    }

    best_point
}

// =============================================================================
// Polygon Transformations
// =============================================================================

/// Translate a polygon by `(dx, dy)`.
pub fn translate_polygon(vertices: &[Point], dx: f64, dy: f64) -> Vec<Point> {
    vertices
        .iter()
        .map(|p| Point::new(p.x + dx, p.y + dy))
        .collect()
}

/// Scale a polygon around its centroid by factors `(sx, sy)`.
///
/// Uses the arithmetic mean centroid as the centre of scaling.
pub fn scale_polygon(vertices: &[Point], sx: f64, sy: f64) -> Vec<Point> {
    if vertices.is_empty() {
        return vec![];
    }
    let center = primitives::points_centroid(vertices);
    vertices
        .iter()
        .map(|p| {
            Point::new(
                center.x + (p.x - center.x) * sx,
                center.y + (p.y - center.y) * sy,
            )
        })
        .collect()
}

/// Rotate a polygon around its centroid by `angle_rad` (CCW positive).
///
/// Uses the arithmetic mean centroid as the centre of rotation.
pub fn rotate_polygon(vertices: &[Point], angle_rad: f64) -> Vec<Point> {
    if vertices.is_empty() {
        return vec![];
    }
    let center = primitives::points_centroid(vertices);
    let cos_a = angle_rad.cos();
    let sin_a = angle_rad.sin();
    vertices
        .iter()
        .map(|p| {
            let dx = p.x - center.x;
            let dy = p.y - center.y;
            Point::new(
                center.x + dx * cos_a - dy * sin_a,
                center.y + dx * sin_a + dy * cos_a,
            )
        })
        .collect()
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    const EPS: f64 = 1e-9;

    fn unit_square() -> Vec<Point> {
        vec![
            Point::new(0.0, 0.0),
            Point::new(1.0, 0.0),
            Point::new(1.0, 1.0),
            Point::new(0.0, 1.0),
        ]
    }

    fn star_polygon() -> Vec<Point> {
        vec![
            Point::new(0.0, 0.0),
            Point::new(2.0, 1.0),
            Point::new(0.0, 2.0),
            Point::new(1.0, 1.0),
            Point::new(2.0, 0.0),
        ]
    }

    // -----------------------------------------------------------------
    // polygon_area / polygon_signed_area
    // -----------------------------------------------------------------
    #[test]
    fn test_polygon_area_square() {
        let sq = unit_square();
        let area = polygon_area(&sq);
        assert!((area - 1.0).abs() < EPS, "expected 1.0, got {area}");
    }

    #[test]
    fn test_polygon_signed_area_ccw() {
        let poly = vec![
            Point::new(0.0, 0.0),
            Point::new(1.0, 0.0),
            Point::new(1.0, 1.0),
            Point::new(0.0, 1.0),
        ];
        let area = polygon_signed_area(&poly);
        assert!(area > 0.0, "CCW should have positive area, got {area}");
        assert!((area - 1.0).abs() < EPS);
    }

    #[test]
    fn test_polygon_signed_area_cw() {
        let poly = vec![
            Point::new(0.0, 0.0),
            Point::new(0.0, 1.0),
            Point::new(1.0, 1.0),
            Point::new(1.0, 0.0),
        ];
        let area = polygon_signed_area(&poly);
        assert!(area < 0.0, "CW should have negative area, got {area}");
        assert!((area - (-1.0)).abs() < EPS);
    }

    #[test]
    fn test_polygon_area_empty() {
        assert!((polygon_area(&[]) - 0.0).abs() < EPS);
    }

    #[test]
    fn test_polygon_signed_area_less_than_3() {
        let poly = vec![Point::new(0.0, 0.0), Point::new(1.0, 0.0)];
        assert!((polygon_signed_area(&poly) - 0.0).abs() < EPS);
        assert!((polygon_area(&poly) - 0.0).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // triangle_area
    // -----------------------------------------------------------------
    #[test]
    fn test_triangle_area_basic() {
        let a = Point::new(0.0, 0.0);
        let b = Point::new(3.0, 0.0);
        let c = Point::new(0.0, 4.0);
        assert!((triangle_area(&a, &b, &c) - 6.0).abs() < EPS);
    }

    #[test]
    fn test_triangle_area_right_triangle() {
        let a = Point::new(0.0, 0.0);
        let b = Point::new(1.0, 0.0);
        let c = Point::new(0.0, 1.0);
        assert!((triangle_area(&a, &b, &c) - 0.5).abs() < EPS);
    }

    #[test]
    fn test_triangle_area_via_shoelace() {
        let tri = vec![
            Point::new(0.0, 0.0),
            Point::new(1.0, 0.0),
            Point::new(0.0, 1.0),
        ];
        assert!((triangle_area(&tri[0], &tri[1], &tri[2]) - polygon_area(&tri)).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // polygon_centroid
    // -----------------------------------------------------------------
    #[test]
    fn test_centroid_square() {
        let sq = unit_square();
        let c = polygon_centroid(&sq);
        assert!((c.x - 0.5).abs() < EPS, "cx expected 0.5, got {}", c.x);
        assert!((c.y - 0.5).abs() < EPS, "cy expected 0.5, got {}", c.y);
    }

    #[test]
    fn test_centroid_triangle() {
        let tri = vec![
            Point::new(0.0, 0.0),
            Point::new(2.0, 0.0),
            Point::new(0.0, 2.0),
        ];
        let c = polygon_centroid(&tri);
        assert!((c.x - 2.0 / 3.0).abs() < EPS, "cx expected 2/3, got {}", c.x);
        assert!((c.y - 2.0 / 3.0).abs() < EPS, "cy expected 2/3, got {}", c.y);
    }

    #[test]
    fn test_centroid_degenerate_fallback() {
        let collinear = vec![
            Point::new(0.0, 0.0),
            Point::new(1.0, 0.0),
            Point::new(2.0, 0.0),
        ];
        let c = polygon_centroid(&collinear);
        assert!((c.x - 1.0).abs() < EPS, "expected mean x=1.0, got {}", c.x);
        assert!((c.y - 0.0).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // points_centroid_winding
    // -----------------------------------------------------------------
    #[test]
    fn test_points_centroid_winding_matches_centroid() {
        let sq = unit_square();
        let c1 = polygon_centroid(&sq);
        let c2 = points_centroid_winding(&sq);
        assert!((c1.x - c2.x).abs() < EPS);
        assert!((c1.y - c2.y).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // point_in_polygon_winding
    // -----------------------------------------------------------------
    #[test]
    fn test_point_in_polygon_inside() {
        let sq = unit_square();
        assert!(point_in_polygon_winding(&Point::new(0.5, 0.5), &sq));
    }

    #[test]
    fn test_point_in_polygon_outside() {
        let sq = unit_square();
        assert!(!point_in_polygon_winding(&Point::new(2.0, 2.0), &sq));
    }

    #[test]
    fn test_point_in_polygon_on_edge() {
        let sq = unit_square();
        assert!(point_in_polygon_winding(&Point::new(1.0, 0.5), &sq));
    }

    #[test]
    fn test_point_in_polygon_on_vertex() {
        let sq = unit_square();
        assert!(point_in_polygon_winding(&Point::new(0.0, 0.0), &sq));
    }

    // -----------------------------------------------------------------
    // point_in_polygon_soft
    // -----------------------------------------------------------------
    #[test]
    fn test_point_in_polygon_soft_inside() {
        let sq = unit_square();
        let r = point_in_polygon_soft(&Point::new(0.5, 0.5), &sq, 10.0);
        assert!(r > 0.99, "expected ~1 inside, got {r}");
    }

    #[test]
    fn test_point_in_polygon_soft_outside() {
        let sq = unit_square();
        let r = point_in_polygon_soft(&Point::new(2.0, 2.0), &sq, 10.0);
        assert!(r < 0.01, "expected ~0 outside, got {r}");
    }

    // -----------------------------------------------------------------
    // point_in_rect / point_in_rect_soft
    // -----------------------------------------------------------------
    #[test]
    fn test_point_in_rect_inside() {
        assert!(point_in_rect(&Point::new(5.0, 5.0), &Rect::new(0.0, 0.0, 10.0, 10.0)));
    }

    #[test]
    fn test_point_in_rect_outside() {
        assert!(!point_in_rect(&Point::new(20.0, 5.0), &Rect::new(0.0, 0.0, 10.0, 10.0)));
    }

    #[test]
    fn test_point_in_rect_soft_inside() {
        let r = point_in_rect_soft(&Point::new(5.0, 5.0), &Rect::new(0.0, 0.0, 10.0, 10.0), 10.0);
        assert!(r > 0.99, "expected ~1 inside, got {r}");
    }

    #[test]
    fn test_point_in_rect_soft_outside() {
        let r = point_in_rect_soft(&Point::new(20.0, 5.0), &Rect::new(0.0, 0.0, 10.0, 10.0), 10.0);
        assert!(r < 0.01, "expected ~0 outside, got {r}");
    }

    // -----------------------------------------------------------------
    // polygon_perimeter
    // -----------------------------------------------------------------
    #[test]
    fn test_perimeter_square() {
        assert!((polygon_perimeter(&unit_square()) - 4.0).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // compute_loop_area / compute_loop_perimeter / loop_area_penalty
    // -----------------------------------------------------------------
    #[test]
    fn test_loop_area_matches_polygon_area() {
        assert!((compute_loop_area(&unit_square()) - polygon_area(&unit_square())).abs() < EPS);
    }

    #[test]
    fn test_loop_perimeter_matches() {
        assert!((compute_loop_perimeter(&unit_square()) - polygon_perimeter(&unit_square())).abs() < EPS);
    }

    #[test]
    fn test_loop_area_penalty_no_violation() {
        let p = loop_area_penalty(&unit_square(), 2.0, 1.0);
        assert!((p - 0.0).abs() < EPS, "expected 0, got {p}");
    }

    #[test]
    fn test_loop_area_penalty_with_violation() {
        // area = 1.0, max = 0.5, violation = 0.5, weight = 2, penalty = 2 * 0.25 = 0.5
        let p = loop_area_penalty(&unit_square(), 0.5, 2.0);
        assert!((p - 0.5).abs() < EPS, "expected 0.5, got {p}");
    }

    // -----------------------------------------------------------------
    // polygon_bounding_box
    // -----------------------------------------------------------------
    #[test]
    fn test_bounding_box_square() {
        let bb = polygon_bounding_box(&unit_square());
        assert!((bb.x_min - 0.0).abs() < EPS);
        assert!((bb.y_min - 0.0).abs() < EPS);
        assert!((bb.x_max - 1.0).abs() < EPS);
        assert!((bb.y_max - 1.0).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // polygon_bounding_circle
    // -----------------------------------------------------------------
    #[test]
    fn test_bounding_circle_square() {
        let (center, radius) = polygon_bounding_circle(&unit_square());
        assert!((center.x - 0.5).abs() < EPS);
        assert!((center.y - 0.5).abs() < EPS);
        let expected_r = (0.5f64).sqrt();
        assert!((radius - expected_r).abs() < EPS, "expected {expected_r}, got {radius}");
    }

    // -----------------------------------------------------------------
    // is_convex
    // -----------------------------------------------------------------
    #[test]
    fn test_is_convex_square() {
        assert!(is_convex(&unit_square()), "square should be convex");
    }

    #[test]
    fn test_is_convex_star() {
        assert!(!is_convex(&star_polygon()), "star should not be convex");
    }

    #[test]
    fn test_is_convex_triangle() {
        let tri = vec![
            Point::new(0.0, 0.0),
            Point::new(1.0, 0.0),
            Point::new(0.0, 1.0),
        ];
        assert!(is_convex(&tri));
    }

    // -----------------------------------------------------------------
    // polygon_orientation
    // -----------------------------------------------------------------
    #[test]
    fn test_orientation_ccw() {
        let poly = vec![
            Point::new(0.0, 0.0),
            Point::new(1.0, 0.0),
            Point::new(1.0, 1.0),
            Point::new(0.0, 1.0),
        ];
        assert_eq!(polygon_orientation(&poly), 1);
    }

    #[test]
    fn test_orientation_cw() {
        let poly = vec![
            Point::new(0.0, 0.0),
            Point::new(0.0, 1.0),
            Point::new(1.0, 1.0),
            Point::new(1.0, 0.0),
        ];
        assert_eq!(polygon_orientation(&poly), -1);
    }

    // -----------------------------------------------------------------
    // nearest_point_on_segment
    // -----------------------------------------------------------------
    #[test]
    fn test_nearest_point_on_segment_midpoint() {
        let seg = Segment::new(Point::new(0.0, 0.0), Point::new(2.0, 0.0));
        let np = nearest_point_on_segment(&Point::new(1.0, 1.0), &seg);
        assert!((np.x - 1.0).abs() < EPS);
        assert!((np.y - 0.0).abs() < EPS);
    }

    #[test]
    fn test_nearest_point_on_segment_clamped() {
        let seg = Segment::new(Point::new(0.0, 0.0), Point::new(2.0, 0.0));
        let np = nearest_point_on_segment(&Point::new(5.0, 0.0), &seg);
        assert!((np.x - 2.0).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // nearest_point_on_polygon
    // -----------------------------------------------------------------
    #[test]
    fn test_nearest_point_on_polygon_inside() {
        let sq = unit_square();
        let np = nearest_point_on_polygon(&Point::new(0.5, 0.5), &sq);
        let d = np.distance(&Point::new(0.5, 0.5));
        assert!(d > 0.49 && d < 0.51, "expected ~0.5, got {d}");
    }

    #[test]
    fn test_nearest_point_on_polygon_outside() {
        let sq = unit_square();
        let np = nearest_point_on_polygon(&Point::new(2.0, 0.5), &sq);
        assert!((np.x - 1.0).abs() < EPS);
        assert!((np.y - 0.5).abs() < EPS);
    }

    #[test]
    fn test_nearest_point_on_polygon_empty() {
        let np = nearest_point_on_polygon(&Point::new(1.0, 2.0), &[]);
        assert!((np.x - 1.0).abs() < EPS);
        assert!((np.y - 2.0).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // translate_polygon
    // -----------------------------------------------------------------
    #[test]
    fn test_translate_polygon() {
        let t = translate_polygon(&unit_square(), 2.0, 3.0);
        assert_eq!(t.len(), 4);
        assert!((t[0].x - 2.0).abs() < EPS);
        assert!((t[0].y - 3.0).abs() < EPS);
        assert!((t[2].x - 3.0).abs() < EPS);
        assert!((t[2].y - 4.0).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // scale_polygon
    // -----------------------------------------------------------------
    #[test]
    fn test_scale_polygon_uniform() {
        let scaled = scale_polygon(&unit_square(), 2.0, 2.0);
        assert_eq!(scaled.len(), 4);
        assert!((scaled[0].x - (-0.5)).abs() < EPS);
        assert!((scaled[0].y - (-0.5)).abs() < EPS);
        assert!((polygon_area(&scaled) - 4.0).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // rotate_polygon: 90° of unit square
    // -----------------------------------------------------------------
    #[test]
    fn test_rotate_polygon_90_degrees() {
        let rotated = rotate_polygon(&unit_square(), std::f64::consts::FRAC_PI_2);
        assert_eq!(rotated.len(), 4);
        // (0, 0) -> (1.0, 0.0)
        assert!((rotated[0].x - 1.0).abs() < 1e-12);
        assert!((rotated[0].y - 0.0).abs() < 1e-12);
        // (1, 0) -> (1.0, 1.0)
        assert!((rotated[1].x - 1.0).abs() < 1e-12);
        assert!((rotated[1].y - 1.0).abs() < 1e-12);
        // Area preserved
        assert!((polygon_area(&rotated) - 1.0).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // sigmoid helper
    // -----------------------------------------------------------------
    #[test]
    fn test_sigmoid_zero() {
        assert!((sigmoid(0.0, 1.0) - 0.5).abs() < EPS);
    }
}
