//! `ClearanceHalo` — a conservative-superset obstacle halo.
//!
//! A *halo* is the region around an obstacle that must be kept clear of a
//! pour.  This module defines a type whose **only** constructors guarantee
//! the halo is a conservative superset of the true Minkowski sum
//! `obstacle ⊕ clearance_disc`:
//!
//! ```text
//! halo ⊇ obstacle ⊕ disc(clearance)
//! ```
//!
//! If a halo satisfies that containment, then any point outside the halo is
//! at least `clearance` away from every point of the obstacle — which is
//! exactly the property a DRC-aware pour carve needs.  Violating the
//! containment means the DRC measures a separation *shorter* than the
//! required figure on the real board.
//!
//! # Why this type exists — three measured geometry bugs
//!
//! During verification of the Rust zone generator (`zone_generator.rs`,
//! #1257) the following three "close but not right" approximations were
//! found — none of them surfaced until DRC measurement on the production
//! board (`docs/evidence/2026-08-16-geometry-invariant-types.md`):
//!
//! 1. **Inscribed polygon undercut.** A regular n-gon built from vertices
//!    at radius `R` is *inscribed*: its edges (the points of closest
//!    approach to the centre) sit at `R·cos(π/n) < R`.  When the polygon
//!    approximates a clearance disc of radius `R`, the carve distance is the
//!    edge-to-edge gap, so the required separation is undercut by
//!    `R·(1 − cos(π/n))` — measured 12.49 mm actual vs 12.60 mm required on
//!    the production board (a 24-gon halo).  The fix is a *circumscribed*
//!    polygon: edges tangent to the clearance disc, vertices outside it.
//! 2. **Rect-pad corner reach.** A rectangular pad's furthest point from its
//!    centre is a *corner* at half-diagonal `hypot(w/2, h/2)`, not an edge
//!    midpoint at `max(w, h)/2`.  A disc halo of radius
//!    `max(w, h)/2 + clearance` under-covers the corners — measured 12.48 mm
//!    actual vs 12.60 mm required for the 3.0×2.0 mm PTH relay pad.
//! 3. **Library panic on 500+ overlapping halos.** `geo` 0.28's sweep-line
//!    `BooleanOps` panicked ("unable to compare active segments!" /
//!    "segment not found in active-vec-set") when hundreds of overlapping
//!    halos produced nearly-coincident collinear edges.  Fixed upstream in
//!    geo 0.29 (i_overlay engine); a stress test guards the regression.
//!
//! The three bugs share a shape: each approximation was *almost* right, and
//! each needed the real board's DRC to be caught.  This type encodes the
//! correct construction in the only place the approximations can be made
//! (the constructors below), and the property tests in this module assert
//! the invariant those constructors claim.
//!
//! # The ConservativeSuperset contract
//!
//! * `from_circular_pad(center, radius, clearance, eps)` returns a halo with
//!   `halo ⊇ disc(center, radius + clearance)` — the true Minkowski sum of a
//!   circular pad and the clearance disc.  Every polygon **edge** sits at
//!   distance exactly `radius + clearance` from `center` (edges tangent to
//!   the clearance disc), and every **vertex** sits at most `eps` beyond the
//!   disc (the approximation error is bounded on the *outside* — the halo is
//!   tight, never under-covering).  Consequently the minimum distance from
//!   the pad boundary to the halo boundary is `≥ clearance` **exactly**,
//!   regardless of `eps`: `eps` only controls how much *extra* board area
//!   the halo claims, never the guarantee.
//! * `from_rect_pad(center, width, height, corner_radius, rotation,
//!   clearance, eps)` returns a halo with `halo ⊇ rect ⊕ disc(clearance)`
//!   for **any** corner radius and rotation: the rect (and therefore any
//!   rounding of it) is a subset of `disc(center, hypot(w/2, h/2))`, so the
//!   circular construction at the half-diagonal is a conservative superset
//!   of the rounded rect's Minkowski sum.
//! * `from_track(start, end, width, clearance, eps)` returns a halo with
//!   `halo ⊇ capsule(segment, width/2) ⊕ disc(clearance)`: a circumscribed
//!   capsule whose every edge sits at distance `≥ width/2 + clearance` from
//!   the segment (the capsule polygon being convex, this implies the entire
//!   true capsule is contained — the tube argument).
//!
//! # The guarantee is structural, not conventional
//!
//! The polygon field is private: `ClearanceHalo` cannot be assembled from a
//! raw polygon, so a halo that under-covers its obstacle is *unrepresentable*,
//! not merely untested.  On top of that, every constructor runs a
//! **verification** before the value can exist: witnesses sampled from the
//! true shape's boundary (edge-midpoint directions for circles — where an
//! inscribed polygon undercuts most — and the actual corners for rect pads)
//! are checked against the halo polygon, alongside the geometric proof
//! condition (every edge at distance ≥ the true radius from the shape).  The
//! [`ConservativeSuperset`] ZST marker's only constructor executes that
//! check, and its field is private — so a `ClearanceHalo` can only exist if
//! the containment check ran and passed.  A construction that fails the
//! check increases the segment count and retries, then panics loudly (a
//! halo that cannot hold its guarantee is a programming error, and silence
//! is exactly how the three bugs above shipped).

use crate::polygon::point_in_polygon_winding;
use geo::{Contains, Coord, Point, Polygon};
use std::f64::consts::PI;

/// Maximum number of sides in the circumscribed polygon.
///
/// `from_circular_pad`'s side count is `n = ⌈π / acos(r/(r+eps))⌉`, which
/// grows without bound as `eps → 0` (for `r = 50`, `eps = 1e-9` it is
/// ~500 000 — a memory/CPU footgun).  The count is capped here.  The cap
/// only ever loosens the *tightness* bound (vertices may sit more than `eps`
/// beyond the clearance disc); the ConservativeSuperset guarantee — halo
/// contains the Minkowski sum — holds for **any** number of sides ≥ 3, so
/// the cap can never turn a safe halo into an unsafe one.
pub const MAX_SIDES: usize = 2048;

/// Floating-point tolerance for the geometric proof-condition checks (edge
/// distances must be within this of the true radius).  Several orders of
/// magnitude below any DRC-relevant dimension; absorbs ulp-level rounding in
/// the trig construction.
const EDGE_TOLERANCE: f64 = 1e-9;

/// A clearance halo around an obstacle, guaranteed conservative.
///
/// See the module doc for the construction guarantee.  The polygon field is
/// private precisely so that only the constructors — which all build a
/// *circumscribed* polygon whose edges sit at the required separation and
/// verify that containment against boundary witnesses — can create a
/// `ClearanceHalo`.
#[derive(Debug, Clone)]
pub struct ClearanceHalo {
    polygon: Polygon<f64>,
    _guarantee: ConservativeSuperset,
}

/// ZST marker proving the containment check ran and passed.
///
/// The field is private and the only constructor is private, so this marker
/// can only be minted by [`ClearanceHalo`]'s verified construction paths —
/// external code can name the type but cannot fabricate the guarantee.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ConservativeSuperset {
    _private: (),
}

impl ConservativeSuperset {
    /// The ONLY way to construct a `ConservativeSuperset`.  Runs the
    /// containment check against the true shape's boundary witnesses; a
    /// witness outside the polygon is a halo that under-approximates the
    /// shape it bounds — the bug class this type exists to eliminate — so
    /// this asserts (fails loudly) rather than silently producing a bad
    /// halo.
    fn verified(polygon: &Polygon<f64>, witnesses: &[Point<f64>], description: &str) -> Self {
        for (i, w) in witnesses.iter().enumerate() {
            assert!(
                contains_boundary_inclusive(polygon, w),
                "ClearanceHalo containment violation: witness #{i} ({}, {}) is OUTSIDE the halo \
                 polygon ({description}). A clearance halo must CONTAIN the shape it bounds; \
                 under-approximation is the bug class this type exists to eliminate \
                 (inscribed-polygon undercut / rect-pad half-width corner reach).",
                w.x(),
                w.y()
            );
        }
        Self { _private: () }
    }
}

