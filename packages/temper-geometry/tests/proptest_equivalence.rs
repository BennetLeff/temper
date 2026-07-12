// =============================================================================
// Property-based tests for temper-geometry using proptest!
//
// Each test exercises an invariant that should hold for all (or a large
// random sample of) inputs.  This catches regressions that example-based
// tests miss.
// =============================================================================

use proptest::prelude::*;
use temper_geometry::overlap::*;
use temper_geometry::polygon::*;
use temper_geometry::primitives::*;
use temper_geometry::projections::*;
use temper_geometry::sdf::*;
use temper_geometry::smooth::*;
use temper_geometry::transform::*;
use temper_geometry_core::types::*;

// ---------------------------------------------------------------------------
// Strategy helpers
// ---------------------------------------------------------------------------

/// Strategy: any finite 2D coordinate with reasonable magnitude.
fn any_coord_bounded() -> impl Strategy<Value = f64> {
    (-1e5f64..1e5f64).prop_filter("finite coord", |v| v.is_finite())
}

/// Strategy: non-negative finite coordinate.
fn any_coord_nonneg() -> impl Strategy<Value = f64> {
    (0.0f64..1e5f64).prop_filter("finite nonneg", |v| v.is_finite())
}

/// Strategy: any 2D point with finite coordinates.
fn any_point() -> impl Strategy<Value = Point> {
    (any_coord_bounded(), any_coord_bounded()).prop_map(|(x, y)| Point::new(x, y))
}

/// Strategy: a finite angle in radians.
fn any_angle() -> impl Strategy<Value = f64> {
    (-6.3f64..6.3f64).prop_filter("finite", |v| v.is_finite())
}

/// Strategy: an axis-aligned Rect with non-negative width/height.
fn any_rect() -> impl Strategy<Value = Rect> {
    (any_coord_bounded(), any_coord_bounded(), any_coord_nonneg(), any_coord_nonneg())
        .prop_map(|(x, y, w, h)| Rect::new(x, y, w, h))
}

/// Strategy: an AABB with x_min <= x_max and y_min <= y_max.
fn any_aabb() -> impl Strategy<Value = AABB> {
    (any_coord_bounded(), any_coord_bounded(), any_coord_bounded(), any_coord_bounded())
        .prop_filter("valid AABB: x_min <= x_max && y_min <= y_max",
            |&(x1, y1, x2, y2)| x1 <= x2 && y1 <= y2)
        .prop_map(|(x1, y1, x2, y2)| AABB::new(x1, y1, x2, y2))
}

/// Strategy: a convex CCW polygon (as a Vec of points) with non-zero area.
/// Places vertices on a circle of random radius (single radius for all vertices
/// guarantees convexity).
fn convex_polygon(min_vertices: usize) -> impl Strategy<Value = Vec<Point>> {
    (min_vertices..=12usize, 1.0f64..100.0f64).prop_map(|(n, r)| {
        (0..n)
            .map(|i| {
                let angle = i as f64 / n as f64 * 2.0 * std::f64::consts::PI;
                Point::new(r * angle.cos(), r * angle.sin())
            })
            .collect()
    })
}

// =============================================================================
// Point distance invariants
// =============================================================================

proptest! {
    #[test]
    fn point_distance_symmetry(p1 in any_point(), p2 in any_point()) {
        let d1 = point_distance(&p1, &p2);
        let d2 = point_distance(&p2, &p1);
        let diff = (d1 - d2).abs();
        prop_assert!(diff < 1e-12, "distance not symmetric: |{} - {}| = {}", d1, d2, diff);
    }

    #[test]
    fn point_distance_non_negative(p1 in any_point(), p2 in any_point()) {
        let d = point_distance(&p1, &p2);
        prop_assert!(d >= 0.0, "distance should be non-negative, got {}", d);
    }

    #[test]
    fn point_distance_triangle_inequality(a in any_point(), b in any_point(), c in any_point()) {
        let ab = point_distance(&a, &b);
        let bc = point_distance(&b, &c);
        let ac = point_distance(&a, &c);
        prop_assert!(
            ac <= ab + bc + 1e-9,
            "triangle inequality violated: {} > {} + {}",
            ac, ab, bc
        );
    }

    #[test]
    fn point_distance_self_zero(p in any_point()) {
        let d = point_distance(&p, &p);
        prop_assert!(d <= 1e-5, "self-distance should be ~sqrt(eps), got {}", d);
    }
}

