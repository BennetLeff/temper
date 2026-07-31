use crate::types::*;

// =============================================================================
// Rotation Matrix
// =============================================================================

/// Get a 2×2 counter-clockwise rotation matrix for the given angle in radians.
///
/// ```
/// # use temper_geometry::transform::get_rotation_matrix;
/// let m = get_rotation_matrix(std::f64::consts::FRAC_PI_2);
/// assert!((m[0][0] - 0.0).abs() < 1e-15);
/// assert!((m[0][1] - (-1.0)).abs() < 1e-15);
/// assert!((m[1][0] - 1.0).abs() < 1e-15);
/// assert!((m[1][1] - 0.0).abs() < 1e-15);
/// ```
pub fn get_rotation_matrix(angle_rad: f64) -> [[f64; 2]; 2] {
    let cos = angle_rad.cos();
    let sin = angle_rad.sin();
    [[cos, -sin], [sin, cos]]
}

// =============================================================================
// Core Rotation Functions
// =============================================================================

/// Rotate a single point around an optional center (defaults to the origin).
///
/// When `center` is `None`, the point is rotated about `(0, 0)`.
pub fn rotate_point(p: &Point, angle_rad: f64, center: Option<&Point>) -> Point {
    let c = center.copied().unwrap_or(Point::zero());
    let dx = p.x - c.x;
    let dy = p.y - c.y;
    let m = get_rotation_matrix(angle_rad);
    Point::new(
        c.x + m[0][0] * dx + m[0][1] * dy,
        c.y + m[1][0] * dx + m[1][1] * dy,
    )
}

/// Rotate multiple points by the same angle around an optional common center.
pub fn rotate_points(points: &[Point], angle_rad: f64, center: Option<&Point>) -> Vec<Point> {
    let c = center.copied().unwrap_or(Point::zero());
    let m = get_rotation_matrix(angle_rad);
    points
        .iter()
        .map(|p| {
            let dx = p.x - c.x;
            let dy = p.y - c.y;
            Point::new(
                c.x + m[0][0] * dx + m[0][1] * dy,
                c.y + m[1][0] * dx + m[1][1] * dy,
            )
        })
        .collect()
}

// =============================================================================
// Rectangle and Bounds Rotation
// =============================================================================

/// Compute the axis-aligned bounding box of a rectangle rotated around its
/// own center by the given angle.
pub fn get_rotated_bounds(r: &Rect, angle_rad: f64) -> AABB {
    let center = r.center();
    let corners = rotate_rectangle_corners(r, angle_rad, &center);
    AABB::from_points(&corners)
}

/// Rotate the four corners of a rectangle around a given center point.
///
/// Returns corners in order `[bottom-left, bottom-right, top-right, top-left]`
/// **after** rotation (no longer axis-aligned after rotation).
pub fn rotate_rectangle_corners(r: &Rect, angle_rad: f64, center: &Point) -> Vec<Point> {
    let half_w = r.w * 0.5;
    let half_h = r.h * 0.5;

    // Corners relative to the rect center (pre-rotation)
    let rel_corners = [
        Point::new(-half_w, -half_h), // bottom-left
        Point::new(half_w, -half_h),  // bottom-right
        Point::new(half_w, half_h),   // top-right
        Point::new(-half_w, half_h),  // top-left
    ];

    let m = get_rotation_matrix(angle_rad);
    rel_corners
        .iter()
        .map(|c| {
            let rx = m[0][0] * c.x + m[0][1] * c.y;
            let ry = m[1][0] * c.x + m[1][1] * c.y;
            Point::new(center.x + rx, center.y + ry)
        })
        .collect()
}

/// Compute the axis-aligned bounding box from an arbitrary set of vertices.
///
/// This is a convenience wrapper around [`AABB::from_points`].
pub fn get_rotated_aabb(vertices: &[Point]) -> AABB {
    AABB::from_points(vertices)
}

// =============================================================================
// Pin Position Transforms
// =============================================================================

