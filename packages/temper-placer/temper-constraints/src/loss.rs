// Loss computation functions for PCL constraint types.
//
// Implements scalar loss values for each constraint type using
// nalgebra geometry.  These functions are pure compute kernels:
// they accept flat position arrays + constraint parameters and
// return f64 loss values.
//
// R5: Exposed via PyO3 bindings in lib.rs
// R6: Must produce values identical to Python within 1e-6
// R14: All errors caught internally, returned as Python exceptions

use crate::constraints::*;
use nalgebra::Vector2;

// Tier-to-weight mapping (mirrors Python tier_to_weight)
pub fn tier_to_weight(tier: &ConstraintTier) -> f64 {
    tier.weight()
}

// Compute distance between two positions based on metric
fn compute_pairwise_distance(
    pos_a: &Vector2<f64>,
    pos_b: &Vector2<f64>,
    metric: &DistanceMetric,
    pin_a: Option<(f64, f64)>,
    pin_b: Option<(f64, f64)>,
) -> f64 {
    match metric {
        DistanceMetric::CenterToCenter => (pos_a - pos_b).norm(),
        DistanceMetric::EdgeToEdge => {
            (pos_a - pos_b).norm()
        }
        DistanceMetric::PinToPin => {
            let a = match pin_a {
                Some((px, py)) => Vector2::new(pos_a.x + px, pos_a.y + py),
                None => *pos_a,
            };
            let b = match pin_b {
                Some((px, py)) => Vector2::new(pos_b.x + px, pos_b.y + py),
                None => *pos_b,
            };
            (a - b).norm()
        }
    }
}

// AdjacentConstraint -> ProximityLoss (R5)
pub fn compute_adjacent_loss(
    positions: &[f64],
    idx_a: usize,
    idx_b: usize,
    max_distance_mm: f64,
    weight: f64,
    metric: DistanceMetric,
    pin_a: Option<(f64, f64)>,
    pin_b: Option<(f64, f64)>,
) -> f64 {
    let n = positions.len() / 2;
    if idx_a >= n || idx_b >= n {
        return 0.0;
    }
    let pos_a = Vector2::new(positions[idx_a * 2], positions[idx_a * 2 + 1]);
    let pos_b = Vector2::new(positions[idx_b * 2], positions[idx_b * 2 + 1]);

    let dist = compute_pairwise_distance(&pos_a, &pos_b, &metric, pin_a, pin_b);
    let excess = (dist - max_distance_mm).max(0.0);
    weight * excess * excess
}

// SeparatedConstraint -> GroupSeparationLoss (R5)
// Computes distance from each position in group A to each in group B,
// penalizing if min distance is violated.
pub fn compute_separation_loss_batch(
    positions_a_flat: &[f64],
    positions_b_flat: &[f64],
    min_distance_mm: f64,
    weight: f64,
) -> f64 {
    let n_a = positions_a_flat.len() / 2;
    let n_b = positions_b_flat.len() / 2;
    if n_a == 0 || n_b == 0 {
        return 0.0;
    }

    let positions_a: Vec<Vector2<f64>> = (0..n_a)
        .map(|i| Vector2::new(positions_a_flat[i * 2], positions_a_flat[i * 2 + 1]))
        .collect();
    let positions_b: Vec<Vector2<f64>> = (0..n_b)
        .map(|i| Vector2::new(positions_b_flat[i * 2], positions_b_flat[i * 2 + 1]))
        .collect();

    let mut total = 0.0;
    for pos_a in &positions_a {
        for pos_b in &positions_b {
            let dist = (pos_a - pos_b).norm();
            let violation: f64 = (min_distance_mm - dist).max(0.0);
            total += violation * violation;
        }
    }
    weight * total
}

// EnclosingConstraint -> ZoneMembershipLoss (R5)
// Computes distance from each position to the nearest zone boundary.
pub fn compute_zone_membership_loss(
    positions_flat: &[f64],
    zone_bounds: (f64, f64, f64, f64),
    margin_mm: f64,
    weight: f64,
) -> f64 {
    let (x_min, y_min, x_max, y_max) = zone_bounds;
    let n = positions_flat.len() / 2;
    if n == 0 {
        return 0.0;
    }

    let mut total = 0.0;
    for i in 0..n {
        let x = positions_flat[i * 2];
        let y = positions_flat[i * 2 + 1];

        let margin_x_min = x_min + margin_mm;
        let margin_y_min = y_min + margin_mm;
        let margin_x_max = x_max - margin_mm;
        let margin_y_max = y_max - margin_mm;

        let outside_x = (margin_x_min - x).max(0.0) + (x - margin_x_max).max(0.0);
        let outside_y = (margin_y_min - y).max(0.0) + (y - margin_y_max).max(0.0);
        let outside_dist = (outside_x * outside_x + outside_y * outside_y).sqrt();
        total += outside_dist * outside_dist;
    }
    weight * total
}