/// Minimum number of sides for a regular circumscribed polygon whose edge
/// midpoints sit on a circle of `radius` and whose vertices overhang that
/// circle by no more than `epsilon_mm`: `n = ⌈π / acos(r / (r + eps))⌉`,
/// floored at 8 (octagon) and capped at [`MAX_SIDES`].
///
/// Degenerate inputs (radius 0, eps 0/NaN) land on the floor — containment
/// holds for any n ≥ 3, so a floored n is always safe; the cap only loosens
/// tightness, never the guarantee (see [`MAX_SIDES`]'s doc).
pub fn required_sides(radius: f64, epsilon_mm: f64) -> usize {
    (PI / (radius / (radius + epsilon_mm)).acos())
        .ceil()
        .max(8.0)
        .min(MAX_SIDES as f64) as usize
}

impl ClearanceHalo {
    /// Halo for a circular pad: a circumscribed regular polygon whose edges
    /// are tangent to the circle of radius `radius + clearance`.
    ///
    /// * **Circumscribed, not inscribed.** Vertices sit at
    ///   `(radius + clearance) / cos(π/n)` so the polygon *contains* the
    ///   clearance disc (an inscribed polygon's edges at
    ///   `(radius + clearance)·cos(π/n)` undercut the required separation —
    ///   bug 1 in the module doc).
    /// * **Tight.** `n ≥ ⌈π / acos(r/(r+eps))⌉` bounds the vertex overshoot
    ///   by `eps`: `r·(sec(π/n) − 1) ≤ eps`.  Smaller `eps` → more sides →
    ///   less wasted board area; the containment guarantee holds for any
    ///   `eps`.
    /// * **Verified.** Before the value can exist, witnesses sampled ON the
    ///   true circle — including the edge-midpoint directions, where an
    ///   inscribed polygon undercuts most — are checked inside the polygon,
    ///   and every edge's distance from the centre is checked to be at
    ///   least the true radius.  If the check fails, the side count is
    ///   increased and retried (belt-and-suspenders on top of the formula);
    ///   a construction that cannot hold the guarantee panics loudly.
    pub fn from_circular_pad(
        center: Point<f64>,
        radius: f64,
        clearance: f64,
        epsilon_mm: f64,
    ) -> Self {
        let r = radius + clearance;
        let mut n = required_sides(r, epsilon_mm);
        loop {
            let polygon = circumscribed_regular_polygon(center, r, n);
            let witnesses = circle_witnesses(center, r, n);
            if witnesses
                .iter()
                .all(|w| contains_boundary_inclusive(&polygon, w))
                && min_edge_distance_to_point(&polygon, &center) >= r - EDGE_TOLERANCE
            {
                let description = format!(
                    "circular pad radius {radius} clearance {clearance} at ({}, {}) \
                     (true circle r={r}, n={n})",
                    center.x(),
                    center.y()
                );
                let _guarantee = ConservativeSuperset::verified(&polygon, &witnesses, &description);
                return Self { polygon, _guarantee };
            }
            n = (n + 4).min(MAX_SIDES);
            assert!(
                n < MAX_SIDES,
                "from_circular_pad: circumscribed polygon failed containment even at \
                 n={MAX_SIDES}; construction is broken"
            );
        }
    }

    /// Halo for a circular pad using a fixed segment count (the zone
    /// generator's fixed-24 convention, or any consumer that needs a
    /// controlled vertex count).  Same circumscribed + verified guarantee as
    /// [`ClearanceHalo::from_circular_pad`]; `segments` must be >= 8.
    pub fn from_circular_pad_with_segments(
        center: Point<f64>,
        radius: f64,
        clearance: f64,
        segments: usize,
    ) -> Self {
        let n = segments.clamp(8, MAX_SIDES);
        let r = radius + clearance;
        let mut n = n;
        loop {
            let polygon = circumscribed_regular_polygon(center, r, n);
            let witnesses = circle_witnesses(center, r, n);
            if witnesses
                .iter()
                .all(|w| contains_boundary_inclusive(&polygon, w))
                && min_edge_distance_to_point(&polygon, &center) >= r - EDGE_TOLERANCE
            {
                let description = format!(
                    "circular pad radius {radius} clearance {clearance} at ({}, {}) \
                     (true circle r={r}, n={n})",
                    center.x(),
                    center.y()
                );
                let _guarantee = ConservativeSuperset::verified(&polygon, &witnesses, &description);
                return Self { polygon, _guarantee };
            }
            n = (n + 4).min(MAX_SIDES);
            assert!(
                n < MAX_SIDES,
                "from_circular_pad_with_segments: circumscribed polygon failed containment even \
                 at n={MAX_SIDES}; construction is broken"
            );
        }
    }

    /// Halo for a circular via of `diameter` inflated by `clearance`.
    pub fn from_via(position: Point<f64>, diameter: f64, clearance: f64, epsilon_mm: f64) -> Self {
        Self::from_circular_pad(position, diameter / 2.0, clearance, epsilon_mm)
    }

    /// Halo for a rectangular pad (optionally rounded): a disc halo of
    /// radius `hypot(width/2, height/2) + clearance`, circumscribed.
    ///
    /// * **Half-diagonal, not half-width.** The furthest point of a
    ///   rectangular pad from its centre is a corner, at distance
    ///   `hypot(w/2, h/2)`.  A disc of radius `max(w, h)/2 + clearance`
    ///   under-covers the corners: measured 12.48 mm actual vs 12.60 mm
    ///   required for the 3.0×2.0 mm PTH relay pad (bug 2 in the module
    ///   doc).  A disc of the half-diagonal radius contains the whole rect
    ///   and therefore keeps *every* pad point, corners included, at least
    ///   `clearance` from the halo boundary.
    /// * **`corner_radius` is accepted and, for the disc shape, harmless.**
    ///   The rounded rect is a subset of the full rect, which is a subset of
    ///   `disc(center, hypot(w/2, h/2))`, so the disc halo is a conservative
    ///   superset of the rounded rect's Minkowski sum for *any* corner
    ///   radius.  The parameter exists for signature stability with future
    ///   tighter constructions.
    /// * **`rotation` is accepted and, for the disc shape, harmless.** A
    ///   disc halo is rotation-invariant; the corner reach is the same in
    ///   every orientation (the same convention `zone_generator.rs`
    ///   documents for its `ZoneObstacle::Pad`).  The rotated rect's actual
    ///   corners are nevertheless verified inside the halo at construction
    ///   (see below).
    /// * **Verified.** The circular construction mints the guarantee for the
    ///   half-diagonal disc; the actual (rotated, optionally rounded) rect
    ///   boundary — straight edges, corner arcs, and the four sharp corners
    ///   (the farthest points — conservative even when rounded off) — is
    ///   additionally asserted inside the halo.  This is the exact check a
    ///   half-width halo fails.
    pub fn from_rect_pad(
        center: Point<f64>,
        width: f64,
        height: f64,
        corner_radius: f64,
        rotation: f64,
        clearance: f64,
        epsilon_mm: f64,
    ) -> Self {
        let half_diag = ((width / 2.0).powi(2) + (height / 2.0).powi(2)).sqrt();
        let halo = Self::from_circular_pad(center, half_diag, clearance, epsilon_mm);
        // Belt: the actual (rotated) rect boundary must be inside the halo.
        // It always is (rect ⊆ disc(half_diag) ⊆ halo polygon); the assert
        // is the structural check that a future edit cannot silently break
        // that chain.
        for w in rect_boundary_witnesses(center, width, height, corner_radius, rotation) {
            assert!(
                contains_boundary_inclusive(halo.polygon(), &w),
                "from_rect_pad: rect boundary witness ({}, {}) outside the half-diagonal halo \
                 for a {width}x{height} pad rot={rotation} cr={corner_radius} — the \
                 half-diagonal containment chain is broken",
                w.x(),
                w.y()
            );
        }
        halo
    }

    /// Halo for a rectangular pad using a fixed segment count.  Same
    /// circumscribed-disc + verified guarantee as
    /// [`ClearanceHalo::from_rect_pad`]; `segments` must be >= 8.
    pub fn from_rect_pad_with_segments(
        center: Point<f64>,
        width: f64,
        height: f64,
        corner_radius: f64,
        rotation: f64,
        clearance: f64,
        segments: usize,
    ) -> Self {
        let half_diag = ((width / 2.0).powi(2) + (height / 2.0).powi(2)).sqrt();
        let halo = Self::from_circular_pad_with_segments(center, half_diag, clearance, segments);
        for w in rect_boundary_witnesses(center, width, height, corner_radius, rotation) {
            assert!(
                contains_boundary_inclusive(halo.polygon(), &w),
                "from_rect_pad_with_segments: rect boundary witness ({}, {}) outside the \
                 half-diagonal halo for a {width}x{height} pad rot={rotation} cr={corner_radius}",
                w.x(),
                w.y()
            );
        }
        halo
    }

