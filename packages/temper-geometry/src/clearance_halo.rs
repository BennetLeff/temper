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
//! (`from_circular_pad` / `from_rect_pad`), and the property tests in this
//! module assert the invariant those constructors claim.  The zone generator
//! can adopt this type in a follow-up; see
//! `docs/evidence/2026-08-16-geometry-invariant-types.md`.
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
//!
//! The field is private: `ClearanceHalo` cannot be assembled from a raw
//! polygon, so a halo that under-covers its obstacle is *unrepresentable*,
//! not merely untested.

use geo::{Contains, Coord, Point, Polygon};

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

/// A clearance halo around an obstacle, guaranteed conservative.
///
/// See the module doc for the construction guarantee.  The polygon field is
/// private precisely so that only the two constructors — which both build a
/// *circumscribed* polygon whose edges sit at the required separation — can
/// create a `ClearanceHalo`.
#[derive(Debug, Clone)]
pub struct ClearanceHalo {
    polygon: Polygon<f64>,
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
    /// * At least an octagon (`n ≥ 8`).
    pub fn from_circular_pad(
        center: Point<f64>,
        radius: f64,
        clearance: f64,
        epsilon_mm: f64,
    ) -> Self {
        let r = radius + clearance;
        // n >= π / acos(r / (r + eps)): a circumscribed n-gon has vertex
        // overshoot r·(sec(π/n) − 1); bounding that by eps gives
        //   r·sec(π/n) <= r + eps
        //   <=> cos(π/n) >= r / (r + eps)
        //   <=> n >= π / acos(r / (r + eps)).
        // Degenerate inputs (r == 0, eps == 0, eps == NaN) make the ratio
        // 0, 1, or NaN; acos handles 0 and 1, and a NaN ratio casts to 0
        // sides, all of which land on the `max(8)` floor — no panic, and
        // containment still holds (it holds for any n >= 3).
        let n = (std::f64::consts::PI / (r / (r + epsilon_mm)).acos())
            .ceil()
            .max(8.0)
            .min(MAX_SIDES as f64) as usize;
        let polygon = circumscribed_regular_polygon(center, r, n);
        Self { polygon }
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
    /// * **`corner_radius` is accepted and ignored.** The rounded rect is a
    ///   subset of the full rect, which is a subset of
    ///   `disc(center, hypot(w/2, h/2))`, so the disc halo is a conservative
    ///   superset of the rounded rect's Minkowski sum for *any* corner
    ///   radius.  The parameter exists for signature stability with future
    ///   tighter constructions.
    /// * **`rotation` is accepted and ignored.** A disc halo is
    ///   rotation-invariant; the corner reach is the same in every
    ///   orientation (the same convention `zone_generator.rs` documents for
    ///   its `ZoneObstacle::Pad`).
    pub fn from_rect_pad(
        center: Point<f64>,
        width: f64,
        height: f64,
        _corner_radius: f64,
        _rotation: f64,
        clearance: f64,
        epsilon_mm: f64,
    ) -> Self {
        let half_diag = ((width / 2.0).powi(2) + (height / 2.0).powi(2)).sqrt();
        Self::from_circular_pad(center, half_diag, clearance, epsilon_mm)
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
}

/// A regular `n`-gon **circumscribing** the circle of radius `r` at `center`:
/// vertices at `r / cos(π/n)`, so every edge is tangent to the circle at
/// distance exactly `r`.  The circle is inside the polygon; the vertices are
/// outside it by `r·(sec(π/n) − 1)`.
fn circumscribed_regular_polygon(center: Point<f64>, r: f64, n: usize) -> Polygon<f64> {
    let vertex_r = r / (std::f64::consts::PI / n as f64).cos();
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
        // this test guards the same call pattern that crashed.
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
        ];
        for case in &cases {
            let mut keepout: MultiPolygon<f64> = MultiPolygon::new(vec![]);
            for center in &case.positions {
                let halo = ClearanceHalo::from_circular_pad(*center, case.radius, case.clearance, case.eps);
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

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("clearance_halo::tests::circumscribed_polygon_contains_circle", circumscribed_polygon_contains_circle),
        ("clearance_halo::tests::rect_halo_contains_all_four_corners", rect_halo_contains_all_four_corners),
        ("clearance_halo::tests::stress_500_overlapping_halos_union_no_panic", stress_500_overlapping_halos_union_no_panic),
        ("clearance_halo::tests::min_distance_from_pad_boundary_to_halo_boundary_meets_clearance", min_distance_from_pad_boundary_to_halo_boundary_meets_clearance),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