/// Transform a single pin offset into world coordinates given a component
/// position and rotation, matching KiCad's real footprint-child rotation
/// convention: R(-theta), not R(+theta) (`get_rotation_matrix`'s generic
/// CCW matrix). Confirmed against real `kicad-cli 10.0.4 pcb drc` ground
/// truth, see
/// `docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md`
/// Sec. 2, and matches the Python reference
/// `temper_placer.core.pin_geometry.pin_world_position_at`. Not currently
/// called from any production Python path (only exposed via the pyo3
/// bridge and its own tests here) -- fixed anyway so a future caller does
/// not inherit the bug.
///
/// The pin offset is defined relative to the component center at 0° rotation.
pub fn transform_pin_position(
    pin_pos: &Point,
    comp_pos: &Point,
    rotation_rad: f64,
) -> Point {
    let cos = rotation_rad.cos();
    let sin = rotation_rad.sin();
    let rx = pin_pos.x * cos + pin_pos.y * sin;
    let ry = -pin_pos.x * sin + pin_pos.y * cos;
    Point::new(comp_pos.x + rx, comp_pos.y + ry)
}

/// Transform multiple pin offsets into world coordinates for a single
/// component. See `transform_pin_position` for the rotation convention.
pub fn transform_pin_positions(
    pin_positions: &[Point],
    comp_pos: &Point,
    rotation_rad: f64,
) -> Vec<Point> {
    let cos = rotation_rad.cos();
    let sin = rotation_rad.sin();
    pin_positions
        .iter()
        .map(|p| {
            let rx = p.x * cos + p.y * sin;
            let ry = -p.x * sin + p.y * cos;
            Point::new(comp_pos.x + rx, comp_pos.y + ry)
        })
        .collect()
}

// =============================================================================
// Batch Operations
// =============================================================================

/// Element-wise rotated bounds for pairs of rectangles and angles.
///
/// Both slices must have the same length.
pub fn batch_get_rotated_bounds(rects: &[Rect], angles: &[f64]) -> Vec<AABB> {
    rects
        .iter()
        .zip(angles.iter())
        .map(|(r, a)| get_rotated_bounds(r, *a))
        .collect()
}

/// Element-wise rotation of individual points, each with its own angle and
/// center.
///
/// All three slices must have the same length.
pub fn batch_rotate_points(
    points: &[Point],
    angles: &[f64],
    centers: &[Point],
) -> Vec<Point> {
    points
        .iter()
        .zip(angles.iter().zip(centers.iter()))
        .map(|(p, (a, c))| rotate_point(p, *a, Some(c)))
        .collect()
}

// =============================================================================
// One-hot Encoding / Decoding
// =============================================================================

/// Convert a rotation index to a one-hot vector of length `n_angles`.
///
/// The result has `1.0` at index `idx` (clamped to `[0, n_angles)`) and `0.0`
/// elsewhere.
pub fn rotation_index_to_onehot(idx: usize, n_angles: usize) -> Vec<f64> {
    let mut v = vec![0.0; n_angles];
    if idx < n_angles {
        v[idx] = 1.0;
    }
    v
}

/// Convert a rotation angle in degrees to a one-hot vector by finding the
/// nearest allowed angle.
///
/// The input is normalized to `[0, 360)` before matching.
pub fn rotation_degrees_to_onehot(deg: f64, allowed: &[f64]) -> Vec<f64> {
    let deg_norm = deg % 360.0;
    let mut best_i = 0;
    let mut best_dist = f64::INFINITY;
    for (i, &a) in allowed.iter().enumerate() {
        let diff = (deg_norm - a).abs();
        if diff < best_dist {
            best_dist = diff;
            best_i = i;
        }
    }
    let mut v = vec![0.0; allowed.len()];
    v[best_i] = 1.0;
    v
}

/// Decode a (possibly soft) one-hot vector to a rotation angle in degrees
/// via weighted sum with the allowed angles.
pub fn onehot_to_rotation_degrees(onehot: &[f64], allowed: &[f64]) -> f64 {
    onehot
        .iter()
        .zip(allowed.iter())
        .map(|(o, a)| o * a)
        .sum()
}