    /// Halo for a track of `width` between `start` and `end` inflated by
    /// `clearance`: a regular-polygon approximation of the capsule
    /// (Minkowski sum of the segment and a circle of radius
    /// `width/2 + clearance`) whose edges all sit at or beyond the true
    /// capsule radius.
    ///
    /// **Verified.** Every polygon edge's distance from the segment is
    /// checked to be ≥ `width/2 + clearance` — which, the capsule polygon
    /// being convex, implies the entire true capsule is contained (the tube
    /// argument) — and witnesses sampled on the true capsule boundary
    /// (straight sides and both cap semicircles, including the cap-edge-
    /// midpoint directions where an inscribed cap undercuts most) are
    /// checked inside the polygon.
    pub fn from_track(
        start: Point<f64>,
        end: Point<f64>,
        width: f64,
        clearance: f64,
        epsilon_mm: f64,
    ) -> Self {
        let r = width / 2.0 + clearance;
        let mut segments = required_sides(r, epsilon_mm);
        if !segments.is_multiple_of(2) {
            segments += 1;
        }
        Self::from_capsule_with_segments(start, end, r, segments, width, clearance)
    }

    /// Halo for a track using a fixed segment count (must be even, >= 8).
    pub fn from_track_with_segments(
        start: Point<f64>,
        end: Point<f64>,
        width: f64,
        clearance: f64,
        segments: usize,
    ) -> Self {
        let r = width / 2.0 + clearance;
        let mut segments = segments.clamp(8, MAX_SIDES);
        if !segments.is_multiple_of(2) {
            segments += 1;
        }
        Self::from_capsule_with_segments(start, end, r, segments, width, clearance)
    }

    /// The halo polygon (circumscribed; edges at the required separation).
    pub fn polygon(&self) -> &Polygon<f64> {
        &self.polygon
    }

    /// Whether `point` is inside the halo.
    ///
    /// Points exactly on the polygon boundary are *not* contained (`geo`
    /// `Contains` requires the point to be in the interior); callers that
    /// probe boundary-adjacent geometry should sample with a small margin.
    pub fn contains(&self, point: Point<f64>) -> bool {
        self.polygon.contains(&point)
    }

    /// The guarantee marker proving this halo's containment check ran and
    /// passed.
    pub fn guarantee(&self) -> &ConservativeSuperset {
        &self._guarantee
    }

    /// Minimum distance from `p` to the halo's boundary (the closest point
    /// on any polygon edge).  The clearance floor: for any point `p` on the
    /// true shape's boundary, this is >= the requested clearance (up to
    /// floating-point tolerance).
    pub fn distance_to_boundary(&self, p: &Point<f64>) -> f64 {
        min_edge_distance_to_point(&self.polygon, p)
    }

    /// Shared capsule construction: builds the circumscribed capsule,
    /// checks the geometric proof condition (every edge at distance >= `r`
    /// from the segment) AND the boundary witnesses, and mints the
    /// guarantee.  If the check fails, increases the segment count and
    /// retries (belt-and-suspenders on top of the formula).
    fn from_capsule_with_segments(
        start: Point<f64>,
        end: Point<f64>,
        r: f64,
        mut segments: usize,
        shape_width: f64,
        clearance: f64,
    ) -> Self {
        loop {
            let polygon = circumscribed_capsule(start, end, r, segments);
            let witnesses = capsule_witnesses(start, end, r, segments);
            if witnesses
                .iter()
                .all(|w| contains_boundary_inclusive(&polygon, w))
                && min_edge_distance_to_segment(&polygon, &start, &end) >= r - EDGE_TOLERANCE
            {
                let description = format!(
                    "track width {shape_width} clearance {clearance} from ({}, {}) to ({}, {}) \
                     (true capsule radius r={r}, segments={segments})",
                    start.x(),
                    start.y(),
                    end.x(),
                    end.y()
                );
                let _guarantee = ConservativeSuperset::verified(&polygon, &witnesses, &description);
                return Self { polygon, _guarantee };
            }
            segments = (segments + 2).min(MAX_SIDES);
            assert!(
                segments < MAX_SIDES,
                "from_track: circumscribed capsule failed containment even at segments={MAX_SIDES}; \
                 construction is broken"
            );
        }
    }
}

/// Boundary-INCLUSIVE point-in-polygon test, needed because the witnesses
/// that pin the circumscription (edge-midpoint directions) sit exactly ON
/// the polygon's edges, and geo's `Contains` requires strict interior.
/// Uses the crate's winding predicate with its 1e-12 on-edge tolerance.
fn contains_boundary_inclusive(polygon: &Polygon<f64>, p: &Point<f64>) -> bool {
    let verts: Vec<crate::types::Point> = polygon
        .exterior()
        .coords()
        .map(|c| crate::types::Point::new(c.x, c.y))
        .collect();
    point_in_polygon_winding(
        &crate::types::Point::new(p.x(), p.y()),
        &verts,
    )
}

/// A regular `n`-gon **circumscribing** the circle of radius `r` at `center`:
/// vertices at `r / cos(π/n)`, so every edge is tangent to the circle at
/// distance exactly `r`.  The circle is inside the polygon; the vertices are
/// outside it by `r·(sec(π/n) − 1)`.
fn circumscribed_regular_polygon(center: Point<f64>, r: f64, n: usize) -> Polygon<f64> {
    let vertex_r = r / (PI / n as f64).cos();
    let ring: Vec<Coord<f64>> = (0..n)
        .map(|i| {
            let a = std::f64::consts::TAU * (i as f64) / (n as f64);
            Coord {
                x: center.x() + vertex_r * a.cos(),
                y: center.y() + vertex_r * a.sin(),
            }
        })
        .collect();
    // Angles increase CCW from the +x axis -> CCW ring, the crate's
    // normalised orientation (cf. zone_generator's orientation_is_normalised).
    Polygon::new(ring.into(), vec![])
}

/// A regular-polygon approximation of the capsule (Minkowski sum of segment
/// `start`-`end` and a circle of `radius`) whose edges all sit AT OR BEYOND
/// `radius` from the segment: the cap vertices are inflated by
/// `1/cos(π/segments)` so the cap edge midpoints land at exactly `radius`
/// (the true capsule radius), and the straight sides sit at
/// `radius / cos(π/segments) > radius`.  Since the capsule polygon is
/// convex, every edge being at distance >= `radius` from the segment means
/// the entire true capsule is contained (the tube argument).
///
/// Ring order matches the zone generator's `capsule` (right cap sweeping
/// `+p → +u → -p`, bottom straight side, left cap, top straight side),
/// where `p` is the +90° CCW perpendicular of the segment direction.
fn circumscribed_capsule(start: Point<f64>, end: Point<f64>, radius: f64, segments: usize) -> Polygon<f64> {
    let half = segments / 2;
    let vertex_r = radius / (PI / segments as f64).cos();
    let dx = end.x() - start.x();
    let dy = end.y() - start.y();
    let len = (dx * dx + dy * dy).sqrt();
    // Perpendicular (px,py) = +90° CCW rotation of the segment direction.
    // For a zero-length segment, default to pointing along +y.
    let (px, py) = if len > 1e-12 {
        (-dy / len, dx / len)
    } else {
        (0.0, 1.0)
    };
    let mut ring: Vec<Coord<f64>> = Vec::with_capacity(2 * half + 4);
    // Rotate (px,py) by t radians (standard CCW rotation matrix).
    let rot = |t: f64| -> (f64, f64) {
        (px * t.cos() - py * t.sin(), px * t.sin() + py * t.cos())
    };
    // Right cap: t from 0 (end + p*r) down to -π (end - p*r); at t=-π/2
    // this passes through end + u*r (the front axis point).
    for i in 0..=half {
        let t = -PI * (i as f64) / (half as f64);
        let (dirx, diry) = rot(t);
        ring.push(Coord {
            x: end.x() + vertex_r * dirx,
            y: end.y() + vertex_r * diry,
        });
    }
    // Left cap: t from +π (start - p*r) down to 0 (start + p*r); at
    // t=+π/2 this passes through start - u*r (the rear axis point).
    for i in 0..=half {
        let t = PI * (1.0 - (i as f64) / (half as f64));
        let (dirx, diry) = rot(t);
        ring.push(Coord {
            x: start.x() + vertex_r * dirx,
            y: start.y() + vertex_r * diry,
        });
    }
    Polygon::new(ring.into(), vec![])
}

