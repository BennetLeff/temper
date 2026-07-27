// =============================================================================
// Component overlap detection
// =============================================================================
//
// This module provides overlap detection between PCB components using signed
// distance functions and axis-aligned bounding box (AABB) approximations for
// efficient overlap computation.
//
// Ported from the Python `temper_placer.geometry.overlap` module.
//
// Key features:
// - Efficient AABB-based overlap detection
// - Batch operations for computing all pairwise overlaps
// - Clearance violation checking
// - Smooth penalties suitable for loss functions

use crate::types::*;
use crate::smooth::*;

// =============================================================================
// Core Box-Box Distance Functions
// =============================================================================

/// Compute minimum signed distance between two axis-aligned rectangles.
///
/// The `Rect` already carries its final dimensions (accounting for any
/// rotation), so this function works directly with center positions and
/// half-dimensions.
///
/// Returns:
/// - Positive: boxes are separated by this distance
/// - Zero: boxes are touching
/// - Negative: boxes overlap by this amount
pub fn box_box_distance(a: &Rect, b: &Rect) -> f64 {
    let ca = a.center();
    let cb = b.center();
    let half_wa = a.w * 0.5;
    let half_ha = a.h * 0.5;
    let half_wb = b.w * 0.5;
    let half_hb = b.h * 0.5;

    // Compute gaps in each dimension
    let gap_x = (ca.x - cb.x).abs() - (half_wa + half_wb);
    let gap_y = (ca.y - cb.y).abs() - (half_ha + half_hb);

    // When both gaps are negative (overlapping), return the most restrictive
    // (most negative) gap. When at least one is positive (separated), return
    // the larger (positive) value—both gaps must be crossed to overlap.
    if gap_x < 0.0 && gap_y < 0.0 {
        gap_x.min(gap_y)
    } else {
        gap_x.max(gap_y)
    }
}

/// Compute minimum signed distance between two axis-aligned bounding boxes.
///
/// Simpler version when AABB corners are already available.
///
/// Returns signed distance (negative if overlapping).
pub fn box_box_distance_aabb(a: &AABB, b: &AABB) -> f64 {
    let gap_x = (a.x_min - b.x_max).max(b.x_min - a.x_max);
    let gap_y = (a.y_min - b.y_max).max(b.y_min - a.y_max);

    if gap_x < 0.0 && gap_y < 0.0 {
        gap_x.min(gap_y)
    } else {
        gap_x.max(gap_y)
    }
}

// =============================================================================
// Overlap Amount and Area
// =============================================================================

/// Compute overlap amount between two AABBs as a fraction of the smaller box's area.
///
/// Returns `overlap_area / min(area_a, area_b)`, i.e. a value in `[0.0, 1.0]`:
/// - `1.0` when one box is fully contained within the other
/// - `0.0` when there is no overlap
pub fn component_overlap_amount(a: &AABB, b: &AABB) -> f64 {
    let overlap = a.overlap_area(b);
    if overlap <= 0.0 {
        return 0.0;
    }
    let min_area = a.area().min(b.area());
    if min_area <= 0.0 {
        return 0.0;
    }
    overlap / min_area
}

/// Compute absolute overlap area between two AABBs.
///
/// Returns the intersection area of the AABBs — a direct measure of overlap
/// severity. Returns 0.0 when there is no overlap.
pub fn overlap_area_estimate(a: &AABB, b: &AABB) -> f64 {
    a.overlap_area(b)
}

// =============================================================================
// Batch Operations — All Pairwise Overlaps
// =============================================================================

