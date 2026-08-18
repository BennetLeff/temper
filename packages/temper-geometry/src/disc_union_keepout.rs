//! `DiscUnionKeepout` — an exact, conservative union of discs.
//!
//! This is the Rust replacement for `router_v6/_ground_plane.py`'s
//! shapely/GEOS keepout construction
//!
//! ```python
//! discs = [Point(x, y).buffer(radius, quad_segs=16) for x, y in hv_positions]
//! keepout = unary_union(discs)
//! ```
//!
//! and for the identical construction inside what is now `hv_copper_discs`
//! (HV pad half-extents and HV vias).  Both are **unions of discs** — never
//! general polygons — and a union of discs has a direct construction that
//! needs no polygon boolean engine at all.  On the production board the two
//! terms are 109 pad-centre discs at `r = 14.1 mm` plus 113 pad/via
//! half-extent discs: 222 in total, one union.
//!
//! # Why this is more accurate than the GEOS path it replaces
//!
//! `shapely`'s `Point.buffer(r, quad_segs=16)` is a **64-gon inscribed in the
//! circle**: its vertices sit on the circle and its *edges* sit at
//! `r·cos(π/64)`.  For the production keepout radius (`13.1 + 1.0 = 14.1 mm`)
//! that is `14.099831 mm` — the emitted keepout **under-covers the required
//! disc by 1.69e-2 mm all the way around**, which is exactly the
//! inscribed-polygon undercut that [`crate::clearance_halo`]'s module doc
//! records as measured bug 1.  Matching that polygon bit-for-bit would
//! reproduce the undercut.  Measured over all 222 discs of the real board's
//! keepout (2026-08-18): worst shapely under-coverage **2.259e-2 mm**, on an
//! 18.757 mm HV pad half-extent disc; this module's worst is **0.0 mm**, and
//! the shapely keepout is a strict subset of this one (`old \ new` is
//! empty, `new \ old` is 21.93 mm² of extra claimed area, +0.0798%).
//!
//! This module instead does what `ClearanceHalo` does: it bounds the
//! approximation error on the *outside*.  Every emitted edge sits at distance
//! `≥ r` from its centre, so the emitted keepout is a superset of the true
//! disc union — and therefore also a strict superset of the 64-gon union it
//! replaces, point for point.
//!
//! # The construction (no polygon booleans)
//!
//! For a set of discs `D_i = disc(c_i, r_i)`, a point on circle `i` is on the
//! boundary of `⋃ D_i` exactly when it is not strictly inside any other disc.
//! For each pair `(i, j)` the part of circle `i` inside disc `j` is a single
//! angular interval centred on the direction `c_j − c_i` with half-width
//! `acos((r_i² + d² − r_j²) / (2·r_i·d))`.  So:
//!
//! 1. per circle, subtract the covered intervals from `[0, 2π)`; what remains
//!    are the circle's **boundary arcs**;
//! 2. chain them — walking a circle CCW keeps the union on the left, so at the
//!    end of an arc on circle `i` (where circle `i` enters disc `j`) the
//!    boundary continues CCW along circle `j`, which is exiting disc `i` at
//!    that same point.  The successor is therefore known *by index*, not by
//!    a proximity search over a soup of vertices;
//! 3. emit each arc as a polyline **inscribed in the inflated circle**: the
//!    topology is computed on `R_i = r_i + SAFETY + eps` and every vertex sits
//!    exactly on that circle, subdivided finely enough that each chord's
//!    closest approach is still `≥ R_i − eps ≥ r_i`.  The emitted geometry is
//!    therefore sandwiched, `⋃ disc(c_i, r_i) ⊆ emitted ⊆ ⋃ disc(c_i, R_i)`:
//!    the left inclusion is the safety guarantee, and the right one is what
//!    keeps two pieces the union calls separate from overlapping each other
//!    (a randomized property test caught exactly that, with two discs 0.011 mm
//!    apart, when the polyline overhung its circle instead);
//! 4. loops with positive signed area are outer rings, negative are holes
//!    (the CCW walk orients them automatically); holes are nested into the
//!    smallest outer ring that contains them.
//!
//! # The guarantee, enforced at construction
//!
//! [`DiscUnionKeepout`]'s outline field is private and its only constructor
//! runs [`ContainsEveryDisc::verified`], which checks, **for every required
//! disc** (including ones dropped as redundant):
//!
//! * `c_i` is inside the emitted region, and
//! * **no emitted edge — of any ring, outer or hole — comes within `r_i` of
//!   `c_i`**.
//!
//! Those two conditions together are a *proof*, not a sample: a disc is
//! connected, so if its centre is inside the region and its boundary never
//! meets the region's boundary, the whole disc is inside the region.  This is
//! strictly stronger than a witness-point check — there is no set of sample
//! points to get wrong.
//!
//! The check runs with **zero tolerance** (`≥ r_i`, not `≥ r_i − ε`).  That is
//! affordable because the construction inflates every working radius by
//! [`SAFETY_INFLATION_MM`] (1 nm) on top of `eps` before unioning, so the
//! emitted boundary clears the *required* radius by a margin many orders of
//! magnitude above floating-point noise, while claiming 1 nm of extra board
//! area.  Same idiom as `ClearanceHalo`'s `eps`: a cost knob, never a
//! correctness risk.
//!
//! A construction that cannot hold the guarantee returns
//! [`KeepoutError::ContainmentViolation`] — it does not return a keepout.  An
//! under-covering `DiscUnionKeepout` is unrepresentable, not merely untested.

use crate::polygon::point_in_polygon_winding;
use crate::types::Point;
use std::f64::consts::TAU;

/// Approximation budget, in mm.  The keepout is drawn on circles inflated by
/// this much, so it claims at most `eps` of extra board area beyond the true
/// disc union — and never less than zero.  Only affects area and vertex
/// count; never the containment guarantee, which holds for any positive
/// value.
///
/// 0.01 mm (10 µm) is a little under the 1.69e-2 mm the shapely path's own
/// inscribed 64-gon was wrong by in the *unsafe* direction, and well below any
/// DRC-relevant dimension on this board.
pub const DEFAULT_EPSILON_MM: f64 = 0.01;

/// Extra outward inflation, in mm, applied on top of `eps` to every disc
/// radius before the union is computed, so that the containment check can run
/// with zero tolerance against the *required* radii.
///
/// 1e-6 mm = 1 nanometre: ~7 orders of magnitude above the f64 noise floor of
/// this board's coordinates (~1e-13 mm at x ≈ 200 mm) and ~4 orders of
/// magnitude below the smallest dimension any DRU rule on this board names
/// (0.05 mm).  It can only ever make the keepout larger.
pub const SAFETY_INFLATION_MM: f64 = 1e-6;

/// Two vertices closer than this (mm) are treated as the same point when a
/// ring is assembled.  Arc endpoints are computed twice — once from each of
/// the two circles meeting there — and the two results differ by f64 noise
/// (~1e-13 mm here).  Collapsing them avoids emitting zero-length edges; the
/// collapse can move the boundary by at most this distance, which is
/// [`SAFETY_INFLATION_MM`]/1000 and therefore cannot consume the inflation
/// margin.
const VERTEX_MERGE_MM: f64 = 1e-9;

/// Maximum number of segments used for a single arc.  A pure cost cap: more
/// segments only ever tightens the approximation, so capping can never turn a
/// safe keepout into an unsafe one (same reasoning as
/// [`crate::clearance_halo::MAX_SIDES`]).
const MAX_ARC_SEGMENTS: usize = 4096;

/// A disc: everything this module unions.
#[derive(Debug, Clone, Copy, PartialEq)]
pub struct Disc {
    pub center: Point,
    pub radius: f64,
}

impl Disc {
    pub fn new(x: f64, y: f64, radius: f64) -> Self {
        Self {
            center: Point::new(x, y),
            radius,
        }
    }
}

/// One connected piece of the keepout: an outer ring plus its holes.  Rings
/// are open (the closing vertex is not repeated); the outer ring is CCW and
/// holes are CW.
#[derive(Debug, Clone, PartialEq)]
pub struct KeepoutOutline {
    pub exterior: Vec<Point>,
    pub holes: Vec<Vec<Point>>,
}