/// Witness points ON the true circle of `radius` at `center`: the `segments`
/// edge-midpoint directions (the tightest — where an inscribed polygon
/// undercuts most), the `segments` vertex directions, and a uniform sample.
/// Every witness is ON the circle — points such as the circle's bounding-box
/// corners (±r, ±r) are NOT on the circle (they sit at r√2 from the centre)
/// and no circumscribed polygon is required to contain them.
fn circle_witnesses(center: Point<f64>, radius: f64, segments: usize) -> Vec<Point<f64>> {
    let mut out = Vec::with_capacity(4 * segments);
    // Edge-midpoint directions: the polygon edges are tangent to the circle
    // there, so these are the closest points of the circle to the boundary.
    for i in 0..segments {
        let a = std::f64::consts::TAU * ((i as f64) + 0.5) / (segments as f64);
        out.push(Point::new(
            center.x() + radius * a.cos(),
            center.y() + radius * a.sin(),
        ));
    }
    // Vertex directions: at radius (inside the circumscribed vertices).
    for i in 0..segments {
        let a = std::f64::consts::TAU * (i as f64) / (segments as f64);
        out.push(Point::new(
            center.x() + radius * a.cos(),
            center.y() + radius * a.sin(),
        ));
    }
    // Uniform dense sample (the arc between adjacent edge-midpoint
    // witnesses is convex-outward, so this is belt-and-suspenders).
    let uniform = (4 * segments).max(64);
    for i in 0..uniform {
        let a = std::f64::consts::TAU * (i as f64) / (uniform as f64);
        out.push(Point::new(
            center.x() + radius * a.cos(),
            center.y() + radius * a.sin(),
        ));
    }
    out
}

/// Witness points on the true rect-pad boundary: the straight edges, the
/// corner arcs (if `corner_radius > 0`), and the sharp corners (the farthest
/// points from the centre — the exact spots a half-width halo under-covers).
/// All rotated by `rotation` around `center`.
fn rect_boundary_witnesses(
    center: Point<f64>,
    width: f64,
    height: f64,
    corner_radius: f64,
    rotation: f64,
) -> Vec<Point<f64>> {
    let half_w = width / 2.0;
    let half_h = height / 2.0;
    let cr = corner_radius;
    let cos_r = rotation.cos();
    let sin_r = rotation.sin();
    // `p` is a LOCAL offset from `center` (the rect is built centred on the
    // origin below); rotate the offset and translate to the halo centre.
    // (2026-08-16 regression: a draft subtracted `center` here too, which
    // double-translated every witness off-origin — caught by the proptest,
    // not by the centred example tests.)
    let rotate = |p: Point<f64>| -> Point<f64> {
        let dx = p.x();
        let dy = p.y();
        Point::new(
            center.x() + dx * cos_r - dy * sin_r,
            center.y() + dx * sin_r + dy * cos_r,
        )
    };
    let mut out = Vec::with_capacity(128);
    // Straight edges (axis-aligned in local coords).  When corner_radius > 0
    // the edges stop at the corner-arc junctions; else they run corner to
    // corner.
    let jx = (half_w - cr).max(0.0);
    let jy = (half_h - cr).max(0.0);
    for k in 0..=8 {
        let t = (k as f64) / 8.0;
        // Top edge: (-jx, half_h) → (+jx, half_h)
        out.push(rotate(Point::new(-jx + 2.0 * jx * t, half_h)));
        // Bottom edge: (-jx, -half_h) → (+jx, -half_h)
        out.push(rotate(Point::new(-jx + 2.0 * jx * t, -half_h)));
        // Left edge: (-half_w, -jy) → (-half_w, +jy)
        out.push(rotate(Point::new(-half_w, -jy + 2.0 * jy * t)));
        // Right edge: (+half_w, -jy) → (+half_w, +jy)
        out.push(rotate(Point::new(half_w, -jy + 2.0 * jy * t)));
    }
    // Corner arcs (quarter circles of radius cr centred at the inset
    // corners).  For quadrant (sx, sy) the arc centre is (sx·jx, sy·jy) and
    // the arc runs from the top/right junction through the corner,
    // parametrised by φ from π/2 down to 0 (see the +/+ quadrant: centre
    // (jx, jy), junction points (jx, half_h) at φ=π/2 and (half_w, jy) at
    // φ=0).
    if cr > 0.0 {
        for (sx, sy) in [(1.0, 1.0), (-1.0, 1.0), (1.0, -1.0), (-1.0, -1.0)] {
            for k in 0..=8 {
                let phi = (PI / 2.0) * (1.0 - (k as f64) / 8.0);
                let p = Point::new(sx * jx + cr * phi.cos(), sy * jy + cr * phi.sin());
                out.push(rotate(p));
            }
        }
    }
    // The four sharp corners — the farthest points from the centre.  For a
    // rounded rect these are not on the true boundary (the corner is rounded
    // off), but requiring the halo to contain them anyway is conservative
    // and cheap, and it is exactly the point a half-width halo misses.
    for (sx, sy) in [(1.0, 1.0), (-1.0, 1.0), (1.0, -1.0), (-1.0, -1.0)] {
        out.push(rotate(Point::new(sx * half_w, sy * half_h)));
    }
    out
}

/// Witness points on the true capsule boundary (segment `start`-`end`
/// buffered by `radius`): the straight sides at distance `radius` from the
/// segment, and the two cap semicircles of radius `radius` — including the
/// exact cap-edge-midpoint directions, where an inscribed cap undercuts
/// most.
fn capsule_witnesses(
    start: Point<f64>,
    end: Point<f64>,
    radius: f64,
    segments: usize,
) -> Vec<Point<f64>> {
    let half = segments / 2;
    let dx = end.x() - start.x();
    let dy = end.y() - start.y();
    let len = (dx * dx + dy * dy).sqrt();
    let (px, py) = if len > 1e-12 {
        (-dy / len, dx / len)
    } else {
        (0.0, 1.0)
    };
    let rot = |t: f64| -> (f64, f64) {
        (px * t.cos() - py * t.sin(), px * t.sin() + py * t.cos())
    };
    let mut out = Vec::with_capacity(6 * segments + 8);
    // Right cap semicircle: directions +p → +u → -p at radius, both at the
    // vertex angles and at the edge-midpoint angles (the tightest).
    for i in 0..=half {
        let t = -PI * (i as f64) / (half as f64);
        let (dirx, diry) = rot(t);
        out.push(Point::new(end.x() + radius * dirx, end.y() + radius * diry));
    }
    for i in 0..half {
        let t = -PI * ((i as f64) + 0.5) / (half as f64);
        let (dirx, diry) = rot(t);
        out.push(Point::new(end.x() + radius * dirx, end.y() + radius * diry));
    }
    // Left cap semicircle: directions -p → -u → +p.
    for i in 0..=half {
        let t = PI * (1.0 - (i as f64) / (half as f64));
        let (dirx, diry) = rot(t);
        out.push(Point::new(start.x() + radius * dirx, start.y() + radius * diry));
    }
    for i in 0..half {
        let t = PI * (1.0 - ((i as f64) + 0.5) / (half as f64));
        let (dirx, diry) = rot(t);
        out.push(Point::new(start.x() + radius * dirx, start.y() + radius * diry));
    }
    // Straight sides at distance `radius` from the segment.
    for k in 0..=16 {
        let t = (k as f64) / 16.0;
        let sx = start.x() + (end.x() - start.x()) * t;
        let sy = start.y() + (end.y() - start.y()) * t;
        out.push(Point::new(sx + radius * px, sy + radius * py));
        out.push(Point::new(sx - radius * px, sy - radius * py));
    }
    out
}

/// Minimum distance from `p` to any edge of the polygon.
fn min_edge_distance_to_point(polygon: &Polygon<f64>, p: &Point<f64>) -> f64 {
    polygon
        .exterior()
        .lines()
        .map(|l| point_segment_distance(p, l.start, l.end))
        .fold(f64::INFINITY, f64::min)
}

/// Minimum distance between the segment `a`-`b` and any edge of the polygon.
fn min_edge_distance_to_segment(polygon: &Polygon<f64>, a: &Point<f64>, b: &Point<f64>) -> f64 {
    polygon.exterior().lines().map(|l| {
        let l1 = Point::new(l.start.x, l.start.y);
        let l2 = Point::new(l.end.x, l.end.y);
        segment_segment_distance(a, b, &l1, &l2)
    })
    .fold(f64::INFINITY, f64::min)
}

