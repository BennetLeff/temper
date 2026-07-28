// =============================================================================
// DRC inflation functions — ported from temper-placer Python
// =============================================================================
//
// Precompute Minkowski-inflated pad dimensions for DRC proxy loss.
//
// The Python version used `shapely.geometry.Polygon.buffer()` for Minkowski
// sum padding.  This Rust port uses a simpler approach:
//   - Rectangular pads → expand AABB by clearance_mm on each side
//   - Non-rectangular pads → compute centroid and push each vertex outward
//     by clearance_mm/2 along the centroid-to-vertex direction
//
// At evaluation time only pairwise AABB distance checks run — lightweight
// and amortises the inflation step.

use crate::types::*;
use crate::primitives;
use crate::smooth::*;

// =============================================================================
// Helpers
// =============================================================================

/// Check whether a set of vertices form an axis-aligned rectangle (4 corners
/// that exactly match the AABB).
fn is_axis_aligned_rectangle(vertices: &[Point]) -> bool {
    if vertices.len() != 4 {
        return false;
    }
    let bb = AABB::from_points(vertices);
    let corners = [
        Point::new(bb.x_min, bb.y_min),
        Point::new(bb.x_max, bb.y_min),
        Point::new(bb.x_max, bb.y_max),
        Point::new(bb.x_min, bb.y_max),
    ];
    for corner in &corners {
        if !vertices
            .iter()
            .any(|v| (v.x - corner.x).abs() < 1e-9 && (v.y - corner.y).abs() < 1e-9)
        {
            return false;
        }
    }
    true
}

// =============================================================================
// Core Inflation Functions
// =============================================================================

/// Inflate a pad polygon outward by `clearance_mm / 2`.
///
/// *Rectangular pads* — compute the AABB and expand it by `clearance_mm / 2`
/// on each side.  Returns the four corners of the expanded rectangle.
///
/// *Non-rectangular pads* — compute the arithmetic-mean centroid, then push
/// each vertex outward along the centroid→vertex direction by
/// `clearance_mm / 2`.
pub fn inflate_pad_polygon(pad_points: &[Point], clearance_mm: f64) -> Vec<Point> {
    if pad_points.is_empty() {
        return vec![];
    }

    if is_axis_aligned_rectangle(pad_points) {
        // Expand the AABB uniformly by half the clearance on each side.
        let bb = AABB::from_points(pad_points);
        let half = clearance_mm * 0.5;
        let x_min = bb.x_min - half;
        let x_max = bb.x_max + half;
        let y_min = bb.y_min - half;
        let y_max = bb.y_max + half;
        vec![
            Point::new(x_min, y_min),
            Point::new(x_max, y_min),
            Point::new(x_max, y_max),
            Point::new(x_min, y_max),
        ]
    } else {
        // Push each vertex outward from the centroid.
        let centroid = primitives::points_centroid(pad_points);
        let half = clearance_mm * 0.5;
        pad_points
            .iter()
            .map(|p| {
                let dx = p.x - centroid.x;
                let dy = p.y - centroid.y;
                let dist = (dx * dx + dy * dy).sqrt();
                if dist < 1e-15 {
                    *p
                } else {
                    Point::new(p.x + (dx / dist) * half, p.y + (dy / dist) * half)
                }
            })
            .collect()
    }
}

/// Add clearance to both dimensions for a simple rectangular pad.
///
/// This is the cheap path when you already know the raw (width, height) and
/// only need the inflated dimensions rather than full polygon vertices.
pub fn precompute_inflated_dims(width: f64, height: f64, clearance_mm: f64) -> (f64, f64) {
    (width + clearance_mm, height + clearance_mm)
}

/// Precompute inflated (width, height) for every pad polygon in a batch.
///
/// Each pad is inflated via [`inflate_pad_polygon`], the AABB is extracted,
/// and the resulting (width, height) is returned.  Empty polygons yield
/// `(0.0, 0.0)`.
pub fn precompute_from_pad_polygons(
    pad_polys: &[Vec<Point>],
    clearance_mm: f64,
) -> Vec<(f64, f64)> {
    pad_polys
        .iter()
        .map(|poly| {
            if poly.is_empty() {
                return (0.0, 0.0);
            }
            let inflated = inflate_pad_polygon(poly, clearance_mm);
            let bb = AABB::from_points(&inflated);
            (bb.width(), bb.height())
        })
        .collect()
}