// AlignedConstraint -> AlignmentLoss (R5)
// Penalizes deviation from alignment along the specified axis.
pub fn compute_alignment_loss(
    positions_flat: &[f64],
    axis: Axis,
    tolerance_mm: f64,
    weight: f64,
) -> f64 {
    let n = positions_flat.len() / 2;
    if n < 2 {
        return 0.0;
    }

    let positions: Vec<Vector2<f64>> = (0..n)
        .map(|i| Vector2::new(positions_flat[i * 2], positions_flat[i * 2 + 1]))
        .collect();

    // Compute mean position along the alignment axis
    let mean: f64 = match axis {
        Axis::X | Axis::Major => {
            positions.iter().map(|p| p.x).sum::<f64>() / n as f64
        }
        Axis::Y | Axis::Minor => {
            positions.iter().map(|p| p.y).sum::<f64>() / n as f64
        }
    };

    let mut total = 0.0;
    for p in &positions {
        let deviation = match axis {
            Axis::X | Axis::Major => (p.x - mean).abs(),
            Axis::Y | Axis::Minor => (p.y - mean).abs(),
        };
        let excess = (deviation - tolerance_mm).max(0.0);
        total += excess * excess;
    }
    weight * total
}

// OnSideConstraint -> EdgePreferenceLoss (R5)
// Penalizes distance from board edge for specified components.
pub fn compute_edge_preference_loss(
    positions_flat: &[f64],
    side: BoardSide,
    board_width: f64,
    board_height: f64,
    max_distance_mm: f64,
    weight: f64,
) -> f64 {
    let n = positions_flat.len() / 2;
    if n == 0 {
        return 0.0;
    }

    let mut total = 0.0;
    for i in 0..n {
        let x = positions_flat[i * 2];
        let y = positions_flat[i * 2 + 1];

        let dist_to_edge = match side {
            BoardSide::Top => board_height - y,
            BoardSide::Bottom => y,
            BoardSide::Left => x,
            BoardSide::Right => board_width - x,
        };

        let excess = (dist_to_edge - max_distance_mm).max(0.0);
        total += excess * excess;
    }
    weight * total
}

// AnchoredConstraint -> PositionalLoss (R5)
// Penalizes distance from a target position.
pub fn compute_anchored_loss_position(
    positions_flat: &[f64],
    _idx: usize,
    target_x: f64,
    target_y: f64,
    weight: f64,
) -> f64 {
    let n = positions_flat.len() / 2;
    if n == 0 {
        return 0.0;
    }
    let x = positions_flat[0];
    let y = positions_flat[1];
    let dx = x - target_x;
    let dy = y - target_y;
    weight * (dx * dx + dy * dy)
}

// AnchoredConstraint -> RegionLoss (R5)
// Penalizes distance from region center + outside-bounds penalty.
pub fn compute_anchored_loss_region(
    positions_flat: &[f64],
    _idx: usize,
    region: (f64, f64, f64, f64),
    weight: f64,
) -> f64 {
    let n = positions_flat.len() / 2;
    if n == 0 {
        return 0.0;
    }
    let x = positions_flat[0];
    let y = positions_flat[1];
    let (x_min, y_min, x_max, y_max) = region;

    let center_x = (x_min + x_max) / 2.0;
    let center_y = (y_min + y_max) / 2.0;
    let dx = x - center_x;
    let dy = y - center_y;
    let dist_sq = dx * dx + dy * dy;

    let outside_x = (x_min - x).max(0.0) + (x - x_max).max(0.0);
    let outside_y = (y_min - y).max(0.0) + (y - y_max).max(0.0);
    let outside_penalty = (outside_x + outside_y).powi(2);

    weight * (dist_sq + 10.0 * outside_penalty)
}