// =============================================================================
// Rotation + inverse rotation invariants
// =============================================================================

proptest! {
    #[test]
    fn rotate_then_inverse_rotate_identity(p in any_point(), angle in any_angle()) {
        let rotated = rotate_point(&p, angle, None);
        let restored = rotate_point(&rotated, -angle, None);
        let dx = (restored.x - p.x).abs();
        let dy = (restored.y - p.y).abs();
        prop_assert!(dx < 1e-9, "x drifted by {}", dx);
        prop_assert!(dy < 1e-9, "y drifted by {}", dy);
    }

    #[test]
    fn rotate_round_trip_about_center(p in any_point(), angle in any_angle(), center in any_point()) {
        let rotated = rotate_point(&p, angle, Some(&center));
        let restored = rotate_point(&rotated, -angle, Some(&center));
        let dx = (restored.x - p.x).abs();
        let dy = (restored.y - p.y).abs();
        prop_assert!(dx < 1e-9, "x drifted by {}", dx);
        prop_assert!(dy < 1e-9, "y drifted by {}", dy);
    }

    #[test]
    fn rotate_preserves_distance(p1 in any_point(), p2 in any_point(), angle in any_angle()) {
        let d_before = point_distance(&p1, &p2);
        let r1 = rotate_point(&p1, angle, None);
        let r2 = rotate_point(&p2, angle, None);
        let d_after = point_distance(&r1, &r2);
        let diff = (d_before - d_after).abs();
        prop_assert!(diff < 1e-9, "rotation changed distance by {}", diff);
    }
}

// =============================================================================
// Polygon area invariants
// =============================================================================

proptest! {
    #[test]
    fn convex_polygon_area_positive(verts in convex_polygon(3)) {
        let area = polygon_area(&verts);
        prop_assert!(area > 0.0, "convex polygon area should be > 0, got {}", area);
    }

    #[test]
    fn polygon_area_equals_signed_abs(verts in convex_polygon(3)) {
        let signed = polygon_signed_area(&verts);
        let area = polygon_area(&verts);
        prop_assert!((area - signed.abs()).abs() < 1e-12,
            "area {} != |signed| {}", area, signed.abs());
    }

    #[test]
    fn polygon_area_translation_invariant(verts in convex_polygon(3), dx in any_coord_bounded(), dy in any_coord_bounded()) {
        let area_before = polygon_area(&verts);
        let translated = translate_polygon(&verts, dx, dy);
        let area_after = polygon_area(&translated);
        let diff = (area_before - area_after).abs();
        // Shoelace formula suffers from catastrophic cancellation with large
        // coordinate offsets.  Tolerance reflects the achievable precision.
        prop_assert!(diff < 1e-5, "area changed by {} after translation", diff);
    }

    #[test]
    fn polygon_area_preserved_under_rotation(verts in convex_polygon(3), angle in any_angle()) {
        let area_before = polygon_area(&verts);
        let rotated = rotate_polygon(&verts, angle);
        let area_after = polygon_area(&rotated);
        let diff = (area_before - area_after).abs();
        prop_assert!(diff < 1e-9, "area changed by {} after rotation", diff);
    }
}

// =============================================================================
// SDF invariants
// =============================================================================

proptest! {
    #[test]
    fn sdf_circle_center_is_negative_radius(cx in any_coord_bounded(), cy in any_coord_bounded(), r in 1e-3f64..1e4) {
        let center = Point::new(cx, cy);
        let d = sdf_circle(&center, cx, cy, r);
        let expected = -r;
        let diff = (d - expected).abs();
        prop_assert!(diff < 1e-9, "sdf_circle at center: expected {}, got {}, diff={}", expected, d, diff);
    }

    #[test]
    fn sdf_union_is_min(d1 in any_coord_bounded(), d2 in any_coord_bounded()) {
        let result = sdf_union(d1, d2);
        let expected = d1.min(d2);
        let diff = (result - expected).abs();
        prop_assert!(diff < 1e-15, "sdf_union({}, {}) = {}, expected {}", d1, d2, result, expected);
    }

    #[test]
    fn sdf_intersection_is_max(d1 in any_coord_bounded(), d2 in any_coord_bounded()) {
        let result = sdf_intersection(d1, d2);
        let expected = d1.max(d2);
        let diff = (result - expected).abs();
        prop_assert!(diff < 1e-15, "sdf_intersection({}, {}) = {}, expected {}", d1, d2, result, expected);
    }
}

