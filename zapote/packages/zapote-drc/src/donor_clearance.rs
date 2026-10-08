//! Shape-aware pad clearance kernel copied from Temper's pure Rust
//! `clearance_geometry` implementation.  This module deliberately has no
//! pyo3 or runtime dependency on Temper; it is a local donor for Zapote's
//! native DRC transport.  Donor source at canonical HEAD `e1df19698` had
//! SHA-256 `33ecab3dddbaa021fa4cbf74d7038120d327c6db7f6924a0e1b4f5a45c0948ed`.

// These are the donor kernel's stable internal codes, not pcbnew's raw
// `GetShape()` enum.  Use `raw_kicad_shape_to_donor_shape` at the transport
// boundary; raw 3/5/6 (trapezoid/chamfered/custom) are intentionally rejected.
const SHAPE_CIRCLE: i64 = 0;
const SHAPE_OVAL: i64 = 1;
const SHAPE_RECT: i64 = 2;
const SHAPE_ROUNDRECT: i64 = 3;
const SHAPE_THRU_HOLE: i64 = 4;

/// (width, height, donor shape code, centre x, centre y, clockwise rotation
/// in radians, roundrect radius ratio).
pub type PadSpec = (f64, f64, i64, f64, f64, f64, f64);

/// Translate pcbnew's raw `PAD_SHAPE` values to the donor's shape codes.
/// pcbnew uses 0=circle, 1=rect, 2=oval, 3=trapezoid, 4=roundrect,
/// 5=chamfered and 6=custom.  Unknown or unsupported shapes fail closed.
pub fn raw_kicad_shape_to_donor_shape(raw_shape: i64) -> Result<i64, String> {
    match raw_shape {
        0 => Ok(SHAPE_CIRCLE),
        1 => Ok(SHAPE_RECT),
        2 => Ok(SHAPE_OVAL),
        4 => Ok(SHAPE_ROUNDRECT),
        3 | 5 | 6 => Err(format!("unsupported pcbnew pad shape code {raw_shape}")),
        _ => Err(format!("unknown pcbnew pad shape code {raw_shape}")),
    }
}

fn math_cos_sin(value: f64) -> (f64, f64) {
    (value.cos(), value.sin())
}

fn corner_radius(width: f64, height: f64, shape: i64, ratio: f64) -> f64 {
    match shape {
        SHAPE_CIRCLE | SHAPE_THRU_HOLE => width.max(height) / 2.0,
        SHAPE_OVAL => width.min(height) / 2.0,
        SHAPE_ROUNDRECT => (ratio * width.min(height)).clamp(0.0, width.min(height) / 2.0),
        SHAPE_RECT => 0.0,
        _ => f64::NAN,
    }
}

fn core_half_extents(width: f64, height: f64, shape: i64, ratio: f64) -> (f64, f64) {
    let radius = corner_radius(width, height, shape, ratio);
    (
        (width / 2.0 - radius).max(0.0),
        (height / 2.0 - radius).max(0.0),
    )
}

/// Minkowski-summed with), resolved into world coordinates exactly as
/// Shapely's rotate+translate would.
enum Core {
    Point(f64, f64),
    Segment(f64, f64, f64, f64), // (x1, y1, x2, y2)
    Rect([[f64; 2]; 4]),         // 4 corners; ring closure is implicit
}

impl Core {
    /// The unique vertices that `ConnectedElementLocationFilter` would
    /// report (points, line endpoints, ring vertices).
    fn vertices(&self) -> Vec<[f64; 2]> {
        match self {
            Core::Point(x, y) => vec![[*x, *y]],
            Core::Segment(x1, y1, x2, y2) => vec![[*x1, *y1], [*x2, *y2]],
            Core::Rect(corners) => corners.to_vec(),
        }
    }
}