/// Decode a (possibly soft) one-hot vector to a rotation angle in radians
/// via weighted sum with the allowed angles.
pub fn onehot_to_rotation_radians(onehot: &[f64], allowed_rad: &[f64]) -> f64 {
    onehot
        .iter()
        .zip(allowed_rad.iter())
        .map(|(o, a)| o * a)
        .sum()
}

// =============================================================================
// Gumbel-Softmax & Rotation Sampling
// =============================================================================

/// Apply Gumbel-Softmax reparameterization to logits.
///
/// Adds Gumbel-distributed noise to the logits, scales by `temperature`, then
/// applies softmax. As `temperature → 0`, the output approaches a true
/// one-hot vector (argmax).
///
/// Uses `rand::thread_rng()` for the Gumbel noise samples.
pub fn gumbel_softmax(logits: &[f64], temperature: f64) -> Vec<f64> {
    let n = logits.len();
    if n == 0 {
        return Vec::new();
    }

    // Numerical stability: shift logits so max = 0 before adding noise
    let max_logit = logits
        .iter()
        .fold(f64::NEG_INFINITY, |a, &b| a.max(b));

    let mut shifted: Vec<f64> = Vec::with_capacity(n);
    for &l in logits {
        // Sample Gumbel(0, 1) noise via inverse-CDF transform
        let u: f64 = rand::random::<f64>().clamp(1e-15, 1.0 - 1e-15);
        let gumbel = -(-u.ln()).ln();
        shifted.push((l - max_logit + gumbel) / temperature);
    }

    // Stable softmax over the shifted values
    let max_shifted = shifted
        .iter()
        .fold(f64::NEG_INFINITY, |a, &b| a.max(b));

    let mut exps: Vec<f64> = Vec::with_capacity(n);
    let mut sum = 0.0;
    for &s in &shifted {
        let e = (s - max_shifted).exp();
        exps.push(e);
        sum += e;
    }

    if sum <= 0.0 {
        // Degenerate case: uniform distribution
        return vec![1.0 / n as f64; n];
    }

    exps.iter().map(|e| e / sum).collect()
}

/// Sample a discrete rotation index from logits via argmax.
///
/// Returns the index of the largest logit. Ties are broken by first
/// occurrence (deterministic).
pub fn sample_rotation(logits: &[f64]) -> usize {
    logits
        .iter()
        .enumerate()
        .max_by(|(_, a), (_, b)| {
            // prefer first element on tie (matching np.argmax semantics)
            a.partial_cmp(b)
                .unwrap_or(std::cmp::Ordering::Equal)
                .then_with(|| std::cmp::Ordering::Greater)
        })
        .map(|(i, _)| i)
        .unwrap_or(0)
}

/// Sample discrete rotation indices for a batch of logit vectors.
pub fn sample_rotation_batch(logits: &[Vec<f64>]) -> Vec<usize> {
    logits.iter().map(|l| sample_rotation(l)).collect()
}

// =============================================================================
// Pre-computed constants for the standard 4-angle PCB rotation set
// =============================================================================

/// The four standard PCB rotation angles in radians: 0, π/2, π, 3π/2.
pub const ROTATION_ANGLES_RAD: [f64; 4] = [
    0.0,
    std::f64::consts::FRAC_PI_2,
    std::f64::consts::PI,
    3.0 * std::f64::consts::FRAC_PI_2,
];

/// The four standard PCB rotation angles in degrees: 0, 90, 180, 270.
pub const ROTATION_ANGLES_DEG: [f64; 4] = [0.0, 90.0, 180.0, 270.0];

// =============================================================================
// Tests
// =============================================================================

#[cfg(test)]
mod tests {
    use super::*;

    // -----------------------------------------------------------------
    // get_rotation_matrix
    // -----------------------------------------------------------------
    #[test]
    fn test_get_rotation_matrix_0() {
        let m = get_rotation_matrix(0.0);
        assert!((m[0][0] - 1.0).abs() < 1e-15);
        assert!((m[0][1] - 0.0).abs() < 1e-15);
        assert!((m[1][0] - 0.0).abs() < 1e-15);
        assert!((m[1][1] - 1.0).abs() < 1e-15);
    }