// =============================================================================
// Smooth min/max invariants
// =============================================================================

proptest! {
    #[test]
    fn smooth_max_ge_true_max(a in any_coord_bounded(), b in any_coord_bounded(), alpha in 1e-3f64..1e6) {
        let result = smooth_max(a, b, alpha);
        let true_max = a.max(b);
        prop_assert!(result >= true_max - 1e-12,
            "smooth_max({}, {}, {}) = {} < true_max {}", a, b, alpha, result, true_max);
    }

    #[test]
    fn smooth_min_le_true_min(a in any_coord_bounded(), b in any_coord_bounded(), alpha in 1e-3f64..1e6) {
        let result = smooth_min(a, b, alpha);
        let true_min = a.min(b);
        prop_assert!(result <= true_min + 1e-12,
            "smooth_min({}, {}, {}) = {} > true_min {}", a, b, alpha, result, true_min);
    }

    #[test]
    fn smooth_max_symmetry(a in any_coord_bounded(), b in any_coord_bounded(), alpha in 1e-3f64..1e6) {
        let ab = smooth_max(a, b, alpha);
        let ba = smooth_max(b, a, alpha);
        let diff = (ab - ba).abs();
        prop_assert!(diff < 1e-12, "smooth_max not symmetric: |{} - {}| = {}", ab, ba, diff);
    }

    #[test]
    fn smooth_min_symmetry(a in any_coord_bounded(), b in any_coord_bounded(), alpha in 1e-3f64..1e6) {
        let ab = smooth_min(a, b, alpha);
        let ba = smooth_min(b, a, alpha);
        let diff = (ab - ba).abs();
        prop_assert!(diff < 1e-12, "smooth_min not symmetric: |{} - {}| = {}", ab, ba, diff);
    }

    #[test]
    fn smooth_min_equals_neg_smooth_max(a in any_coord_bounded(), b in any_coord_bounded(), alpha in 1e-3f64..1e6) {
        let min_val = smooth_min(a, b, alpha);
        let neg_max = -smooth_max(-a, -b, alpha);
        let diff = (min_val - neg_max).abs();
        prop_assert!(diff < 1e-12, "min(a,b) = -max(-a,-b) identity failed: {} vs {}", min_val, neg_max);
    }

    #[test]
    fn smooth_max_converges_with_high_alpha(a in any_coord_bounded(), b in any_coord_bounded()) {
        let result = smooth_max(a, b, 1e6);
        let true_max = a.max(b);
        let diff = (result - true_max).abs();
        prop_assert!(diff < 1e-3,
            "smooth_max should converge to max at high alpha, diff={}", diff);
    }
}

// =============================================================================
// AABB overlap invariants
// =============================================================================

proptest! {
    #[test]
    fn aabb_overlap_area_bounded_by_areas(a in any_aabb(), b in any_aabb()) {
        let overlap = aabb_overlap_area(&a, &b);
        let area_a = a.area();
        let area_b = b.area();
        prop_assert!(overlap <= area_a + 1e-12,
            "overlap {} > area_a {}", overlap, area_a);
        prop_assert!(overlap <= area_b + 1e-12,
            "overlap {} > area_b {}", overlap, area_b);
    }

    #[test]
    fn aabb_overlap_symmetric(a in any_aabb(), b in any_aabb()) {
        let o1 = aabb_overlap_area(&a, &b);
        let o2 = aabb_overlap_area(&b, &a);
        let diff = (o1 - o2).abs();
        prop_assert!(diff < 1e-12, "overlap not symmetric: {} vs {}", o1, o2);
    }

    #[test]
    fn aabb_intersects_consistent_with_overlap(a in any_aabb(), b in any_aabb()) {
        let intersects = aabb_intersects(&a, &b);
        let overlap = aabb_overlap_area(&a, &b);
        if intersects {
            prop_assert!(overlap >= 0.0, "intersecting AABBs must have overlap >= 0");
        } else {
            prop_assert!((overlap - 0.0).abs() < 1e-12,
                "non-intersecting AABBs must have overlap == 0, got {}", overlap);
        }
    }

    #[test]
    fn aabb_expand_increases_bounds(aabb in any_aabb(), margin in 0.0f64..1e3) {
        let expanded = aabb_expand(&aabb, margin);
        prop_assert!(expanded.x_min <= aabb.x_min - 1e-12,
            "expand should move x_min left: {} vs {}", expanded.x_min, aabb.x_min);
        prop_assert!(expanded.y_min <= aabb.y_min - 1e-12);
        prop_assert!(expanded.x_max >= aabb.x_max + 1e-12);
        prop_assert!(expanded.y_max >= aabb.y_max + 1e-12);
    }
}