/// Shapely's effective rotation of a pad core: `math.degrees`, the
/// sanctioned R(-theta) sign flip, then shapely's own degrees->radians and
/// the `2.5e-16` cos/sin snap. Returns `(cosp, sinp)`.
///
/// The sign flip is `kicad_transform::shapely_rotation_angle_deg`, called
/// rather than typed: `shapely.affinity.rotate`'s `angle` is CCW-positive
/// (R(+theta)) and KiCad orients a pad's copper R(-theta), so the two are
/// negations of each other. Until 2026-08-18 this function omitted the
/// flip entirely -- mirroring every pad polygon at any angle that is not
/// a multiple of 90 degrees. See `pad_core_polygon`'s docstring on the
/// Python side, and `scripts/check_pad_core_polygon_oracle.py` for the
/// pcbnew ground truth that now pins it. `core_graph_geometry.rs::
/// courtyard_global_points` is the same shapely-replica shape and already
/// negated its angle; this is now consistent with it.
fn shapely_rotation_cos_sin(rotation_rad: f64) -> (f64, f64) {
    // Python chain, exact f64 order:
    //   deg  = math.degrees(rotation_rad)   = rotation_rad * (180.0 / PI)
    //   deg  = shapely_rotation_angle_deg(deg)  == -deg (IEEE negation)
    //   angle = deg * pi / 180.0             (shapely.affinity.rotate)
    // Preserve the donor's Python/Shapely degree round-trip and KiCad's
    // clockwise child transform, rather than substituting a direct trig call.
    let degrees = -(rotation_rad * (180.0 / std::f64::consts::PI));
    let angle = degrees * std::f64::consts::PI / 180.0;
    let (mut cosp, mut sinp) = math_cos_sin(angle);
    if cosp.abs() < 2.5e-16 {
        cosp = 0.0;
    }
    if sinp.abs() < 2.5e-16 {
        sinp = 0.0;
    }
    (cosp, sinp)
}

/// One corner of the core, rotated by shapely's affine (origin (0,0),
/// offsets 0.0) and translated by (cx, cy).
fn rotate_corner(x: f64, y: f64, cosp: f64, sinp: f64, cx: f64, cy: f64) -> [f64; 2] {
    // shapely: xp = (cosp*x + (-sinp)*y) + xoff; yp = (sinp*x + cosp*y) + yoff
    // (xoff == yoff == 0.0 for origin (0,0)), then translate:
    // x'' = (1.0*xp + 0.0*yp) + cx == xp + cx.
    let xp = (cosp * x + (-sinp) * y) + 0.0;
    let yp = (sinp * x + cosp * y) + 0.0;
    [xp + cx, yp + cy]
}

/// Build the core (same branches and order as `pad_core_polygon`).
fn pad_core(
    width: f64,
    height: f64,
    shape: i64,
    cx: f64,
    cy: f64,
    rotation_rad: f64,
    ratio: f64,
) -> Core {
    let (hw, hh) = core_half_extents(width, height, shape, ratio);
    let (cosp, sinp) = shapely_rotation_cos_sin(rotation_rad);
    if hw <= 0.0 && hh <= 0.0 {
        let [x, y] = rotate_corner(0.0, 0.0, cosp, sinp, cx, cy);
        Core::Point(x, y)
    } else if hh <= 0.0 {
        let [x1, y1] = rotate_corner(-hw, 0.0, cosp, sinp, cx, cy);
        let [x2, y2] = rotate_corner(hw, 0.0, cosp, sinp, cx, cy);
        Core::Segment(x1, y1, x2, y2)
    } else if hw <= 0.0 {
        let [x1, y1] = rotate_corner(0.0, -hh, cosp, sinp, cx, cy);
        let [x2, y2] = rotate_corner(0.0, hh, cosp, sinp, cx, cy);
        Core::Segment(x1, y1, x2, y2)
    } else {
        Core::Rect([
            rotate_corner(-hw, -hh, cosp, sinp, cx, cy),
            rotate_corner(hw, -hh, cosp, sinp, cx, cy),
            rotate_corner(hw, hh, cosp, sinp, cx, cy),
            rotate_corner(-hw, hh, cosp, sinp, cx, cy),
        ])
    }
}

// ---------------------------------------------------------------------------
// GEOS DistanceOp replica (bit-exact vs Shapely/GEOS 3.13.1 `.distance()`)
// ---------------------------------------------------------------------------