    #[test]
    fn test_get_rotation_matrix_90() {
        let m = get_rotation_matrix(std::f64::consts::FRAC_PI_2);
        assert!((m[0][0] - 0.0).abs() < 1e-15);
        assert!((m[0][1] - (-1.0)).abs() < 1e-15);
        assert!((m[1][0] - 1.0).abs() < 1e-15);
        assert!((m[1][1] - 0.0).abs() < 1e-15);
    }

    // -----------------------------------------------------------------
    // rotate_point: 90°, 180°, 270° rotation of (1, 0)
    // -----------------------------------------------------------------
    #[test]
    fn test_rotate_point_90() {
        // (1, 0) rotated 90° CCW about origin → (0, 1)
        let p = Point::new(1.0, 0.0);
        let r = rotate_point(&p, std::f64::consts::FRAC_PI_2, None);
        assert!((r.x - 0.0).abs() < 1e-15, "expected 0, got {}", r.x);
        assert!((r.y - 1.0).abs() < 1e-15, "expected 1, got {}", r.y);
    }

    #[test]
    fn test_rotate_point_180() {
        // (1, 0) rotated 180° CCW about origin → (-1, 0)
        let p = Point::new(1.0, 0.0);
        let r = rotate_point(&p, std::f64::consts::PI, None);
        assert!((r.x - (-1.0)).abs() < 1e-15, "expected -1, got {}", r.x);
        assert!((r.y - 0.0).abs() < 1e-15, "expected 0, got {}", r.y);
    }

    #[test]
    fn test_rotate_point_270() {
        // (1, 0) rotated 270° CCW about origin → (0, -1)
        let p = Point::new(1.0, 0.0);
        let r = rotate_point(&p, 3.0 * std::f64::consts::FRAC_PI_2, None);
        assert!((r.x - 0.0).abs() < 1e-15, "expected 0, got {}", r.x);
        assert!((r.y - (-1.0)).abs() < 1e-15, "expected -1, got {}", r.y);
    }

    #[test]
    fn test_rotate_point_about_center() {
        // Rotate (2, 1) 90° CCW about (1, 1)
        // Relative vector: (1, 0) → rotated: (0, 1) → final: (1, 2)
        let p = Point::new(2.0, 1.0);
        let c = Point::new(1.0, 1.0);
        let r = rotate_point(&p, std::f64::consts::FRAC_PI_2, Some(&c));
        assert!((r.x - 1.0).abs() < 1e-15, "expected 1, got {}", r.x);
        assert!((r.y - 2.0).abs() < 1e-15, "expected 2, got {}", r.y);
    }

    #[test]
    fn test_rotate_point_noop() {
        let p = Point::new(3.0, 4.0);
        let r = rotate_point(&p, 0.0, None);
        assert!((r.x - 3.0).abs() < 1e-15);
        assert!((r.y - 4.0).abs() < 1e-15);
    }

    // -----------------------------------------------------------------
    // rotate_points
    // -----------------------------------------------------------------
    #[test]
    fn test_rotate_points_empty() {
        let result = rotate_points(&[], 1.0, None);
        assert!(result.is_empty());
    }

    #[test]
    fn test_rotate_points_batch() {
        let pts = vec![Point::new(1.0, 0.0), Point::new(0.0, 1.0)];
        let result = rotate_points(&pts, std::f64::consts::FRAC_PI_2, None);
        assert_eq!(result.len(), 2);
        // (1,0) → (0,1)
        assert!((result[0].x - 0.0).abs() < 1e-15);
        assert!((result[0].y - 1.0).abs() < 1e-15);
        // (0,1) → (-1,0)
        assert!((result[1].x - (-1.0)).abs() < 1e-15);
        assert!((result[1].y - 0.0).abs() < 1e-15);
    }

    // -----------------------------------------------------------------
    // get_rotated_bounds: square at 0°, 45°, 90°
    // -----------------------------------------------------------------
    fn square_at_origin() -> Rect {
        // 2×2 square with bottom-left at (-1, -1) → center at (0, 0)
        Rect::new(-1.0, -1.0, 2.0, 2.0)
    }