/// Distance from `p` to the segment `a`-`b` (clamped projection).
fn point_segment_distance(p: &Point<f64>, a: Coord<f64>, b: Coord<f64>) -> f64 {
    let abx = b.x - a.x;
    let aby = b.y - a.y;
    let len2 = abx * abx + aby * aby;
    let t = if len2 <= 0.0 {
        0.0
    } else {
        (((p.x() - a.x) * abx + (p.y() - a.y) * aby) / len2).clamp(0.0, 1.0)
    };
    let cx = a.x + t * abx;
    let cy = a.y + t * aby;
    ((p.x() - cx).powi(2) + (p.y() - cy).powi(2)).sqrt()
}

/// Minimum distance between two segments (0.0 if they intersect).
fn segment_segment_distance(a1: &Point<f64>, a2: &Point<f64>, b1: &Point<f64>, b2: &Point<f64>) -> f64 {
    if segments_intersect(a1, a2, b1, b2) {
        return 0.0;
    }
    let b1c = Coord { x: b1.x(), y: b1.y() };
    let b2c = Coord { x: b2.x(), y: b2.y() };
    let a1c = Coord { x: a1.x(), y: a1.y() };
    let a2c = Coord { x: a2.x(), y: a2.y() };
    point_segment_distance(a1, b1c, b2c)
        .min(point_segment_distance(a2, b1c, b2c))
        .min(point_segment_distance(b1, a1c, a2c))
        .min(point_segment_distance(b2, a1c, a2c))
}

fn segments_intersect(a1: &Point<f64>, a2: &Point<f64>, b1: &Point<f64>, b2: &Point<f64>) -> bool {
    let o1 = orientation(a1, a2, b1);
    let o2 = orientation(a1, a2, b2);
    let o3 = orientation(b1, b2, a1);
    let o4 = orientation(b1, b2, a2);
    (o1 * o2 < 0.0 && o3 * o4 < 0.0)
        || (o1.abs() <= 1e-12 && on_segment(a1, a2, b1))
        || (o2.abs() <= 1e-12 && on_segment(a1, a2, b2))
        || (o3.abs() <= 1e-12 && on_segment(b1, b2, a1))
        || (o4.abs() <= 1e-12 && on_segment(b1, b2, a2))
}

fn orientation(a: &Point<f64>, b: &Point<f64>, c: &Point<f64>) -> f64 {
    (b.x() - a.x()) * (c.y() - a.y()) - (b.y() - a.y()) * (c.x() - a.x())
}

fn on_segment(a: &Point<f64>, b: &Point<f64>, p: &Point<f64>) -> bool {
    p.x() >= a.x().min(b.x()) - 1e-12
        && p.x() <= a.x().max(b.x()) + 1e-12
        && p.y() >= a.y().min(b.y()) - 1e-12
        && p.y() <= a.y().max(b.y()) + 1e-12
}