/// GEOS `CoordinateXY::distance`: `sqrt(dx*dx + dy*dy)` — NOT hypot.
fn pt_dist(ax: f64, ay: f64, bx: f64, by: f64) -> f64 {
    let dx = ax - bx;
    let dy = ay - by;
    (dx * dx + dy * dy).sqrt()
}

/// GEOS `Distance::pointToSegment`, exact operation order.
fn pt_seg_dist(px: f64, py: f64, ax: f64, ay: f64, bx: f64, by: f64) -> f64 {
    if ax == bx && ay == by {
        // GEOS `A == B` is `equals2D` — bit equality of both ordinates.
        return pt_dist(px, py, ax, ay);
    }
    let r = ((px - ax) * (bx - ax) + (py - ay) * (by - ay))
        / ((bx - ax) * (bx - ax) + (by - ay) * (by - ay));
    if r <= 0.0 {
        return pt_dist(px, py, ax, ay);
    }
    if r >= 1.0 {
        return pt_dist(px, py, bx, by);
    }
    let s = ((ay - py) * (bx - ax) - (ax - px) * (by - ay))
        / ((bx - ax) * (bx - ax) + (by - ay) * (by - ay));
    s.abs() * ((bx - ax) * (bx - ax) + (by - ay) * (by - ay)).sqrt()
}

/// GEOS `Envelope::intersects(p1, p2, q1, q2)` (segment envelopes, touching
/// counts as intersecting).
#[expect(
    clippy::too_many_arguments,
    reason = "GEOS port mirrors Envelope::intersects' 4-point signature 1:1; a config struct would change the ported shape"
)]
fn env_intersects(ax: f64, ay: f64, bx: f64, by: f64, cx: f64, cy: f64, dx: f64, dy: f64) -> bool {
    let minp = ax.min(bx);
    let maxp = ax.max(bx);
    let minq = cx.min(dx);
    let maxq = cx.max(dx);
    if minp > maxq || maxp < minq {
        return false;
    }
    let minp = ay.min(by);
    let maxp = ay.max(by);
    let minq = cy.min(dy);
    let maxq = cy.max(dy);
    !(minp > maxq || maxp < minq)
}

/// GEOS `Distance::segmentToSegment`, exact operation order (envelope
/// pre-check, `denom == 0`, strict r/s comparisons, nested min chain).
#[expect(
    clippy::too_many_arguments,
    reason = "GEOS port mirrors Distance::segmentToSegment's 4-point signature 1:1; a config struct would change the ported shape"
)]
fn seg_seg_dist(ax: f64, ay: f64, bx: f64, by: f64, cx: f64, cy: f64, dx: f64, dy: f64) -> f64 {
    if ax == bx && ay == by {
        return pt_seg_dist(ax, ay, cx, cy, dx, dy);
    }
    if cx == dx && cy == dy {
        return pt_seg_dist(dx, dy, ax, ay, bx, by);
    }
    let no_intersection = if !env_intersects(ax, ay, bx, by, cx, cy, dx, dy) {
        true
    } else {
        let denom = (bx - ax) * (dy - cy) - (by - ay) * (dx - cx);
        if denom == 0.0 {
            true
        } else {
            let r_num = (ay - cy) * (dx - cx) - (ax - cx) * (dy - cy);
            let s_num = (ay - cy) * (bx - ax) - (ax - cx) * (by - ay);
            let s = s_num / denom;
            let r = r_num / denom;
            // NaN-sensitive: for NaN r/s, `r < 0.0 || r > 1.0` is false but
            // `!RangeInclusive::contains` would be true — GEOS uses the
            // former, so keep the explicit comparisons.
            #[expect(
                clippy::manual_range_contains,
                reason = "NaN-sensitive GEOS port; RangeInclusive::contains treats NaN as outside, changing behavior"
            )]
            let no_overlap = r < 0.0 || r > 1.0 || s < 0.0 || s > 1.0;
            no_overlap
        }
    };
    if no_intersection {
        // GEOS: std::min(pt(A,CD), std::min(pt(B,CD), std::min(pt(C,AB),
        // pt(D,AB)))) — the nested order is preserved (only matters for
        // exact ties, where either pick yields the same value).
        let d1 = pt_seg_dist(ax, ay, cx, cy, dx, dy);
        let d2 = pt_seg_dist(bx, by, cx, cy, dx, dy);
        let d3 = pt_seg_dist(cx, cy, ax, ay, bx, by);
        let d4 = pt_seg_dist(dx, dy, ax, ay, bx, by);
        d1.min(d2.min(d3.min(d4)))
    } else {
        0.0
    }
}