// =============================================================================
// Clearance / overlap invariants
// =============================================================================

proptest! {
    #[test]
    fn box_box_distance_symmetric(a in any_rect(), b in any_rect()) {
        let d1 = box_box_distance(&a, &b);
        let d2 = box_box_distance(&b, &a);
        let diff = (d1 - d2).abs();
        prop_assert!(diff < 1e-12, "box_box_distance not symmetric: {} vs {}", d1, d2);
    }

    #[test]
    fn clearance_violation_positive_when_overlap(clearance in 0.0f64..100.0) {
        let a = Rect::new(0.0, 0.0, 10.0, 10.0);
        let b = Rect::new(0.0, 0.0, 10.0, 10.0); // identical = fully overlapping
        let violations = check_clearance_violation(&[a, b], clearance);
        if !violations.is_empty() {
            prop_assert!(violations[0].2 > 0.0,
                "clearance violation should be positive when overlapping, got {}", violations[0].2);
        }
    }

    #[test]
    fn count_overlaps_commutative(a in any_rect(), b in any_rect()) {
        let count1 = count_overlaps(&[a, b]);
        let count2 = count_overlaps(&[b, a]);
        prop_assert_eq!(count1, count2, "overlap count should be commutative");
    }
}

// =============================================================================
// Projection invariants
// =============================================================================

proptest! {
    #[test]
    fn project_onto_board_stays_inside(p in any_point(), board_w in 1.0f64..1e4, board_h in 1.0f64..1e4, margin in 0.0f64..1e3) {
        let margin_ok = 2.0 * margin < board_w.min(board_h);
        if !margin_ok {
            return Ok(());
        }
        let projected = project_onto_board(&p, board_w, board_h, margin);
        let x_ok = projected.x >= margin - 1e-9 && projected.x <= board_w - margin + 1e-9;
        let y_ok = projected.y >= margin - 1e-9 && projected.y <= board_h - margin + 1e-9;
        prop_assert!(x_ok && y_ok,
            "projected point ({}, {}) outside board [{}, {}]×[{}, {}]",
            projected.x, projected.y, margin, board_w - margin, margin, board_h - margin);
    }

    #[test]
    fn project_onto_zone_containment(p in any_point(), zone in any_rect()) {
        let projected = project_onto_zone(&p, &zone);
        let in_zone = zone.contains_point(&projected);
        prop_assert!(in_zone,
            "projected point ({}, {}) is outside zone ({}, {}, {}, {})",
            projected.x, projected.y, zone.x, zone.y, zone.w, zone.h);
    }

    #[test]
    fn identity_projection_returns_same_point(p in any_point()) {
        let result = identity_projection(&p);
        let dx = (result.x - p.x).abs();
        let dy = (result.y - p.y).abs();
        prop_assert!(dx < 1e-12, "identity should preserve x: {} vs {}", result.x, p.x);
        prop_assert!(dy < 1e-12, "identity should preserve y: {} vs {}", result.y, p.y);
    }

    #[test]
    fn project_onto_edge_strip_clamps_distance(
        p in any_point(),
        start in any_point(),
        end in any_point(),
        strip_width in 1e-3f64..1e4,
    ) {
        let projected = project_onto_edge_strip(&p, &start, &end, strip_width);
        let seg = Segment::new(start, end);
        let nearest = seg.nearest_point(&projected);
        let dist = projected.distance(&nearest);
        prop_assert!(dist <= strip_width + 1e-9,
            "projected point dist {} > strip_width {}", dist, strip_width);
    }
}