// `items_after_test_module` is allowed deliberately: the wasm-registry
// generator appends the `WASM_TESTS` const AFTER this module's nested
// `proptests` submodule (its canonical position is module-end), so the lint
// would fire on every regeneration. The ordering is generator-forced.
// (The comment sits ABOVE the gate; the gate must stay the attribute
// immediately above `mod` or the registry generator reports
// "gate-not-adjacent-to-mod".)
#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;
    use geo::{Area as _, BooleanOps, HasDimensions, MultiPolygon};

    // ------------------------------------------------------------------
    // Property-test helpers
    // ------------------------------------------------------------------

    /// `count` points on the circle of `radius` at `center`.
    ///
    /// Every sample angle carries a fixed offset of `1e-4` rad.  A point
    /// exactly on a polygon edge is *not* `Contains`-contained (geo requires
    /// `CoordPos::Inside`), and the circumscribed polygon's edges are tangent
    /// to the sampled circle at the edge midpoints — so a sample landing on a
    /// tangency point would spuriously fail a containment assertion.  The
    /// tangency angles are `(2k+1)·π/n` for integer `n`; a sample angle is
    /// `1e-4 + 2π·i/count`.  `1e-4` is irrational relative to `π`, so
    /// `1e-4 + 2π·i/count = (2k+1)·π/n` has no integer solution for any
    /// integer `n`, `k`, `i`, `count` — no sample can ever land on an edge,
    /// and each sample is strictly inside the polygon.
    fn sample_circle_points(center: Point<f64>, radius: f64, count: usize) -> Vec<Point<f64>> {
        const ANGLE_OFFSET: f64 = 1e-4;
        (0..count)
            .map(|i| {
                let a = ANGLE_OFFSET + std::f64::consts::TAU * (i as f64) / (count as f64);
                Point::new(center.x() + radius * a.cos(), center.y() + radius * a.sin())
            })
            .collect()
    }

    /// Points on the perimeter of an axis-aligned rect of `width`×`height`
    /// centred at `center`: `SAMPLES_PER_EDGE` per edge, endpoints included,
    /// so corners and edge midpoints are always sampled.
    fn rect_perimeter_points(
        center: Point<f64>,
        width: f64,
        height: f64,
        samples_per_edge: usize,
    ) -> Vec<Point<f64>> {
        let hw = width / 2.0;
        let hh = height / 2.0;
        let mut pts = Vec::with_capacity(4 * samples_per_edge);
        for (ax, ay, bx, by) in [
            (-hw, -hh, hw, -hh), // bottom
            (hw, -hh, hw, hh),   // right
            (hw, hh, -hw, hh),   // top
            (-hw, hh, -hw, -hh), // left
        ] {
            for k in 0..samples_per_edge {
                let t = k as f64 / (samples_per_edge as f64 - 1.0);
                pts.push(Point::new(
                    center.x() + ax + (bx - ax) * t,
                    center.y() + ay + (by - ay) * t,
                ));
            }
        }
        pts
    }

    /// Distance from `p` to the line segment `a`–`b`.
    fn point_segment_distance(p: Point<f64>, a: Coord<f64>, b: Coord<f64>) -> f64 {
        let abx = b.x - a.x;
        let aby = b.y - a.y;
        let len2 = abx * abx + aby * aby;
        let t = if len2 <= 0.0 {
            0.0
        } else {
            (((p.x() - a.x) * abx + (p.y() - a.y) * aby) / len2).clamp(0.0, 1.0)
        };
        let cx = a.x + t * abx;
        let cy = a.y + t * aby;
        ((p.x() - cx).powi(2) + (p.y() - cy).powi(2)).sqrt()
    }

    /// Minimum distance from `p` to the boundary (all edges, closing edge
    /// included) of `poly`.
    fn min_distance_to_boundary(p: Point<f64>, poly: &Polygon<f64>) -> f64 {
        poly.exterior()
            .lines()
            .map(|l| point_segment_distance(p, l.start, l.end))
            .fold(f64::INFINITY, f64::min)
    }

    /// Minimum distance from the *pad boundary* (sampled) to the halo
    /// boundary (all edges).
    fn min_pad_to_halo_distance(pad_points: &[Point<f64>], halo: &ClearanceHalo) -> f64 {
        pad_points
            .iter()
            .map(|p| min_distance_to_boundary(*p, halo.polygon()))
            .fold(f64::INFINITY, f64::min)
    }

    // ------------------------------------------------------------------
    // Property 1: circumscribed polygon CONTAINS the circle
    // (catches the inscribed-polygon undercut, bug 1)
    // ------------------------------------------------------------------

    #[cfg_attr(test, test)]
    fn circumscribed_polygon_contains_circle() {
        let origin = Point::new(0.0, 0.0);
        for &radius in &[0.1, 1.0, 5.0, 12.6, 50.0] {
            for &eps in &[0.001, 0.01, 0.1] {
                let halo = ClearanceHalo::from_circular_pad(origin, radius, 0.0, eps);
                // (a) Every sampled point ON the circle is inside.  An
                // inscribed polygon would fail this: between adjacent
                // vertices its edges dip inside the circle by
                // r·(1 − cos(π/n)).
                for p in sample_circle_points(origin, radius, 1000) {
                    assert!(
                        halo.contains(p),
                        "radius={radius} eps={eps}: circle point ({}, {}) not contained",
                        p.x(),
                        p.y()
                    );
                }
                // (b) Every EDGE sits at distance >= radius from the centre
                // (the DRC-relevant separation is the edge-to-edge gap).  An
                // inscribed polygon's edges sit at radius·cos(π/n) < radius.
                let min_edge = halo
                    .polygon()
                    .exterior()
                    .lines()
                    .map(|l| point_segment_distance(origin, l.start, l.end))
                    .fold(f64::INFINITY, f64::min);
                assert!(
                    min_edge >= radius - 1e-9,
                    "radius={radius} eps={eps}: edge apothem {min_edge} < radius"
                );
                // (c) Tightness: vertices sit within eps of the circle
                // (never further out).  Catches over-inflation (e.g. an
                // extra sec(π/n) factor) that would waste board area.
                for v in halo.polygon().exterior().points() {
                    let d = ((v.x() - origin.x()).powi(2) + (v.y() - origin.y()).powi(2)).sqrt();
                    assert!(
                        d <= radius + eps + 1e-9,
                        "radius={radius} eps={eps}: vertex overshoot {} > eps",
                        d - radius
                    );
                }
            }
        }
    }

    /// Demonstrates the bug class the constructor now excludes: a regular
    /// 24-gon built the old buggy way — vertices ON the circle (inscribed) —
    /// fails the containment property (edge midpoints sit at
    /// `R·cos(π/24) = 0.9914R`, so circle points near them are outside).
    /// The same points are inside the circumscribed halo the constructor
    /// builds, so this test documents why the property above discriminates.
    #[cfg_attr(test, test)]
    fn inscribed_polygon_undercuts_the_circle() {
        let radius = 12.6;
        // Buggy construction: 24-gon with vertices AT radius (inscribed).
        let ring: Vec<Coord<f64>> = (0..24)
            .map(|i| {
                let a = std::f64::consts::TAU * (i as f64) / 24.0;
                Coord {
                    x: radius * a.cos(),
                    y: radius * a.sin(),
                }
            })
            .collect();
        let inscribed = Polygon::new(ring.into(), vec![]);
        let mut any_outside = false;
        for i in 0..24 {
            let a = std::f64::consts::TAU * ((i as f64) + 0.5) / 24.0;
            let p = Point::new(radius * a.cos(), radius * a.sin());
            if !contains_boundary_inclusive(&inscribed, &p) {
                any_outside = true;
                break;
            }
        }
        assert!(
            any_outside,
            "an inscribed 24-gon undercuts the circle at its edge midpoints \
             (R·cos(π/24) = 0.9914R < R); the test that catches bug 1 must fail on it"
        );
    }

    // ------------------------------------------------------------------
    // Property 2: rect-pad halo contains all four corners
    // (catches the half-width corner reach bug, bug 2)
    // ------------------------------------------------------------------

    #[cfg_attr(test, test)]
    fn rect_halo_contains_all_four_corners() {
        let origin = Point::new(0.0, 0.0);
        // Clearance is 1 um: large enough that the corners are strictly
        // inside the correct halo (no boundary/tangency risk), small enough
        // that a half-width halo `max(w,h)/2 + clearance` still fails on the
        // (5.0, 0.3) pad whose half-diagonal exceeds max(w,h)/2 by only
        // ~4.7 um.
        let clearance = 0.001;
        let eps = 0.01;
        for &(w, h) in &[(1.0, 0.6), (2.0, 2.0), (5.0, 0.3), (1.95, 0.6)] {
            let halo = ClearanceHalo::from_rect_pad(origin, w, h, 0.0, 0.0, clearance, eps);
            for &(cx, cy) in &[(1.0, 1.0), (1.0, -1.0), (-1.0, 1.0), (-1.0, -1.0)] {
                let corner = Point::new(cx * w / 2.0, cy * h / 2.0);
                assert!(
                    halo.contains(corner),
                    "pad {w}x{h}: corner ({}, {}) not contained",
                    corner.x(),
                    corner.y()
                );
            }
            // Sanity: the pad centre is contained, a point far outside is not.
            assert!(halo.contains(origin));
            let far = Point::new(origin.x() + w + h + 100.0, origin.y());
            assert!(!halo.contains(far), "pad {w}x{h}: far point unexpectedly contained");
        }
    }

    /// Rect corners at an OFF-ORIGIN centre and arbitrary rotations (the
    /// 2026-08-16 proptest finding: a draft of the witness machinery
    /// double-translated off-origin; every origin-centred example passed).
    #[cfg_attr(test, test)]
    fn rect_halo_contains_corners_off_origin_and_rotated() {
        let clearance = 12.6;
        for &(w, h) in &[(1.0, 0.6), (2.0, 2.0), (5.0, 0.3), (3.0, 2.0), (0.4, 8.0)] {
            for rotation in [0.0, 0.5, std::f64::consts::FRAC_PI_4, 1.9] {
                for &(cx, cy) in &[(-43.3, 0.0), (12.5, -77.2), (0.0, 0.0)] {
                    let center = Point::new(cx, cy);
                    let halo =
                        ClearanceHalo::from_rect_pad(center, w, h, 0.0, rotation, clearance, 0.01);
                    let (c, s) = (rotation.cos(), rotation.sin());
                    for &(dx, dy) in &[
                        (w / 2.0, h / 2.0),
                        (-w / 2.0, h / 2.0),
                        (w / 2.0, -h / 2.0),
                        (-w / 2.0, -h / 2.0),
                    ] {
                        let corner = Point::new(cx + dx * c - dy * s, cy + dx * s + dy * c);
                        // The corner is strictly inside (clearance dominates),
                        // so geo's interior-only Contains is the right probe.
                        assert!(
                            halo.contains(corner),
                            "corner ({dx}, {dy}) not in halo for pad {w}x{h} rot {rotation} at \
                             ({cx}, {cy})"
                        );
                    }
                }
            }
        }
    }

    /// Demonstrates the bug 2 bug class at the CLEARANCE level: a disc halo
    /// of radius `max(w,h)/2 + clearance` (the old convention) does contain
    /// the corners (the clearance dominates), but the corner-to-boundary
    /// distance is `clearance − (half_diag − half_width)` — SHORT of the
    /// requested clearance by exactly the amount the half-width
    /// approximation under-reaches.  The DRC measured that shortfall
    /// (0.30 mm for the 3.0×2.0 mm PTH relay pad at 12.6 mm).
    #[cfg_attr(test, test)]
    fn half_width_halo_misses_rect_corners() {
        let (w, h): (f64, f64) = (3.0, 2.0);
        let clearance = 12.6;
        let half_width_radius = w.max(h) / 2.0 + clearance; // old, buggy
        let half_diag = ((w / 2.0).powi(2) + (h / 2.0).powi(2)).sqrt();
        assert!(
            half_diag > w.max(h) / 2.0,
            "precondition: the corner reaches further than max(w,h)/2"
        );
        // With the half-width halo the corner-to-boundary distance is short
        // of the requested clearance — the DRC-measured violation.
        let corner_clearance = half_width_radius - half_diag;
        assert!(
            corner_clearance < clearance - 1e-9,
            "a half-width halo gives corner clearance {corner_clearance} >= requested {clearance}; \
             the test that catches bug 2 must fail on it"
        );
    }

    // ------------------------------------------------------------------
    // Property 3: stress — 500+ overlapping halos union without panic
    // (catches the geo BooleanOps panic, bug 3)
    // ------------------------------------------------------------------

    #[cfg_attr(test, test)]
    fn stress_500_overlapping_halos_union_no_panic() {
        // Phase 1: the task's exact shape — a 1-D chain of 500 halos whose
        // centres are 0.01 mm apart, so every halo overlaps dozens of
        // neighbours.
        //
        // Phase 2: a dense 25x20 grid at 0.01 mm spacing of identical
        // octagons — the shape that produced near-coincident COLLINEAR
        // edges in production and panicked geo 0.28's sweep-line
        // BooleanOps ("unable to compare active segments!").
        //
        // Union incrementally (fold), exactly as zone_generator.rs does, so
        // this test guards the same call pattern that crashed.  (On geo
        // 0.28 a ONE-SHOT union of 500 varying-radius halos also panicked —
        // "segment not found in active-vec-set: 791", reproduced
        // 2026-08-16; geo 0.29's i_overlay engine fixes the library bug,
        // and the test stays as the regression guard.)
        struct StressCase {
            name: &'static str,
            positions: Vec<Point<f64>>,
            radius: f64,
            clearance: f64,
            eps: f64,
        }
        let cases = [
            StressCase {
                name: "chain",
                positions: chain_positions(500, 0.01),
                radius: 0.5,
                clearance: 0.0,
                eps: 0.1,
            },
            StressCase {
                name: "grid",
                positions: grid_positions(25, 20, 0.01),
                radius: 0.5,
                clearance: 0.5,
                eps: 0.1,
            },
            StressCase {
                // Production-shaped: creepage-sized halos (radius 13.6) of
                // slightly varying radii — the near-coincident collinear
                // edge configuration that panicked geo 0.28 one-shot.
                name: "creepage-chain",
                positions: chain_positions(500, 0.01),
                radius: 1.0,
                clearance: 12.6,
                eps: 0.01,
            },
        ];
        for case in &cases {
            let mut keepout: MultiPolygon<f64> = MultiPolygon::new(vec![]);
            for center in &case.positions {
                let halo =
                    ClearanceHalo::from_circular_pad(*center, case.radius, case.clearance, case.eps);
                let poly = halo.polygon().clone();
                keepout = keepout.union(&MultiPolygon::new(vec![poly]));
            }
            assert!(
                !keepout.is_empty(),
                "{}: union of 500 overlapping halos is EMPTY",
                case.name
            );
            let area: f64 = keepout.iter().map(|p| p.unsigned_area()).sum();
            assert!(
                area > 1.0,
                "{}: union area {area} far below expected for 500 overlapping halos",
                case.name
            );
            // A probe point near the middle of the layout must be inside.
            let mid = *case
                .positions
                .get(case.positions.len() / 2)
                .unwrap_or(&Point::new(0.0, 0.0));
            assert!(
                keepout.contains(&mid),
                "{}: probe point ({}, {}) not inside union",
                case.name,
                mid.x(),
                mid.y()
            );
        }
    }

    /// `count` centres spaced `step` mm apart along the x axis, starting at
    /// the origin.
    fn chain_positions(count: usize, step: f64) -> Vec<Point<f64>> {
        (0..count)
            .map(|i| Point::new(step * (i as f64), 0.0))
            .collect()
    }

    /// `cols`×`rows` centres spaced `step` mm apart in both axes.
    fn grid_positions(cols: usize, rows: usize, step: f64) -> Vec<Point<f64>> {
        let mut pts = Vec::with_capacity(cols * rows);
        for r in 0..rows {
            for c in 0..cols {
                pts.push(Point::new(step * (c as f64), step * (r as f64)));
            }
        }
        pts
    }

    // ------------------------------------------------------------------
    // Property 4: clearance guarantee — min distance from the pad boundary
    // to the halo boundary >= clearance
    // (catches all three bugs)
    // ------------------------------------------------------------------

    #[cfg_attr(test, test)]
    fn min_distance_from_pad_boundary_to_halo_boundary_meets_clearance() {
        let origin = Point::new(0.0, 0.0);
        // The geometric guarantee is EXACT: pad ⊆ disc(half_diag) and
        // halo ⊇ disc(half_diag + clearance), so every pad-boundary point is
        // at least `clearance` from the halo boundary.  The 1e-6 tolerance
        // is pure floating-point slack, NOT the constructor's eps — eps only
        // bounds how far OUTSIDE the clearance disc the vertices sit, and
        // cannot weaken the minimum distance.
        let tol = 1e-6;

        // Circular pads.
        for &(radius, clearance, eps) in &[(1.0, 0.5, 0.01), (2.0, 2.0, 0.01), (3.0, 12.6, 0.001)] {
            let halo = ClearanceHalo::from_circular_pad(origin, radius, clearance, eps);
            let pad_pts = sample_circle_points(origin, radius, 360);
            let min_d = min_pad_to_halo_distance(&pad_pts, &halo);
            assert!(
                min_d >= clearance - tol,
                "circular pad radius={radius} clearance={clearance} eps={eps}: \
                 min pad-to-halo distance {min_d} < clearance"
            );
        }

        // Rectangular pads at the production creepage figure — the
        // 3.0x2.0 mm PTH relay-pad scenario that measured 12.48 vs 12.60 mm
        // on the board.  The half-width construction fails here (corner
        // reach 14.1 - hypot(1.5, 1.0) = 12.297 < 12.6).
        for &(w, h) in &[
            (1.0, 0.6),
            (2.0, 2.0),
            (5.0, 0.3),
            (1.95, 0.6),
            (3.0, 2.0), // the PTH relay pad from the 2026-08-16 measurement
        ] {
            let clearance = 12.6;
            let halo = ClearanceHalo::from_rect_pad(origin, w, h, 0.0, 0.0, clearance, 0.001);
            let pad_pts = rect_perimeter_points(origin, w, h, 64);
            let min_d = min_pad_to_halo_distance(&pad_pts, &halo);
            assert!(
                min_d >= clearance - tol,
                "rect pad {w}x{h} clearance={clearance}: min pad-to-halo distance {min_d} \
                 < clearance (corner reach under-cut)"
            );
        }
    }

    // ------------------------------------------------------------------
    // Delta (2026-08-16, second pass): tracks, vias, the guarantee marker,
    // and the clearance floor via the public distance_to_boundary
    // ------------------------------------------------------------------

    /// The guarantee marker is present and observable on every halo — the
    /// structural check that the value passed a verified construction.
    #[cfg_attr(test, test)]
    fn guarantee_marker_is_minted_by_every_constructor() {
        let origin = Point::new(0.0, 0.0);
        let halos = [
            ClearanceHalo::from_circular_pad(origin, 1.0, 12.6, 0.01),
            ClearanceHalo::from_rect_pad(origin, 3.0, 2.0, 0.0, 0.7, 12.6, 0.01),
            ClearanceHalo::from_track(
                Point::new(-5.0, -2.0),
                Point::new(7.0, 3.0),
                0.635,
                12.6,
                0.01,
            ),
            ClearanceHalo::from_via(origin, 1.0, 12.6, 0.01),
            ClearanceHalo::from_circular_pad_with_segments(origin, 1.0, 12.6, 24),
            ClearanceHalo::from_rect_pad_with_segments(origin, 3.0, 2.0, 0.0, 0.0, 12.6, 24),
            ClearanceHalo::from_track_with_segments(
                Point::new(0.0, 0.0),
                Point::new(10.0, 0.0),
                0.635,
                12.6,
                24,
            ),
        ];
        for halo in &halos {
            assert!(
                halo.polygon().exterior().coords().count() >= 8,
                "halo polygon too small"
            );
            let _g = halo.guarantee(); // observable, not fabricable externally
        }
    }

    /// Track (capsule) halo: the fundamental clearance floor via the public
    /// `distance_to_boundary` — straight sides and cap semicircles of the
    /// obstacle capsule must all clear the halo boundary by >= clearance.
    #[cfg_attr(test, test)]
    fn track_halo_clearance_guarantee() {
        let start = Point::new(-5.0, -2.0);
        let end = Point::new(7.0, 3.0);
        let width = 0.635;
        let clearance = 12.6;
        let halo = ClearanceHalo::from_track(start, end, width, clearance, 0.01);
        let r_obstacle = width / 2.0;
        let dx = end.x() - start.x();
        let dy = end.y() - start.y();
        let len = (dx * dx + dy * dy).sqrt();
        let (px, py) = (-dy / len, dx / len);
        // Straight sides of the obstacle capsule at distance width/2.
        for k in 0..=64 {
            let t = (k as f64) / 64.0;
            let sx = start.x() + dx * t;
            let sy = start.y() + dy * t;
            for sign in [1.0, -1.0] {
                let p = Point::new(sx + sign * px * r_obstacle, sy + sign * py * r_obstacle);
                let d = halo.distance_to_boundary(&p);
                assert!(
                    d >= clearance - 1e-9,
                    "track side point ({}, {}) is {d} from halo boundary, below clearance \
                     {clearance}",
                    p.x(),
                    p.y()
                );
            }
        }
        // Cap semicircles of the obstacle capsule at radius width/2 from the
        // endpoints.
        for i in 0..=128 {
            let a = PI * (i as f64) / 128.0;
            for (cxp, cyp) in [(start.x(), start.y()), (end.x(), end.y())] {
                for (dirx, diry) in [
                    (px * a.cos() - py * a.sin(), px * a.sin() + py * a.cos()),
                    (px * a.cos() + py * a.sin(), -px * a.sin() + py * a.cos()),
                ] {
                    let p = Point::new(cxp + dirx * r_obstacle, cyp + diry * r_obstacle);
                    let d = halo.distance_to_boundary(&p);
                    assert!(
                        d >= clearance - 1e-9,
                        "track cap point ({}, {}) is {d} from halo boundary, below clearance \
                         {clearance}",
                        p.x(),
                        p.y()
                    );
                }
            }
        }
    }

    /// Via halo: the via's circumference clears the halo boundary by at
    /// least the clearance, and the via centre is inside the halo.
    #[cfg_attr(test, test)]
    fn via_halo_clearance_guarantee() {
        let center = Point::new(3.5, -9.25);
        let diameter = 1.2;
        let clearance = 12.6;
        let halo = ClearanceHalo::from_via(center, diameter, clearance, 0.01);
        for p in sample_circle_points(center, diameter / 2.0, 128) {
            let d = halo.distance_to_boundary(&p);
            assert!(
                d >= clearance - 1e-9,
                "via-boundary point ({}, {}) is {d} from halo boundary, below clearance {clearance}",
                p.x(),
                p.y()
            );
        }
        assert!(halo.contains(center), "via centre not contained");
    }


    // ------------------------------------------------------------------
    // Randomized properties (nested module: its own wasm-registry census
    // entry, excluded as a proptest dev-dependency — the outer tests module
    // stays registered).  `#[cfg(test)]` ONLY: proptest is a dev-dependency,
    // absent from the non-test wasm-registry build this module would
    // otherwise break.
    // ------------------------------------------------------------------

    // `items_after_test_module` on THIS declaration: the wasm-registry
    // generator always appends the `WASM_TESTS` const after the whole
    // module body, so this cfg(test) submodule is unavoidably followed by
    // items. The ordering is generator-forced.
    #[cfg(test)]
    #[allow(clippy::items_after_test_module)]
    mod proptests {
        use super::*;
        use proptest::prelude::*;

        proptest! {
            /// For random circular pads (off-origin centres, arbitrary
            /// clearances), the halo contains the true circle and the
            /// clearance floor holds.
            #[test]
            fn circle_halo_contains_circle_property(
                cx in -100.0f64..100.0,
                cy in -100.0f64..100.0,
                radius in 0.05f64..50.0,
                clearance in 0.0f64..30.0,
                epsilon in 0.001f64..0.5,
            ) {
                let center = Point::new(cx, cy);
                let halo = ClearanceHalo::from_circular_pad(center, radius, clearance, epsilon);
                let r = radius + clearance;
                let n = halo.polygon().exterior().coords().count();
                // Edge-midpoint directions are the tightest; sample several
                // per edge.  Use the boundary-inclusive probe (the witnesses
                // are exactly on the edges).
                for i in 0..(4 * n) {
                    let a = std::f64::consts::TAU * (i as f64) / (4 * n) as f64;
                    let p = Point::new(cx + r * a.cos(), cy + r * a.sin());
                    prop_assert!(
                        contains_boundary_inclusive(halo.polygon(), &p),
                        "circle point at angle {a} not contained (r={radius}, c={clearance}, n={n})"
                    );
                }
                // Clearance floor: pad boundary to halo boundary >= clearance.
                for i in 0..64 {
                    let a = std::f64::consts::TAU * (i as f64) / 64.0;
                    let p = Point::new(cx + radius * a.cos(), cy + radius * a.sin());
                    let d = halo.distance_to_boundary(&p);
                    prop_assert!(
                        d >= clearance - 1e-9,
                        "clearance floor violated: {d} < {clearance} at angle {a}"
                    );
                }
            }

            /// For random rect pads (including elongated and rotated, at
            /// off-origin centres), the four corners and the clearance floor
            /// hold.  This is the property that caught the off-origin
            /// double-translation bug in a draft of the witness machinery.
            #[test]
            fn rect_halo_contains_corners_property(
                cx in -50.0f64..50.0,
                cy in -50.0f64..50.0,
                w in 0.2f64..10.0,
                h in 0.2f64..10.0,
                rotation in -3.2f64..3.2,
                clearance in 0.0f64..30.0,
            ) {
                let center = Point::new(cx, cy);
                let halo =
                    ClearanceHalo::from_rect_pad(center, w, h, 0.0, rotation, clearance, 0.01);
                let (c, s) = (rotation.cos(), rotation.sin());
                for &(dx, dy) in &[
                    (w / 2.0, h / 2.0),
                    (-w / 2.0, h / 2.0),
                    (w / 2.0, -h / 2.0),
                    (-w / 2.0, -h / 2.0),
                ] {
                    let p = Point::new(cx + dx * c - dy * s, cy + dx * s + dy * c);
                    prop_assert!(
                        halo.contains(p),
                        "corner ({dx},{dy}) not contained for {w}x{h} rot {rotation}"
                    );
                    let d = halo.distance_to_boundary(&p);
                    prop_assert!(
                        d >= clearance - 1e-9,
                        "corner ({dx},{dy}) clearance floor violated: {d} < {clearance}"
                    );
                }
            }

            /// For random tracks, the capsule surface clears the halo
            /// boundary by at least the clearance.
            #[test]
            fn track_halo_clearance_floor_property(
                x0 in -50.0f64..50.0,
                y0 in -50.0f64..50.0,
                x1 in -50.0f64..50.0,
                y1 in -50.0f64..50.0,
                width in 0.1f64..3.0,
                clearance in 0.0f64..30.0,
            ) {
                let start = Point::new(x0, y0);
                let end = Point::new(x1, y1);
                let halo = ClearanceHalo::from_track(start, end, width, clearance, 0.01);
                let r_ob = width / 2.0;
                let dx = x1 - x0;
                let dy = y1 - y0;
                let len = (dx * dx + dy * dy).sqrt();
                let (px, py) = if len > 1e-9 { (-dy / len, dx / len) } else { (0.0, 1.0) };
                for k in 0..16 {
                    let t = (k as f64) / 15.0;
                    let sx = x0 + dx * t;
                    let sy = y0 + dy * t;
                    for sign in [1.0, -1.0] {
                        let p = Point::new(sx + sign * px * r_ob, sy + sign * py * r_ob);
                        let d = halo.distance_to_boundary(&p);
                        prop_assert!(
                            d >= clearance - 1e-9,
                            "track side point clearance floor violated: {d} < {clearance}"
                        );
                    }
                }
                // Caps at the endpoints.
                for i in 0..16 {
                    let a = PI * (i as f64) / 15.0;
                    for (cxp, cyp) in [(x0, y0), (x1, y1)] {
                        for (dirx, diry) in [
                            (px * a.cos() - py * a.sin(), px * a.sin() + py * a.cos()),
                            (px * a.cos() + py * a.sin(), -px * a.sin() + py * a.cos()),
                        ] {
                            let p = Point::new(cxp + dirx * r_ob, cyp + diry * r_ob);
                            let d = halo.distance_to_boundary(&p);
                            prop_assert!(
                                d >= clearance - 1e-9,
                                "track cap point clearance floor violated: {d} < {clearance}"
                            );
                        }
                    }
                }
            }
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("clearance_halo::tests::circumscribed_polygon_contains_circle", circumscribed_polygon_contains_circle),
        ("clearance_halo::tests::inscribed_polygon_undercuts_the_circle", inscribed_polygon_undercuts_the_circle),
        ("clearance_halo::tests::rect_halo_contains_all_four_corners", rect_halo_contains_all_four_corners),
        ("clearance_halo::tests::rect_halo_contains_corners_off_origin_and_rotated", rect_halo_contains_corners_off_origin_and_rotated),
        ("clearance_halo::tests::half_width_halo_misses_rect_corners", half_width_halo_misses_rect_corners),
        ("clearance_halo::tests::stress_500_overlapping_halos_union_no_panic", stress_500_overlapping_halos_union_no_panic),
        ("clearance_halo::tests::min_distance_from_pad_boundary_to_halo_boundary_meets_clearance", min_distance_from_pad_boundary_to_halo_boundary_meets_clearance),
        ("clearance_halo::tests::guarantee_marker_is_minted_by_every_constructor", guarantee_marker_is_minted_by_every_constructor),
        ("clearance_halo::tests::track_halo_clearance_guarantee", track_halo_clearance_guarantee),
        ("clearance_halo::tests::via_halo_clearance_guarantee", via_halo_clearance_guarantee),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