/// Is `p` exactly on segment `a`-`b` (f64 orientation == 0 and within the
/// segment envelope)? This is the `RayCrossingCounter::isOnSegment` case
/// of GEOS's `PointLocation::locate`, evaluated in plain f64 (see module
/// docstring for when the robust predicate could differ).
fn point_on_segment(px: f64, py: f64, ax: f64, ay: f64, bx: f64, by: f64) -> bool {
    let det = (bx - ax) * (py - ay) - (by - ay) * (px - ax);
    if det != 0.0 {
        return false;
    }
    (ax.min(bx) <= px && px <= ax.max(bx)) && (ay.min(by) <= py && py <= ay.max(by))
}

/// `PointLocation::locate(p, ring)` replica for a rect (no holes): the
/// f64 ray-cast with the same crossing decision as GEOS's
/// `RayCrossingCounter`. `ring` is the closed 5-coordinate loop.
fn locate_in_rect(px: f64, py: f64, ring: &[[f64; 2]; 5]) -> u8 {
    // 0 = EXTERIOR, 1 = INTERIOR, 2 = BOUNDARY (GEOS Location).
    for seg in ring.windows(2) {
        let a = seg[0];
        let b = seg[1];
        if point_on_segment(px, py, a[0], a[1], b[0], b[1]) {
            return 2; // BOUNDARY
        }
    }
    let mut inside = false;
    for seg in ring.windows(2) {
        let (x1, y1) = (seg[0][0], seg[0][1]);
        let (x2, y2) = (seg[1][0], seg[1][1]);
        if (y1 > py) != (y2 > py) {
            // sign of orientation(p1, p2, p), matching RayCrossingCounter's
            // crossing decision
            let det = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1);
            if (y2 > y1) == (det > 0.0) {
                inside = !inside;
            }
        }
    }
    if inside {
        1
    } else {
        0
    }
}

/// Rect ring as a closed 5-coordinate loop (GEOS iterates `npts - 1`
/// segments of the closed ring, i.e. `(0,1),(1,2),(2,3),(3,4)`).
fn rect_ring(rect: &Core) -> [[f64; 2]; 5] {
    match rect {
        Core::Rect(corners) => [
            corners[0], corners[1], corners[2], corners[3], corners[0], // closing coordinate
        ],
        _ => unreachable!("rect_ring called on a non-rect core"),
    }
}

/// The DistanceOp facet distance between two cores (min over the same
/// segment/point candidate set GEOS enumerates; the min value is
/// independent of enumeration order — see module docstring).
fn facet_distance(a: &Core, b: &Core) -> f64 {
    match (a, b) {
        (Core::Rect(_ra), Core::Rect(_rb)) => {
            let ring_a = rect_ring(a);
            let ring_b = rect_ring(b);
            let mut best = f64::INFINITY;
            for seg_a in ring_a.windows(2) {
                for seg_b in ring_b.windows(2) {
                    let d = seg_seg_dist(
                        seg_a[0][0],
                        seg_a[0][1],
                        seg_a[1][0],
                        seg_a[1][1],
                        seg_b[0][0],
                        seg_b[0][1],
                        seg_b[1][0],
                        seg_b[1][1],
                    );
                    if d < best {
                        best = d;
                    }
                }
            }
            best
        }
        (Core::Rect(_), Core::Segment(x1, y1, x2, y2)) => {
            let ring = rect_ring(a);
            let mut best = f64::INFINITY;
            for seg in ring.windows(2) {
                let d = seg_seg_dist(
                    seg[0][0], seg[0][1], seg[1][0], seg[1][1], *x1, *y1, *x2, *y2,
                );
                if d < best {
                    best = d;
                }
            }
            best
        }
        (Core::Segment(_x1, _y1, _x2, _y2), Core::Rect(_)) => facet_distance(b, a),
        (Core::Segment(x1, y1, x2, y2), Core::Segment(x3, y3, x4, y4)) => {
            seg_seg_dist(*x1, *y1, *x2, *y2, *x3, *y3, *x4, *y4)
        }
        (Core::Point(x1, y1), Core::Point(x2, y2)) => pt_dist(*x1, *y1, *x2, *y2),
        (Core::Point(x, y), Core::Segment(x1, y1, x2, y2)) => {
            pt_seg_dist(*x, *y, *x1, *y1, *x2, *y2)
        }
        (Core::Segment(x1, y1, x2, y2), Core::Point(x, y)) => {
            pt_seg_dist(*x, *y, *x1, *y1, *x2, *y2)
        }
        (Core::Point(x, y), Core::Rect(_)) => {
            let ring = rect_ring(b);
            let mut best = f64::INFINITY;
            for seg in ring.windows(2) {
                let d = pt_seg_dist(*x, *y, seg[0][0], seg[0][1], seg[1][0], seg[1][1]);
                if d < best {
                    best = d;
                }
            }
            best
        }
        (Core::Rect(_), Core::Point(_x, _y)) => facet_distance(b, a),
    }
}