/// Why a keepout could not be constructed.
#[derive(Debug, Clone, PartialEq)]
pub enum KeepoutError {
    /// No disc with a positive radius was supplied.  The caller must treat
    /// this as "cannot establish a keepout", never as "no keepout needed" —
    /// the same contract `compute_hv_selv_keepout`'s `None` already carries.
    NoDiscs,
    /// A disc radius was negative, NaN or infinite, or a centre coordinate
    /// was not finite.
    InvalidDisc(usize),
    /// The arc walk did not close into loops — a numerical failure in the
    /// boundary construction.  Never silently patched over: an unclosed
    /// boundary cannot carry the containment guarantee.
    ArcChainBroken(String),
    /// The emitted region failed the containment proof for the disc at this
    /// index.  Carries the measured shortfall in mm.
    ContainmentViolation { disc: usize, shortfall_mm: f64 },
}

impl std::fmt::Display for KeepoutError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        match self {
            Self::NoDiscs => write!(f, "no discs with positive radius were supplied"),
            Self::InvalidDisc(i) => write!(f, "disc #{i} has a non-finite or negative parameter"),
            Self::ArcChainBroken(why) => write!(f, "disc-union arc chain broken: {why}"),
            Self::ContainmentViolation { disc, shortfall_mm } => write!(
                f,
                "keepout containment violation: required disc #{disc} is NOT fully inside the \
                 emitted keepout (short by {shortfall_mm} mm). A keepout that under-covers a \
                 required disc is a clearance reduction by another route; refusing to emit it."
            ),
        }
    }
}

impl std::error::Error for KeepoutError {}

/// ZST marker proving the containment proof ran and passed for every required
/// disc.
///
/// The field is private and the only constructor is private, so this marker
/// can only be minted by [`DiscUnionKeepout`]'s verified construction path —
/// external code can name the type but cannot fabricate the guarantee.
#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub struct ContainsEveryDisc {
    _private: (),
}

impl ContainsEveryDisc {
    /// The ONLY way to construct a `ContainsEveryDisc`.
    ///
    /// For each required disc: the centre must be inside the region, and no
    /// emitted edge may come within `radius` of the centre.  Together those
    /// imply the entire disc is contained (the disc is connected and its
    /// boundary never meets the region's boundary).
    fn verified(outlines: &[KeepoutOutline], required: &[Disc]) -> Result<Self, KeepoutError> {
        check_containment(outlines, required)?;
        Ok(Self { _private: () })
    }
}

/// The containment proof itself, separated from the marker so the property
/// tests can run the identical predicate against a **deliberately broken**
/// construction and watch it fail (see the `tests::anti_vacuity` block).  A
/// property test that cannot fail proves nothing.
pub(crate) fn check_containment(
    outlines: &[KeepoutOutline],
    required: &[Disc],
) -> Result<(), KeepoutError> {
    for (i, d) in required.iter().enumerate() {
        if !region_contains_point(outlines, &d.center) {
            return Err(KeepoutError::ContainmentViolation {
                disc: i,
                shortfall_mm: d.radius,
            });
        }
        let clearance = min_distance_to_region_boundary(outlines, &d.center, d.radius);
        if clearance < d.radius {
            return Err(KeepoutError::ContainmentViolation {
                disc: i,
                shortfall_mm: d.radius - clearance,
            });
        }
    }
    Ok(())
}

/// A keepout region guaranteed to contain every disc it was built from.
///
/// See the module doc.  The outline field is private precisely so that only
/// the verified constructor can create a value: a keepout that under-covers a
/// required disc cannot be built.
#[derive(Debug, Clone)]
pub struct DiscUnionKeepout {
    outlines: Vec<KeepoutOutline>,
    _guarantee: ContainsEveryDisc,
}

impl DiscUnionKeepout {
    /// Build the union of `discs`, as a conservative superset.
    ///
    /// Deterministic: the discs are canonicalised (sorted, deduped) before
    /// anything else runs, and every emitted ring is rotated to start at its
    /// lexicographically smallest vertex, so the output is byte-identical for
    /// the same disc *set* regardless of the order it arrives in.
    pub fn new(discs: &[Disc], epsilon_mm: f64) -> Result<Self, KeepoutError> {
        for (i, d) in discs.iter().enumerate() {
            if !d.center.x.is_finite() || !d.center.y.is_finite() || !d.radius.is_finite() {
                return Err(KeepoutError::InvalidDisc(i));
            }
            if d.radius < 0.0 {
                return Err(KeepoutError::InvalidDisc(i));
            }
        }
        let required = canonical_discs(discs);
        if required.is_empty() {
            return Err(KeepoutError::NoDiscs);
        }
        let eps = if epsilon_mm.is_finite() && epsilon_mm > 0.0 {
            epsilon_mm
        } else {
            DEFAULT_EPSILON_MM
        };
        // INFLATE, THEN INSCRIBE.  The union topology is computed on the
        // *outer* circles `R_i = r_i + SAFETY_INFLATION_MM + eps`, and every
        // emitted vertex sits exactly ON its outer circle, so the emitted
        // geometry is sandwiched:
        //
        //     ⋃ disc(c_i, r_i)  ⊆  emitted  ⊆  ⋃ disc(c_i, R_i)
        //
        // The left containment is the safety guarantee (proved below).  The
        // right containment is what keeps the emitted *pieces* disjoint:
        // two pieces the union says are separate are separate in R-space, so
        // their approximations cannot overlap.  Building the polyline the
        // other way round (vertices overhanging the circle, edges tangent to
        // it) satisfies the left containment but not the right, and a
        // randomized property test caught it directly: two discs 0.011 mm
        // apart -- disjoint, so two separate pieces -- had polygons that
        // overlapped, because each vertex overhung its circle by up to
        // `eps` = 0.01 mm.  A pair of overlapping rings is an invalid
        // MultiPolygon downstream.
        let working: Vec<Disc> = required
            .iter()
            .map(|d| Disc {
                center: d.center,
                radius: d.radius + SAFETY_INFLATION_MM + eps,
            })
            .collect();
        let outlines = union_of_discs(&working, eps, ArcMode::InscribedInOuter)?;
        let _guarantee = ContainsEveryDisc::verified(&outlines, &required)?;
        Ok(Self {
            outlines,
            _guarantee,
        })
    }

    /// The keepout pieces (outer ring + holes each).
    pub fn outlines(&self) -> &[KeepoutOutline] {
        &self.outlines
    }

    /// The guarantee marker proving the containment proof ran and passed.
    pub fn guarantee(&self) -> &ContainsEveryDisc {
        &self._guarantee
    }

    /// Total area of the keepout (outer rings minus holes), mm².
    pub fn area_mm2(&self) -> f64 {
        self.outlines
            .iter()
            .map(|o| {
                signed_area(&o.exterior).abs()
                    - o.holes.iter().map(|h| signed_area(h).abs()).sum::<f64>()
            })
            .sum()
    }

    /// Total emitted vertex count across every ring.
    pub fn vertex_count(&self) -> usize {
        self.outlines
            .iter()
            .map(|o| o.exterior.len() + o.holes.iter().map(Vec::len).sum::<usize>())
            .sum()
    }

    /// Whether `p` is inside the keepout (outer ring and not in a hole).
    pub fn contains_point(&self, p: &Point) -> bool {
        region_contains_point(&self.outlines, p)
    }