// LoopAreaConstraint -> LoopAreaLoss (R5)
// Computes polygon area via shoelace formula and penalizes if > max_area.
pub fn compute_loop_area_loss(
    positions_flat: &[f64],
    max_area_mm2: f64,
    weight: f64,
) -> f64 {
    let n = positions_flat.len() / 2;
    if n < 3 {
        return 0.0;
    }

    // Shoelace formula for polygon area
    let mut area = 0.0;
    for i in 0..n {
        let j = (i + 1) % n;
        let x_i = positions_flat[i * 2];
        let y_i = positions_flat[i * 2 + 1];
        let x_j = positions_flat[j * 2];
        let y_j = positions_flat[j * 2 + 1];
        area += x_i * y_j - x_j * y_i;
    }
    area = (area / 2.0).abs();

    let excess = (area - max_area_mm2).max(0.0);
    weight * excess * excess
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_tier_to_weight() {
        assert_eq!(tier_to_weight(&ConstraintTier::Hard), 1_000_000.0);
        assert_eq!(tier_to_weight(&ConstraintTier::Strong), 1_000.0);
        assert_eq!(tier_to_weight(&ConstraintTier::Soft), 10.0);
    }

    #[test]
    fn test_adjacent_loss_zero_when_within_range() {
        let positions = vec![0.0, 0.0, 5.0, 0.0]; // 5mm apart
        let loss = compute_adjacent_loss(
            &positions, 0, 1, 10.0, 1.0,
            DistanceMetric::CenterToCenter, None, None,
        );
        assert_eq!(loss, 0.0);
    }

    #[test]
    fn test_adjacent_loss_positive_when_exceeds() {
        let positions = vec![0.0, 0.0, 20.0, 0.0]; // 20mm apart
        let loss = compute_adjacent_loss(
            &positions, 0, 1, 10.0, 1.0,
            DistanceMetric::CenterToCenter, None, None,
        );
        assert!(loss > 0.0);
        // excess = 10mm, loss = 1.0 * 10^2 = 100
        assert!((loss - 100.0).abs() < 1e-6);
    }

    #[test]
    fn test_separation_loss_zero_when_far_enough() {
        let pos_a = vec![0.0, 0.0];
        let pos_b = vec![50.0, 0.0];
        let loss = compute_separation_loss_batch(&pos_a, &pos_b, 5.0, 1.0);
        assert_eq!(loss, 0.0);
    }

    #[test]
    fn test_separation_loss_positive_when_too_close() {
        let pos_a = vec![0.0, 0.0];
        let pos_b = vec![2.0, 0.0];
        let loss = compute_separation_loss_batch(&pos_a, &pos_b, 10.0, 1.0);
        assert!(loss > 0.0);
        // dist=2, min=10, violation=8, loss = 1.0 * 8^2 = 64
        assert!((loss - 64.0).abs() < 1e-6);
    }

    #[test]
    fn test_zone_membership_loss_inside() {
        let positions = vec![25.0, 25.0, 30.0, 30.0];
        let zone = (0.0, 0.0, 50.0, 50.0);
        let loss = compute_zone_membership_loss(&positions, zone, 0.0, 1.0);
        assert_eq!(loss, 0.0);
    }

    #[test]
    fn test_zone_membership_loss_outside() {
        let positions = vec![60.0, 25.0]; // x outside zone (max=50)
        let zone = (0.0, 0.0, 50.0, 50.0);
        let loss = compute_zone_membership_loss(&positions, zone, 0.0, 1.0);
        assert!(loss > 0.0);
    }

    #[test]
    fn test_alignment_loss_perfect() {
        let positions = vec![10.0, 20.0, 10.0, 30.0, 10.0, 40.0]; // all x=10
        let loss = compute_alignment_loss(&positions, Axis::X, 0.5, 1.0);
        assert_eq!(loss, 0.0);
    }

    #[test]
    fn test_alignment_loss_misaligned() {
        let positions = vec![10.0, 20.0, 10.0, 30.0, 20.0, 40.0]; // third x=20
        let loss = compute_alignment_loss(&positions, Axis::X, 0.5, 1.0);
        assert!(loss > 0.0);
    }

    #[test]
    fn test_edge_preference_loss_on_edge() {
        let positions = vec![0.0, 0.0]; // at left edge
        let loss = compute_edge_preference_loss(
            &positions, BoardSide::Left, 100.0, 80.0, 5.0, 1.0,
        );
        assert_eq!(loss, 0.0);
    }

    #[test]
    fn test_edge_preference_loss_far_from_edge() {
        let positions = vec![50.0, 40.0]; // far from left edge
        let loss = compute_edge_preference_loss(
            &positions, BoardSide::Left, 100.0, 80.0, 5.0, 1.0,
        );
        assert!(loss > 0.0);
    }

    #[test]
    fn test_anchored_loss_at_target() {
        let positions = vec![30.0, 30.0];
        let loss = compute_anchored_loss_position(&positions, 0, 30.0, 30.0, 1.0);
        assert_eq!(loss, 0.0);
    }

    #[test]
    fn test_anchored_loss_away_from_target() {
        let positions = vec![10.0, 10.0];
        let loss = compute_anchored_loss_position(&positions, 0, 30.0, 30.0, 1.0);
        // dx=20, dy=20, dist_sq=800, loss=800
        assert!((loss - 800.0).abs() < 1e-6);
    }

    #[test]
    fn test_loop_area_loss_zero_when_small() {
        // 10x10 square = 100 mm^2, max_area=200
        let positions = vec![0.0, 0.0, 10.0, 0.0, 10.0, 10.0, 0.0, 10.0];
        let loss = compute_loop_area_loss(&positions, 200.0, 1.0);
        assert_eq!(loss, 0.0);
    }

    #[test]
    fn test_loop_area_loss_positive_when_large() {
        // 20x20 square = 400 mm^2, max_area=200
        let positions = vec![0.0, 0.0, 20.0, 0.0, 20.0, 20.0, 0.0, 20.0];
        let loss = compute_loop_area_loss(&positions, 200.0, 1.0);
        // excess = 200, loss = 1.0 * 200^2 = 40000
        assert!((loss - 40000.0).abs() < 1e-6);
    }
}