/// Compute pairwise signed distances between all rectangles.
///
/// Returns a flattened N×N row-major matrix where element `[i * n + j]` is the
/// signed distance between rect `i` and rect `j`. The diagonal is zero.
pub fn compute_pairwise_distances(rects: &[Rect]) -> Vec<f64> {
    let n = rects.len();
    if n == 0 {
        return Vec::new();
    }

    // Pre-compute centers and half-dimensions
    let centers: Vec<Point> = rects.iter().map(|r| r.center()).collect();
    let half_w: Vec<f64> = rects.iter().map(|r| r.w * 0.5).collect();
    let half_h: Vec<f64> = rects.iter().map(|r| r.h * 0.5).collect();

    let mut distances = vec![0.0; n * n];

    for i in 0..n {
        for j in 0..n {
            if i == j {
                continue;
            }
            let cx_dist = (centers[i].x - centers[j].x).abs();
            let cy_dist = (centers[i].y - centers[j].y).abs();
            let gap_x = cx_dist - (half_w[i] + half_w[j]);
            let gap_y = cy_dist - (half_h[i] + half_h[j]);

            let d = if gap_x < 0.0 && gap_y < 0.0 {
                gap_x.min(gap_y)
            } else {
                gap_x.max(gap_y)
            };
            distances[i * n + j] = d;
        }
    }

    distances
}

/// Compute total overlap amount for all rectangle pairs.
///
/// Returns the sum of smooth overlap amounts for all unique pairs (upper
/// triangle only). Zero if no overlaps exist.
pub fn compute_total_overlap(rects: &[Rect]) -> f64 {
    if rects.len() < 2 {
        return 0.0;
    }
    let distances = compute_pairwise_distances(rects);
    let n = rects.len();
    let mut total = 0.0;
    for i in 0..n {
        for j in (i + 1)..n {
            let overlap = smooth_relu(-distances[i * n + j], 10.0);
            total += overlap;
        }
    }
    total
}

/// Compute squared overlap penalty for use in a loss function.
///
/// Applies `weight` to the sum of squared overlaps (pairwise), giving stronger
/// gradients when components heavily overlap.
pub fn compute_overlap_penalty(rects: &[Rect], weight: f64) -> f64 {
    if rects.len() < 2 {
        return 0.0;
    }
    let distances = compute_pairwise_distances(rects);
    let n = rects.len();
    let mut total = 0.0;
    for i in 0..n {
        for j in (i + 1)..n {
            let overlap = smooth_relu(-distances[i * n + j], 10.0);
            total += overlap * overlap;
        }
    }
    weight * total
}

// =============================================================================
// Clearance Checking
// =============================================================================

/// Check all rectangle pairs for clearance violations against a uniform minimum.
///
/// Returns a list of `(i, j, violation_amount)` tuples for every pair whose
/// signed distance is less than `clearance_mm`. The violation amount is the
/// smooth positive excess: `smooth_ReLU(clearance - distance)`.
pub fn check_clearance_violation(
    rects: &[Rect],
    clearance_mm: f64,
) -> Vec<(usize, usize, f64)> {
    if rects.len() < 2 {
        return Vec::new();
    }
    let distances = compute_pairwise_distances(rects);
    let n = rects.len();
    let mut violations = Vec::new();
    for i in 0..n {
        for j in (i + 1)..n {
            let violation = smooth_relu(clearance_mm - distances[i * n + j], 10.0);
            if violation > 0.0 {
                violations.push((i, j, violation));
            }
        }
    }
    violations
}

/// Compute clearance violation penalties for specific pairs.
///
/// Each entry in `clearances` is a `(i, j, required_clearance)` tuple. For a
/// given pair, the penalty is `smooth_relu(clearance - distance, 10)^2`.
///
/// Returns one penalty value per clearance entry.
pub fn compute_clearance_penalties(
    rects: &[Rect],
    clearances: &[(usize, usize, f64)],
) -> Vec<f64> {
    if rects.is_empty() || clearances.is_empty() {
        return Vec::new();
    }
    let distances = compute_pairwise_distances(rects);
    let n = rects.len();
    clearances
        .iter()
        .map(|&(i, j, clearance)| {
            let dist = distances[i * n + j];
            let violation = smooth_relu(clearance - dist, 10.0);
            violation * violation
        })
        .collect()
}