    /// Whether any two non-adjacent edges of any ring properly cross.
    ///
    /// Ring-touching at a single point (exactly tangent circles) is not a
    /// crossing and is not reported.  O(n²) in the emitted vertex count with
    /// a bounding-box reject — a verification helper for tests, not a
    /// production-path check.
    pub fn has_self_intersection(&self) -> bool {
        let mut rings: Vec<&Vec<Point>> = Vec::new();
        for o in &self.outlines {
            rings.push(&o.exterior);
            for h in &o.holes {
                rings.push(h);
            }
        }
        let mut edges: Vec<(Point, Point, usize, usize)> = Vec::new();
        for (ri, ring) in rings.iter().enumerate() {
            let n = ring.len();
            for i in 0..n {
                edges.push((ring[i], ring[(i + 1) % n], ri, i));
            }
        }
        for (a, &(p1, p2, ra, ia)) in edges.iter().enumerate() {
            let (aminx, amaxx) = (p1.x.min(p2.x), p1.x.max(p2.x));
            let (aminy, amaxy) = (p1.y.min(p2.y), p1.y.max(p2.y));
            for &(p3, p4, rb, ib) in edges.iter().skip(a + 1) {
                // Adjacent edges of the same ring share an endpoint by
                // construction; that is not a crossing.
                if ra == rb {
                    let n = rings[ra].len();
                    if ib == (ia + 1) % n || ia == (ib + 1) % n {
                        continue;
                    }
                }
                if p3.x.min(p4.x) > amaxx
                    || p3.x.max(p4.x) < aminx
                    || p3.y.min(p4.y) > amaxy
                    || p3.y.max(p4.y) < aminy
                {
                    continue;
                }
                if segments_properly_cross(&p1, &p2, &p3, &p4) {
                    return true;
                }
            }
        }
        false
    }
}

// ---------------------------------------------------------------------------
// Canonicalisation
// ---------------------------------------------------------------------------

/// Sort by `(x, y, radius)` on the f64 total order and drop exact duplicates
/// and zero-radius discs.  Making the disc list order-independent is what
/// makes the emitted geometry order-independent.
fn canonical_discs(discs: &[Disc]) -> Vec<Disc> {
    let mut out: Vec<Disc> = discs.iter().copied().filter(|d| d.radius > 0.0).collect();
    out.sort_by(|a, b| {
        a.center
            .x
            .total_cmp(&b.center.x)
            .then_with(|| a.center.y.total_cmp(&b.center.y))
            .then_with(|| a.radius.total_cmp(&b.radius))
    });
    out.dedup_by(|a, b| {
        a.center.x == b.center.x && a.center.y == b.center.y && a.radius == b.radius
    });
    out
}

// ---------------------------------------------------------------------------
// The disc union
// ---------------------------------------------------------------------------

/// How an arc is turned into line segments.
///
/// Every variant places its vertices at some radius on the arc's own angular
/// range; they differ only in *which* radius, and that single choice is what
/// decides whether the emitted region covers the required disc or cuts into
/// it.
///
/// Production uses [`ArcMode::InscribedInOuter`] and nothing else —
/// [`DiscUnionKeepout::new`], the only public constructor, hardcodes it.  The
/// other two variants exist **solely to prove the guarantee is not vacuous**:
/// they reproduce, on demand, the two ways a disc union can under-cover, so
/// the property tests can be shown failing against them.  A property test that
/// has never been observed to fail is worth nothing.
#[derive(Debug, Clone, Copy, PartialEq)]
pub(crate) enum ArcMode {
    /// Vertices exactly ON the outer circle `R` the union topology was
    /// computed with, subdivided finely enough that every chord's midpoint
    /// still sits at `≥ R − eps`.  The polyline is therefore inside
    /// `disc(c, R)` (so separate pieces stay separate) and outside
    /// `disc(c, R − eps)` (so the required disc stays covered).
    InscribedInOuter,
    /// BROKEN ON PURPOSE.  Vertices pulled in to `R − eps`, the *required*
    /// circle — this is what `shapely`'s `Point.buffer(r, quad_segs=16)`
    /// emits, and its chords fall inside the required circle by
    /// `r·(1 − cos(δ/2))`.
    #[allow(dead_code)]
    OnRequiredCircle,
    /// BROKEN ON PURPOSE.  Vertices pulled in by this many mm — a keepout
    /// that is simply too small.
    #[allow(dead_code)]
    Shrunk(f64),
}

/// One boundary arc of the union, CCW on its own circle.
#[derive(Debug, Clone, Copy)]
struct Arc {
    circle: usize,
    start: f64,
    end: f64,
    /// Circle the boundary continues onto at `end`.  `usize::MAX` for a whole
    /// free circle, which closes on itself.
    next_circle: usize,
}

