//! Small copied kernel from Temper's Rust DRC engine.
//!
//! Source: `packages/temper-drc-rs/src/validation_kernels.rs`,
//! `segments_intersect`; exact source hash is recorded in
//! `zapote/ports.toml`. It is copied rather than linked to the legacy package.

/// Sign-based orientation test copied from Temper's geometry kernel. The
/// RTD rule uses it against expanded rectangle edges, so segment crossings
/// are caught even when no trace vertex is inside the region.
#[allow(clippy::too_many_arguments)]
pub fn segments_intersect(
    a1x: f64,
    a1y: f64,
    a2x: f64,
    a2y: f64,
    b1x: f64,
    b1y: f64,
    b2x: f64,
    b2y: f64,
) -> bool {
    let orientation = |ax: f64, ay: f64, bx: f64, by: f64, cx: f64, cy: f64| {
        (bx - ax) * (cy - ay) - (by - ay) * (cx - ax)
    };
    let on_segment = |ax: f64, ay: f64, bx: f64, by: f64, px: f64, py: f64| {
        (ax.min(bx) - 1e-9 <= px && px <= ax.max(bx) + 1e-9)
            && (ay.min(by) - 1e-9 <= py && py <= ay.max(by) + 1e-9)
    };
    let o1 = orientation(a1x, a1y, a2x, a2y, b1x, b1y);
    let o2 = orientation(a1x, a1y, a2x, a2y, b2x, b2y);
    let o3 = orientation(b1x, b1y, b2x, b2y, a1x, a1y);
    let o4 = orientation(b1x, b1y, b2x, b2y, a2x, a2y);
    if ((o1 > 0.0) != (o2 > 0.0)) && ((o3 > 0.0) != (o4 > 0.0)) {
        return true;
    }
    let eps = 1e-9;
    (o1.abs() < eps && on_segment(a1x, a1y, a2x, a2y, b1x, b1y))
        || (o2.abs() < eps && on_segment(a1x, a1y, a2x, a2y, b2x, b2y))
        || (o3.abs() < eps && on_segment(b1x, b1y, b2x, b2y, a1x, a1y))
        || (o4.abs() < eps && on_segment(b1x, b1y, b2x, b2y, a2x, a2y))
}

#[cfg(test)]
mod tests {
    use super::segments_intersect;
    #[test]
    fn crossing_segments_are_intersecting() {
        assert!(segments_intersect(
            0.0, 0.0, 10.0, 10.0, 0.0, 10.0, 10.0, 0.0
        ));
    }
    #[test]
    fn separated_segments_are_not_intersecting() {
        assert!(!segments_intersect(
            0.0, 0.0, 10.0, 0.0, 0.0, 3.0, 10.0, 3.0
        ));
    }
}