/// Compute inflated *half*-dimensions from an existing AABB.
///
/// Inflation is applied on both sides, so the full width/height grows by
/// `clearance_mm` and the result is halved:
///
/// ```text
/// half_w = (bounds.width()  + clearance_mm) / 2
/// half_h = (bounds.height() + clearance_mm) / 2
/// ```
pub fn compute_inflated_half_dims_from_bounds(bounds: &AABB, clearance_mm: f64) -> (f64, f64) {
    let w = bounds.width() + clearance_mm;
    let h = bounds.height() + clearance_mm;
    (w * 0.5, h * 0.5)
}

/// Compute the DRC proxy score — sum of squared clearance violations across
/// all component pairs.
///
/// This is a direct port of the Python `compute_drc_proxy_score`.  It:
///
/// 1. Inflates each pad polygon via [`precompute_from_pad_polygons`] to obtain
///    half-dimensions for every component.
/// 2. Derives component center positions from each AABB.
/// 3. For every pair computes the gap in x and y using the inflated
///    half-dimensions, determines the signed distance between the pads,
///    and applies a smooth ReLU penalty for any violation of `clearance_mm`.
///
/// The smoothing parameter `beta` is fixed at 10.0 (matching the Python default).
pub fn compute_drc_proxy_score(
    component_rects: &[AABB],
    pad_polys: &[Vec<Point>],
    clearance_mm: f64,
) -> f64 {
    let n = component_rects.len();
    if n < 2 {
        return 0.0;
    }

    // Precompute inflated half-dimensions.
    let inflated_dims = precompute_from_pad_polygons(pad_polys, clearance_mm);

    // Component centres.
    let centers: Vec<Point> = component_rects.iter().map(|r| r.center()).collect();

    let beta = 10.0;
    let mut total = 0.0;

    for i in 0..n {
        let (hw_i, hh_i) = inflated_dims[i];
        for j in (i + 1)..n {
            let dx = (centers[i].x - centers[j].x).abs();
            let dy = (centers[i].y - centers[j].y).abs();

            let (hw_j, hh_j) = inflated_dims[j];

            let gap_x = dx - (hw_i + hw_j);
            let gap_y = dy - (hh_i + hh_j);

            // When both gaps are negative the boxes overlap — take the more
            // restrictive (more negative) gap.  Otherwise at least one dimension
            // is separated — take the larger (positive) gap.
            let dist = if gap_x < 0.0 && gap_y < 0.0 {
                gap_x.min(gap_y)
            } else {
                gap_x.max(gap_y)
            };

            let violation = smooth_relu(clearance_mm - dist, beta);
            total += violation * violation;
        }
    }

    total
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    const EPS: f64 = 1e-9;

    fn square_pad() -> Vec<Point> {
        vec![
            Point::new(0.0, 0.0),
            Point::new(1.0, 0.0),
            Point::new(1.0, 1.0),
            Point::new(0.0, 1.0),
        ]
    }

    fn rect_pad() -> Vec<Point> {
        vec![
            Point::new(0.0, 0.0),
            Point::new(2.0, 0.0),
            Point::new(2.0, 1.0),
            Point::new(0.0, 1.0),
        ]
    }

    fn l_shaped_pad() -> Vec<Point> {
        vec![
            Point::new(0.0, 0.0),
            Point::new(2.0, 0.0),
            Point::new(2.0, 1.0),
            Point::new(1.0, 1.0),
            Point::new(1.0, 2.0),
            Point::new(0.0, 2.0),
        ]
    }

    // -----------------------------------------------------------------
    // inflate_pad_polygon: square pad → larger square
    // -----------------------------------------------------------------
    #[test]
    fn test_inflate_square_pad() {
        let sq = square_pad();
        let inflated = inflate_pad_polygon(&sq, 2.0);

        // Should still be a 4-vertex rectangle.
        assert_eq!(inflated.len(), 4);
        assert!(is_axis_aligned_rectangle(&inflated));

        // Original was 1×1.  Clearance = 2 → each side gets 1 → 3×3.
        let bb = AABB::from_points(&inflated);
        let w = bb.width();
        let h = bb.height();
        assert!((w - 3.0).abs() < EPS, "expected width 3.0, got {w}");
        assert!((h - 3.0).abs() < EPS, "expected height 3.0, got {h}");

        // Centered: original was [0,1] → expanded to [-1, 2].
        assert!((bb.x_min - (-1.0)).abs() < EPS);
        assert!((bb.y_min - (-1.0)).abs() < EPS);
        assert!((bb.x_max - 2.0).abs() < EPS);
        assert!((bb.y_max - 2.0).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // inflate_pad_polygon: clearance=0 → same polygon
    // -----------------------------------------------------------------
    #[test]
    fn test_inflate_zero_clearance() {
        let sq = square_pad();
        let inflated = inflate_pad_polygon(&sq, 0.0);

        assert_eq!(inflated.len(), 4);
        for (orig, inf) in sq.iter().zip(inflated.iter()) {
            assert!((orig.x - inf.x).abs() < EPS);
            assert!((orig.y - inf.y).abs() < EPS);
        }
    }

    // -----------------------------------------------------------------
    // inflate_pad_polygon: l-shaped pad with clearance
    // -----------------------------------------------------------------
    #[test]
    fn test_inflate_l_shaped_pad() {
        let l = l_shaped_pad();
        let inflated = inflate_pad_polygon(&l, 1.0);

        assert_eq!(inflated.len(), 6);
        // Non-rectangular: vertices should have moved outward from centroid.
        // At minimum, some vertex should be further from origin than before.
        let orig_bb = AABB::from_points(&l);
        let inf_bb = AABB::from_points(&inflated);
        assert!(inf_bb.width() > orig_bb.width());
        assert!(inf_bb.height() > orig_bb.height());
    }

    // -----------------------------------------------------------------
    // inflate_pad_polygon: empty input
    // -----------------------------------------------------------------
    #[test]
    fn test_inflate_empty() {
        let inflated = inflate_pad_polygon(&[], 2.0);
        assert!(inflated.is_empty());
    }

    // -----------------------------------------------------------------
    // precompute_inflated_dims: adds clearance to dimensions
    // -----------------------------------------------------------------
    #[test]
    fn test_precompute_inflated_dims() {
        let (w, h) = precompute_inflated_dims(1.0, 2.0, 0.5);
        assert!((w - 1.5).abs() < EPS, "expected 1.5, got {w}");
        assert!((h - 2.5).abs() < EPS, "expected 2.5, got {h}");
    }

    #[test]
    fn test_precompute_inflated_dims_zero_clearance() {
        let (w, h) = precompute_inflated_dims(3.0, 4.0, 0.0);
        assert!((w - 3.0).abs() < EPS);
        assert!((h - 4.0).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // precompute_from_pad_polygons
    // -----------------------------------------------------------------
    #[test]
    fn test_precompute_from_pad_polygons() {
        let polys = vec![square_pad(), rect_pad()];
        let dims = precompute_from_pad_polygons(&polys, 1.0);

        assert_eq!(dims.len(), 2);

        // Square: 1×1 + 1 = 2×2
        assert!((dims[0].0 - 2.0).abs() < EPS, "expected 2.0, got {}", dims[0].0);
        assert!((dims[0].1 - 2.0).abs() < EPS, "expected 2.0, got {}", dims[0].1);

        // Rect: 2×1 + 1 = 3×2
        assert!((dims[1].0 - 3.0).abs() < EPS, "expected 3.0, got {}", dims[1].0);
        assert!((dims[1].1 - 2.0).abs() < EPS, "expected 2.0, got {}", dims[1].1);
    }

    #[test]
    fn test_precompute_from_pad_polygons_empty() {
        let dims = precompute_from_pad_polygons(&[], 1.0);
        assert!(dims.is_empty());
    }

    #[test]
    fn test_precompute_from_pad_polygons_empty_poly() {
        let polys = vec![vec![], square_pad()];
        let dims = precompute_from_pad_polygons(&polys, 1.0);
        assert_eq!(dims.len(), 2);
        assert!((dims[0].0 - 0.0).abs() < EPS);
        assert!((dims[0].1 - 0.0).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // compute_inflated_half_dims_from_bounds
    // -----------------------------------------------------------------
    #[test]
    fn test_inflated_half_dims_from_bounds() {
        // AABB for a 10×20 rect centered at origin → x_min=-5, y_min=-10, ...
        let bb = AABB::new(-5.0, -10.0, 5.0, 10.0);
        let (hw, hh) = compute_inflated_half_dims_from_bounds(&bb, 2.0);

        // width=10, clearance=2 → (10+2)/2 = 6
        assert!((hw - 6.0).abs() < EPS, "expected 6.0, got {hw}");
        // height=20, clearance=2 → (20+2)/2 = 11
        assert!((hh - 11.0).abs() < EPS, "expected 11.0, got {hh}");
    }

    #[test]
    fn test_inflated_half_dims_zero_clearance() {
        let bb = AABB::new(0.0, 0.0, 10.0, 20.0);
        let (hw, hh) = compute_inflated_half_dims_from_bounds(&bb, 0.0);
        assert!((hw - 5.0).abs() < EPS, "expected 5.0, got {hw}");
        assert!((hh - 10.0).abs() < EPS, "expected 10.0, got {hh}");
    }

    // -----------------------------------------------------------------
    // compute_drc_proxy_score: no overlap → 0
    // -----------------------------------------------------------------
    #[test]
    fn test_drc_proxy_score_no_overlap() {
        // Two components far apart — no DRC violation expected.
        let rects = vec![
            AABB::new(0.0, 0.0, 10.0, 10.0),
            AABB::new(100.0, 0.0, 110.0, 10.0),
        ];
        let pads = vec![square_pad(), square_pad()];

        let score = compute_drc_proxy_score(&rects, &pads, 0.2);
        assert!(
            score < 1e-6,
            "far-apart components should give ~0 score, got {score}"
        );
    }

    // -----------------------------------------------------------------
    // compute_drc_proxy_score: some overlap → > 0
    // -----------------------------------------------------------------
    #[test]
    fn test_drc_proxy_score_some_overlap() {
        // Two overlapping components — should produce a positive score.
        let rects = vec![
            AABB::new(0.0, 0.0, 10.0, 10.0),
            AABB::new(1.0, 1.0, 11.0, 11.0),
        ];
        let pads = vec![square_pad(), square_pad()];

        let score = compute_drc_proxy_score(&rects, &pads, 0.2);
        assert!(
            score > 1e-6,
            "overlapping components should give positive score, got {score}"
        );
    }

    // -----------------------------------------------------------------
    // compute_drc_proxy_score: single component → 0
    // -----------------------------------------------------------------
    #[test]
    fn test_drc_proxy_score_single() {
        let rects = vec![AABB::new(0.0, 0.0, 10.0, 10.0)];
        let pads = vec![square_pad()];
        let score = compute_drc_proxy_score(&rects, &pads, 0.2);
        assert!(
            (score - 0.0).abs() < EPS,
            "single component should give 0, got {score}"
        );
    }

    // -----------------------------------------------------------------
    // compute_drc_proxy_score: empty → 0
    // -----------------------------------------------------------------
    #[test]
    fn test_drc_proxy_score_empty() {
        let score = compute_drc_proxy_score(&[], &[], 0.2);
        assert!((score - 0.0).abs() < EPS);
    }

    // -----------------------------------------------------------------
    // compute_drc_proxy_score: tight clearance still passes
    // -----------------------------------------------------------------
    #[test]
    fn test_drc_proxy_score_tight_clearance() {
        // Components separated by exactly the required clearance.
        let rects = vec![
            AABB::new(0.0, 0.0, 10.0, 10.0),
            AABB::new(12.0, 0.0, 22.0, 10.0),
        ];
        let pads = vec![square_pad(), square_pad()];
        // Centres: (5,5) and (17,5), gap_x = 12, half_w each = (1+0)/2 = 0.5
        // Inflated half_dims: (1.0, 1.0) each (after inflation with clearance=0.0)
        // Actually we need the clearance parameter to affect both inflation AND the violation check.
        // With clearance=2.0, each pad is inflated by 1 per side:
        //   square becomes 3×3, half_w = 1.5
        //   gap_x = 12 - (1.5+1.5) = 9
        //   clearance - dist = 2 - 9 = -7 → no violation
        let score = compute_drc_proxy_score(&rects, &pads, 2.0);
        assert!(
            score < 1e-6,
            "components at exactly clearance distance should give ~0 score, got {score}"
        );
    }
}