pub(crate) fn union_of_discs(
    discs: &[Disc],
    eps: f64,
    mode: ArcMode,
) -> Result<Vec<KeepoutOutline>, KeepoutError> {
    let n = discs.len();
    // 1. Drop discs swallowed whole by another disc: they contribute no
    // boundary, and leaving them in would produce covered-everywhere circles.
    let mut swallowed = vec![false; n];
    for i in 0..n {
        for j in 0..n {
            if i == j || swallowed[j] {
                continue;
            }
            let d = discs[i].center.distance(&discs[j].center);
            if d + discs[i].radius <= discs[j].radius {
                swallowed[i] = true;
                break;
            }
        }
    }
    let live: Vec<usize> = (0..n).filter(|i| !swallowed[*i]).collect();

    // 2. Per live circle: the free (boundary) arcs.
    let mut arcs: Vec<Arc> = Vec::new();
    let mut arcs_of_circle: Vec<Vec<usize>> = vec![Vec::new(); n];
    for &i in &live {
        let mut covered: Vec<(f64, f64, usize)> = Vec::new(); // start, end, source
        let mut fully_covered = false;
        for &j in &live {
            if i == j {
                continue;
            }
            let ci = discs[i].center;
            let cj = discs[j].center;
            let (ri, rj) = (discs[i].radius, discs[j].radius);
            let d = ci.distance(&cj);
            if d >= ri + rj {
                continue; // disjoint or externally tangent: no coverage
            }
            if d + rj <= ri {
                continue; // j sits inside i: covers none of circle i
            }
            if d + ri <= rj {
                fully_covered = true; // should be unreachable (step 1)
                break;
            }
            if d <= 0.0 {
                continue; // concentric; handled by the containment cases above
            }
            let k = ((ri * ri + d * d - rj * rj) / (2.0 * ri * d)).clamp(-1.0, 1.0);
            let alpha = k.acos();
            if alpha <= 0.0 {
                continue; // tangent: a zero-width interval covers nothing
            }
            let phi = (cj.y - ci.y).atan2(cj.x - ci.x);
            let s = norm_angle(phi - alpha);
            let len = 2.0 * alpha;
            if len >= TAU {
                fully_covered = true;
                break;
            }
            if s + len <= TAU {
                covered.push((s, s + len, j));
            } else {
                covered.push((s, TAU, j));
                covered.push((0.0, s + len - TAU, j));
            }
        }
        if fully_covered {
            continue;
        }
        if covered.is_empty() {
            let idx = arcs.len();
            arcs.push(Arc {
                circle: i,
                start: 0.0,
                end: TAU,
                next_circle: usize::MAX,
            });
            arcs_of_circle[i].push(idx);
            continue;
        }
        // Merge the covered intervals, keeping the source disc of each
        // merged interval's start and end -- those sources are the circles
        // the boundary arrives from / departs to.
        covered.sort_by(|a, b| a.0.total_cmp(&b.0));
        let mut merged: Vec<(f64, f64, usize, usize)> = Vec::new(); // s, e, src_s, src_e
        for &(s, e, src) in &covered {
            match merged.last_mut() {
                Some(last) if s <= last.1 => {
                    if e > last.1 {
                        last.1 = e;
                        last.3 = src;
                    }
                }
                _ => merged.push((s, e, src, src)),
            }
        }
        // Wrap-around: a covered interval touching 2π joins one touching 0.
        if merged.len() > 1 {
            let first = merged[0];
            let last_i = merged.len() - 1;
            if merged[last_i].1 >= TAU && first.0 <= 0.0 {
                merged[last_i].1 = TAU + first.1;
                merged[last_i].3 = first.3;
                merged.remove(0);
            }
        }
        // One merged interval spanning a full turn means the circle is
        // covered everywhere.  Compared as a LENGTH, not against `[0, TAU]`:
        // after the wrap-around join above the single interval can read
        // e.g. `[2.0, 2.0 + TAU]`, which covers everything without either
        // endpoint touching 0 or 2π.
        if merged.len() == 1 && merged[0].1 - merged[0].0 >= TAU {
            continue; // covered all the way round
        }
        // The gaps between consecutive covered intervals are the free arcs.
        for w in 0..merged.len() {
            // Only the END of this covered interval and the START of the next
            // one matter: the free arc runs between them, and the disc that
            // opened the NEXT interval is the circle the boundary turns onto.
            let e = merged[w].1;
            let (s_next, _, src_s_next, _) = merged[(w + 1) % merged.len()];
            let start = norm_angle(e);
            let mut end = norm_angle(s_next);
            if end <= start {
                end += TAU;
            }
            if end - start <= 0.0 {
                continue;
            }
            let idx = arcs.len();
            arcs.push(Arc {
                circle: i,
                start,
                end,
                next_circle: src_s_next,
            });
            arcs_of_circle[i].push(idx);
        }
    }

    if arcs.is_empty() {
        return Err(KeepoutError::ArcChainBroken(
            "no boundary arcs survived; every circle was reported fully covered".into(),
        ));
    }

    // 3. Successor of each arc: the arc on `next_circle` that starts at the
    // same point.  Known by index, then pinned by angle -- no vertex-soup
    // proximity search.
    let mut successor = vec![usize::MAX; arcs.len()];
    for (ai, arc) in arcs.iter().enumerate() {
        if arc.next_circle == usize::MAX {
            successor[ai] = ai; // whole free circle: a loop on its own
            continue;
        }
        let c = discs[arc.circle].center;
        let r = discs[arc.circle].radius;
        let p = Point::new(c.x + r * arc.end.cos(), c.y + r * arc.end.sin());
        let cj = discs[arc.next_circle].center;
        let theta = norm_angle((p.y - cj.y).atan2(p.x - cj.x));
        let mut best = usize::MAX;
        let mut best_gap = f64::INFINITY;
        for &cand in &arcs_of_circle[arc.next_circle] {
            let gap = angular_gap(norm_angle(arcs[cand].start), theta);
            if gap < best_gap {
                best_gap = gap;
                best = cand;
            }
        }
        if best == usize::MAX || best_gap > 1e-6 {
            return Err(KeepoutError::ArcChainBroken(format!(
                "arc on circle {} ending at angle {} found no continuation on circle {} \
                 (closest arc start was {best_gap} rad away)",
                arc.circle, arc.end, arc.next_circle
            )));
        }
        successor[ai] = best;
    }
    // The successor map must be a permutation, or the walk cannot close.
    let mut indegree = vec![0usize; arcs.len()];
    for &s in &successor {
        indegree[s] += 1;
    }
    if let Some(bad) = indegree.iter().position(|d| *d != 1) {
        return Err(KeepoutError::ArcChainBroken(format!(
            "arc {bad} has in-degree {} in the successor map (expected exactly 1); the \
             boundary walk is not a set of disjoint closed loops",
            indegree[bad]
        )));
    }

    // 4. Walk the loops and polygonise.
    let mut visited = vec![false; arcs.len()];
    let mut rings: Vec<Vec<Point>> = Vec::new();
    for start_arc in 0..arcs.len() {
        if visited[start_arc] {
            continue;
        }
        let mut ring: Vec<Point> = Vec::new();
        let mut cur = start_arc;
        let mut steps = 0usize;
        loop {
            visited[cur] = true;
            let arc = arcs[cur];
            push_arc_polyline(&mut ring, &discs[arc.circle], arc.start, arc.end, eps, mode);
            cur = successor[cur];
            steps += 1;
            if cur == start_arc {
                break;
            }
            if visited[cur] || steps > arcs.len() {
                return Err(KeepoutError::ArcChainBroken(
                    "boundary walk re-entered a visited arc without closing its loop".into(),
                ));
            }
        }
        close_ring(&mut ring);
        if ring.len() >= 3 {
            rings.push(ring);
        }
    }

    // 5. Outer rings vs holes: the CCW walk orients outer rings positively
    // and holes negatively.
    let mut outers: Vec<Vec<Point>> = Vec::new();
    let mut holes: Vec<Vec<Point>> = Vec::new();
    for ring in rings {
        if signed_area(&ring) >= 0.0 {
            outers.push(ring);
        } else {
            holes.push(ring);
        }
    }
    // Deterministic ring order: largest |area| first, then lexicographic on
    // the first vertex.
    let order = |a: &Vec<Point>, b: &Vec<Point>| {
        let aa = signed_area(a).abs();
        let ba = signed_area(b).abs();
        ba.total_cmp(&aa).then_with(|| {
            let av = a.first().copied().unwrap_or(Point::zero());
            let bv = b.first().copied().unwrap_or(Point::zero());
            av.x.total_cmp(&bv.x).then_with(|| av.y.total_cmp(&bv.y))
        })
    };
    for r in outers.iter_mut() {
        rotate_to_canonical_start(r);
    }
    for r in holes.iter_mut() {
        rotate_to_canonical_start(r);
    }
    outers.sort_by(order);
    holes.sort_by(order);

    let mut result: Vec<KeepoutOutline> = outers
        .into_iter()
        .map(|exterior| KeepoutOutline {
            exterior,
            holes: Vec::new(),
        })
        .collect();
    for hole in holes {
        let probe = match hole.first() {
            Some(p) => *p,
            None => continue,
        };
        // Smallest containing outer ring: a hole can sit inside a piece that
        // itself sits inside another piece's hole.
        let mut best: Option<usize> = None;
        let mut best_area = f64::INFINITY;
        for (oi, o) in result.iter().enumerate() {
            if point_in_polygon_winding(&probe, &o.exterior) {
                let a = signed_area(&o.exterior).abs();
                if a < best_area {
                    best_area = a;
                    best = Some(oi);
                }
            }
        }
        match best {
            Some(oi) => result[oi].holes.push(hole),
            None => {
                return Err(KeepoutError::ArcChainBroken(
                    "a clockwise (hole) loop was not contained by any outer ring".into(),
                ));
            }
        }
    }
    Ok(result)
}

/// Append the polyline of the CCW arc `[start, end]` on `disc`, whose radius
/// is the **outer** radius `R` the union topology was computed with.
///
/// Vertices land on the `R` circle at equally-spaced angles, including both
/// arc endpoints — so consecutive arcs meet exactly at the circle-circle
/// intersection point they share, and the ring closes without a stitch.  The
/// spacing satisfies `δ ≤ 2·acos(1 − eps/R)`, which puts every chord's closest
/// approach to the centre at `R·cos(δ/2) ≥ R − eps`: the polyline never dips
/// below the required radius, and never rises above `R`.
fn push_arc_polyline(
    out: &mut Vec<Point>,
    disc: &Disc,
    start: f64,
    end: f64,
    eps: f64,
    mode: ArcMode,
) {
    let r_outer = disc.radius;
    let sweep = end - start;
    let delta_max = if r_outer > 0.0 {
        2.0 * (1.0 - eps / r_outer).clamp(-1.0, 1.0).acos()
    } else {
        0.0
    };
    let n = if delta_max > 0.0 {
        ((sweep / delta_max).ceil() as usize).clamp(1, MAX_ARC_SEGMENTS)
    } else {
        MAX_ARC_SEGMENTS
    };
    let delta = sweep / n as f64;
    // The one line that decides whether the emitted region contains the
    // required disc or cuts into it.
    let vertex_r = match mode {
        ArcMode::InscribedInOuter => r_outer,
        ArcMode::OnRequiredCircle => (r_outer - eps).max(0.0),
        ArcMode::Shrunk(by) => (r_outer - by).max(0.0),
    };
    for i in 0..=n {
        let a = start + delta * i as f64;
        push_point(
            out,
            Point::new(
                disc.center.x + vertex_r * a.cos(),
                disc.center.y + vertex_r * a.sin(),
            ),
        );
    }
}

fn push_point(out: &mut Vec<Point>, p: Point) {
    if out
        .last()
        .is_some_and(|last| last.distance(&p) <= VERTEX_MERGE_MM)
    {
        return;
    }
    out.push(p);
}

/// Drop the repeated closing vertex, if the walk produced one.
fn close_ring(ring: &mut Vec<Point>) {
    while ring.len() >= 2 {
        let first = ring[0];
        let last = ring[ring.len() - 1];
        if first.distance(&last) <= VERTEX_MERGE_MM {
            ring.pop();
        } else {
            break;
        }
    }
}