    #[test]
    fn test_get_rotated_bounds_0() {
        let r = square_at_origin();
        let bb = get_rotated_bounds(&r, 0.0);
        assert!((bb.x_min - (-1.0)).abs() < 1e-15);
        assert!((bb.y_min - (-1.0)).abs() < 1e-15);
        assert!((bb.x_max - 1.0).abs() < 1e-15);
        assert!((bb.y_max - 1.0).abs() < 1e-15);
    }

    #[test]
    fn test_get_rotated_bounds_45() {
        // 2×2 square rotated 45° about its center → AABB side = 2√2 ≈ 2.828
        let r = square_at_origin();
        let bb = get_rotated_bounds(&r, std::f64::consts::FRAC_PI_4);
        let half_diag = (2.0_f64).sqrt(); // half diagonal of 2×2 = √2
        assert!((bb.x_min - (-half_diag)).abs() < 1e-14);
        assert!((bb.y_min - (-half_diag)).abs() < 1e-14);
        assert!((bb.x_max - half_diag).abs() < 1e-14);
        assert!((bb.y_max - half_diag).abs() < 1e-14);
        assert!((bb.width() - (2.0 * half_diag)).abs() < 1e-14);
    }

    #[test]
    fn test_get_rotated_bounds_90() {
        // 2×2 square rotated 90° → same AABB (square)
        let r = square_at_origin();
        let bb = get_rotated_bounds(&r, std::f64::consts::FRAC_PI_2);
        assert!((bb.x_min - (-1.0)).abs() < 1e-15);
        assert!((bb.y_min - (-1.0)).abs() < 1e-15);
        assert!((bb.x_max - 1.0).abs() < 1e-15);
        assert!((bb.y_max - 1.0).abs() < 1e-15);
    }

    // -----------------------------------------------------------------
    // rotate_rectangle_corners
    // -----------------------------------------------------------------
    #[test]
    fn test_rotate_rectangle_corners_no_rotation() {
        let r = Rect::new(0.0, 0.0, 2.0, 2.0);
        let center = r.center();
        let corners = rotate_rectangle_corners(&r, 0.0, &center);
        assert_eq!(corners.len(), 4);
        // bottom-left
        assert!((corners[0].x - 0.0).abs() < 1e-15);
        assert!((corners[0].y - 0.0).abs() < 1e-15);
        // bottom-right
        assert!((corners[1].x - 2.0).abs() < 1e-15);
        assert!((corners[1].y - 0.0).abs() < 1e-15);
        // top-right
        assert!((corners[2].x - 2.0).abs() < 1e-15);
        assert!((corners[2].y - 2.0).abs() < 1e-15);
        // top-left
        assert!((corners[3].x - 0.0).abs() < 1e-15);
        assert!((corners[3].y - 2.0).abs() < 1e-15);
    }

    // -----------------------------------------------------------------
    // get_rotated_aabb
    // -----------------------------------------------------------------
    #[test]
    fn test_get_rotated_aabb_from_vertices() {
        let vertices = vec![
            Point::new(2.0, 3.0),
            Point::new(5.0, 1.0),
            Point::new(8.0, 4.0),
        ];
        let bb = get_rotated_aabb(&vertices);
        assert!((bb.x_min - 2.0).abs() < 1e-15);
        assert!((bb.y_min - 1.0).abs() < 1e-15);
        assert!((bb.x_max - 8.0).abs() < 1e-15);
        assert!((bb.y_max - 4.0).abs() < 1e-15);
    }

    // -----------------------------------------------------------------
    // transform_pin_position
    // -----------------------------------------------------------------
    #[test]
    fn test_transform_pin_position_no_rotation() {
        // Pin offset (1, 0) at component center (10, 20), 0° rotation → (11, 20)
        let result = transform_pin_position(&Point::new(1.0, 0.0), &Point::new(10.0, 20.0), 0.0);
        assert!((result.x - 11.0).abs() < 1e-15);
        assert!((result.y - 20.0).abs() < 1e-15);
    }