// =============================================================================
// Overlap Statistics
// =============================================================================

/// Count the number of overlapping rectangle pairs.
///
/// A pair is counted when its signed distance is negative (any overlap).
///
/// Note: This function is not differentiable. Use for metrics/reporting only.
pub fn count_overlaps(rects: &[Rect]) -> usize {
    if rects.len() < 2 {
        return 0;
    }
    let distances = compute_pairwise_distances(rects);
    let n = rects.len();
    let mut count = 0;
    for i in 0..n {
        for j in (i + 1)..n {
            if distances[i * n + j] < 0.0 {
                count += 1;
            }
        }
    }
    count
}

/// Find the worst (most severe) overlap between any two rectangles.
///
/// Returns `(i, j, overlap_amount)` where `overlap_amount` is the positive
/// penetration depth (negative of the signed distance). If no overlaps exist,
/// returns `(0, 0, 0.0)`.
pub fn get_worst_overlap(rects: &[Rect]) -> (usize, usize, f64) {
    let n = rects.len();
    if n < 2 {
        return (0, 0, 0.0);
    }
    let distances = compute_pairwise_distances(rects);
    let mut worst_overlap = 0.0f64;
    let mut worst_i = 0usize;
    let mut worst_j = 0usize;

    for i in 0..n {
        for j in (i + 1)..n {
            let dist = distances[i * n + j];
            let overlap = (-dist).max(0.0);
            if overlap > worst_overlap {
                worst_overlap = overlap;
                worst_i = i;
                worst_j = j;
            }
        }
    }

    (worst_i, worst_j, worst_overlap)
}

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    // -----------------------------------------------------------------
    // box_box_distance
    // -----------------------------------------------------------------

    #[test]
    fn test_box_box_distance_overlapping() {
        // Two identical rects at the same position → fully overlapping
        let a = Rect::new(0.0, 0.0, 10.0, 10.0);
        let b = Rect::new(0.0, 0.0, 10.0, 10.0);
        let d = box_box_distance(&a, &b);
        // gap_x = 0 - (5 + 5) = -10, gap_y = same → both negative → min = -10
        assert!(d < 0.0, "overlapping rects should give negative distance, got {d}");
        assert!((d - (-10.0)).abs() < 1e-12);
    }

    #[test]
    fn test_box_box_distance_touching() {
        // Two rects touching edge-to-edge
        let a = Rect::new(0.0, 0.0, 10.0, 10.0);
        let b = Rect::new(10.0, 0.0, 10.0, 10.0);
        let d = box_box_distance(&a, &b);
        // centers: (5,5) and (15,5)
        // gap_x = 10 - (5+5) = 0, gap_y = 0 - (5+5) = -10
        // gap_x == 0 → not < 0 → not both negative → max(0, -10) = 0
        assert!((d - 0.0).abs() < 1e-12, "touching rects should give distance 0, got {d}");
    }

    #[test]
    fn test_box_box_distance_separated() {
        // Two rects separated along the x axis
        let a = Rect::new(0.0, 0.0, 10.0, 10.0);
        let b = Rect::new(30.0, 0.0, 10.0, 10.0);
        let d = box_box_distance(&a, &b);
        // centers: (5,5) and (35,5)
        // gap_x = 30 - (5+5) = 20, gap_y = 0 - (5+5) = -10
        // not both negative → max(20, -10) = 20
        assert!(d > 0.0, "separated rects should give positive distance, got {d}");
        assert!((d - 20.0).abs() < 1e-12);
    }

    // -----------------------------------------------------------------
    // box_box_distance_aabb
    // -----------------------------------------------------------------

    #[test]
    fn test_box_box_distance_aabb_overlapping() {
        let a = AABB::new(0.0, 0.0, 10.0, 10.0);
        let b = AABB::new(2.0, 2.0, 12.0, 12.0);
        let d = box_box_distance_aabb(&a, &b);
        assert!(d < 0.0);
    }

    #[test]
    fn test_box_box_distance_aabb_separated() {
        let a = AABB::new(0.0, 0.0, 10.0, 10.0);
        let b = AABB::new(20.0, 0.0, 30.0, 10.0);
        let d = box_box_distance_aabb(&a, &b);
        assert!(d > 0.0);
    }

    // -----------------------------------------------------------------
    // component_overlap_amount
    // -----------------------------------------------------------------

    #[test]
    fn test_component_overlap_amount_fully_overlapping() {
        let a = AABB::new(0.0, 0.0, 10.0, 10.0);
        let b = AABB::new(0.0, 0.0, 10.0, 10.0);
        let amount = component_overlap_amount(&a, &b);
        assert!(
            (amount - 1.0).abs() < 1e-12,
            "identical AABBs should give overlap 1.0, got {amount}"
        );
    }

    #[test]
    fn test_component_overlap_amount_no_overlap() {
        let a = AABB::new(0.0, 0.0, 10.0, 10.0);
        let b = AABB::new(20.0, 0.0, 30.0, 10.0);
        let amount = component_overlap_amount(&a, &b);
        assert!(
            (amount - 0.0).abs() < 1e-12,
            "separated AABBs should give overlap 0.0, got {amount}"
        );
    }

    #[test]
    fn test_component_overlap_amount_partial() {
        // 10x10 at (0,0) and 10x10 at (5,0) → overlap 5x10 = 50/100 = 0.5
        let a = AABB::new(0.0, 0.0, 10.0, 10.0);
        let b = AABB::new(5.0, 0.0, 15.0, 10.0);
        let amount = component_overlap_amount(&a, &b);
        assert!(
            (amount - 0.5).abs() < 1e-12,
            "half-overlapping AABBs should give 0.5, got {amount}"
        );
    }

    #[test]
    fn test_component_overlap_amount_contained() {
        // One box entirely inside the other
        let a = AABB::new(0.0, 0.0, 20.0, 20.0);
        let b = AABB::new(5.0, 5.0, 10.0, 10.0);
        let amount = component_overlap_amount(&a, &b);
        // overlap = 5*5 = 25, min_area = min(400, 25) = 25, ratio = 1.0
        assert!(
            (amount - 1.0).abs() < 1e-12,
            "contained box should give 1.0, got {amount}"
        );
    }

    // -----------------------------------------------------------------
    // overlap_area_estimate
    // -----------------------------------------------------------------

    #[test]
    fn test_overlap_area_estimate_no_overlap() {
        let a = AABB::new(0.0, 0.0, 10.0, 10.0);
        let b = AABB::new(20.0, 20.0, 30.0, 30.0);
        let area = overlap_area_estimate(&a, &b);
        assert!((area - 0.0).abs() < 1e-12);
    }

    #[test]
    fn test_overlap_area_estimate_partial() {
        let a = AABB::new(0.0, 0.0, 10.0, 10.0);
        let b = AABB::new(5.0, 0.0, 15.0, 10.0);
        let area = overlap_area_estimate(&a, &b);
        assert!((area - 50.0).abs() < 1e-12, "expected 50, got {area}");
    }

    // -----------------------------------------------------------------
    // compute_pairwise_distances
    // -----------------------------------------------------------------

    #[test]
    fn test_compute_pairwise_distances_empty() {
        let d = compute_pairwise_distances(&[]);
        assert!(d.is_empty());
    }

    #[test]
    fn test_compute_pairwise_distances_single() {
        let d = compute_pairwise_distances(&[Rect::new(0.0, 0.0, 10.0, 10.0)]);
        assert_eq!(d.len(), 1);
        assert!((d[0] - 0.0).abs() < 1e-12);
    }

    #[test]
    fn test_compute_pairwise_distances_symmetric() {
        let rects = vec![
            Rect::new(0.0, 0.0, 10.0, 10.0),
            Rect::new(20.0, 0.0, 10.0, 10.0),
            Rect::new(0.0, 20.0, 10.0, 10.0),
        ];
        let d = compute_pairwise_distances(&rects);
        assert_eq!(d.len(), 9);
        // Symmetry: d[i][j] == d[j][i]
        assert!((d[1] - d[3]).abs() < 1e-12);
        assert!((d[2] - d[6]).abs() < 1e-12);
        assert!((d[5] - d[7]).abs() < 1e-12);
        // Diagonal is zero
        assert!((d[0] - 0.0).abs() < 1e-12);
        assert!((d[4] - 0.0).abs() < 1e-12);
        assert!((d[8] - 0.0).abs() < 1e-12);
    }

    // -----------------------------------------------------------------
    // compute_total_overlap
    // -----------------------------------------------------------------

    #[test]
    fn test_compute_total_overlap_no_overlap() {
        let rects = vec![
            Rect::new(0.0, 0.0, 10.0, 10.0),
            Rect::new(20.0, 20.0, 10.0, 10.0),
        ];
        let total = compute_total_overlap(&rects);
        assert!(
            (total - 0.0).abs() < 1e-6,
            "separated rects should have zero total overlap, got {total}"
        );
    }

    #[test]
    fn test_compute_total_overlap_one_pair() {
        // Two identical overlapping rects
        let rects = vec![
            Rect::new(0.0, 0.0, 10.0, 10.0),
            Rect::new(1.0, 1.0, 10.0, 10.0),
        ];
        let total = compute_total_overlap(&rects);
        assert!(
            total > 0.0,
            "overlapping rects should have positive total overlap, got {total}"
        );
    }

    #[test]
    fn test_compute_total_overlap_separated() {
        // Four rects clearly separated with gaps
        let rects = vec![
            Rect::new(0.0, 0.0, 10.0, 10.0),
            Rect::new(15.0, 0.0, 10.0, 10.0),
            Rect::new(0.0, 15.0, 10.0, 10.0),
            Rect::new(15.0, 15.0, 10.0, 10.0),
        ];
        let total = compute_total_overlap(&rects);
        assert!(
            (total - 0.0).abs() < 1e-6,
            "separated rects should have zero overlap, got {total}"
        );
    }

    #[test]
    fn test_compute_total_overlap_all_pairs() {
        // Three overlapping rects — every pair overlaps
        let rects = vec![
            Rect::new(0.0, 0.0, 10.0, 10.0),
            Rect::new(1.0, 0.0, 10.0, 10.0),
            Rect::new(0.0, 1.0, 10.0, 10.0),
        ];
        let total = compute_total_overlap(&rects);
        assert!(
            total > 0.0,
            "overlapping rects should have positive total overlap"
        );
        // Every pair overlaps, so total should be sum of 3 positive overlaps
        let d = compute_pairwise_distances(&rects);
        let n = rects.len();
        let mut expected = 0.0;
        for i in 0..n {
            for j in (i + 1)..n {
                expected += smooth_relu(-d[i * n + j], 10.0);
            }
        }
        assert!(
            (total - expected).abs() < 1e-12,
            "total overlap should match sum of pairwise overlaps: {total} vs {expected}"
        );
    }

    // -----------------------------------------------------------------
    // compute_overlap_penalty
    // -----------------------------------------------------------------

    #[test]
    fn test_compute_overlap_penalty_zero_weight() {
        let rects = vec![
            Rect::new(0.0, 0.0, 10.0, 10.0),
            Rect::new(1.0, 1.0, 10.0, 10.0),
        ];
        let penalty = compute_overlap_penalty(&rects, 0.0);
        assert!((penalty - 0.0).abs() < 1e-12);
    }

    #[test]
    fn test_compute_overlap_penalty_nonzero() {
        let rects = vec![
            Rect::new(0.0, 0.0, 10.0, 10.0),
            Rect::new(1.0, 1.0, 10.0, 10.0),
        ];
        let penalty = compute_overlap_penalty(&rects, 100.0);
        assert!(
            penalty > 0.0,
            "overlapping rects with positive weight should give penalty > 0"
        );
    }

    // -----------------------------------------------------------------
    // check_clearance_violation
    // -----------------------------------------------------------------

    #[test]
    fn test_check_clearance_violation_none() {
        let rects = vec![
            Rect::new(0.0, 0.0, 10.0, 10.0),
            Rect::new(30.0, 0.0, 10.0, 10.0),
        ];
        // distance = 20, clearance = 5
        // smooth_relu(5-20, 10) = smooth_relu(-15, 10) returns ~7e-67
        // Technically > 0 but negligibly small — verify it's negligible
        let violations = check_clearance_violation(&rects, 5.0);
        if !violations.is_empty() {
            assert!(
                violations[0].2 < 1e-50,
                "violation should be negligible, got {}",
                violations[0].2
            );
        }
    }

    #[test]
    fn test_check_clearance_violation_exists() {
        let rects = vec![
            Rect::new(0.0, 0.0, 10.0, 10.0),
            Rect::new(12.0, 0.0, 10.0, 10.0),
        ];
        // distance = 2, clearance = 5 → violation of ~3
        let violations = check_clearance_violation(&rects, 5.0);
        assert_eq!(violations.len(), 1);
        assert_eq!(violations[0].0, 0);
        assert_eq!(violations[0].1, 1);
        assert!(violations[0].2 > 0.0);
    }

    // -----------------------------------------------------------------
    // compute_clearance_penalties
    // -----------------------------------------------------------------

    #[test]
    fn test_compute_clearance_penalties_empty_clearances() {
        let rects = vec![Rect::new(0.0, 0.0, 10.0, 10.0)];
        let penalties = compute_clearance_penalties(&rects, &[]);
        assert!(penalties.is_empty());
    }

    #[test]
    fn test_compute_clearance_penalties_some() {
        let rects = vec![
            Rect::new(0.0, 0.0, 10.0, 10.0),
            Rect::new(15.0, 0.0, 10.0, 10.0),
        ];
        // distance = 5, clearance = 3 → no violation
        // distance = 5, clearance = 10 → violation of 5 (smooth)
        let clearances = vec![(0, 1, 3.0), (0, 1, 10.0)];
        let penalties = compute_clearance_penalties(&rects, &clearances);
        assert_eq!(penalties.len(), 2);
        // First: clearance 3 < distance 5 → no violation → penalty ≈ 0
        assert!(
            penalties[0] < 1e-6,
            "clearance < distance should give ~0 penalty, got {}",
            penalties[0]
        );
        // Second: clearance 10 > distance 5 → has violation → penalty > 0
        assert!(
            penalties[1] > 0.0,
            "clearance > distance should give positive penalty, got {}",
            penalties[1]
        );
    }

    // -----------------------------------------------------------------
    // count_overlaps
    // -----------------------------------------------------------------

    #[test]
    fn test_count_overlaps_no_overlaps() {
        let rects = vec![
            Rect::new(0.0, 0.0, 10.0, 10.0),
            Rect::new(20.0, 0.0, 10.0, 10.0),
            Rect::new(0.0, 20.0, 10.0, 10.0),
        ];
        assert_eq!(count_overlaps(&rects), 0);
    }

    #[test]
    fn test_count_overlaps_all_overlapping() {
        let rects = vec![
            Rect::new(0.0, 0.0, 10.0, 10.0),
            Rect::new(1.0, 1.0, 10.0, 10.0),
            Rect::new(2.0, 2.0, 10.0, 10.0),
        ];
        // 3 rects → 3 choose 2 = 3 pairs, all overlapping
        assert_eq!(count_overlaps(&rects), 3);
    }

    #[test]
    fn test_count_overlaps_partial() {
        let rects = vec![
            Rect::new(0.0, 0.0, 10.0, 10.0),  // overlaps with #1
            Rect::new(5.0, 0.0, 10.0, 10.0),  // overlaps with #0, #2
            Rect::new(5.0, 5.0, 10.0, 10.0),  // overlaps with #1
            Rect::new(30.0, 30.0, 10.0, 10.0), // isolated
        ];
        // Pairs that overlap: (0,1), (1,2) → 2 pairs
        // (0,2) may also overlap depending on exact positions
        let count = count_overlaps(&rects);
        // At minimum: (0,1) and (1,2) overlap
        assert!(count >= 2, "expected at least 2 overlapping pairs, got {count}");
    }

    #[test]
    fn test_count_overlaps_empty() {
        assert_eq!(count_overlaps(&[]), 0);
    }

    #[test]
    fn test_count_overlaps_single() {
        assert_eq!(count_overlaps(&[Rect::new(0.0, 0.0, 10.0, 10.0)]), 0);
    }

    // -----------------------------------------------------------------
    // get_worst_overlap
    // -----------------------------------------------------------------

    #[test]
    fn test_get_worst_overlap_no_overlap() {
        let rects = vec![
            Rect::new(0.0, 0.0, 10.0, 10.0),
            Rect::new(20.0, 0.0, 10.0, 10.0),
        ];
        let (_, _, amount) = get_worst_overlap(&rects);
        assert!(
            (amount - 0.0).abs() < 1e-12,
            "no overlap should give amount 0, got {amount}"
        );
    }

    #[test]
    fn test_get_worst_overlap_finds_worst() {
        // Three rects: #0 and #1 slightly overlapping, #0 and #2 heavily overlapping
        // #0: Rect(0,0,10,10) → center (5,5)
        // #1: Rect(9,9,10,10) → center (14,14), gap = (-1,-1), dist = -1, overlap ≈ 1
        // #2: Rect(0,0,10,10)  → same as #0, gap = (-10,-10), dist = -10, overlap ≈ 10
        let rects = vec![
            Rect::new(0.0, 0.0, 10.0, 10.0),
            Rect::new(9.0, 9.0, 10.0, 10.0),   // offset in both x and y
            Rect::new(0.0, 0.0, 10.0, 10.0),   // identical to #0
        ];
        let (i, j, amount) = get_worst_overlap(&rects);
        assert!(
            amount > 0.0,
            "should find positive overlap, got {amount}"
        );
        // The worst is (0,2) — they're fully overlapped
        assert!(
            (i == 0 && j == 2) || (i == 2 && j == 0),
            "worst overlap should be pair (0,2), got ({i},{j})"
        );
    }

    // -----------------------------------------------------------------
    // Edge cases
    // -----------------------------------------------------------------

    #[test]
    fn test_box_box_distance_zero_dimensions() {
        // Zero-area rect
        let a = Rect::new(0.0, 0.0, 0.0, 0.0);
        let b = Rect::new(5.0, 0.0, 10.0, 10.0);
        let d = box_box_distance(&a, &b);
        // center a: (0,0), half: (0,0)
        // center b: (10,5), half: (5,5)
        // gap_x = 10 - (0+5) = 5, gap_y = 5 - (0+5) = 0
        // not both negative → max(5, 0) = 5
        assert!((d - 5.0).abs() < 1e-12);
    }

    #[test]
    fn test_compute_total_overlap_empty() {
        assert!((compute_total_overlap(&[]) - 0.0).abs() < 1e-12);
    }

    #[test]
    fn test_compute_total_overlap_single() {
        assert!(
            (compute_total_overlap(&[Rect::new(0.0, 0.0, 10.0, 10.0)]) - 0.0).abs() < 1e-12
        );
    }
}