/// Rotate the ring so it starts at its lexicographically smallest vertex.
/// Orientation is preserved; only the starting index moves.  This is what
/// makes the emitted vertex list independent of which arc the walk happened
/// to start from.
fn rotate_to_canonical_start(ring: &mut [Point]) {
    if ring.len() < 2 {
        return;
    }
    let mut best = 0usize;
    for i in 1..ring.len() {
        let a = ring[i];
        let b = ring[best];
        if a.x.total_cmp(&b.x).then_with(|| a.y.total_cmp(&b.y)) == std::cmp::Ordering::Less {
            best = i;
        }
    }
    ring.rotate_left(best);
}

// ---------------------------------------------------------------------------
// Predicates used by the guarantee
// ---------------------------------------------------------------------------

fn norm_angle(a: f64) -> f64 {
    let mut x = a % TAU;
    if x < 0.0 {
        x += TAU;
    }
    x
}

/// Smallest absolute angular difference between two angles in `[0, 2π)`.
fn angular_gap(a: f64, b: f64) -> f64 {
    let d = (a - b).abs() % TAU;
    d.min(TAU - d)
}

pub(crate) fn signed_area(ring: &[Point]) -> f64 {
    let n = ring.len();
    if n < 3 {
        return 0.0;
    }
    let mut s = 0.0;
    for i in 0..n {
        let a = ring[i];
        let b = ring[(i + 1) % n];
        s += a.x * b.y - b.x * a.y;
    }
    s / 2.0
}

fn region_contains_point(outlines: &[KeepoutOutline], p: &Point) -> bool {
    for o in outlines {
        if point_in_polygon_winding(p, &o.exterior) {
            let in_hole = o.holes.iter().any(|h| point_in_polygon_winding(p, h));
            if !in_hole {
                return true;
            }
        }
    }
    false
}

/// Minimum distance from `p` to any edge of any ring, with a bounding-box
/// reject: edges whose bounding box is already further than `cutoff` cannot
/// be the minimum, so a "≥ required radius" question is answered without
/// visiting every edge closely.  Returns `f64::INFINITY` if nothing is within
/// `cutoff`.
fn min_distance_to_region_boundary(outlines: &[KeepoutOutline], p: &Point, cutoff: f64) -> f64 {
    let mut best = f64::INFINITY;
    for o in outlines {
        for ring in std::iter::once(&o.exterior).chain(o.holes.iter()) {
            let n = ring.len();
            for i in 0..n {
                let a = ring[i];
                let b = ring[(i + 1) % n];
                let lim = best.min(cutoff);
                if (a.x.min(b.x) - p.x) > lim
                    || (p.x - a.x.max(b.x)) > lim
                    || (a.y.min(b.y) - p.y) > lim
                    || (p.y - a.y.max(b.y)) > lim
                {
                    continue;
                }
                let d = point_segment_distance(p, &a, &b);
                if d < best {
                    best = d;
                }
            }
        }
    }
    best
}

fn point_segment_distance(p: &Point, a: &Point, b: &Point) -> f64 {
    let dx = b.x - a.x;
    let dy = b.y - a.y;
    let len2 = dx * dx + dy * dy;
    if len2 <= 0.0 {
        return p.distance(a);
    }
    let t = (((p.x - a.x) * dx + (p.y - a.y) * dy) / len2).clamp(0.0, 1.0);
    let qx = a.x + t * dx;
    let qy = a.y + t * dy;
    ((p.x - qx) * (p.x - qx) + (p.y - qy) * (p.y - qy)).sqrt()
}

fn orient(a: &Point, b: &Point, c: &Point) -> f64 {
    (b.x - a.x) * (c.y - a.y) - (b.y - a.y) * (c.x - a.x)
}

/// Proper crossing only: shared endpoints and collinear touching do not
/// count.
fn segments_properly_cross(p1: &Point, p2: &Point, p3: &Point, p4: &Point) -> bool {
    let d1 = orient(p3, p4, p1);
    let d2 = orient(p3, p4, p2);
    let d3 = orient(p1, p2, p3);
    let d4 = orient(p1, p2, p4);
    ((d1 > 0.0 && d2 < 0.0) || (d1 < 0.0 && d2 > 0.0))
        && ((d3 > 0.0 && d4 < 0.0) || (d3 < 0.0 && d4 > 0.0))
}

// ---------------------------------------------------------------------------
// Python bridge
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
mod py {
    use super::*;
    use pyo3::exceptions::PyValueError;
    use pyo3::prelude::*;

    /// Union a list of `(x, y, radius)` discs into a conservative keepout.
    ///
    /// Returns `list[list[list[(x, y)]]]`: one entry per connected piece,
    /// each a list of rings with ring 0 the exterior (CCW) and rings 1.. the
    /// holes (CW).  Rings are open — the closing vertex is not repeated.
    /// Mirrors `zone_generator.pour_outline_py`'s established return shape.
    ///
    /// Raises `ValueError` if no disc has a positive radius (the caller must
    /// treat that as "cannot establish a keepout"), or if the containment
    /// proof fails — an under-covering keepout is never returned.
    #[pyfunction]
    #[pyo3(signature = (discs, epsilon_mm = DEFAULT_EPSILON_MM))]
    #[allow(clippy::type_complexity)]
    pub fn disc_union_keepout_py(
        discs: Vec<(f64, f64, f64)>,
        epsilon_mm: f64,
    ) -> PyResult<Vec<Vec<Vec<(f64, f64)>>>> {
        let input: Vec<Disc> = discs
            .iter()
            .map(|(x, y, r)| Disc::new(*x, *y, *r))
            .collect();
        let keepout = DiscUnionKeepout::new(&input, epsilon_mm)
            .map_err(|e| PyValueError::new_err(e.to_string()))?;
        Ok(keepout
            .outlines()
            .iter()
            .map(|o| {
                let mut rings: Vec<Vec<(f64, f64)>> = Vec::with_capacity(o.holes.len() + 1);
                rings.push(o.exterior.iter().map(|p| (p.x, p.y)).collect());
                for h in &o.holes {
                    rings.push(h.iter().map(|p| (p.x, p.y)).collect());
                }
                rings
            })
            .collect())
    }
}

#[cfg(feature = "python")]
pub use py::disc_union_keepout_py;