    #[test]
    fn test_transform_pin_position_rotated() {
        // Pin offset (1, 0) at (10, 20), 90° rotation.
        //
        // KiCad's real footprint-child rotation is R(-theta), confirmed
        // against real kicad-cli 10.0.4 pcb drc ground truth (see
        // docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md
        // Sec. 2): world = R(-theta) * local. At theta=90°,
        // R(-90) = [[cos(-90), -sin(-90)], [sin(-90), cos(-90)]] = [[0, 1], [-1, 0]].
        // Applied to (1, 0): (0*1 + 1*0, -1*1 + 0*0) = (0, -1).
        // So the offset becomes (0, -1) -> world (10, 19), NOT the old
        // R(+theta) value of (10, 21) this test asserted before the fix.
        let result = transform_pin_position(&Point::new(1.0, 0.0), &Point::new(10.0, 20.0), std::f64::consts::FRAC_PI_2);
        assert!((result.x - 10.0).abs() < 1e-15);
        assert!((result.y - 19.0).abs() < 1e-15);
    }

    // -----------------------------------------------------------------
    // transform_pin_positions
    // -----------------------------------------------------------------
    #[test]
    fn test_transform_pin_positions_empty() {
        let result = transform_pin_positions(&[], &Point::new(0.0, 0.0), 0.0);
        assert!(result.is_empty());
    }

    // -----------------------------------------------------------------
    // batch_get_rotated_bounds
    // -----------------------------------------------------------------
    #[test]
    fn test_batch_get_rotated_bounds_empty() {
        let result = batch_get_rotated_bounds(&[], &[]);
        assert!(result.is_empty());
    }

    #[test]
    fn test_batch_get_rotated_bounds() {
        let rects = vec![Rect::new(0.0, 0.0, 2.0, 2.0), Rect::new(0.0, 0.0, 4.0, 2.0)];
        let angles = vec![0.0, std::f64::consts::FRAC_PI_2];
        let result = batch_get_rotated_bounds(&rects, &angles);
        assert_eq!(result.len(), 2);
        // First rect at 0° → same bounds
        assert!((result[0].x_min - 0.0).abs() < 1e-15);
        assert!((result[0].x_max - 2.0).abs() < 1e-15);
        assert!((result[0].y_min - 0.0).abs() < 1e-15);
        assert!((result[0].y_max - 2.0).abs() < 1e-15);
    }

    // -----------------------------------------------------------------
    // batch_rotate_points: N=5
    // -----------------------------------------------------------------
    #[test]
    fn test_batch_rotate_points_n5() {
        let points = vec![
            Point::new(1.0, 0.0),
            Point::new(0.0, 1.0),
            Point::new(-1.0, 0.0),
            Point::new(0.0, -1.0),
            Point::new(1.0, 1.0),
        ];
        let angles = vec![
            0.0,
            std::f64::consts::FRAC_PI_2,
            std::f64::consts::PI,
            3.0 * std::f64::consts::FRAC_PI_2,
            0.0,
        ];
        let centers = vec![
            Point::zero(),
            Point::zero(),
            Point::zero(),
            Point::zero(),
            Point::new(1.0, 1.0), // (1,1) rotated 0° about (1,1) → (1,1)
        ];
        let result = batch_rotate_points(&points, &angles, &centers);
        assert_eq!(result.len(), 5);

        // 0° about origin: (1,0) → (1,0)
        assert!((result[0].x - 1.0).abs() < 1e-15);
        assert!((result[0].y - 0.0).abs() < 1e-15);

        // 90° about origin: (0,1) → (-1,0)
        assert!((result[1].x - (-1.0)).abs() < 1e-15);
        assert!((result[1].y - 0.0).abs() < 1e-15);

        // 180° about origin: (-1,0) → (1,0)
        assert!((result[2].x - 1.0).abs() < 1e-15);
        assert!((result[2].y - 0.0).abs() < 1e-15);

        // 270° about origin: (0,-1) → (-1,0)
        assert!((result[3].x - (-1.0)).abs() < 1e-15);
        assert!((result[3].y - 0.0).abs() < 1e-15);

        // 0° about (1,1): (1,1) → (1,1)
        assert!((result[4].x - 1.0).abs() < 1e-15);
        assert!((result[4].y - 1.0).abs() < 1e-15);
    }