/// `DistanceOp::distance` replica: containment first (any vertex of one
/// core inside-or-on the other's rect -> 0.0), then the facet distance.
fn core_distance(a: &Core, b: &Core) -> f64 {
    if let Core::Rect(_) = b {
        for v in a.vertices() {
            if locate_in_rect(v[0], v[1], &rect_ring(b)) != 0 {
                return 0.0; // INTERIOR or BOUNDARY -> GEOS reports 0.0
            }
        }
    }
    if let Core::Rect(_) = a {
        for v in b.vertices() {
            if locate_in_rect(v[0], v[1], &rect_ring(a)) != 0 {
                return 0.0;
            }
        }
    }
    facet_distance(a, b)
}

/// `pad_pair_distance`, exact operation order:
/// `max(gap - ra - rb, 0.0)` with the radii subtracted in pad order.
fn pad_pair_distance_spec(a: &PadSpec, b: &PadSpec) -> f64 {
    let (wa, ha, sa, cxa, cya, rota, rra) = a;
    let (wb, hb, sb, cxb, cyb, rotb, rrb) = b;
    let core_a = pad_core(*wa, *ha, *sa, *cxa, *cya, *rota, *rra);
    let core_b = pad_core(*wb, *hb, *sb, *cxb, *cyb, *rotb, *rrb);
    let gap = core_distance(&core_a, &core_b);
    let ra = corner_radius(*wa, *ha, *sa, *rra);
    let rb = corner_radius(*wb, *hb, *sb, *rrb);
    (gap - ra - rb).max(0.0)
}

/// Pure-Rust shape-aware distance between two pads.
pub fn pad_pair_distance(a: PadSpec, b: PadSpec) -> f64 {
    let Ok(a) = validate_pad_spec(a) else {
        return 0.0;
    };
    let Ok(b) = validate_pad_spec(b) else {
        return 0.0;
    };
    pad_pair_distance_spec(&a, &b)
}

/// Exact copper distance from one shape-aware pad to a capsule.
///
/// A routed segment is its centreline Minkowski-summed with a disk whose
/// radius is half the copper width. A via is the degenerate case where both
/// centreline endpoints are equal and the width is the via diameter.
fn pad_to_capsule_distance_spec(
    pad: &PadSpec,
    p0: (f64, f64),
    p1: (f64, f64),
    width: f64,
) -> Result<f64, String> {
    if !width.is_finite() || width <= 0.0 {
        return Err("capsule width must be finite and positive".into());
    }
    for value in [p0.0, p0.1, p1.0, p1.1] {
        if !value.is_finite() {
            return Err("capsule endpoints must be finite".into());
        }
    }
    let (pad_width, pad_height, shape, cx, cy, rotation_rad, roundrect_ratio) = pad;
    let pad_core = pad_core(
        *pad_width,
        *pad_height,
        *shape,
        *cx,
        *cy,
        *rotation_rad,
        *roundrect_ratio,
    );
    let capsule_core = Core::Segment(p0.0, p0.1, p1.0, p1.1);
    let gap = core_distance(&pad_core, &capsule_core);
    let pad_radius = corner_radius(*pad_width, *pad_height, *shape, *roundrect_ratio);
    Ok((gap - pad_radius - width / 2.0).max(0.0))
}

