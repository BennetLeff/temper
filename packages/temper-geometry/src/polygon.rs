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

use crate::types::*;
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

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
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
    #[cfg_attr(test, test)]
    fn test_polygon_area_square() {
        let sq = unit_square();
        let area = polygon_area(&sq);
        assert!((area - 1.0).abs() < EPS, "expected 1.0, got {area}");
    }

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
    fn test_polygon_area_empty() {
        assert!((polygon_area(&[]) - 0.0).abs() < EPS);
    }

    #[cfg_attr(test, test)]
    fn test_polygon_signed_area_less_than_3() {
        let poly = vec![Point::new(0.0, 0.0), Point::new(1.0, 0.0)];
        assert!((polygon_signed_area(&poly) - 0.0).abs() < EPS);
        assert!((polygon_area(&poly) - 0.0).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // triangle_area
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_triangle_area_basic() {
        let a = Point::new(0.0, 0.0);
        let b = Point::new(3.0, 0.0);
        let c = Point::new(0.0, 4.0);
        assert!((triangle_area(&a, &b, &c) - 6.0).abs() < EPS);
    }

    #[cfg_attr(test, test)]
    fn test_triangle_area_right_triangle() {
        let a = Point::new(0.0, 0.0);
        let b = Point::new(1.0, 0.0);
        let c = Point::new(0.0, 1.0);
        assert!((triangle_area(&a, &b, &c) - 0.5).abs() < EPS);
    }

    #[cfg_attr(test, test)]
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
    #[cfg_attr(test, test)]
    fn test_centroid_square() {
        let sq = unit_square();
        let c = polygon_centroid(&sq);
        assert!((c.x - 0.5).abs() < EPS, "cx expected 0.5, got {}", c.x);
        assert!((c.y - 0.5).abs() < EPS, "cy expected 0.5, got {}", c.y);
    }

    #[cfg_attr(test, test)]
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

    #[cfg_attr(test, test)]
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
    // point_in_polygon_winding
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_point_in_polygon_inside() {
        let sq = unit_square();
        assert!(point_in_polygon_winding(&Point::new(0.5, 0.5), &sq));
    }

    #[cfg_attr(test, test)]
    fn test_point_in_polygon_outside() {
        let sq = unit_square();
        assert!(!point_in_polygon_winding(&Point::new(2.0, 2.0), &sq));
    }

    #[cfg_attr(test, test)]
    fn test_point_in_polygon_on_edge() {
        let sq = unit_square();
        assert!(point_in_polygon_winding(&Point::new(1.0, 0.5), &sq));
    }

    #[cfg_attr(test, test)]
    fn test_point_in_polygon_on_vertex() {
        let sq = unit_square();
        assert!(point_in_polygon_winding(&Point::new(0.0, 0.0), &sq));
    }

    // -----------------------------------------------------------------
    // point_in_polygon_soft
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_point_in_polygon_soft_inside() {
        let sq = unit_square();
        let r = point_in_polygon_soft(&Point::new(0.5, 0.5), &sq, 10.0);
        assert!(r > 0.99, "expected ~1 inside, got {r}");
    }

    #[cfg_attr(test, test)]
    fn test_point_in_polygon_soft_outside() {
        let sq = unit_square();
        let r = point_in_polygon_soft(&Point::new(2.0, 2.0), &sq, 10.0);
        assert!(r < 0.01, "expected ~0 outside, got {r}");
    }

    // -----------------------------------------------------------------
    // point_in_rect / point_in_rect_soft
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_point_in_rect_inside() {
        assert!(point_in_rect(&Point::new(5.0, 5.0), &Rect::new(0.0, 0.0, 10.0, 10.0)));
    }

    #[cfg_attr(test, test)]
    fn test_point_in_rect_outside() {
        assert!(!point_in_rect(&Point::new(20.0, 5.0), &Rect::new(0.0, 0.0, 10.0, 10.0)));
    }

    #[cfg_attr(test, test)]
    fn test_point_in_rect_soft_inside() {
        let r = point_in_rect_soft(&Point::new(5.0, 5.0), &Rect::new(0.0, 0.0, 10.0, 10.0), 10.0);
        assert!(r > 0.99, "expected ~1 inside, got {r}");
    }

    #[cfg_attr(test, test)]
    fn test_point_in_rect_soft_outside() {
        let r = point_in_rect_soft(&Point::new(20.0, 5.0), &Rect::new(0.0, 0.0, 10.0, 10.0), 10.0);
        assert!(r < 0.01, "expected ~0 outside, got {r}");
    }

    // -----------------------------------------------------------------
    // polygon_perimeter
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_perimeter_square() {
        assert!((polygon_perimeter(&unit_square()) - 4.0).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // compute_loop_area / compute_loop_perimeter / loop_area_penalty
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_loop_area_matches_polygon_area() {
        assert!((compute_loop_area(&unit_square()) - polygon_area(&unit_square())).abs() < EPS);
    }

    #[cfg_attr(test, test)]
    fn test_loop_perimeter_matches() {
        assert!((compute_loop_perimeter(&unit_square()) - polygon_perimeter(&unit_square())).abs() < EPS);
    }

    #[cfg_attr(test, test)]
    fn test_loop_area_penalty_no_violation() {
        let p = loop_area_penalty(&unit_square(), 2.0, 1.0);
        assert!((p - 0.0).abs() < EPS, "expected 0, got {p}");
    }

    #[cfg_attr(test, test)]
    fn test_loop_area_penalty_with_violation() {
        // area = 1.0, max = 0.5, violation = 0.5, weight = 2, penalty = 2 * 0.25 = 0.5
        let p = loop_area_penalty(&unit_square(), 0.5, 2.0);
        assert!((p - 0.5).abs() < EPS, "expected 0.5, got {p}");
    }

    // -----------------------------------------------------------------
    // polygon_bounding_box
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
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
    #[cfg_attr(test, test)]
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
    #[cfg_attr(test, test)]
    fn test_is_convex_square() {
        assert!(is_convex(&unit_square()), "square should be convex");
    }

    #[cfg_attr(test, test)]
    fn test_is_convex_star() {
        assert!(!is_convex(&star_polygon()), "star should not be convex");
    }

    #[cfg_attr(test, test)]
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
    #[cfg_attr(test, test)]
    fn test_orientation_ccw() {
        let poly = vec![
            Point::new(0.0, 0.0),
            Point::new(1.0, 0.0),
            Point::new(1.0, 1.0),
            Point::new(0.0, 1.0),
        ];
        assert_eq!(polygon_orientation(&poly), 1);
    }

    #[cfg_attr(test, test)]
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
    #[cfg_attr(test, test)]
    fn test_nearest_point_on_segment_midpoint() {
        let seg = Segment::new(Point::new(0.0, 0.0), Point::new(2.0, 0.0));
        let np = nearest_point_on_segment(&Point::new(1.0, 1.0), &seg);
        assert!((np.x - 1.0).abs() < EPS);
        assert!((np.y - 0.0).abs() < EPS);
    }

    #[cfg_attr(test, test)]
    fn test_nearest_point_on_segment_clamped() {
        let seg = Segment::new(Point::new(0.0, 0.0), Point::new(2.0, 0.0));
        let np = nearest_point_on_segment(&Point::new(5.0, 0.0), &seg);
        assert!((np.x - 2.0).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // nearest_point_on_polygon
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn test_nearest_point_on_polygon_inside() {
        let sq = unit_square();
        let np = nearest_point_on_polygon(&Point::new(0.5, 0.5), &sq);
        let d = np.distance(&Point::new(0.5, 0.5));
        assert!(d > 0.49 && d < 0.51, "expected ~0.5, got {d}");
    }

    #[cfg_attr(test, test)]
    fn test_nearest_point_on_polygon_outside() {
        let sq = unit_square();
        let np = nearest_point_on_polygon(&Point::new(2.0, 0.5), &sq);
        assert!((np.x - 1.0).abs() < EPS);
        assert!((np.y - 0.5).abs() < EPS);
    }

    #[cfg_attr(test, test)]
    fn test_nearest_point_on_polygon_empty() {
        let np = nearest_point_on_polygon(&Point::new(1.0, 2.0), &[]);
        assert!((np.x - 1.0).abs() < EPS);
        assert!((np.y - 2.0).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // translate_polygon
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
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
    #[cfg_attr(test, test)]
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
    #[cfg_attr(test, test)]
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
    #[cfg_attr(test, test)]
    fn test_sigmoid_zero() {
        assert!((sigmoid(0.0, 1.0) - 0.5).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // WASM-tier mirror of `mod proptests` below (R19/U6: `proptest` is a
    // dev-dependency, absent from the non-test `wasm-registry` build --
    // see `docs/evidence/2026-08-11-native-only-classification-all-crates.md`,
    // which counts this crate's 55 zero-mirror-coverage proptests).
    // Deterministic SplitMix64 seeded generator: no `rand`, no `proptest`,
    // no OS entropy (wasm32-unknown-unknown has none). Each `pN_..._impl`
    // below is the exact assertion body of its `mod proptests` sibling;
    // each is called by CAMPAIGN_N registered wrapper tests below, one per
    // seed, so a failure names the exact seed to replay. The native
    // `mod proptests` is NOT touched -- it keeps exploring randomly.
    //
    // Vacuity guard: `mod proptests`'s `small_polygon()` draws 3-8
    // independent uniform points, which is overwhelmingly likely to
    // produce a generic, well-separated, non-degenerate polygon every
    // time -- the shoelace-formula identities below (non-negativity, sign
    // flip on reversal, bbox containment, ...) hold trivially for those,
    // and a bug that only misbehaves on collinear points, duplicated
    // vertices, or near-zero area would never be reached. `gen_polygon`
    // and `gen_triangle` below deliberately construct a collinear or
    // duplicate-vertex-heavy case on roughly half of all draws (not by
    // sampling and hoping); `wasm_mirror_vacuity_guard` measures and
    // asserts that rate rather than assuming it.
    // -----------------------------------------------------------------

    struct SplitMix64(u64);

    impl SplitMix64 {
        fn new(seed: u64) -> Self {
            Self(seed)
        }
        fn next_u64(&mut self) -> u64 {
            self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
            let mut z = self.0;
            z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
            z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
            z ^ (z >> 31)
        }
        fn next_f64(&mut self) -> f64 {
            (self.next_u64() >> 11) as f64 * (1.0 / (1u64 << 53) as f64)
        }
        fn range(&mut self, lo: f64, hi: f64) -> f64 {
            lo + self.next_f64() * (hi - lo)
        }
        fn index(&mut self, n: usize) -> usize {
            debug_assert!(n > 0);
            (self.next_u64() % n as u64) as usize
        }
        fn bool(&mut self) -> bool {
            self.next_u64() & 1 == 0
        }
    }

    fn sub_rng(seed: u64, salt: u64) -> SplitMix64 {
        SplitMix64::new(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15).wrapping_add(salt))
    }

    const CAMPAIGN_N: usize = 20;

    /// Deliberately-chosen coordinate boundary values (zero, negative
    /// zero, endpoints of the `coord()` strategy's `-100.0..100.0`
    /// domain, midpoints): 50% of draws use one of these, 50% uniform.
    const BOUNDARY_COORDS: &[f64] = &[0.0, -0.0, 99.999_999, -99.999_999, 50.0, -50.0];

    fn gen_coord(rng: &mut SplitMix64) -> (f64, bool) {
        if rng.bool() {
            (BOUNDARY_COORDS[rng.index(BOUNDARY_COORDS.len())], true)
        } else {
            (rng.range(-100.0, 100.0), false)
        }
    }

    /// A 3-8 vertex polygon. 50% of the time, deliberately degenerate:
    /// either every vertex collinear (on the line through two random
    /// points, extrapolated as well as interpolated via `t in -2.0..3.0`
    /// so some vertices fall outside the a-b segment), or built from only
    /// 1-2 distinct points repeated to fill the vertex count. Returns
    /// `(vertices, was_degenerate)`.
    fn gen_polygon(seed: u64, salt: u64) -> (Vec<Point>, bool) {
        let mut rng = sub_rng(seed, salt);
        let n = 3 + rng.index(6); // 3..=8, matching small_polygon()'s 3..=8
        if rng.bool() {
            if rng.bool() {
                let (ax, _) = gen_coord(&mut rng);
                let (ay, _) = gen_coord(&mut rng);
                let (bx, _) = gen_coord(&mut rng);
                let (by, _) = gen_coord(&mut rng);
                let mut pts = Vec::with_capacity(n);
                for _ in 0..n {
                    let t = rng.range(-2.0, 3.0);
                    pts.push(Point::new(ax + t * (bx - ax), ay + t * (by - ay)));
                }
                (pts, true)
            } else {
                let k = 1 + rng.index(2); // 1 or 2 distinct points
                let mut distinct = Vec::with_capacity(k);
                for _ in 0..k {
                    let (x, _) = gen_coord(&mut rng);
                    let (y, _) = gen_coord(&mut rng);
                    distinct.push(Point::new(x, y));
                }
                let mut pts = Vec::with_capacity(n);
                for i in 0..n {
                    pts.push(distinct[i % k]);
                }
                (pts, true)
            }
        } else {
            let mut pts = Vec::with_capacity(n);
            for _ in 0..n {
                let (x, _) = gen_coord(&mut rng);
                let (y, _) = gen_coord(&mut rng);
                pts.push(Point::new(x, y));
            }
            (pts, false)
        }
    }

    /// Three points for the triangle_area properties. 50% of the time,
    /// `c` is deliberately placed on the infinite line through `a`, `b`
    /// (collinear, zero true area) rather than drawn independently.
    /// Returns `(a, b, c, was_collinear)`.
    fn gen_triangle(seed: u64, salt: u64) -> (Point, Point, Point, bool) {
        let mut rng = sub_rng(seed, salt);
        let (ax, _) = gen_coord(&mut rng);
        let (ay, _) = gen_coord(&mut rng);
        let a = Point::new(ax, ay);
        let (bx, _) = gen_coord(&mut rng);
        let (by, _) = gen_coord(&mut rng);
        let b = Point::new(bx, by);
        if rng.bool() {
            let t = rng.range(-2.0, 3.0);
            let c = Point::new(a.x + t * (b.x - a.x), a.y + t * (b.y - a.y));
            (a, b, c, true)
        } else {
            let (cx, _) = gen_coord(&mut rng);
            let (cy, _) = gen_coord(&mut rng);
            (a, b, Point::new(cx, cy), false)
        }
    }

    // -----------------------------------------------------------------
    // polygon_area
    // -----------------------------------------------------------------

    fn p1_polygon_area_non_negative_impl(seed: u64) {
        let (poly, _) = gen_polygon(seed, 1);
        let area = polygon_area(&poly);
        assert!(area >= 0.0, "negative area {area} for poly {poly:?}");
    }

    fn p2_area_sign_flips_on_reversal_impl(seed: u64) {
        let (poly, _) = gen_polygon(seed, 2);
        let mut rev = poly.clone();
        rev.reverse();
        let forward = polygon_signed_area(&poly);
        let backward = polygon_signed_area(&rev);
        assert!(
            (forward + backward).abs() < 1e-9,
            "forward={forward}, backward={backward} expected opposite signs"
        );
    }

    // -----------------------------------------------------------------
    // triangle_area
    // -----------------------------------------------------------------

    fn p3_triangle_area_non_negative_impl(seed: u64) {
        let (a, b, c, _) = gen_triangle(seed, 3);
        assert!(triangle_area(&a, &b, &c) >= 0.0);
    }

    fn p4_triangle_area_symmetric_impl(seed: u64) {
        let (a, b, c, _) = gen_triangle(seed, 4);
        let areas = [
            triangle_area(&a, &b, &c),
            triangle_area(&b, &c, &a),
            triangle_area(&c, &a, &b),
            triangle_area(&a, &c, &b),
            triangle_area(&b, &a, &c),
            triangle_area(&c, &b, &a),
        ];
        for pair in areas.windows(2) {
            assert!(
                (pair[0] - pair[1]).abs() < 1e-9,
                "triangle_area varies under permutation: {} != {}", pair[0], pair[1]
            );
        }
    }

    fn p5_triangle_area_matches_polygon_area_impl(seed: u64) {
        let (a, b, c, _) = gen_triangle(seed, 5);
        let poly = vec![a, b, c];
        assert!(
            (triangle_area(&a, &b, &c) - polygon_area(&poly)).abs() < 1e-9,
            "triangle_area != polygon_area"
        );
    }

    // -----------------------------------------------------------------
    // polygon_perimeter
    // -----------------------------------------------------------------

    fn p6_perimeter_non_negative_impl(seed: u64) {
        let (poly, _) = gen_polygon(seed, 6);
        assert!(polygon_perimeter(&poly) >= 0.0);
    }

    fn p7_perimeter_is_sum_of_edge_lengths_impl(seed: u64) {
        let (poly, _) = gen_polygon(seed, 7);
        let n = poly.len();
        let mut sum = 0.0;
        for i in 0..n {
            let j = (i + 1) % n;
            sum += poly[i].distance(&poly[j]);
        }
        assert!(
            (polygon_perimeter(&poly) - sum).abs() < 1e-9,
            "perimeter {} != sum {}", polygon_perimeter(&poly), sum
        );
    }

    // -----------------------------------------------------------------
    // polygon_bounding_box
    // -----------------------------------------------------------------

    fn p8_bounding_box_contains_vertices_impl(seed: u64) {
        let (poly, _) = gen_polygon(seed, 8);
        let bb = polygon_bounding_box(&poly);
        for p in &poly {
            assert!(
                bb.x_min <= p.x && p.x <= bb.x_max,
                "x {} out of [{}, {}]", p.x, bb.x_min, bb.x_max
            );
            assert!(
                bb.y_min <= p.y && p.y <= bb.y_max,
                "y {} out of [{}, {}]", p.y, bb.y_min, bb.y_max
            );
        }
    }

    // -----------------------------------------------------------------
    // translate_polygon
    // -----------------------------------------------------------------

    fn p9_translation_preserves_area_impl(seed: u64) {
        let (poly, _) = gen_polygon(seed, 9);
        let mut rng2 = sub_rng(seed, 90);
        let (tx, _) = gen_coord(&mut rng2);
        let (ty, _) = gen_coord(&mut rng2);
        let translated = translate_polygon(&poly, tx, ty);
        assert!(
            (polygon_area(&poly) - polygon_area(&translated)).abs() < 1e-9,
            "area changed under translation"
        );
    }

    /// Vacuity guard: measures, per property (by its own generator salt),
    /// what fraction of the CAMPAIGN_N seeds actually produced a
    /// deliberately degenerate polygon (collinear / duplicate-heavy) or
    /// collinear triangle, rather than a generic well-separated one.
    #[cfg_attr(test, test)]
    fn wasm_mirror_vacuity_guard() {
        for salt in [1u64, 2, 6, 7, 8, 9] {
            let mut hits = 0usize;
            for seed in 0..CAMPAIGN_N as u64 {
                let (_, was_degenerate) = gen_polygon(seed, salt);
                if was_degenerate {
                    hits += 1;
                }
            }
            let rate = hits as f64 / CAMPAIGN_N as f64;
            assert!(
                rate >= 0.20,
                "gen_polygon salt={salt}: only {hits}/{CAMPAIGN_N} ({:.0}%) \
                 degenerate; expected >= 20% (gen_polygon is 50/50 by \
                 construction)",
                rate * 100.0
            );
        }
        for salt in [3u64, 4, 5] {
            let mut hits = 0usize;
            for seed in 0..CAMPAIGN_N as u64 {
                let (_, _, _, was_collinear) = gen_triangle(seed, salt);
                if was_collinear {
                    hits += 1;
                }
            }
            let rate = hits as f64 / CAMPAIGN_N as f64;
            assert!(
                rate >= 0.20,
                "gen_triangle salt={salt}: only {hits}/{CAMPAIGN_N} ({:.0}%) \
                 collinear; expected >= 20% (gen_triangle is 50/50 by \
                 construction)",
                rate * 100.0
            );
        }
    }

    // 9 properties x 20 seeds = 180 distinct-input wasm tests.
    #[cfg_attr(test, test)]
    fn p1_polygon_area_non_negative_seed_000() { p1_polygon_area_non_negative_impl(0); }
    #[cfg_attr(test, test)]
    fn p1_polygon_area_non_negative_seed_001() { p1_polygon_area_non_negative_impl(1); }
    #[cfg_attr(test, test)]
    fn p1_polygon_area_non_negative_seed_002() { p1_polygon_area_non_negative_impl(2); }
    #[cfg_attr(test, test)]
    fn p1_polygon_area_non_negative_seed_003() { p1_polygon_area_non_negative_impl(3); }
    #[cfg_attr(test, test)]
    fn p1_polygon_area_non_negative_seed_004() { p1_polygon_area_non_negative_impl(4); }
    #[cfg_attr(test, test)]
    fn p1_polygon_area_non_negative_seed_005() { p1_polygon_area_non_negative_impl(5); }
    #[cfg_attr(test, test)]
    fn p1_polygon_area_non_negative_seed_006() { p1_polygon_area_non_negative_impl(6); }
    #[cfg_attr(test, test)]
    fn p1_polygon_area_non_negative_seed_007() { p1_polygon_area_non_negative_impl(7); }
    #[cfg_attr(test, test)]
    fn p1_polygon_area_non_negative_seed_008() { p1_polygon_area_non_negative_impl(8); }
    #[cfg_attr(test, test)]
    fn p1_polygon_area_non_negative_seed_009() { p1_polygon_area_non_negative_impl(9); }
    #[cfg_attr(test, test)]
    fn p1_polygon_area_non_negative_seed_010() { p1_polygon_area_non_negative_impl(10); }
    #[cfg_attr(test, test)]
    fn p1_polygon_area_non_negative_seed_011() { p1_polygon_area_non_negative_impl(11); }
    #[cfg_attr(test, test)]
    fn p1_polygon_area_non_negative_seed_012() { p1_polygon_area_non_negative_impl(12); }
    #[cfg_attr(test, test)]
    fn p1_polygon_area_non_negative_seed_013() { p1_polygon_area_non_negative_impl(13); }
    #[cfg_attr(test, test)]
    fn p1_polygon_area_non_negative_seed_014() { p1_polygon_area_non_negative_impl(14); }
    #[cfg_attr(test, test)]
    fn p1_polygon_area_non_negative_seed_015() { p1_polygon_area_non_negative_impl(15); }
    #[cfg_attr(test, test)]
    fn p1_polygon_area_non_negative_seed_016() { p1_polygon_area_non_negative_impl(16); }
    #[cfg_attr(test, test)]
    fn p1_polygon_area_non_negative_seed_017() { p1_polygon_area_non_negative_impl(17); }
    #[cfg_attr(test, test)]
    fn p1_polygon_area_non_negative_seed_018() { p1_polygon_area_non_negative_impl(18); }
    #[cfg_attr(test, test)]
    fn p1_polygon_area_non_negative_seed_019() { p1_polygon_area_non_negative_impl(19); }
    #[cfg_attr(test, test)]
    fn p2_area_sign_flips_on_reversal_seed_000() { p2_area_sign_flips_on_reversal_impl(0); }
    #[cfg_attr(test, test)]
    fn p2_area_sign_flips_on_reversal_seed_001() { p2_area_sign_flips_on_reversal_impl(1); }
    #[cfg_attr(test, test)]
    fn p2_area_sign_flips_on_reversal_seed_002() { p2_area_sign_flips_on_reversal_impl(2); }
    #[cfg_attr(test, test)]
    fn p2_area_sign_flips_on_reversal_seed_003() { p2_area_sign_flips_on_reversal_impl(3); }
    #[cfg_attr(test, test)]
    fn p2_area_sign_flips_on_reversal_seed_004() { p2_area_sign_flips_on_reversal_impl(4); }
    #[cfg_attr(test, test)]
    fn p2_area_sign_flips_on_reversal_seed_005() { p2_area_sign_flips_on_reversal_impl(5); }
    #[cfg_attr(test, test)]
    fn p2_area_sign_flips_on_reversal_seed_006() { p2_area_sign_flips_on_reversal_impl(6); }
    #[cfg_attr(test, test)]
    fn p2_area_sign_flips_on_reversal_seed_007() { p2_area_sign_flips_on_reversal_impl(7); }
    #[cfg_attr(test, test)]
    fn p2_area_sign_flips_on_reversal_seed_008() { p2_area_sign_flips_on_reversal_impl(8); }
    #[cfg_attr(test, test)]
    fn p2_area_sign_flips_on_reversal_seed_009() { p2_area_sign_flips_on_reversal_impl(9); }
    #[cfg_attr(test, test)]
    fn p2_area_sign_flips_on_reversal_seed_010() { p2_area_sign_flips_on_reversal_impl(10); }
    #[cfg_attr(test, test)]
    fn p2_area_sign_flips_on_reversal_seed_011() { p2_area_sign_flips_on_reversal_impl(11); }
    #[cfg_attr(test, test)]
    fn p2_area_sign_flips_on_reversal_seed_012() { p2_area_sign_flips_on_reversal_impl(12); }
    #[cfg_attr(test, test)]
    fn p2_area_sign_flips_on_reversal_seed_013() { p2_area_sign_flips_on_reversal_impl(13); }
    #[cfg_attr(test, test)]
    fn p2_area_sign_flips_on_reversal_seed_014() { p2_area_sign_flips_on_reversal_impl(14); }
    #[cfg_attr(test, test)]
    fn p2_area_sign_flips_on_reversal_seed_015() { p2_area_sign_flips_on_reversal_impl(15); }
    #[cfg_attr(test, test)]
    fn p2_area_sign_flips_on_reversal_seed_016() { p2_area_sign_flips_on_reversal_impl(16); }
    #[cfg_attr(test, test)]
    fn p2_area_sign_flips_on_reversal_seed_017() { p2_area_sign_flips_on_reversal_impl(17); }
    #[cfg_attr(test, test)]
    fn p2_area_sign_flips_on_reversal_seed_018() { p2_area_sign_flips_on_reversal_impl(18); }
    #[cfg_attr(test, test)]
    fn p2_area_sign_flips_on_reversal_seed_019() { p2_area_sign_flips_on_reversal_impl(19); }
    #[cfg_attr(test, test)]
    fn p3_triangle_area_non_negative_seed_000() { p3_triangle_area_non_negative_impl(0); }
    #[cfg_attr(test, test)]
    fn p3_triangle_area_non_negative_seed_001() { p3_triangle_area_non_negative_impl(1); }
    #[cfg_attr(test, test)]
    fn p3_triangle_area_non_negative_seed_002() { p3_triangle_area_non_negative_impl(2); }
    #[cfg_attr(test, test)]
    fn p3_triangle_area_non_negative_seed_003() { p3_triangle_area_non_negative_impl(3); }
    #[cfg_attr(test, test)]
    fn p3_triangle_area_non_negative_seed_004() { p3_triangle_area_non_negative_impl(4); }
    #[cfg_attr(test, test)]
    fn p3_triangle_area_non_negative_seed_005() { p3_triangle_area_non_negative_impl(5); }
    #[cfg_attr(test, test)]
    fn p3_triangle_area_non_negative_seed_006() { p3_triangle_area_non_negative_impl(6); }
    #[cfg_attr(test, test)]
    fn p3_triangle_area_non_negative_seed_007() { p3_triangle_area_non_negative_impl(7); }
    #[cfg_attr(test, test)]
    fn p3_triangle_area_non_negative_seed_008() { p3_triangle_area_non_negative_impl(8); }
    #[cfg_attr(test, test)]
    fn p3_triangle_area_non_negative_seed_009() { p3_triangle_area_non_negative_impl(9); }
    #[cfg_attr(test, test)]
    fn p3_triangle_area_non_negative_seed_010() { p3_triangle_area_non_negative_impl(10); }
    #[cfg_attr(test, test)]
    fn p3_triangle_area_non_negative_seed_011() { p3_triangle_area_non_negative_impl(11); }
    #[cfg_attr(test, test)]
    fn p3_triangle_area_non_negative_seed_012() { p3_triangle_area_non_negative_impl(12); }
    #[cfg_attr(test, test)]
    fn p3_triangle_area_non_negative_seed_013() { p3_triangle_area_non_negative_impl(13); }
    #[cfg_attr(test, test)]
    fn p3_triangle_area_non_negative_seed_014() { p3_triangle_area_non_negative_impl(14); }
    #[cfg_attr(test, test)]
    fn p3_triangle_area_non_negative_seed_015() { p3_triangle_area_non_negative_impl(15); }
    #[cfg_attr(test, test)]
    fn p3_triangle_area_non_negative_seed_016() { p3_triangle_area_non_negative_impl(16); }
    #[cfg_attr(test, test)]
    fn p3_triangle_area_non_negative_seed_017() { p3_triangle_area_non_negative_impl(17); }
    #[cfg_attr(test, test)]
    fn p3_triangle_area_non_negative_seed_018() { p3_triangle_area_non_negative_impl(18); }
    #[cfg_attr(test, test)]
    fn p3_triangle_area_non_negative_seed_019() { p3_triangle_area_non_negative_impl(19); }
    #[cfg_attr(test, test)]
    fn p4_triangle_area_symmetric_seed_000() { p4_triangle_area_symmetric_impl(0); }
    #[cfg_attr(test, test)]
    fn p4_triangle_area_symmetric_seed_001() { p4_triangle_area_symmetric_impl(1); }
    #[cfg_attr(test, test)]
    fn p4_triangle_area_symmetric_seed_002() { p4_triangle_area_symmetric_impl(2); }
    #[cfg_attr(test, test)]
    fn p4_triangle_area_symmetric_seed_003() { p4_triangle_area_symmetric_impl(3); }
    #[cfg_attr(test, test)]
    fn p4_triangle_area_symmetric_seed_004() { p4_triangle_area_symmetric_impl(4); }
    #[cfg_attr(test, test)]
    fn p4_triangle_area_symmetric_seed_005() { p4_triangle_area_symmetric_impl(5); }
    #[cfg_attr(test, test)]
    fn p4_triangle_area_symmetric_seed_006() { p4_triangle_area_symmetric_impl(6); }
    #[cfg_attr(test, test)]
    fn p4_triangle_area_symmetric_seed_007() { p4_triangle_area_symmetric_impl(7); }
    #[cfg_attr(test, test)]
    fn p4_triangle_area_symmetric_seed_008() { p4_triangle_area_symmetric_impl(8); }
    #[cfg_attr(test, test)]
    fn p4_triangle_area_symmetric_seed_009() { p4_triangle_area_symmetric_impl(9); }
    #[cfg_attr(test, test)]
    fn p4_triangle_area_symmetric_seed_010() { p4_triangle_area_symmetric_impl(10); }
    #[cfg_attr(test, test)]
    fn p4_triangle_area_symmetric_seed_011() { p4_triangle_area_symmetric_impl(11); }
    #[cfg_attr(test, test)]
    fn p4_triangle_area_symmetric_seed_012() { p4_triangle_area_symmetric_impl(12); }
    #[cfg_attr(test, test)]
    fn p4_triangle_area_symmetric_seed_013() { p4_triangle_area_symmetric_impl(13); }
    #[cfg_attr(test, test)]
    fn p4_triangle_area_symmetric_seed_014() { p4_triangle_area_symmetric_impl(14); }
    #[cfg_attr(test, test)]
    fn p4_triangle_area_symmetric_seed_015() { p4_triangle_area_symmetric_impl(15); }
    #[cfg_attr(test, test)]
    fn p4_triangle_area_symmetric_seed_016() { p4_triangle_area_symmetric_impl(16); }
    #[cfg_attr(test, test)]
    fn p4_triangle_area_symmetric_seed_017() { p4_triangle_area_symmetric_impl(17); }
    #[cfg_attr(test, test)]
    fn p4_triangle_area_symmetric_seed_018() { p4_triangle_area_symmetric_impl(18); }
    #[cfg_attr(test, test)]
    fn p4_triangle_area_symmetric_seed_019() { p4_triangle_area_symmetric_impl(19); }
    #[cfg_attr(test, test)]
    fn p5_triangle_area_matches_polygon_area_seed_000() { p5_triangle_area_matches_polygon_area_impl(0); }
    #[cfg_attr(test, test)]
    fn p5_triangle_area_matches_polygon_area_seed_001() { p5_triangle_area_matches_polygon_area_impl(1); }
    #[cfg_attr(test, test)]
    fn p5_triangle_area_matches_polygon_area_seed_002() { p5_triangle_area_matches_polygon_area_impl(2); }
    #[cfg_attr(test, test)]
    fn p5_triangle_area_matches_polygon_area_seed_003() { p5_triangle_area_matches_polygon_area_impl(3); }
    #[cfg_attr(test, test)]
    fn p5_triangle_area_matches_polygon_area_seed_004() { p5_triangle_area_matches_polygon_area_impl(4); }
    #[cfg_attr(test, test)]
    fn p5_triangle_area_matches_polygon_area_seed_005() { p5_triangle_area_matches_polygon_area_impl(5); }
    #[cfg_attr(test, test)]
    fn p5_triangle_area_matches_polygon_area_seed_006() { p5_triangle_area_matches_polygon_area_impl(6); }
    #[cfg_attr(test, test)]
    fn p5_triangle_area_matches_polygon_area_seed_007() { p5_triangle_area_matches_polygon_area_impl(7); }
    #[cfg_attr(test, test)]
    fn p5_triangle_area_matches_polygon_area_seed_008() { p5_triangle_area_matches_polygon_area_impl(8); }
    #[cfg_attr(test, test)]
    fn p5_triangle_area_matches_polygon_area_seed_009() { p5_triangle_area_matches_polygon_area_impl(9); }
    #[cfg_attr(test, test)]
    fn p5_triangle_area_matches_polygon_area_seed_010() { p5_triangle_area_matches_polygon_area_impl(10); }
    #[cfg_attr(test, test)]
    fn p5_triangle_area_matches_polygon_area_seed_011() { p5_triangle_area_matches_polygon_area_impl(11); }
    #[cfg_attr(test, test)]
    fn p5_triangle_area_matches_polygon_area_seed_012() { p5_triangle_area_matches_polygon_area_impl(12); }
    #[cfg_attr(test, test)]
    fn p5_triangle_area_matches_polygon_area_seed_013() { p5_triangle_area_matches_polygon_area_impl(13); }
    #[cfg_attr(test, test)]
    fn p5_triangle_area_matches_polygon_area_seed_014() { p5_triangle_area_matches_polygon_area_impl(14); }
    #[cfg_attr(test, test)]
    fn p5_triangle_area_matches_polygon_area_seed_015() { p5_triangle_area_matches_polygon_area_impl(15); }
    #[cfg_attr(test, test)]
    fn p5_triangle_area_matches_polygon_area_seed_016() { p5_triangle_area_matches_polygon_area_impl(16); }
    #[cfg_attr(test, test)]
    fn p5_triangle_area_matches_polygon_area_seed_017() { p5_triangle_area_matches_polygon_area_impl(17); }
    #[cfg_attr(test, test)]
    fn p5_triangle_area_matches_polygon_area_seed_018() { p5_triangle_area_matches_polygon_area_impl(18); }
    #[cfg_attr(test, test)]
    fn p5_triangle_area_matches_polygon_area_seed_019() { p5_triangle_area_matches_polygon_area_impl(19); }
    #[cfg_attr(test, test)]
    fn p6_perimeter_non_negative_seed_000() { p6_perimeter_non_negative_impl(0); }
    #[cfg_attr(test, test)]
    fn p6_perimeter_non_negative_seed_001() { p6_perimeter_non_negative_impl(1); }
    #[cfg_attr(test, test)]
    fn p6_perimeter_non_negative_seed_002() { p6_perimeter_non_negative_impl(2); }
    #[cfg_attr(test, test)]
    fn p6_perimeter_non_negative_seed_003() { p6_perimeter_non_negative_impl(3); }
    #[cfg_attr(test, test)]
    fn p6_perimeter_non_negative_seed_004() { p6_perimeter_non_negative_impl(4); }
    #[cfg_attr(test, test)]
    fn p6_perimeter_non_negative_seed_005() { p6_perimeter_non_negative_impl(5); }
    #[cfg_attr(test, test)]
    fn p6_perimeter_non_negative_seed_006() { p6_perimeter_non_negative_impl(6); }
    #[cfg_attr(test, test)]
    fn p6_perimeter_non_negative_seed_007() { p6_perimeter_non_negative_impl(7); }
    #[cfg_attr(test, test)]
    fn p6_perimeter_non_negative_seed_008() { p6_perimeter_non_negative_impl(8); }
    #[cfg_attr(test, test)]
    fn p6_perimeter_non_negative_seed_009() { p6_perimeter_non_negative_impl(9); }
    #[cfg_attr(test, test)]
    fn p6_perimeter_non_negative_seed_010() { p6_perimeter_non_negative_impl(10); }
    #[cfg_attr(test, test)]
    fn p6_perimeter_non_negative_seed_011() { p6_perimeter_non_negative_impl(11); }
    #[cfg_attr(test, test)]
    fn p6_perimeter_non_negative_seed_012() { p6_perimeter_non_negative_impl(12); }
    #[cfg_attr(test, test)]
    fn p6_perimeter_non_negative_seed_013() { p6_perimeter_non_negative_impl(13); }
    #[cfg_attr(test, test)]
    fn p6_perimeter_non_negative_seed_014() { p6_perimeter_non_negative_impl(14); }
    #[cfg_attr(test, test)]
    fn p6_perimeter_non_negative_seed_015() { p6_perimeter_non_negative_impl(15); }
    #[cfg_attr(test, test)]
    fn p6_perimeter_non_negative_seed_016() { p6_perimeter_non_negative_impl(16); }
    #[cfg_attr(test, test)]
    fn p6_perimeter_non_negative_seed_017() { p6_perimeter_non_negative_impl(17); }
    #[cfg_attr(test, test)]
    fn p6_perimeter_non_negative_seed_018() { p6_perimeter_non_negative_impl(18); }
    #[cfg_attr(test, test)]
    fn p6_perimeter_non_negative_seed_019() { p6_perimeter_non_negative_impl(19); }
    #[cfg_attr(test, test)]
    fn p7_perimeter_is_sum_of_edge_lengths_seed_000() { p7_perimeter_is_sum_of_edge_lengths_impl(0); }
    #[cfg_attr(test, test)]
    fn p7_perimeter_is_sum_of_edge_lengths_seed_001() { p7_perimeter_is_sum_of_edge_lengths_impl(1); }
    #[cfg_attr(test, test)]
    fn p7_perimeter_is_sum_of_edge_lengths_seed_002() { p7_perimeter_is_sum_of_edge_lengths_impl(2); }
    #[cfg_attr(test, test)]
    fn p7_perimeter_is_sum_of_edge_lengths_seed_003() { p7_perimeter_is_sum_of_edge_lengths_impl(3); }
    #[cfg_attr(test, test)]
    fn p7_perimeter_is_sum_of_edge_lengths_seed_004() { p7_perimeter_is_sum_of_edge_lengths_impl(4); }
    #[cfg_attr(test, test)]
    fn p7_perimeter_is_sum_of_edge_lengths_seed_005() { p7_perimeter_is_sum_of_edge_lengths_impl(5); }
    #[cfg_attr(test, test)]
    fn p7_perimeter_is_sum_of_edge_lengths_seed_006() { p7_perimeter_is_sum_of_edge_lengths_impl(6); }
    #[cfg_attr(test, test)]
    fn p7_perimeter_is_sum_of_edge_lengths_seed_007() { p7_perimeter_is_sum_of_edge_lengths_impl(7); }
    #[cfg_attr(test, test)]
    fn p7_perimeter_is_sum_of_edge_lengths_seed_008() { p7_perimeter_is_sum_of_edge_lengths_impl(8); }
    #[cfg_attr(test, test)]
    fn p7_perimeter_is_sum_of_edge_lengths_seed_009() { p7_perimeter_is_sum_of_edge_lengths_impl(9); }
    #[cfg_attr(test, test)]
    fn p7_perimeter_is_sum_of_edge_lengths_seed_010() { p7_perimeter_is_sum_of_edge_lengths_impl(10); }
    #[cfg_attr(test, test)]
    fn p7_perimeter_is_sum_of_edge_lengths_seed_011() { p7_perimeter_is_sum_of_edge_lengths_impl(11); }
    #[cfg_attr(test, test)]
    fn p7_perimeter_is_sum_of_edge_lengths_seed_012() { p7_perimeter_is_sum_of_edge_lengths_impl(12); }
    #[cfg_attr(test, test)]
    fn p7_perimeter_is_sum_of_edge_lengths_seed_013() { p7_perimeter_is_sum_of_edge_lengths_impl(13); }
    #[cfg_attr(test, test)]
    fn p7_perimeter_is_sum_of_edge_lengths_seed_014() { p7_perimeter_is_sum_of_edge_lengths_impl(14); }
    #[cfg_attr(test, test)]
    fn p7_perimeter_is_sum_of_edge_lengths_seed_015() { p7_perimeter_is_sum_of_edge_lengths_impl(15); }
    #[cfg_attr(test, test)]
    fn p7_perimeter_is_sum_of_edge_lengths_seed_016() { p7_perimeter_is_sum_of_edge_lengths_impl(16); }
    #[cfg_attr(test, test)]
    fn p7_perimeter_is_sum_of_edge_lengths_seed_017() { p7_perimeter_is_sum_of_edge_lengths_impl(17); }
    #[cfg_attr(test, test)]
    fn p7_perimeter_is_sum_of_edge_lengths_seed_018() { p7_perimeter_is_sum_of_edge_lengths_impl(18); }
    #[cfg_attr(test, test)]
    fn p7_perimeter_is_sum_of_edge_lengths_seed_019() { p7_perimeter_is_sum_of_edge_lengths_impl(19); }
    #[cfg_attr(test, test)]
    fn p8_bounding_box_contains_vertices_seed_000() { p8_bounding_box_contains_vertices_impl(0); }
    #[cfg_attr(test, test)]
    fn p8_bounding_box_contains_vertices_seed_001() { p8_bounding_box_contains_vertices_impl(1); }
    #[cfg_attr(test, test)]
    fn p8_bounding_box_contains_vertices_seed_002() { p8_bounding_box_contains_vertices_impl(2); }
    #[cfg_attr(test, test)]
    fn p8_bounding_box_contains_vertices_seed_003() { p8_bounding_box_contains_vertices_impl(3); }
    #[cfg_attr(test, test)]
    fn p8_bounding_box_contains_vertices_seed_004() { p8_bounding_box_contains_vertices_impl(4); }
    #[cfg_attr(test, test)]
    fn p8_bounding_box_contains_vertices_seed_005() { p8_bounding_box_contains_vertices_impl(5); }
    #[cfg_attr(test, test)]
    fn p8_bounding_box_contains_vertices_seed_006() { p8_bounding_box_contains_vertices_impl(6); }
    #[cfg_attr(test, test)]
    fn p8_bounding_box_contains_vertices_seed_007() { p8_bounding_box_contains_vertices_impl(7); }
    #[cfg_attr(test, test)]
    fn p8_bounding_box_contains_vertices_seed_008() { p8_bounding_box_contains_vertices_impl(8); }
    #[cfg_attr(test, test)]
    fn p8_bounding_box_contains_vertices_seed_009() { p8_bounding_box_contains_vertices_impl(9); }
    #[cfg_attr(test, test)]
    fn p8_bounding_box_contains_vertices_seed_010() { p8_bounding_box_contains_vertices_impl(10); }
    #[cfg_attr(test, test)]
    fn p8_bounding_box_contains_vertices_seed_011() { p8_bounding_box_contains_vertices_impl(11); }
    #[cfg_attr(test, test)]
    fn p8_bounding_box_contains_vertices_seed_012() { p8_bounding_box_contains_vertices_impl(12); }
    #[cfg_attr(test, test)]
    fn p8_bounding_box_contains_vertices_seed_013() { p8_bounding_box_contains_vertices_impl(13); }
    #[cfg_attr(test, test)]
    fn p8_bounding_box_contains_vertices_seed_014() { p8_bounding_box_contains_vertices_impl(14); }
    #[cfg_attr(test, test)]
    fn p8_bounding_box_contains_vertices_seed_015() { p8_bounding_box_contains_vertices_impl(15); }
    #[cfg_attr(test, test)]
    fn p8_bounding_box_contains_vertices_seed_016() { p8_bounding_box_contains_vertices_impl(16); }
    #[cfg_attr(test, test)]
    fn p8_bounding_box_contains_vertices_seed_017() { p8_bounding_box_contains_vertices_impl(17); }
    #[cfg_attr(test, test)]
    fn p8_bounding_box_contains_vertices_seed_018() { p8_bounding_box_contains_vertices_impl(18); }
    #[cfg_attr(test, test)]
    fn p8_bounding_box_contains_vertices_seed_019() { p8_bounding_box_contains_vertices_impl(19); }
    #[cfg_attr(test, test)]
    fn p9_translation_preserves_area_seed_000() { p9_translation_preserves_area_impl(0); }
    #[cfg_attr(test, test)]
    fn p9_translation_preserves_area_seed_001() { p9_translation_preserves_area_impl(1); }
    #[cfg_attr(test, test)]
    fn p9_translation_preserves_area_seed_002() { p9_translation_preserves_area_impl(2); }
    #[cfg_attr(test, test)]
    fn p9_translation_preserves_area_seed_003() { p9_translation_preserves_area_impl(3); }
    #[cfg_attr(test, test)]
    fn p9_translation_preserves_area_seed_004() { p9_translation_preserves_area_impl(4); }
    #[cfg_attr(test, test)]
    fn p9_translation_preserves_area_seed_005() { p9_translation_preserves_area_impl(5); }
    #[cfg_attr(test, test)]
    fn p9_translation_preserves_area_seed_006() { p9_translation_preserves_area_impl(6); }
    #[cfg_attr(test, test)]
    fn p9_translation_preserves_area_seed_007() { p9_translation_preserves_area_impl(7); }
    #[cfg_attr(test, test)]
    fn p9_translation_preserves_area_seed_008() { p9_translation_preserves_area_impl(8); }
    #[cfg_attr(test, test)]
    fn p9_translation_preserves_area_seed_009() { p9_translation_preserves_area_impl(9); }
    #[cfg_attr(test, test)]
    fn p9_translation_preserves_area_seed_010() { p9_translation_preserves_area_impl(10); }
    #[cfg_attr(test, test)]
    fn p9_translation_preserves_area_seed_011() { p9_translation_preserves_area_impl(11); }
    #[cfg_attr(test, test)]
    fn p9_translation_preserves_area_seed_012() { p9_translation_preserves_area_impl(12); }
    #[cfg_attr(test, test)]
    fn p9_translation_preserves_area_seed_013() { p9_translation_preserves_area_impl(13); }
    #[cfg_attr(test, test)]
    fn p9_translation_preserves_area_seed_014() { p9_translation_preserves_area_impl(14); }
    #[cfg_attr(test, test)]
    fn p9_translation_preserves_area_seed_015() { p9_translation_preserves_area_impl(15); }
    #[cfg_attr(test, test)]
    fn p9_translation_preserves_area_seed_016() { p9_translation_preserves_area_impl(16); }
    #[cfg_attr(test, test)]
    fn p9_translation_preserves_area_seed_017() { p9_translation_preserves_area_impl(17); }
    #[cfg_attr(test, test)]
    fn p9_translation_preserves_area_seed_018() { p9_translation_preserves_area_impl(18); }
    #[cfg_attr(test, test)]
    fn p9_translation_preserves_area_seed_019() { p9_translation_preserves_area_impl(19); }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("polygon::tests::test_polygon_area_square", test_polygon_area_square),
        ("polygon::tests::test_polygon_signed_area_ccw", test_polygon_signed_area_ccw),
        ("polygon::tests::test_polygon_signed_area_cw", test_polygon_signed_area_cw),
        ("polygon::tests::test_polygon_area_empty", test_polygon_area_empty),
        ("polygon::tests::test_polygon_signed_area_less_than_3", test_polygon_signed_area_less_than_3),
        ("polygon::tests::test_triangle_area_basic", test_triangle_area_basic),
        ("polygon::tests::test_triangle_area_right_triangle", test_triangle_area_right_triangle),
        ("polygon::tests::test_triangle_area_via_shoelace", test_triangle_area_via_shoelace),
        ("polygon::tests::test_centroid_square", test_centroid_square),
        ("polygon::tests::test_centroid_triangle", test_centroid_triangle),
        ("polygon::tests::test_centroid_degenerate_fallback", test_centroid_degenerate_fallback),
        ("polygon::tests::test_point_in_polygon_inside", test_point_in_polygon_inside),
        ("polygon::tests::test_point_in_polygon_outside", test_point_in_polygon_outside),
        ("polygon::tests::test_point_in_polygon_on_edge", test_point_in_polygon_on_edge),
        ("polygon::tests::test_point_in_polygon_on_vertex", test_point_in_polygon_on_vertex),
        ("polygon::tests::test_point_in_polygon_soft_inside", test_point_in_polygon_soft_inside),
        ("polygon::tests::test_point_in_polygon_soft_outside", test_point_in_polygon_soft_outside),
        ("polygon::tests::test_point_in_rect_inside", test_point_in_rect_inside),
        ("polygon::tests::test_point_in_rect_outside", test_point_in_rect_outside),
        ("polygon::tests::test_point_in_rect_soft_inside", test_point_in_rect_soft_inside),
        ("polygon::tests::test_point_in_rect_soft_outside", test_point_in_rect_soft_outside),
        ("polygon::tests::test_perimeter_square", test_perimeter_square),
        ("polygon::tests::test_loop_area_matches_polygon_area", test_loop_area_matches_polygon_area),
        ("polygon::tests::test_loop_perimeter_matches", test_loop_perimeter_matches),
        ("polygon::tests::test_loop_area_penalty_no_violation", test_loop_area_penalty_no_violation),
        ("polygon::tests::test_loop_area_penalty_with_violation", test_loop_area_penalty_with_violation),
        ("polygon::tests::test_bounding_box_square", test_bounding_box_square),
        ("polygon::tests::test_bounding_circle_square", test_bounding_circle_square),
        ("polygon::tests::test_is_convex_square", test_is_convex_square),
        ("polygon::tests::test_is_convex_star", test_is_convex_star),
        ("polygon::tests::test_is_convex_triangle", test_is_convex_triangle),
        ("polygon::tests::test_orientation_ccw", test_orientation_ccw),
        ("polygon::tests::test_orientation_cw", test_orientation_cw),
        ("polygon::tests::test_nearest_point_on_segment_midpoint", test_nearest_point_on_segment_midpoint),
        ("polygon::tests::test_nearest_point_on_segment_clamped", test_nearest_point_on_segment_clamped),
        ("polygon::tests::test_nearest_point_on_polygon_inside", test_nearest_point_on_polygon_inside),
        ("polygon::tests::test_nearest_point_on_polygon_outside", test_nearest_point_on_polygon_outside),
        ("polygon::tests::test_nearest_point_on_polygon_empty", test_nearest_point_on_polygon_empty),
        ("polygon::tests::test_translate_polygon", test_translate_polygon),
        ("polygon::tests::test_scale_polygon_uniform", test_scale_polygon_uniform),
        ("polygon::tests::test_rotate_polygon_90_degrees", test_rotate_polygon_90_degrees),
        ("polygon::tests::test_sigmoid_zero", test_sigmoid_zero),
        ("polygon::tests::wasm_mirror_vacuity_guard", wasm_mirror_vacuity_guard),
        ("polygon::tests::p1_polygon_area_non_negative_seed_000", p1_polygon_area_non_negative_seed_000),
        ("polygon::tests::p1_polygon_area_non_negative_seed_001", p1_polygon_area_non_negative_seed_001),
        ("polygon::tests::p1_polygon_area_non_negative_seed_002", p1_polygon_area_non_negative_seed_002),
        ("polygon::tests::p1_polygon_area_non_negative_seed_003", p1_polygon_area_non_negative_seed_003),
        ("polygon::tests::p1_polygon_area_non_negative_seed_004", p1_polygon_area_non_negative_seed_004),
        ("polygon::tests::p1_polygon_area_non_negative_seed_005", p1_polygon_area_non_negative_seed_005),
        ("polygon::tests::p1_polygon_area_non_negative_seed_006", p1_polygon_area_non_negative_seed_006),
        ("polygon::tests::p1_polygon_area_non_negative_seed_007", p1_polygon_area_non_negative_seed_007),
        ("polygon::tests::p1_polygon_area_non_negative_seed_008", p1_polygon_area_non_negative_seed_008),
        ("polygon::tests::p1_polygon_area_non_negative_seed_009", p1_polygon_area_non_negative_seed_009),
        ("polygon::tests::p1_polygon_area_non_negative_seed_010", p1_polygon_area_non_negative_seed_010),
        ("polygon::tests::p1_polygon_area_non_negative_seed_011", p1_polygon_area_non_negative_seed_011),
        ("polygon::tests::p1_polygon_area_non_negative_seed_012", p1_polygon_area_non_negative_seed_012),
        ("polygon::tests::p1_polygon_area_non_negative_seed_013", p1_polygon_area_non_negative_seed_013),
        ("polygon::tests::p1_polygon_area_non_negative_seed_014", p1_polygon_area_non_negative_seed_014),
        ("polygon::tests::p1_polygon_area_non_negative_seed_015", p1_polygon_area_non_negative_seed_015),
        ("polygon::tests::p1_polygon_area_non_negative_seed_016", p1_polygon_area_non_negative_seed_016),
        ("polygon::tests::p1_polygon_area_non_negative_seed_017", p1_polygon_area_non_negative_seed_017),
        ("polygon::tests::p1_polygon_area_non_negative_seed_018", p1_polygon_area_non_negative_seed_018),
        ("polygon::tests::p1_polygon_area_non_negative_seed_019", p1_polygon_area_non_negative_seed_019),
        ("polygon::tests::p2_area_sign_flips_on_reversal_seed_000", p2_area_sign_flips_on_reversal_seed_000),
        ("polygon::tests::p2_area_sign_flips_on_reversal_seed_001", p2_area_sign_flips_on_reversal_seed_001),
        ("polygon::tests::p2_area_sign_flips_on_reversal_seed_002", p2_area_sign_flips_on_reversal_seed_002),
        ("polygon::tests::p2_area_sign_flips_on_reversal_seed_003", p2_area_sign_flips_on_reversal_seed_003),
        ("polygon::tests::p2_area_sign_flips_on_reversal_seed_004", p2_area_sign_flips_on_reversal_seed_004),
        ("polygon::tests::p2_area_sign_flips_on_reversal_seed_005", p2_area_sign_flips_on_reversal_seed_005),
        ("polygon::tests::p2_area_sign_flips_on_reversal_seed_006", p2_area_sign_flips_on_reversal_seed_006),
        ("polygon::tests::p2_area_sign_flips_on_reversal_seed_007", p2_area_sign_flips_on_reversal_seed_007),
        ("polygon::tests::p2_area_sign_flips_on_reversal_seed_008", p2_area_sign_flips_on_reversal_seed_008),
        ("polygon::tests::p2_area_sign_flips_on_reversal_seed_009", p2_area_sign_flips_on_reversal_seed_009),
        ("polygon::tests::p2_area_sign_flips_on_reversal_seed_010", p2_area_sign_flips_on_reversal_seed_010),
        ("polygon::tests::p2_area_sign_flips_on_reversal_seed_011", p2_area_sign_flips_on_reversal_seed_011),
        ("polygon::tests::p2_area_sign_flips_on_reversal_seed_012", p2_area_sign_flips_on_reversal_seed_012),
        ("polygon::tests::p2_area_sign_flips_on_reversal_seed_013", p2_area_sign_flips_on_reversal_seed_013),
        ("polygon::tests::p2_area_sign_flips_on_reversal_seed_014", p2_area_sign_flips_on_reversal_seed_014),
        ("polygon::tests::p2_area_sign_flips_on_reversal_seed_015", p2_area_sign_flips_on_reversal_seed_015),
        ("polygon::tests::p2_area_sign_flips_on_reversal_seed_016", p2_area_sign_flips_on_reversal_seed_016),
        ("polygon::tests::p2_area_sign_flips_on_reversal_seed_017", p2_area_sign_flips_on_reversal_seed_017),
        ("polygon::tests::p2_area_sign_flips_on_reversal_seed_018", p2_area_sign_flips_on_reversal_seed_018),
        ("polygon::tests::p2_area_sign_flips_on_reversal_seed_019", p2_area_sign_flips_on_reversal_seed_019),
        ("polygon::tests::p3_triangle_area_non_negative_seed_000", p3_triangle_area_non_negative_seed_000),
        ("polygon::tests::p3_triangle_area_non_negative_seed_001", p3_triangle_area_non_negative_seed_001),
        ("polygon::tests::p3_triangle_area_non_negative_seed_002", p3_triangle_area_non_negative_seed_002),
        ("polygon::tests::p3_triangle_area_non_negative_seed_003", p3_triangle_area_non_negative_seed_003),
        ("polygon::tests::p3_triangle_area_non_negative_seed_004", p3_triangle_area_non_negative_seed_004),
        ("polygon::tests::p3_triangle_area_non_negative_seed_005", p3_triangle_area_non_negative_seed_005),
        ("polygon::tests::p3_triangle_area_non_negative_seed_006", p3_triangle_area_non_negative_seed_006),
        ("polygon::tests::p3_triangle_area_non_negative_seed_007", p3_triangle_area_non_negative_seed_007),
        ("polygon::tests::p3_triangle_area_non_negative_seed_008", p3_triangle_area_non_negative_seed_008),
        ("polygon::tests::p3_triangle_area_non_negative_seed_009", p3_triangle_area_non_negative_seed_009),
        ("polygon::tests::p3_triangle_area_non_negative_seed_010", p3_triangle_area_non_negative_seed_010),
        ("polygon::tests::p3_triangle_area_non_negative_seed_011", p3_triangle_area_non_negative_seed_011),
        ("polygon::tests::p3_triangle_area_non_negative_seed_012", p3_triangle_area_non_negative_seed_012),
        ("polygon::tests::p3_triangle_area_non_negative_seed_013", p3_triangle_area_non_negative_seed_013),
        ("polygon::tests::p3_triangle_area_non_negative_seed_014", p3_triangle_area_non_negative_seed_014),
        ("polygon::tests::p3_triangle_area_non_negative_seed_015", p3_triangle_area_non_negative_seed_015),
        ("polygon::tests::p3_triangle_area_non_negative_seed_016", p3_triangle_area_non_negative_seed_016),
        ("polygon::tests::p3_triangle_area_non_negative_seed_017", p3_triangle_area_non_negative_seed_017),
        ("polygon::tests::p3_triangle_area_non_negative_seed_018", p3_triangle_area_non_negative_seed_018),
        ("polygon::tests::p3_triangle_area_non_negative_seed_019", p3_triangle_area_non_negative_seed_019),
        ("polygon::tests::p4_triangle_area_symmetric_seed_000", p4_triangle_area_symmetric_seed_000),
        ("polygon::tests::p4_triangle_area_symmetric_seed_001", p4_triangle_area_symmetric_seed_001),
        ("polygon::tests::p4_triangle_area_symmetric_seed_002", p4_triangle_area_symmetric_seed_002),
        ("polygon::tests::p4_triangle_area_symmetric_seed_003", p4_triangle_area_symmetric_seed_003),
        ("polygon::tests::p4_triangle_area_symmetric_seed_004", p4_triangle_area_symmetric_seed_004),
        ("polygon::tests::p4_triangle_area_symmetric_seed_005", p4_triangle_area_symmetric_seed_005),
        ("polygon::tests::p4_triangle_area_symmetric_seed_006", p4_triangle_area_symmetric_seed_006),
        ("polygon::tests::p4_triangle_area_symmetric_seed_007", p4_triangle_area_symmetric_seed_007),
        ("polygon::tests::p4_triangle_area_symmetric_seed_008", p4_triangle_area_symmetric_seed_008),
        ("polygon::tests::p4_triangle_area_symmetric_seed_009", p4_triangle_area_symmetric_seed_009),
        ("polygon::tests::p4_triangle_area_symmetric_seed_010", p4_triangle_area_symmetric_seed_010),
        ("polygon::tests::p4_triangle_area_symmetric_seed_011", p4_triangle_area_symmetric_seed_011),
        ("polygon::tests::p4_triangle_area_symmetric_seed_012", p4_triangle_area_symmetric_seed_012),
        ("polygon::tests::p4_triangle_area_symmetric_seed_013", p4_triangle_area_symmetric_seed_013),
        ("polygon::tests::p4_triangle_area_symmetric_seed_014", p4_triangle_area_symmetric_seed_014),
        ("polygon::tests::p4_triangle_area_symmetric_seed_015", p4_triangle_area_symmetric_seed_015),
        ("polygon::tests::p4_triangle_area_symmetric_seed_016", p4_triangle_area_symmetric_seed_016),
        ("polygon::tests::p4_triangle_area_symmetric_seed_017", p4_triangle_area_symmetric_seed_017),
        ("polygon::tests::p4_triangle_area_symmetric_seed_018", p4_triangle_area_symmetric_seed_018),
        ("polygon::tests::p4_triangle_area_symmetric_seed_019", p4_triangle_area_symmetric_seed_019),
        ("polygon::tests::p5_triangle_area_matches_polygon_area_seed_000", p5_triangle_area_matches_polygon_area_seed_000),
        ("polygon::tests::p5_triangle_area_matches_polygon_area_seed_001", p5_triangle_area_matches_polygon_area_seed_001),
        ("polygon::tests::p5_triangle_area_matches_polygon_area_seed_002", p5_triangle_area_matches_polygon_area_seed_002),
        ("polygon::tests::p5_triangle_area_matches_polygon_area_seed_003", p5_triangle_area_matches_polygon_area_seed_003),
        ("polygon::tests::p5_triangle_area_matches_polygon_area_seed_004", p5_triangle_area_matches_polygon_area_seed_004),
        ("polygon::tests::p5_triangle_area_matches_polygon_area_seed_005", p5_triangle_area_matches_polygon_area_seed_005),
        ("polygon::tests::p5_triangle_area_matches_polygon_area_seed_006", p5_triangle_area_matches_polygon_area_seed_006),
        ("polygon::tests::p5_triangle_area_matches_polygon_area_seed_007", p5_triangle_area_matches_polygon_area_seed_007),
        ("polygon::tests::p5_triangle_area_matches_polygon_area_seed_008", p5_triangle_area_matches_polygon_area_seed_008),
        ("polygon::tests::p5_triangle_area_matches_polygon_area_seed_009", p5_triangle_area_matches_polygon_area_seed_009),
        ("polygon::tests::p5_triangle_area_matches_polygon_area_seed_010", p5_triangle_area_matches_polygon_area_seed_010),
        ("polygon::tests::p5_triangle_area_matches_polygon_area_seed_011", p5_triangle_area_matches_polygon_area_seed_011),
        ("polygon::tests::p5_triangle_area_matches_polygon_area_seed_012", p5_triangle_area_matches_polygon_area_seed_012),
        ("polygon::tests::p5_triangle_area_matches_polygon_area_seed_013", p5_triangle_area_matches_polygon_area_seed_013),
        ("polygon::tests::p5_triangle_area_matches_polygon_area_seed_014", p5_triangle_area_matches_polygon_area_seed_014),
        ("polygon::tests::p5_triangle_area_matches_polygon_area_seed_015", p5_triangle_area_matches_polygon_area_seed_015),
        ("polygon::tests::p5_triangle_area_matches_polygon_area_seed_016", p5_triangle_area_matches_polygon_area_seed_016),
        ("polygon::tests::p5_triangle_area_matches_polygon_area_seed_017", p5_triangle_area_matches_polygon_area_seed_017),
        ("polygon::tests::p5_triangle_area_matches_polygon_area_seed_018", p5_triangle_area_matches_polygon_area_seed_018),
        ("polygon::tests::p5_triangle_area_matches_polygon_area_seed_019", p5_triangle_area_matches_polygon_area_seed_019),
        ("polygon::tests::p6_perimeter_non_negative_seed_000", p6_perimeter_non_negative_seed_000),
        ("polygon::tests::p6_perimeter_non_negative_seed_001", p6_perimeter_non_negative_seed_001),
        ("polygon::tests::p6_perimeter_non_negative_seed_002", p6_perimeter_non_negative_seed_002),
        ("polygon::tests::p6_perimeter_non_negative_seed_003", p6_perimeter_non_negative_seed_003),
        ("polygon::tests::p6_perimeter_non_negative_seed_004", p6_perimeter_non_negative_seed_004),
        ("polygon::tests::p6_perimeter_non_negative_seed_005", p6_perimeter_non_negative_seed_005),
        ("polygon::tests::p6_perimeter_non_negative_seed_006", p6_perimeter_non_negative_seed_006),
        ("polygon::tests::p6_perimeter_non_negative_seed_007", p6_perimeter_non_negative_seed_007),
        ("polygon::tests::p6_perimeter_non_negative_seed_008", p6_perimeter_non_negative_seed_008),
        ("polygon::tests::p6_perimeter_non_negative_seed_009", p6_perimeter_non_negative_seed_009),
        ("polygon::tests::p6_perimeter_non_negative_seed_010", p6_perimeter_non_negative_seed_010),
        ("polygon::tests::p6_perimeter_non_negative_seed_011", p6_perimeter_non_negative_seed_011),
        ("polygon::tests::p6_perimeter_non_negative_seed_012", p6_perimeter_non_negative_seed_012),
        ("polygon::tests::p6_perimeter_non_negative_seed_013", p6_perimeter_non_negative_seed_013),
        ("polygon::tests::p6_perimeter_non_negative_seed_014", p6_perimeter_non_negative_seed_014),
        ("polygon::tests::p6_perimeter_non_negative_seed_015", p6_perimeter_non_negative_seed_015),
        ("polygon::tests::p6_perimeter_non_negative_seed_016", p6_perimeter_non_negative_seed_016),
        ("polygon::tests::p6_perimeter_non_negative_seed_017", p6_perimeter_non_negative_seed_017),
        ("polygon::tests::p6_perimeter_non_negative_seed_018", p6_perimeter_non_negative_seed_018),
        ("polygon::tests::p6_perimeter_non_negative_seed_019", p6_perimeter_non_negative_seed_019),
        ("polygon::tests::p7_perimeter_is_sum_of_edge_lengths_seed_000", p7_perimeter_is_sum_of_edge_lengths_seed_000),
        ("polygon::tests::p7_perimeter_is_sum_of_edge_lengths_seed_001", p7_perimeter_is_sum_of_edge_lengths_seed_001),
        ("polygon::tests::p7_perimeter_is_sum_of_edge_lengths_seed_002", p7_perimeter_is_sum_of_edge_lengths_seed_002),
        ("polygon::tests::p7_perimeter_is_sum_of_edge_lengths_seed_003", p7_perimeter_is_sum_of_edge_lengths_seed_003),
        ("polygon::tests::p7_perimeter_is_sum_of_edge_lengths_seed_004", p7_perimeter_is_sum_of_edge_lengths_seed_004),
        ("polygon::tests::p7_perimeter_is_sum_of_edge_lengths_seed_005", p7_perimeter_is_sum_of_edge_lengths_seed_005),
        ("polygon::tests::p7_perimeter_is_sum_of_edge_lengths_seed_006", p7_perimeter_is_sum_of_edge_lengths_seed_006),
        ("polygon::tests::p7_perimeter_is_sum_of_edge_lengths_seed_007", p7_perimeter_is_sum_of_edge_lengths_seed_007),
        ("polygon::tests::p7_perimeter_is_sum_of_edge_lengths_seed_008", p7_perimeter_is_sum_of_edge_lengths_seed_008),
        ("polygon::tests::p7_perimeter_is_sum_of_edge_lengths_seed_009", p7_perimeter_is_sum_of_edge_lengths_seed_009),
        ("polygon::tests::p7_perimeter_is_sum_of_edge_lengths_seed_010", p7_perimeter_is_sum_of_edge_lengths_seed_010),
        ("polygon::tests::p7_perimeter_is_sum_of_edge_lengths_seed_011", p7_perimeter_is_sum_of_edge_lengths_seed_011),
        ("polygon::tests::p7_perimeter_is_sum_of_edge_lengths_seed_012", p7_perimeter_is_sum_of_edge_lengths_seed_012),
        ("polygon::tests::p7_perimeter_is_sum_of_edge_lengths_seed_013", p7_perimeter_is_sum_of_edge_lengths_seed_013),
        ("polygon::tests::p7_perimeter_is_sum_of_edge_lengths_seed_014", p7_perimeter_is_sum_of_edge_lengths_seed_014),
        ("polygon::tests::p7_perimeter_is_sum_of_edge_lengths_seed_015", p7_perimeter_is_sum_of_edge_lengths_seed_015),
        ("polygon::tests::p7_perimeter_is_sum_of_edge_lengths_seed_016", p7_perimeter_is_sum_of_edge_lengths_seed_016),
        ("polygon::tests::p7_perimeter_is_sum_of_edge_lengths_seed_017", p7_perimeter_is_sum_of_edge_lengths_seed_017),
        ("polygon::tests::p7_perimeter_is_sum_of_edge_lengths_seed_018", p7_perimeter_is_sum_of_edge_lengths_seed_018),
        ("polygon::tests::p7_perimeter_is_sum_of_edge_lengths_seed_019", p7_perimeter_is_sum_of_edge_lengths_seed_019),
        ("polygon::tests::p8_bounding_box_contains_vertices_seed_000", p8_bounding_box_contains_vertices_seed_000),
        ("polygon::tests::p8_bounding_box_contains_vertices_seed_001", p8_bounding_box_contains_vertices_seed_001),
        ("polygon::tests::p8_bounding_box_contains_vertices_seed_002", p8_bounding_box_contains_vertices_seed_002),
        ("polygon::tests::p8_bounding_box_contains_vertices_seed_003", p8_bounding_box_contains_vertices_seed_003),
        ("polygon::tests::p8_bounding_box_contains_vertices_seed_004", p8_bounding_box_contains_vertices_seed_004),
        ("polygon::tests::p8_bounding_box_contains_vertices_seed_005", p8_bounding_box_contains_vertices_seed_005),
        ("polygon::tests::p8_bounding_box_contains_vertices_seed_006", p8_bounding_box_contains_vertices_seed_006),
        ("polygon::tests::p8_bounding_box_contains_vertices_seed_007", p8_bounding_box_contains_vertices_seed_007),
        ("polygon::tests::p8_bounding_box_contains_vertices_seed_008", p8_bounding_box_contains_vertices_seed_008),
        ("polygon::tests::p8_bounding_box_contains_vertices_seed_009", p8_bounding_box_contains_vertices_seed_009),
        ("polygon::tests::p8_bounding_box_contains_vertices_seed_010", p8_bounding_box_contains_vertices_seed_010),
        ("polygon::tests::p8_bounding_box_contains_vertices_seed_011", p8_bounding_box_contains_vertices_seed_011),
        ("polygon::tests::p8_bounding_box_contains_vertices_seed_012", p8_bounding_box_contains_vertices_seed_012),
        ("polygon::tests::p8_bounding_box_contains_vertices_seed_013", p8_bounding_box_contains_vertices_seed_013),
        ("polygon::tests::p8_bounding_box_contains_vertices_seed_014", p8_bounding_box_contains_vertices_seed_014),
        ("polygon::tests::p8_bounding_box_contains_vertices_seed_015", p8_bounding_box_contains_vertices_seed_015),
        ("polygon::tests::p8_bounding_box_contains_vertices_seed_016", p8_bounding_box_contains_vertices_seed_016),
        ("polygon::tests::p8_bounding_box_contains_vertices_seed_017", p8_bounding_box_contains_vertices_seed_017),
        ("polygon::tests::p8_bounding_box_contains_vertices_seed_018", p8_bounding_box_contains_vertices_seed_018),
        ("polygon::tests::p8_bounding_box_contains_vertices_seed_019", p8_bounding_box_contains_vertices_seed_019),
        ("polygon::tests::p9_translation_preserves_area_seed_000", p9_translation_preserves_area_seed_000),
        ("polygon::tests::p9_translation_preserves_area_seed_001", p9_translation_preserves_area_seed_001),
        ("polygon::tests::p9_translation_preserves_area_seed_002", p9_translation_preserves_area_seed_002),
        ("polygon::tests::p9_translation_preserves_area_seed_003", p9_translation_preserves_area_seed_003),
        ("polygon::tests::p9_translation_preserves_area_seed_004", p9_translation_preserves_area_seed_004),
        ("polygon::tests::p9_translation_preserves_area_seed_005", p9_translation_preserves_area_seed_005),
        ("polygon::tests::p9_translation_preserves_area_seed_006", p9_translation_preserves_area_seed_006),
        ("polygon::tests::p9_translation_preserves_area_seed_007", p9_translation_preserves_area_seed_007),
        ("polygon::tests::p9_translation_preserves_area_seed_008", p9_translation_preserves_area_seed_008),
        ("polygon::tests::p9_translation_preserves_area_seed_009", p9_translation_preserves_area_seed_009),
        ("polygon::tests::p9_translation_preserves_area_seed_010", p9_translation_preserves_area_seed_010),
        ("polygon::tests::p9_translation_preserves_area_seed_011", p9_translation_preserves_area_seed_011),
        ("polygon::tests::p9_translation_preserves_area_seed_012", p9_translation_preserves_area_seed_012),
        ("polygon::tests::p9_translation_preserves_area_seed_013", p9_translation_preserves_area_seed_013),
        ("polygon::tests::p9_translation_preserves_area_seed_014", p9_translation_preserves_area_seed_014),
        ("polygon::tests::p9_translation_preserves_area_seed_015", p9_translation_preserves_area_seed_015),
        ("polygon::tests::p9_translation_preserves_area_seed_016", p9_translation_preserves_area_seed_016),
        ("polygon::tests::p9_translation_preserves_area_seed_017", p9_translation_preserves_area_seed_017),
        ("polygon::tests::p9_translation_preserves_area_seed_018", p9_translation_preserves_area_seed_018),
        ("polygon::tests::p9_translation_preserves_area_seed_019", p9_translation_preserves_area_seed_019),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

// ---------------------------------------------------------------------------
// Property-based tests (proptest)
// ---------------------------------------------------------------------------
#[cfg(test)]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    fn coord() -> impl Strategy<Value = f64> {
        -100.0f64..100.0f64
    }

    fn point() -> impl Strategy<Value = Point> {
        (coord(), coord()).prop_map(|(x, y)| Point::new(x, y))
    }

    /// A closed polygon with 3–8 vertices (triangle through octagon).
    fn small_polygon() -> impl Strategy<Value = Vec<Point>> {
        prop::collection::vec(point(), 3..=8)
    }

    proptest! {
        // -----------------------------------------------------------------
        // polygon_area
        // -----------------------------------------------------------------

        /// P1. polygon_area is never negative.
        #[test]
        fn p1_polygon_area_non_negative(poly in small_polygon()) {
            prop_assert!(polygon_area(&poly) >= 0.0,
                "negative area {} for poly {:?}", polygon_area(&poly), poly);
        }

        /// P2. polygon_signed_area sign flips on vertex-reversal.
        #[test]
        fn p2_area_sign_flips_on_reversal(poly in small_polygon()) {
            let mut rev = poly.clone();
            rev.reverse();
            let forward = polygon_signed_area(&poly);
            let backward = polygon_signed_area(&rev);
            // The absolute values should match (same magnitude), sign flips.
            prop_assert!(
                (forward + backward).abs() < 1e-9,
                "forward={forward}, backward={backward} expected opposite signs"
            );
        }

        // -----------------------------------------------------------------
        // triangle_area
        // -----------------------------------------------------------------

        /// P3. triangle_area is never negative.
        #[test]
        fn p3_triangle_area_non_negative(
            a in point(), b in point(), c in point(),
        ) {
            prop_assert!(triangle_area(&a, &b, &c) >= 0.0);
        }

        /// P4. triangle_area is symmetric: any permutation of vertices gives
        /// the same area (the absolute value of the half cross product is
        /// invariant under cyclic permutations and reversal).
        #[test]
        fn p4_triangle_area_symmetric(
            a in point(), b in point(), c in point(),
        ) {
            let areas = [
                triangle_area(&a, &b, &c),
                triangle_area(&b, &c, &a),
                triangle_area(&c, &a, &b),
                triangle_area(&a, &c, &b),
                triangle_area(&b, &a, &c),
                triangle_area(&c, &b, &a),
            ];
            for pair in areas.windows(2) {
                prop_assert!(
                    (pair[0] - pair[1]).abs() < 1e-9,
                    "triangle_area varies under permutation: {} != {}", pair[0], pair[1]
                );
            }
        }

        /// P5. triangle_area equals polygon_area on the same three vertices.
        #[test]
        fn p5_triangle_area_matches_polygon_area(
            a in point(), b in point(), c in point(),
        ) {
            let poly = vec![a, b, c];
            prop_assert!(
                (triangle_area(&a, &b, &c) - polygon_area(&poly)).abs() < 1e-9,
                "triangle_area != polygon_area"
            );
        }

        // -----------------------------------------------------------------
        // polygon_perimeter
        // -----------------------------------------------------------------

        /// P6. polygon_perimeter is never negative.
        #[test]
        fn p6_perimeter_non_negative(poly in small_polygon()) {
            prop_assert!(polygon_perimeter(&poly) >= 0.0);
        }

        /// P7. polygon_perimeter equals the explicit sum of all edge lengths.
        #[test]
        fn p7_perimeter_is_sum_of_edge_lengths(poly in small_polygon()) {
            let n = poly.len();
            let mut sum = 0.0;
            for i in 0..n {
                let j = (i + 1) % n;
                sum += poly[i].distance(&poly[j]);
            }
            prop_assert!(
                (polygon_perimeter(&poly) - sum).abs() < 1e-9,
                "perimeter {} != sum {}", polygon_perimeter(&poly), sum
            );
        }

        // -----------------------------------------------------------------
        // polygon_bounding_box
        // -----------------------------------------------------------------

        /// P8. Bounding box contains all vertices.
        #[test]
        fn p8_bounding_box_contains_vertices(poly in small_polygon()) {
            let bb = polygon_bounding_box(&poly);
            for p in &poly {
                prop_assert!(
                    bb.x_min <= p.x && p.x <= bb.x_max,
                    "x {} out of [{}, {}]", p.x, bb.x_min, bb.x_max
                );
                prop_assert!(
                    bb.y_min <= p.y && p.y <= bb.y_max,
                    "y {} out of [{}, {}]", p.y, bb.y_min, bb.y_max
                );
            }
        }

        // -----------------------------------------------------------------
        // translate_polygon
        // -----------------------------------------------------------------

        /// P9. Translation preserves polygon area (up to f64 tolerance).
        #[test]
        fn p9_translation_preserves_area(
            poly in small_polygon(), tx in coord(), ty in coord(),
        ) {
            let translated = translate_polygon(&poly, tx, ty);
            prop_assert!(
                (polygon_area(&poly) - polygon_area(&translated)).abs() < 1e-9,
                "area changed under translation"
            );
        }
    }
}