    // -----------------------------------------------------------------
    // rotation_index_to_onehot
    // -----------------------------------------------------------------
    #[test]
    fn test_rotation_index_to_onehot() {
        let v = rotation_index_to_onehot(1, 4);
        assert_eq!(v, vec![0.0, 1.0, 0.0, 0.0]);
    }

    #[test]
    fn test_rotation_index_to_onehot_out_of_range() {
        let v = rotation_index_to_onehot(10, 4);
        assert_eq!(v, vec![0.0, 0.0, 0.0, 0.0]);
    }

    // -----------------------------------------------------------------
    // rotation_degrees_to_onehot
    // -----------------------------------------------------------------
    #[test]
    fn test_rotation_degrees_to_onehot_exact() {
        let v = rotation_degrees_to_onehot(90.0, &ROTATION_ANGLES_DEG);
        assert_eq!(v, vec![0.0, 1.0, 0.0, 0.0]);
    }

    #[test]
    fn test_rotation_degrees_to_onehot_normalized() {
        // 450° → 90°
        let v = rotation_degrees_to_onehot(450.0, &ROTATION_ANGLES_DEG);
        assert_eq!(v, vec![0.0, 1.0, 0.0, 0.0]);
    }

    #[test]
    fn test_rotation_degrees_to_onehot_rounded() {
        // 91° → nearest is 90°
        let v = rotation_degrees_to_onehot(91.0, &ROTATION_ANGLES_DEG);
        assert_eq!(v, vec![0.0, 1.0, 0.0, 0.0]);
    }

    // -----------------------------------------------------------------
    // onehot_to_rotation_degrees round-trip
    // -----------------------------------------------------------------
    #[test]
    fn test_onehot_to_rotation_degrees_0() {
        let deg = onehot_to_rotation_degrees(&[1.0, 0.0, 0.0, 0.0], &ROTATION_ANGLES_DEG);
        assert!((deg - 0.0).abs() < 1e-15);
    }

    #[test]
    fn test_onehot_to_rotation_degrees_90() {
        let deg = onehot_to_rotation_degrees(&[0.0, 1.0, 0.0, 0.0], &ROTATION_ANGLES_DEG);
        assert!((deg - 90.0).abs() < 1e-15);
    }

    #[test]
    fn test_onehot_to_rotation_degrees_180() {
        let deg = onehot_to_rotation_degrees(&[0.0, 0.0, 1.0, 0.0], &ROTATION_ANGLES_DEG);
        assert!((deg - 180.0).abs() < 1e-15);
    }

    #[test]
    fn test_onehot_to_rotation_degrees_270() {
        let deg = onehot_to_rotation_degrees(&[0.0, 0.0, 0.0, 1.0], &ROTATION_ANGLES_DEG);
        assert!((deg - 270.0).abs() < 1e-15);
    }

    #[test]
    fn test_onehot_round_trip() {
        // round-trip: degree → onehot → degree
        let allowed = &[0.0, 90.0, 180.0, 270.0];
        for &deg in allowed {
            let onehot = rotation_degrees_to_onehot(deg, allowed);
            let deg_back = onehot_to_rotation_degrees(&onehot, allowed);
            assert!(
                (deg - deg_back).abs() < 1e-15,
                "round-trip failed for {}°: got {}°",
                deg,
                deg_back
            );
        }
    }

    #[test]
    fn test_onehot_round_trip_soft() {
        // Soft one-hot (e.g. from Gumbel-Softmax) → weighted average
        let soft = [0.1, 0.7, 0.1, 0.1];
        let deg = onehot_to_rotation_degrees(&soft, &[0.0, 90.0, 180.0, 270.0]);
        // 0.1*0 + 0.7*90 + 0.1*180 + 0.1*270 = 63 + 18 + 27 = 108
        assert!((deg - 108.0).abs() < 1e-14, "expected 108, got {}", deg);
    }

    // -----------------------------------------------------------------
    // onehot_to_rotation_radians
    // -----------------------------------------------------------------
    #[test]
    fn test_onehot_to_rotation_radians() {
        let rad = onehot_to_rotation_radians(
            &[0.0, 1.0, 0.0, 0.0],
            &[0.0, std::f64::consts::FRAC_PI_2, std::f64::consts::PI, 3.0 * std::f64::consts::FRAC_PI_2],
        );
        assert!((rad - std::f64::consts::FRAC_PI_2).abs() < 1e-15);
    }