#[cfg(feature = "python")]
pub fn register(m: &pyo3::Bound<'_, pyo3::types::PyModule>) -> pyo3::PyResult<()> {
    use pyo3::prelude::*;
    m.add_function(pyo3::wrap_pyfunction!(py::disc_union_keepout_py, m)?)?;
    Ok(())
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;
    use std::f64::consts::PI;

    /// The production keepout radius: `DEFAULT_CORRIDOR_WIDTH_MM` (12.6 + 0.5)
    /// plus `KEEPOUT_EXTRA_MARGIN_MM` (1.0).  Used so the tests exercise the
    /// real board's scale, not a toy one.
    const PROD_R: f64 = 14.1;

    fn ring_count(k: &DiscUnionKeepout) -> (usize, usize) {
        (
            k.outlines().len(),
            k.outlines().iter().map(|o| o.holes.len()).sum(),
        )
    }

    /// A deterministic pseudo-random disc field at production radius, spread
    /// so that it overlaps heavily (as the real HV pad field does).
    fn scattered_discs(n: usize, radius: f64) -> Vec<Disc> {
        let mut out = Vec::with_capacity(n);
        let mut s: u64 = 0x5eed_1234_9abc_def0;
        for _ in 0..n {
            s = s
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            let x = ((s >> 33) as f64 / (1u64 << 31) as f64) * 150.0 + 20.0;
            s = s
                .wrapping_mul(6364136223846793005)
                .wrapping_add(1442695040888963407);
            let y = ((s >> 33) as f64 / (1u64 << 31) as f64) * 230.0 + 20.0;
            out.push(Disc::new(x, y, radius));
        }
        out
    }

    // ------------------------------------------------------------------
    // Structure
    // ------------------------------------------------------------------

    #[cfg_attr(test, test)]
    fn single_disc_is_one_ring_containing_the_disc() {
        let d = [Disc::new(10.0, 20.0, PROD_R)];
        let k = match DiscUnionKeepout::new(&d, DEFAULT_EPSILON_MM) {
            Ok(k) => k,
            Err(e) => panic!("construction failed: {e}"),
        };
        assert_eq!(ring_count(&k), (1, 0));
        // Conservative: area is at or above the true disc's, never below.
        let true_area = PI * PROD_R * PROD_R;
        assert!(
            k.area_mm2() >= true_area,
            "the emitted union must not be smaller than the true disc: {} < {}",
            k.area_mm2(),
            true_area
        );
        // ...and tight: the polyline is inside disc(c, r + eps), so the area
        // it claims is bounded by that disc's.
        let outer_area = PI * (PROD_R + DEFAULT_EPSILON_MM + SAFETY_INFLATION_MM).powi(2);
        assert!(
            k.area_mm2() <= outer_area,
            "{} > {outer_area}",
            k.area_mm2()
        );
        assert!(!k.has_self_intersection());
    }

    #[cfg_attr(test, test)]
    fn disjoint_discs_stay_separate_pieces() {
        let d = [Disc::new(0.0, 0.0, 5.0), Disc::new(50.0, 0.0, 5.0)];
        let k = match DiscUnionKeepout::new(&d, DEFAULT_EPSILON_MM) {
            Ok(k) => k,
            Err(e) => panic!("construction failed: {e}"),
        };
        assert_eq!(ring_count(&k), (2, 0));
    }

    #[cfg_attr(test, test)]
    fn overlapping_discs_merge_into_one_piece() {
        let d = [Disc::new(0.0, 0.0, 5.0), Disc::new(6.0, 0.0, 5.0)];
        let k = match DiscUnionKeepout::new(&d, DEFAULT_EPSILON_MM) {
            Ok(k) => k,
            Err(e) => panic!("construction failed: {e}"),
        };
        assert_eq!(ring_count(&k), (1, 0));
        // Union area < sum of the two disc areas (they genuinely overlap).
        assert!(k.area_mm2() < 2.0 * PI * 25.0);
        assert!(k.area_mm2() > PI * 25.0);
        assert!(!k.has_self_intersection());
    }

    #[cfg_attr(test, test)]
    fn a_ring_of_discs_encloses_a_hole() {
        // Four unit-ish discs whose neighbours overlap but whose centre is
        // uncovered: r=1.0 at (+-1.3, 0), (0, +-1.3).  Neighbour distance
        // 1.838 < 2 (overlap); centre distance 1.3 > 1 (uncovered).
        let d = [
            Disc::new(1.3, 0.0, 1.0),
            Disc::new(-1.3, 0.0, 1.0),
            Disc::new(0.0, 1.3, 1.0),
            Disc::new(0.0, -1.3, 1.0),
        ];
        let k = match DiscUnionKeepout::new(&d, 1e-4) {
            Ok(k) => k,
            Err(e) => panic!("construction failed: {e}"),
        };
        assert_eq!(ring_count(&k), (1, 1), "expected one piece with one hole");
        assert!(
            !k.contains_point(&Point::new(0.0, 0.0)),
            "the hole's interior must NOT be part of the keepout"
        );
        assert!(k.contains_point(&Point::new(1.3, 0.0)));
        assert!(!k.has_self_intersection());
    }

    #[cfg_attr(test, test)]
    fn a_disc_sitting_inside_a_hole_is_its_own_piece() {
        let mut d = vec![
            Disc::new(6.5, 0.0, 5.0),
            Disc::new(-6.5, 0.0, 5.0),
            Disc::new(0.0, 6.5, 5.0),
            Disc::new(0.0, -6.5, 5.0),
        ];
        d.push(Disc::new(0.0, 0.0, 0.5)); // free-floating inside the hole
        let k = match DiscUnionKeepout::new(&d, 1e-3) {
            Ok(k) => k,
            Err(e) => panic!("construction failed: {e}"),
        };
        let (pieces, holes) = ring_count(&k);
        assert_eq!((pieces, holes), (2, 1));
        assert!(k.contains_point(&Point::new(0.0, 0.0)));
        // (1.0, 1.0) is in the hole: 5.59 mm from each of the four r=5 discs
        // and 1.41 mm from the r=0.5 disc at the origin.
        assert!(!k.contains_point(&Point::new(1.0, 1.0)));
    }

    #[cfg_attr(test, test)]
    fn a_swallowed_disc_contributes_no_boundary() {
        let d = [Disc::new(0.0, 0.0, 10.0), Disc::new(1.0, 0.0, 2.0)];
        let k = match DiscUnionKeepout::new(&d, DEFAULT_EPSILON_MM) {
            Ok(k) => k,
            Err(e) => panic!("construction failed: {e}"),
        };
        assert_eq!(ring_count(&k), (1, 0));
        let solo = match DiscUnionKeepout::new(&[Disc::new(0.0, 0.0, 10.0)], DEFAULT_EPSILON_MM) {
            Ok(k) => k,
            Err(e) => panic!("construction failed: {e}"),
        };
        assert_eq!(
            k.outlines()[0].exterior.len(),
            solo.outlines()[0].exterior.len()
        );
    }

    #[cfg_attr(test, test)]
    fn identical_discs_are_deduped_not_double_walked() {
        let d = [Disc::new(3.0, 4.0, 7.0); 5];
        let k = match DiscUnionKeepout::new(&d, DEFAULT_EPSILON_MM) {
            Ok(k) => k,
            Err(e) => panic!("construction failed: {e}"),
        };
        assert_eq!(ring_count(&k), (1, 0));
    }

    #[cfg_attr(test, test)]
    fn no_discs_is_an_error_not_an_empty_keepout() {
        assert_eq!(
            DiscUnionKeepout::new(&[], 0.01).err(),
            Some(KeepoutError::NoDiscs)
        );
        assert_eq!(
            DiscUnionKeepout::new(&[Disc::new(0.0, 0.0, 0.0)], 0.01).err(),
            Some(KeepoutError::NoDiscs)
        );
    }

    #[cfg_attr(test, test)]
    fn non_finite_and_negative_discs_are_rejected() {
        assert_eq!(
            DiscUnionKeepout::new(&[Disc::new(0.0, 0.0, -1.0)], 0.01).err(),
            Some(KeepoutError::InvalidDisc(0))
        );
        assert_eq!(
            DiscUnionKeepout::new(&[Disc::new(f64::NAN, 0.0, 1.0)], 0.01).err(),
            Some(KeepoutError::InvalidDisc(0))
        );
        assert_eq!(
            DiscUnionKeepout::new(&[Disc::new(0.0, 0.0, f64::INFINITY)], 0.01).err(),
            Some(KeepoutError::InvalidDisc(0))
        );
    }

    // ------------------------------------------------------------------
    // The four required properties, on production-scale geometry
    // ------------------------------------------------------------------

    /// PROPERTY 1 + 2: every required disc is contained, and no emitted edge
    /// comes within the required radius of a disc centre (i.e. the boundary
    /// distance is >= the required clearance).  This is the guarantee the
    /// constructor enforces; asserting it here documents it and pins the
    /// production-scale case.
    #[cfg_attr(test, test)]
    fn property_containment_and_clearance_at_production_scale() {
        let discs = scattered_discs(109, PROD_R);
        let k = match DiscUnionKeepout::new(&discs, DEFAULT_EPSILON_MM) {
            Ok(k) => k,
            Err(e) => panic!("construction failed: {e}"),
        };
        let canonical = canonical_discs(&discs);
        // Independent re-check (the constructor already ran this; running it
        // again here is what makes the anti-vacuity pairing below meaningful).
        if let Err(e) = check_containment(k.outlines(), &canonical) {
            panic!("containment failed on production-scale input: {e}");
        }
        // Explicit clearance floor, stated as a distance rather than a
        // predicate: for every disc, the nearest emitted edge is at least the
        // required radius away.
        for d in &canonical {
            let dist = min_distance_to_region_boundary(k.outlines(), &d.center, d.radius);
            assert!(
                dist >= d.radius,
                "boundary at {dist} mm from a centre needing {} mm",
                d.radius
            );
        }
    }

    /// PROPERTY 3: polygon validity — no two non-adjacent edges cross.
    #[cfg_attr(test, test)]
    fn property_no_self_intersection_at_production_scale() {
        let discs = scattered_discs(109, PROD_R);
        let k = match DiscUnionKeepout::new(&discs, DEFAULT_EPSILON_MM) {
            Ok(k) => k,
            Err(e) => panic!("construction failed: {e}"),
        };
        assert!(
            !k.has_self_intersection(),
            "emitted keepout rings must not self-intersect"
        );
    }

    /// PROPERTY 4: determinism — the same disc *set* produces byte-identical
    /// geometry regardless of the order it arrives in, and regardless of how
    /// many times it is built.
    #[cfg_attr(test, test)]
    fn property_determinism_is_order_independent_and_repeatable() {
        let discs = scattered_discs(60, PROD_R);
        let a = match DiscUnionKeepout::new(&discs, DEFAULT_EPSILON_MM) {
            Ok(k) => k,
            Err(e) => panic!("construction failed: {e}"),
        };
        let b = match DiscUnionKeepout::new(&discs, DEFAULT_EPSILON_MM) {
            Ok(k) => k,
            Err(e) => panic!("construction failed: {e}"),
        };
        assert_eq!(a.outlines(), b.outlines(), "same input, same output");

        let mut shuffled = discs.clone();
        shuffled.reverse();
        shuffled.rotate_left(17);
        let c = match DiscUnionKeepout::new(&shuffled, DEFAULT_EPSILON_MM) {
            Ok(k) => k,
            Err(e) => panic!("construction failed: {e}"),
        };
        assert_eq!(
            a.outlines(),
            c.outlines(),
            "input order must not change the emitted geometry"
        );
        // Byte-identical, not merely equal-valued: compare the raw f64 bits.
        let bits = |k: &DiscUnionKeepout| -> Vec<u64> {
            let mut v = Vec::new();
            for o in k.outlines() {
                for ring in std::iter::once(&o.exterior).chain(o.holes.iter()) {
                    for p in ring {
                        v.push(p.x.to_bits());
                        v.push(p.y.to_bits());
                    }
                }
            }
            v
        };
        assert_eq!(bits(&a), bits(&c));
    }

    // ------------------------------------------------------------------
    // ANTI-VACUITY.  Each property above is re-run against a construction
    // broken on purpose, and asserted to FAIL.  A property test that passes
    // on a broken implementation proves nothing.
    // ------------------------------------------------------------------

    /// PROPERTY 1/2 anti-vacuity: the *inscribed* polyline — precisely what
    /// `shapely`'s `Point.buffer(r, quad_segs=16)` emits — must be caught by
    /// the containment check.
    #[cfg_attr(test, test)]
    fn anti_vacuity_inscribed_arcs_fail_the_containment_check() {
        let discs = scattered_discs(40, PROD_R);
        let canonical = canonical_discs(&discs);
        let inflated: Vec<Disc> = canonical
            .iter()
            .map(|d| Disc {
                center: d.center,
                radius: d.radius + SAFETY_INFLATION_MM + DEFAULT_EPSILON_MM,
            })
            .collect();
        let broken = match union_of_discs(&inflated, DEFAULT_EPSILON_MM, ArcMode::OnRequiredCircle)
        {
            Ok(o) => o,
            Err(e) => panic!("the broken build should still produce rings: {e}"),
        };
        let verdict = check_containment(&broken, &canonical);
        assert!(
            verdict.is_err(),
            "an INSCRIBED disc union under-covers every disc it draws, and the containment \
             check MUST reject it -- if this passes, the check is vacuous"
        );
        // And the same construction with a 64-gon-equivalent chord (shapely's
        // quad_segs=16) is short by the amount the module doc quotes.
        match verdict {
            Err(KeepoutError::ContainmentViolation { shortfall_mm, .. }) => {
                assert!(
                    shortfall_mm > 0.0,
                    "a violation must report a real shortfall"
                );
            }
            other => panic!("expected a containment violation, got {other:?}"),
        }
    }

    /// PROPERTY 1/2 anti-vacuity: a keepout drawn at a smaller radius than
    /// required — the "shrunk keepout" outcome that must never ship.
    #[cfg_attr(test, test)]
    fn anti_vacuity_shrunk_arcs_fail_the_containment_check() {
        let discs = scattered_discs(40, PROD_R);
        let canonical = canonical_discs(&discs);
        for shrink in [1e-3, 0.05, 0.5] {
            let broken =
                match union_of_discs(&canonical, DEFAULT_EPSILON_MM, ArcMode::Shrunk(shrink)) {
                    Ok(o) => o,
                    Err(_) => continue, // a badly-broken build may not even close
                };
            assert!(
                check_containment(&broken, &canonical).is_err(),
                "a keepout shrunk by {shrink} mm MUST be rejected"
            );
        }
    }

    /// PROPERTY 1/2 anti-vacuity, end to end: the public constructor itself
    /// refuses.  (`DiscUnionKeepout` has no other way in — the outline field
    /// is private — so this is the whole external surface.)
    #[cfg_attr(test, test)]
    fn anti_vacuity_a_shrunk_keepout_cannot_be_constructed() {
        let discs = scattered_discs(20, PROD_R);
        let canonical = canonical_discs(&discs);
        let broken = match union_of_discs(&canonical, DEFAULT_EPSILON_MM, ArcMode::Shrunk(0.2)) {
            Ok(o) => o,
            Err(e) => panic!("broken build failed early: {e}"),
        };
        // The guarantee marker is the only gate, and it refuses.
        assert!(ContainsEveryDisc::verified(&broken, &canonical).is_err());
    }

    /// PROPERTY 3 anti-vacuity: the self-intersection check must actually fire
    /// on geometry that self-intersects.  Shrinking the arcs while keeping the
    /// union's arc *topology* makes consecutive arcs miss each other and the
    /// ring cross itself.
    #[cfg_attr(test, test)]
    fn anti_vacuity_self_intersection_check_fires_on_broken_rings() {
        // Control: the real construction is simple.
        let good = match DiscUnionKeepout::new(&[Disc::new(0.0, 0.0, 5.0)], DEFAULT_EPSILON_MM) {
            Ok(k) => k,
            Err(e) => panic!("construction failed: {e}"),
        };
        assert!(!good.has_self_intersection());

        // Corruption 1: swap two non-adjacent vertices of a ring -- the
        // classic way a ring stops being simple.  If the checker cannot see
        // this, the validity property test is vacuous.
        let mut ring = good.outlines()[0].exterior.clone();
        let n = ring.len();
        assert!(n >= 8);
        ring.swap(1, n / 2);
        let corrupted = DiscUnionKeepout {
            outlines: vec![KeepoutOutline {
                exterior: ring,
                holes: Vec::new(),
            }],
            _guarantee: ContainsEveryDisc { _private: () },
        };
        assert!(
            corrupted.has_self_intersection(),
            "the validity check must detect a ring that crosses itself"
        );

        // Measured, and worth recording: shrinking the arcs does NOT make the
        // rings self-intersect (checked at 6/12/25/60 discs x 1/3/6/10/13 mm
        // of shrink -- zero crossings).  The shrink stays inside each arc's
        // own angular sector, so the ring remains simple while being far too
        // small.  Validity and containment therefore catch *different*
        // failures, and neither substitutes for the other: a shrunk keepout is
        // caught by `check_containment` (the two tests above), never by this
        // check.
    }

    /// PROPERTY 4 anti-vacuity: determinism is *produced* by the
    /// canonicalisation step, not inherent.  Feed the union the raw, unsorted
    /// disc list (skipping `canonical_discs`) and the emitted vertex list
    /// changes with input order — which is exactly what the determinism
    /// property test would catch if that step were ever dropped.
    #[cfg_attr(test, test)]
    fn anti_vacuity_dropping_canonicalisation_breaks_determinism() {
        let discs = scattered_discs(30, PROD_R);
        let mut shuffled = discs.clone();
        shuffled.reverse();
        let a = match union_of_discs(&discs, DEFAULT_EPSILON_MM, ArcMode::InscribedInOuter) {
            Ok(o) => o,
            Err(e) => panic!("build failed: {e}"),
        };
        let b = match union_of_discs(&shuffled, DEFAULT_EPSILON_MM, ArcMode::InscribedInOuter) {
            Ok(o) => o,
            Err(e) => panic!("build failed: {e}"),
        };
        assert_ne!(
            a, b,
            "without canonicalisation the output DOES depend on input order; if this ever \
             becomes equal, the determinism property test has stopped testing anything"
        );
        // ...and with canonicalisation it does not (the production path).
        let ca = match union_of_discs(
            &canonical_discs(&discs),
            DEFAULT_EPSILON_MM,
            ArcMode::InscribedInOuter,
        ) {
            Ok(o) => o,
            Err(e) => panic!("build failed: {e}"),
        };
        let cb = match union_of_discs(
            &canonical_discs(&shuffled),
            DEFAULT_EPSILON_MM,
            ArcMode::InscribedInOuter,
        ) {
            Ok(o) => o,
            Err(e) => panic!("build failed: {e}"),
        };
        assert_eq!(ca, cb);
    }

    /// The tightness knob is a cost knob only: a coarser `eps` claims more
    /// area, and the guarantee holds at every setting.
    #[cfg_attr(test, test)]
    fn epsilon_trades_area_for_vertices_but_never_the_guarantee() {
        let discs = scattered_discs(25, PROD_R);
        let mut prev_area = 0.0;
        let mut prev_verts = usize::MAX;
        for eps in [1.0, 0.1, 0.01, 0.001] {
            let k = match DiscUnionKeepout::new(&discs, eps) {
                Ok(k) => k,
                Err(e) => panic!("construction failed at eps={eps}: {e}"),
            };
            if prev_area > 0.0 {
                assert!(
                    k.area_mm2() <= prev_area,
                    "smaller eps must not claim more area"
                );
                assert!(
                    k.vertex_count() >= prev_verts,
                    "smaller eps must not use fewer vertices"
                );
            }
            prev_area = k.area_mm2();
            prev_verts = k.vertex_count();
        }
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

        fn disc_field_sized(min: usize, max: usize) -> impl Strategy<Value = Vec<Disc>> {
            prop::collection::vec((-60.0f64..60.0, -60.0f64..60.0, 0.5f64..25.0), min..max)
                .prop_map(|v| v.into_iter().map(|(x, y, r)| Disc::new(x, y, r)).collect())
        }

        fn disc_field() -> impl Strategy<Value = Vec<Disc>> {
            disc_field_sized(1, 14)
        }

        proptest! {
            #![proptest_config(ProptestConfig::with_cases(200))]

            /// Containment + clearance floor, over arbitrary disc fields
            /// (overlapping, nested, disjoint, tangent-ish alike).
            #[test]
            fn random_disc_fields_contain_every_disc(discs in disc_field()) {
                let k = DiscUnionKeepout::new(&discs, 0.01);
                prop_assert!(k.is_ok(), "construction failed: {:?}", k.err());
                let k = match k { Ok(k) => k, Err(_) => return Ok(()) };
                for d in canonical_discs(&discs) {
                    prop_assert!(k.contains_point(&d.center));
                    let dist = min_distance_to_region_boundary(k.outlines(), &d.center, d.radius);
                    prop_assert!(
                        dist >= d.radius,
                        "boundary {dist} < required {}", d.radius
                    );
                }
            }

            /// Validity: no ring crosses itself or another.
            #[test]
            fn random_disc_fields_are_simple_polygons(discs in disc_field()) {
                let k = match DiscUnionKeepout::new(&discs, 0.01) {
                    Ok(k) => k,
                    Err(e) => { prop_assert!(false, "{e}"); return Ok(()); }
                };
                prop_assert!(!k.has_self_intersection());
            }

            /// Determinism under permutation.
            #[test]
            fn random_disc_fields_are_order_independent(discs in disc_field()) {
                let mut rev = discs.clone();
                rev.reverse();
                let a = DiscUnionKeepout::new(&discs, 0.01);
                let b = DiscUnionKeepout::new(&rev, 0.01);
                match (a, b) {
                    (Ok(a), Ok(b)) => prop_assert_eq!(a.outlines(), b.outlines()),
                    (Err(a), Err(b)) => prop_assert_eq!(format!("{a}"), format!("{b}")),
                    (x, y) => prop_assert!(false, "one side failed: {:?} vs {:?}", x.is_ok(), y.is_ok()),
                }
            }

            /// ANTI-VACUITY, randomized: for the same random fields, the
            /// inscribed (shapely-shaped) construction is rejected.
            #[test]
            fn random_disc_fields_reject_the_inscribed_construction(
                discs in disc_field_sized(2, 14)
            ) {
                let canonical = canonical_discs(&discs);
                prop_assume!(canonical.len() >= 2);
                let inflated: Vec<Disc> = canonical
                    .iter()
                    .map(|d| Disc {
                        center: d.center,
                        radius: d.radius + SAFETY_INFLATION_MM + 0.01,
                    })
                    .collect();
                if let Ok(broken) = union_of_discs(&inflated, 0.01, ArcMode::OnRequiredCircle) {
                    prop_assert!(check_containment(&broken, &canonical).is_err());
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
        ("disc_union_keepout::tests::single_disc_is_one_ring_containing_the_disc", single_disc_is_one_ring_containing_the_disc),
        ("disc_union_keepout::tests::disjoint_discs_stay_separate_pieces", disjoint_discs_stay_separate_pieces),
        ("disc_union_keepout::tests::overlapping_discs_merge_into_one_piece", overlapping_discs_merge_into_one_piece),
        ("disc_union_keepout::tests::a_ring_of_discs_encloses_a_hole", a_ring_of_discs_encloses_a_hole),
        ("disc_union_keepout::tests::a_disc_sitting_inside_a_hole_is_its_own_piece", a_disc_sitting_inside_a_hole_is_its_own_piece),
        ("disc_union_keepout::tests::a_swallowed_disc_contributes_no_boundary", a_swallowed_disc_contributes_no_boundary),
        ("disc_union_keepout::tests::identical_discs_are_deduped_not_double_walked", identical_discs_are_deduped_not_double_walked),
        ("disc_union_keepout::tests::no_discs_is_an_error_not_an_empty_keepout", no_discs_is_an_error_not_an_empty_keepout),
        ("disc_union_keepout::tests::non_finite_and_negative_discs_are_rejected", non_finite_and_negative_discs_are_rejected),
        ("disc_union_keepout::tests::property_containment_and_clearance_at_production_scale", property_containment_and_clearance_at_production_scale),
        ("disc_union_keepout::tests::property_no_self_intersection_at_production_scale", property_no_self_intersection_at_production_scale),
        ("disc_union_keepout::tests::property_determinism_is_order_independent_and_repeatable", property_determinism_is_order_independent_and_repeatable),
        ("disc_union_keepout::tests::anti_vacuity_inscribed_arcs_fail_the_containment_check", anti_vacuity_inscribed_arcs_fail_the_containment_check),
        ("disc_union_keepout::tests::anti_vacuity_shrunk_arcs_fail_the_containment_check", anti_vacuity_shrunk_arcs_fail_the_containment_check),
        ("disc_union_keepout::tests::anti_vacuity_a_shrunk_keepout_cannot_be_constructed", anti_vacuity_a_shrunk_keepout_cannot_be_constructed),
        ("disc_union_keepout::tests::anti_vacuity_self_intersection_check_fires_on_broken_rings", anti_vacuity_self_intersection_check_fires_on_broken_rings),
        ("disc_union_keepout::tests::anti_vacuity_dropping_canonicalisation_breaks_determinism", anti_vacuity_dropping_canonicalisation_breaks_determinism),
        ("disc_union_keepout::tests::epsilon_trades_area_for_vertices_but_never_the_guarantee", epsilon_trades_area_for_vertices_but_never_the_guarantee),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
