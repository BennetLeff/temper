// Clearance-geometry core (Wave 3, REQ-SAFE-01 slice) — the pure geometry
// compute behind the clearance/creepage validator, migrated to Rust.
//
// Python references (pre-migration, pinned as oracles by the differential
// suite `packages/temper-placer/tests/requirements/
// test_clearance_rust_differential.py`):
//   - temper_placer/requirements/validators/_copper.py
//     (`_rotate` / `_component_pads` / `_CopperModel`: reach, lower_bound,
//     the copper_distance pair scan with its hypot centre-gap pruning)
//   - temper_placer/core/pad_geometry.py (`pad_pair_distance` and its core
//     polygon construction, which used Shapely/GEOS for the gap)
//
// The domain-classification / pairing logic (`clearance.py`'s
// `_nets_domain_map` / `_components_in_domain` / `_domain_boundary_pairs`
// and `_copper.py`'s `pads_in_domain` / `domain_restricted`) STAYS Python:
// this module is the geometry only.
//
// # Bit-exactness: what the Rust must reproduce, and how (all measured)
//
// ## GEOS's distance is `sqrt(dx*dx + dy*dy)`, NOT hypot
// The pre-migration `pad_pair_distance` computed `core_a.distance(core_b)`
// with Shapely/GEOS 3.13. `CoordinateXY::distance` (include/geos/geom/
// Coordinate.h) is `std::sqrt(dx*dx + dy*dy)` — a plain sqrt of the
// squared deltas, not `hypot`. Replicating it with CPython's `math.hypot`
// (Dekker vector_norm) or libm `hypot` fails by 1 ulp on ~12% of random
// pairs (measured). This crate's `py_hypot` (CPython vector_norm) is only
// for the _copper-side_ `math.hypot` call sites (reach, centre-gap
// pruning), where CPython's own `math.hypot` — not GEOS — is the oracle.
//
// ## The point-to-segment / segment-to-segment formulas
// `Distance::pointToSegment` (geos src/algorithm/Distance.cpp): the r
// clamp (strict `<= 0.0` / `>= 1.0`), then the perpendicular branch
// `fabs(s) * sqrt(len2)` with the cross-product s. `segmentToSegment`
// replicates the envelope pre-check, the `denom == 0` branch, the strict
// `(r<0)||(r>1)||(s<0)||(s>1)` intersection test, and the nested
// `std::min` chain of the four point-to-segment distances.
//
// ## Shapely's rotate/translate are NOT the naive trig rotation
// `pad_core_polygon` calls `shapely.affinity.rotate(core,
// math.degrees(rotation_rad), origin=(0,0), use_radians=False)`:
//   1. `math.degrees(x)` = `x * (180.0 / PI)` (CPython);
//   2. shapely converts BACK itself: `angle = angle_deg * pi / 180.0`
//      (affinity.py imports `pi` from math) — so the effective rotation
//      angle is the round-tripped `(rad * 180/pi) * pi/180`, NOT `rad`;
//   3. `cosp/sinp` are snapped to exactly 0.0 when `abs() < 2.5e-16`;
//   4. the affine is `xp = (cosp*x + (-sinp)*y) + xoff` with the origin
//      offsets (0 - 0*cosp + 0*sinp) == 0.0, then translate applies
//      `1.0*xp + 0.0*yp + cx` == `xp + cx` (the sign-of-zero corner cases
//      never reach a value-bearing result).
// `cos`/`sin` are resolved via `dlsym` so the crate matches the host
// Python runtime's own libm (the uv standalone build's sin differs from
// the statically-bound `f64::sin` by 1 ulp on real inputs — measured in
// the Wave 2 slice and again here).
//
// ## Containment (DistanceOp::computeContainmentDistance)
// A vertex of one core inside-or-on the other core's polygon (rect) is an
// immediate 0.0 gap: `PointLocation::locate` != EXTERIOR. The replica
// uses an f64 ray-cast plus an exact-on-segment test (f64 cross product
// == 0.0 within the segment envelope). Random and exact-arithmetic
// boundary cases agree bit-for-bit with GEOS's robust predicate; inputs
// within ~16 ulp of a collinear decision can in principle diverge (GEOS
// falls back to double-double orientation), which is why the differential
// suite's crafted edge cases use exactly-representable coordinates.
//
// ## The `gap - ra - rb` asymmetry is ORACLE behaviour, not a bug
// `dist(A, B)` subtracts the corner radii in pad order:
// `(gap - ra(A)) - rb(B)` vs `(gap - ra(B)) - rb(A)` differ by 1 ulp in
// general. The pre-migration implementation has the same asymmetry; it is
// preserved here, not "fixed".