    // -----------------------------------------------------------------
    // gumbel_softmax: with low temperature → argmax
    // -----------------------------------------------------------------
    #[test]
    fn test_gumbel_softmax_low_temp_argmax() {
        // With very low temperature, the result should approximate a
        // one-hot at the argmax position (index 2 has the largest logit).
        let logits = vec![-10.0, -5.0, 10.0, -8.0];
        let result = gumbel_softmax(&logits, 0.01);
        assert_eq!(result.len(), 4);

        // Index 2 (value 10.0) should dominate
        assert!(
            result[2] > 0.99,
            "expected ~1.0 at index 2 (largest logit), got {:?}",
            result
        );

        // Sum should be ~1.0
        let sum: f64 = result.iter().sum();
        assert!(
            (sum - 1.0).abs() < 1e-6,
            "expected sum ≈ 1.0, got {}",
            sum
        );
    }

    #[test]
    fn test_gumbel_softmax_high_temp_uniform() {
        // With high temperature, the output approaches uniform.
        let logits = vec![1.0, 2.0, 3.0, 4.0];
        let result = gumbel_softmax(&logits, 100.0);
        let n = result.len() as f64;
        for &v in &result {
            assert!(
                (v - 1.0 / n).abs() < 0.1,
                "expected ≈ 1/n = {} with high temp, got {}",
                1.0 / n,
                v
            );
        }
    }

    #[test]
    fn test_gumbel_softmax_empty() {
        let result = gumbel_softmax(&[], 1.0);
        assert!(result.is_empty());
    }

    // -----------------------------------------------------------------
    // sample_rotation
    // -----------------------------------------------------------------
    #[test]
    fn test_sample_rotation_argmax() {
        let logits = vec![-2.0, 5.0, -1.0, 3.0];
        let idx = sample_rotation(&logits);
        assert_eq!(idx, 1); // index 1 has logit 5.0
    }

    #[test]
    fn test_sample_rotation_empty() {
        let idx = sample_rotation(&[]);
        assert_eq!(idx, 0);
    }

    #[test]
    fn test_sample_rotation_tie() {
        // Ties resolve to first occurrence
        let logits = vec![3.0, 1.0, 3.0, 0.0];
        let idx = sample_rotation(&logits);
        assert_eq!(idx, 0);
    }

    // -----------------------------------------------------------------
    // sample_rotation_batch
    // -----------------------------------------------------------------
    #[test]
    fn test_sample_rotation_batch() {
        let batch = vec![
            vec![0.0, 10.0, 0.0, 0.0],
            vec![0.0, 0.0, 10.0, 0.0],
            vec![10.0, 0.0, 0.0, 0.0],
        ];
        let indices = sample_rotation_batch(&batch);
        assert_eq!(indices, vec![1, 2, 0]);
    }

    // -----------------------------------------------------------------
    // Constants
    // -----------------------------------------------------------------
    #[test]
    fn test_rotation_angles_constants() {
        assert!((ROTATION_ANGLES_RAD[0] - 0.0).abs() < 1e-15);
        assert!((ROTATION_ANGLES_RAD[1] - std::f64::consts::FRAC_PI_2).abs() < 1e-15);
        assert!((ROTATION_ANGLES_RAD[2] - std::f64::consts::PI).abs() < 1e-15);
        assert!((ROTATION_ANGLES_RAD[3] - 3.0 * std::f64::consts::FRAC_PI_2).abs() < 1e-15);

        assert!((ROTATION_ANGLES_DEG[0] - 0.0).abs() < 1e-15);
        assert!((ROTATION_ANGLES_DEG[1] - 90.0).abs() < 1e-15);
        assert!((ROTATION_ANGLES_DEG[2] - 180.0).abs() < 1e-15);
        assert!((ROTATION_ANGLES_DEG[3] - 270.0).abs() < 1e-15);
    }
}