/// Pure-Rust shape-aware distance between a pad and a routed copper capsule.
pub fn pad_to_capsule_distance(
    pad: PadSpec,
    p0: (f64, f64),
    p1: (f64, f64),
    width: f64,
) -> Result<f64, String> {
    let pad = validate_pad_spec(pad)?;
    pad_to_capsule_distance_spec(&pad, p0, p1, width)
}

/// Validate a wire pad specification before passing it to the geometry kernel.
/// Unknown KiCad shape codes are rejected so callers cannot silently treat a
/// new shape as a rectangle and under-report clearance.
pub fn validate_pad_spec(spec: PadSpec) -> Result<PadSpec, String> {
    let (w, h, shape, x, y, rotation, ratio) = spec;
    if ![w, h, x, y, rotation, ratio].iter().all(|v| v.is_finite())
        || w <= 0.0
        || h <= 0.0
        || !(0.0..=0.5).contains(&ratio)
    {
        return Err("pad specification has invalid finite dimensions".into());
    }
    if !matches!(
        shape,
        SHAPE_CIRCLE | SHAPE_OVAL | SHAPE_RECT | SHAPE_ROUNDRECT | SHAPE_THRU_HOLE
    ) {
        return Err(format!("unsupported KiCad pad shape code {shape}"));
    }
    Ok(spec)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn shape_aware_pad_to_capsule_uses_rectangular_corners() {
        let pad = (4.0, 1.0, SHAPE_RECT, 0.0, 0.0, 0.0, 0.0);
        let distance =
            pad_to_capsule_distance(pad, (2.4, 0.9), (3.4, 0.9), 0.2).expect("valid capsule");
        assert!(
            distance > 0.0,
            "corner clearance must not use a circumscribed circle"
        );
    }

    #[test]
    fn unsupported_shape_is_rejected_fail_closed() {
        assert!(validate_pad_spec((1.0, 1.0, 77, 0.0, 0.0, 0.0, 0.0)).is_err());
    }

    #[test]
    fn raw_pcbnew_shape_codes_are_explicitly_mapped() {
        assert_eq!(raw_kicad_shape_to_donor_shape(0), Ok(SHAPE_CIRCLE));
        assert_eq!(raw_kicad_shape_to_donor_shape(1), Ok(SHAPE_RECT));
        assert_eq!(raw_kicad_shape_to_donor_shape(2), Ok(SHAPE_OVAL));
        assert_eq!(raw_kicad_shape_to_donor_shape(4), Ok(SHAPE_ROUNDRECT));
        assert!(raw_kicad_shape_to_donor_shape(3).is_err());
        assert!(raw_kicad_shape_to_donor_shape(5).is_err());
        assert!(raw_kicad_shape_to_donor_shape(6).is_err());
    }

    #[test]
    fn oval_and_through_hole_shapes_are_supported() {
        assert!(validate_pad_spec((2.0, 1.0, SHAPE_OVAL, 0.0, 0.0, 0.0, 0.0)).is_ok());
        assert!(validate_pad_spec((1.0, 1.0, SHAPE_THRU_HOLE, 0.0, 0.0, 0.0, 0.0)).is_ok());
    }

    #[test]
    fn mapped_roundrect_uses_its_radius_ratio() {
        let raw = raw_kicad_shape_to_donor_shape(4).expect("pcbnew roundrect");
        let roundrect = (4.0, 2.0, raw, 0.0, 0.0, 0.0, 0.25);
        let rectangle = (4.0, 2.0, SHAPE_RECT, 0.0, 0.0, 0.0, 0.0);
        assert!(pad_pair_distance(roundrect, (1.0, 1.0, SHAPE_CIRCLE, 4.0, 0.0, 0.0, 0.0)) > 0.0);
        assert!(validate_pad_spec(roundrect).is_ok());
        assert!(pad_pair_distance(roundrect, rectangle) >= 0.0);
    }
}