use pyo3::prelude::*;
use temper_py_bridge;

use crate::pad_geometry::{bounding_radius, core_half_extents, corner_radius, math_cos_sin, py_hypot};

/// A pad as consumed by this module:
/// (width, height, shape, cx, cy, rotation_rad, roundrect_ratio) — the
/// same tuple `_CopperModel._spec` and `pad_pair_distance` use.
type PadSpec = (f64, f64, String, f64, f64, f64, f64);

// ---------------------------------------------------------------------------
// Pad-core construction (bit-exact replica of pad_core_polygon's geometry)
// ---------------------------------------------------------------------------

/// One pad's "core" (the rectangle/segment/point the corner disk is
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

/// Shapely's effective rotation of a pad core: `math.degrees` then
/// shapely's own degrees->radians, then the `2.5e-16` cos/sin snap.
/// Returns `(cosp, sinp)`.
fn shapely_rotation_cos_sin(rotation_rad: f64) -> (f64, f64) {
    // Python chain, exact f64 order:
    //   deg  = math.degrees(rotation_rad)   = rotation_rad * (180.0 / PI)
    //   angle = deg * pi / 180.0             (shapely.affinity.rotate)
    let deg = rotation_rad * (180.0 / std::f64::consts::PI);
    let angle = deg * std::f64::consts::PI / 180.0;
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
fn pad_core(width: f64, height: f64, shape: &str, cx: f64, cy: f64, rotation_rad: f64, ratio: f64) -> Core {
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
            r < 0.0 || r > 1.0 || s < 0.0 || s > 1.0
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
    for i in 0..4 {
        let a = ring[i];
        let b = ring[i + 1];
        if point_on_segment(px, py, a[0], a[1], b[0], b[1]) {
            return 2; // BOUNDARY
        }
    }
    let mut inside = false;
    for i in 0..4 {
        let (x1, y1) = (ring[i][0], ring[i][1]);
        let (x2, y2) = (ring[i + 1][0], ring[i + 1][1]);
        if (y1 > py) != (y2 > py) {
            // sign of orientation(p1, p2, p), matching RayCrossingCounter's
            // crossing decision
            let det = (x2 - x1) * (py - y1) - (y2 - y1) * (px - x1);
            if (y2 > y1) == (det > 0.0) {
                inside = !inside;
            }
        }
    }
    if inside { 1 } else { 0 }
}

/// Rect ring as a closed 5-coordinate loop (GEOS iterates `npts - 1`
/// segments of the closed ring, i.e. `(0,1),(1,2),(2,3),(3,4)`).
fn rect_ring(rect: &Core) -> [[f64; 2]; 5] {
    match rect {
        Core::Rect(corners) => [
            corners[0],
            corners[1],
            corners[2],
            corners[3],
            corners[0], // closing coordinate
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
            for i in 0..4 {
                for j in 0..4 {
                    let d = seg_seg_dist(
                        ring_a[i][0], ring_a[i][1], ring_a[i + 1][0], ring_a[i + 1][1],
                        ring_b[j][0], ring_b[j][1], ring_b[j + 1][0], ring_b[j + 1][1],
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
            for i in 0..4 {
                let d = seg_seg_dist(
                    ring[i][0], ring[i][1], ring[i + 1][0], ring[i + 1][1],
                    *x1, *y1, *x2, *y2,
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
        (Core::Point(x, y), Core::Segment(x1, y1, x2, y2)) => pt_seg_dist(*x, *y, *x1, *y1, *x2, *y2),
        (Core::Segment(x1, y1, x2, y2), Core::Point(x, y)) => pt_seg_dist(*x, *y, *x1, *y1, *x2, *y2),
        (Core::Point(x, y), Core::Rect(_)) => {
            let ring = rect_ring(b);
            let mut best = f64::INFINITY;
            for i in 0..4 {
                let d = pt_seg_dist(*x, *y, ring[i][0], ring[i][1], ring[i + 1][0], ring[i + 1][1]);
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
    let core_a = pad_core(*wa, *ha, sa, *cxa, *cya, *rota, *rra);
    let core_b = pad_core(*wb, *hb, sb, *cxb, *cyb, *rotb, *rrb);
    let gap = core_distance(&core_a, &core_b);
    let ra = corner_radius(*wa, *ha, sa, *rra);
    let rb = corner_radius(*wb, *hb, sb, *rrb);
    (gap - ra - rb).max(0.0)
}

// ---------------------------------------------------------------------------
// The copper pair scan (the `_CopperModel.copper_distance` inner loop)
// ---------------------------------------------------------------------------

/// The full pair scan with the hypot centre-gap pruning, bit-exact vs the
/// pre-migration Python: for each `pa` (outer) / `pb` (inner), skip the
/// self-pair when the two pads are the SAME object (Python `pa is pb` —
/// encoded as equal `ids_a[i] == ids_b[j]`, where each id is Python's
/// `id(pad)`, so shared objects between a `matching` sublist and the
/// stored full list are caught too), compute the centre-gap lower bound
/// with CPython `math.hypot`, prune with `>= best`, then the exact pad-pair
/// distance, keeping the first winner on ties (`d < best`).
/// Returns `(best, Some((i, j)))` or `(inf, None)`.
fn copper_scan(
    pads_a: &[PadSpec],
    pads_b: &[PadSpec],
    ids_a: &[i64],
    ids_b: &[i64],
) -> (f64, Option<(usize, usize)>) {
    let mut best = f64::INFINITY;
    let mut best_pair: Option<(usize, usize)> = None;
    for (i, pa) in pads_a.iter().enumerate() {
        let (wa, ha, sa, cxa, cya, _, rra) = pa;
        let ra = bounding_radius(*wa, *ha, sa, *rra);
        for (j, pb) in pads_b.iter().enumerate() {
            if ids_a[i] == ids_b[j] {
                continue; // a pad has no clearance to itself (Python `pa is pb`)
            }
            let (wb, hb, sb, cxb, cyb, _, rrb) = pb;
            let rb = bounding_radius(*wb, *hb, sb, *rrb);
            let centre_gap = py_hypot(cxa - cxb, cya - cyb) - ra - rb;
            if centre_gap >= best {
                continue; // provably cannot beat the incumbent (d >= centre_gap)
            }
            let d = pad_pair_distance_spec(pa, pb);
            if d < best {
                best = d;
                best_pair = Some((i, j));
            }
        }
    }
    (best, best_pair)
}

// ---------------------------------------------------------------------------
// PyO3 bridge
// ---------------------------------------------------------------------------

/// KiCad R(-theta) footprint-child rotation (the formula behind
/// `kicad_transform.rotate_local_to_world`, resolved with the host
/// Python's own libm cos/sin so the result is bit-identical to the
/// pure-Python `math.cos`/`math.sin` version).
fn rotate_local_to_world(x: f64, y: f64, theta_rad: f64) -> (f64, f64) {
    let (c, s) = math_cos_sin(theta_rad);
    (x * c + y * s, -x * s + y * c)
}

#[pyfunction]
pub fn rotate_local_to_world_py(x: f64, y: f64, theta_rad: f64) -> PyResult<(f64, f64)> {
    temper_py_bridge::catch_unwind(|| rotate_local_to_world(x, y, theta_rad))
        .map_err(temper_py_bridge::panic_to_err)
}

/// CPython `math.dist` (Dekker vector_norm) between two points — the
/// origin-to-origin distance used by `lower_bound` and the no-pad-geometry
/// fallbacks.
#[pyfunction]
pub fn origin_distance_py(ax: f64, ay: f64, bx: f64, by: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| py_hypot(ax - bx, ay - by)).map_err(temper_py_bridge::panic_to_err)
}

/// A component's reach: `max(hypot(cx - ox, cy - oy) + bounding_radius)`
/// over its pads (CPython `math.hypot` on the centre offset, plus the
/// Rust bounding radius). Returns 0.0 for an empty pad list (the Python
/// caller only invokes it for components with pads).
#[pyfunction]
pub fn component_reach_py(pads: Vec<PadSpec>, ox: f64, oy: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        let mut best = 0.0f64;
        for (w, h, shape, cx, cy, _, rr) in &pads {
            // reach = hypot + bounding_radius >= 0 always, so the 0.0 seed
            // is only a stand-in for Python's `max` over a non-empty list.
            let reach = py_hypot(cx - ox, cy - oy) + bounding_radius(*w, *h, shape, *rr);
            if reach > best {
                best = reach;
            }
        }
        best
    })
    .map_err(temper_py_bridge::panic_to_err)
}

/// `pad_geometry.pad_pair_distance`, exact and bit-identical to the
/// pre-migration Shapely/GEOS implementation (see module docstring).
#[pyfunction]
pub fn pad_pair_distance_py(pad_a: PadSpec, pad_b: PadSpec) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| pad_pair_distance_spec(&pad_a, &pad_b))
        .map_err(temper_py_bridge::panic_to_err)
}

/// The `_CopperModel.copper_distance` pair scan (see `copper_scan`).
/// `ids_a`/`ids_b` must be ``[id(p) for p in pads_a]`` /
/// ``[id(p) for p in pads_b]`` from Python — equal ids reproduce the
/// `pa is pb` identity skip exactly, including shared objects between a
/// domain-filtered sublist and the component's stored full pad list.
#[pyfunction]
#[pyo3(signature = (pads_a, pads_b, ids_a, ids_b))]
pub fn copper_scan_py(
    pads_a: Vec<PadSpec>,
    pads_b: Vec<PadSpec>,
    ids_a: Vec<i64>,
    ids_b: Vec<i64>,
) -> PyResult<(f64, Option<(usize, usize)>)> {
    temper_py_bridge::catch_unwind(|| copper_scan(&pads_a, &pads_b, &ids_a, &ids_b))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn test_rotate_local_to_world_matches_manual() {
        // R(-theta): (x*c + y*s, -x*s + y*c); 90deg -> (y, -x)
        let (rx, ry) = rotate_local_to_world(1.0, 0.0, std::f64::consts::FRAC_PI_2);
        assert!((rx - 0.0).abs() < 1e-12);
        assert!((ry - (-1.0)).abs() < 1e-12);
    }

    #[test]
    fn test_zero_rotation_is_identity() {
        let (rx, ry) = rotate_local_to_world(3.0, -2.0, 0.0);
        assert_eq!((rx, ry), (3.0, -2.0));
    }

    #[test]
    fn test_corner_radius_agrees_with_shared_model() {
        let r = corner_radius(4.0, 2.0, "roundrect", 0.25);
        assert_eq!(r, 0.5);
        let r = corner_radius(4.0, 2.0, "oval", 0.25);
        assert_eq!(r, 1.0);
    }

    #[test]
    fn test_pad_pair_distance_zero_when_identical() {
        // identical rects at the same position -> gap 0, radii 0 -> 0.0
        let pad: PadSpec = (2.0, 2.0, "rect".to_string(), 0.0, 0.0, 0.0, 0.0);
        assert_eq!(pad_pair_distance_spec(&pad, &pad), 0.0);
    }

    #[test]
    fn test_pad_pair_distance_rect_gap() {
        // two 2x2 rects 5 apart centre-to-centre, axis aligned: gap 3.0
        let a: PadSpec = (2.0, 2.0, "rect".to_string(), 0.0, 0.0, 0.0, 0.0);
        let b: PadSpec = (2.0, 2.0, "rect".to_string(), 5.0, 0.0, 0.0, 0.0);
        assert!((pad_pair_distance_spec(&a, &b) - 3.0).abs() < 1e-12);
    }

    #[test]
    fn test_circle_pad_distance() {
        // two 2x2 circle pads 5 apart: gap 3.0, radii 1+1 -> 3.0
        let a: PadSpec = (2.0, 2.0, "circle".to_string(), 0.0, 0.0, 0.0, 0.0);
        let b: PadSpec = (2.0, 2.0, "circle".to_string(), 5.0, 0.0, 0.0, 0.0);
        assert!((pad_pair_distance_spec(&a, &b) - 3.0).abs() < 1e-12);
    }

    #[test]
    fn test_containment_zero() {
        // small rect fully inside a big rect -> 0.0
        let big: PadSpec = (10.0, 10.0, "rect".to_string(), 0.0, 0.0, 0.0, 0.0);
        let small: PadSpec = (2.0, 2.0, "rect".to_string(), 0.0, 0.0, 0.0, 0.0);
        assert_eq!(pad_pair_distance_spec(&big, &small), 0.0);
        assert_eq!(pad_pair_distance_spec(&small, &big), 0.0);
    }

    #[test]
    fn test_scan_returns_closest_pair() {
        let a: PadSpec = (2.0, 2.0, "rect".to_string(), 0.0, 0.0, 0.0, 0.0);
        let b: PadSpec = (2.0, 2.0, "rect".to_string(), 5.0, 0.0, 0.0, 0.0);
        let c: PadSpec = (2.0, 2.0, "rect".to_string(), 20.0, 0.0, 0.0, 0.0);
        let (best, pair) = copper_scan(&[a.clone(), c], &[b.clone()], &[1, 2], &[3]);
        assert_eq!(pair, Some((0, 0)));
        assert!((best - 3.0).abs() < 1e-12);
    }

    #[test]
    fn test_scan_skips_self_pair_on_shared_object() {
        // The Python `pa is pb` skip: equal object ids (e.g. a domain-
        // filtered sublist vs the stored full list sharing the same pad)
        // must not pair a pad with itself.
        let a: PadSpec = (2.0, 2.0, "rect".to_string(), 0.0, 0.0, 0.0, 0.0);
        let (best, pair) = copper_scan(&[a.clone()], &[a.clone()], &[42], &[42]);
        assert!(best.is_infinite());
        assert_eq!(pair, None);
        // ... distinct ids (two different pad objects) pair normally -> 0.0
        let (best, pair) = copper_scan(&[a.clone()], &[a], &[42], &[43]);
        assert_eq!(best, 0.0);
        assert_eq!(pair, Some((0, 0)));
    }

    #[test]
    fn test_scan_skips_shared_object_in_sublist() {
        // matching = [pad0, pad2] vs stored = [pad0, pad1, pad2]: the
        // (0, 0) and (1, 2) pairs share objects and must be skipped.
        let p0: PadSpec = (2.0, 2.0, "rect".to_string(), 0.0, 0.0, 0.0, 0.0);
        let p1: PadSpec = (2.0, 2.0, "rect".to_string(), 5.0, 0.0, 0.0, 0.0);
        let p2: PadSpec = (2.0, 2.0, "rect".to_string(), 9.0, 0.0, 0.0, 0.0);
        let (best, pair) = copper_scan(&[p0.clone(), p2.clone()], &[p0, p1, p2], &[100, 102], &[100, 101, 102]);
        // surviving pairs: (0,1) p0<->p1 gap 3.0, (0,2) p0<->p2 gap 7.0,
        // (1,0) p2<->p0 gap 7.0, (1,1) p2<->p1 gap 2.0 -- the closest
        // surviving pair is p2<->p1 at 2.0.
        assert_eq!(pair, Some((1, 1)));
        assert!((best - 2.0).abs() < 1e-12);
    }

    #[test]
    fn test_scale_doubling_is_exact() {
        // metamorphic relation M4 pinned at the Rust level too
        let a: PadSpec = (3.7, 2.1, "roundrect".to_string(), 4.0, -2.0, 1.234, 0.25);
        let b: PadSpec = (1.2, 0.9, "oval".to_string(), -6.0, 5.0, -0.5, 0.25);
        let d = pad_pair_distance_spec(&a, &b);
        let s2 = |p: &PadSpec| (p.0 * 2.0, p.1 * 2.0, p.2.clone(), p.3 * 2.0, p.4 * 2.0, p.5, p.6);
        assert_eq!(pad_pair_distance_spec(&s2(&a), &s2(&b)), 2.0 * d);
    }
}
