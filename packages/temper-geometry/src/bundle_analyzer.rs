// Wave 4, spatial-tier-2 unit: `router_v6/bundle_analyzer.py`'s GEOS seam.
//
// The bundle analyzer (net -> bundle equivalence partitioning + geometric
// Jaccard overlap) was the last spatial-DRC module kept back for an
// unresolved GEOS `MultiPoint.convex_hull` / `.union` seam.  This spike
// (docs/evidence/2026-08-09-bundle-analyzer-geos-spike.md) resolved the
// seam per call:
//
// * `MultiPoint(pads).convex_hull` — PORTABLE, via a faithful transcription
//   of GEOS's own `ConvexHull` (Graham scan over a radial sort of the
//   lowest point, then `cleanRing`): `preSort` -> `grahamScan` ->
//   `cleanRing` (`ConvexHull.cpp` r407).  The vertex *set* is a
//   combinatorial selection (no invented coordinates — S1 §5.4), and the
//   collinear-boundary retention policy is reproduced exactly (GEOS drops
//   collinear ring points via `cleanRing`).  The orientation predicate is
//   `Orientation::index` = `CGAlgorithmsDD::orientationIndex` — a fast
//   f64 filter (Shewchuk's `DP_SAFE_EPSILON = 1e-15` band) with a
//   double-double (`geos/math/DD.h`) fallback — transcribed here
//   verbatim, including the DD arithmetic (`selfAdd`/`selfMultiply` with
//   `SPLIT = 2^27+1`).
//
// * `hull.buffer(m)` — PORTABLE, via a faithful transcription of GEOS's
//   `OffsetSegmentGenerator` for a convex ring buffered on the LEFT side
//   (`OffsetCurveBuilder::computeRingBufferCurve` + `addOutsideTurn`'s
//   round join + `addDirectedFillet`).  GEOS's hull ring is CW, so every
//   convex corner is an outside turn whose fillet is a closed-form arc
//   (`nSegs = (int)(totalAngle / filletAngleQuantum + 0.5)`, points at
//   `v + r·(cos,sin)(startAngle - i·angleInc)` with `Angle::sinCosSnap`).
//   The BufferInputLineSimplifier is structurally inert on a convex hull
//   (its `isConcave` gate requires the vertex's orientation to match
//   `angleOrientation`, which for a positive distance is CCW — every
//   vertex of a CW hull fails it), and the buffer pipeline
//   (noding/subgraph/PolygonBuilder) preserves a simple ring's region
//   vertex-for-vertex.  The `quad_segs` is 16 — shapely's *default*
//   `buffer()` parameter (the module's call site passes none), not GEOS's
//   own 8.  Measured: 400/400 random hulls with bit-identical vertex sets,
//   and 1,920,000 contains probes (including 20,470 boundary-exact)
//   agree with shapely 2.1.2 / GEOS 3.13.1.
//
// * `.union` (2 sites) — NARROWED AWAY, not ported: its only consumer is
//   `BundleClass.geometric_footprint`, a field with zero production
//   readers (the pipeline serializes `bundle_id`/`net_indices`/
//   `constraint_types`/`is_diff_pair`/`bundle_id_for_net`/
//   `unbundled_net_indices` only).  The shim keeps the union in Python on
//   that dead field — the same "PORT with kept lines" pattern as
//   `obstacle_map_kernels.rs`.
//
// * `STRtree(points).query(footprint, predicate="contains")` — PORTABLE:
//   the result set is a pure function of the region (the index only prunes
//   candidates; pruning does not affect the predicate outcome).  This
//   kernel scans the midpoints with a bounding-box precheck and a strict
//   point-in-convex-polygon test (`contains` = interior, boundary
//   excluded), which is bit-identical on the transcribed region.
//
// Bit-exactness classes (docs/wave4-discipline-contract.md §2): B6 (GEOS
// distances are `sqrt(dx*dx+dy*dy)`, not `hypot` — used for the corner
// collapse threshold and the snap dedup), B1 (host-libm `atan2`/`sin`/
// `cos` via `dlsym`, `sqrt` is IEEE-correctly-rounded so the intrinsic is
// exact), B7 (expression shape preserved verbatim from the GEOS source,
// including the `(total/fillet + 0.5)` rounding and the DD two-step
// arithmetic).  `GEOS_MATH_PI` is GEOS's constants.h literal, written at
// its declared precision.
//
// Validity boundary (documented, not guarded): coordinates whose edge
// separations fall in the f64 underflow regime (`|dx| < ~1e-162`, where
// `dx*dx` flushes to 0.0) make GEOS's own `computeOffsetSegment` emit
// NaN/inf offset points that its noding pipeline then silently drops —
// the transcription below emits them instead.  Real pad coordinates never
// reach that regime; the differential and PBT suites constrain their
// generators to float32 width (|dx| >= ~1.4e-45), which cannot underflow.

#![allow(clippy::approx_constant, clippy::excessive_precision)]

use std::cmp::Ordering;
use std::collections::{HashMap, HashSet};

/// GEOS `constants.h` `MATH_PI` at its declared precision (bit-exactness
/// class B7 — the constant expression shape, not `f64::consts::PI`).
const GEOS_MATH_PI: f64 = 3.14159265358979323846;

/// GEOS `Angle::PI_OVER_2`.
const PI_OVER_2: f64 = GEOS_MATH_PI / 2.0;

/// GEOS `Angle::PI_TIMES_2`.
const PI_TIMES_2: f64 = 2.0 * GEOS_MATH_PI;

/// shapely `buffer()`'s default `quad_segs` — the module's call site
/// (`hull.buffer(self._median_edge_length)`) passes no `quad_segs`, so the
/// effective GEOS fillet quantum is `PI/2/16`, not GEOS's own default 8.
const QUAD_SEGS: f64 = 16.0;

/// `OffsetSegmentGenerator::CURVE_VERTEX_SNAP_DISTANCE_FACTOR` — consecutive
/// emitted points closer than `distance * this` are dropped.
const CURVE_VERTEX_SNAP_DISTANCE_FACTOR: f64 = 1.0e-4;

/// `OffsetSegmentGenerator::OFFSET_SEGMENT_SEPARATION_FACTOR` — a corner
/// whose two offset endpoints are closer than `distance * this` collapses
/// to a single point (no fillet).
const OFFSET_SEGMENT_SEPARATION_FACTOR: f64 = 1.0e-3;

// ---------------------------------------------------------------------------
// host-libm `atan2` (GEOS's `std::atan2` runs against the host Python
// process's libm; bit-exactness class B1).  `sqrt` is IEEE-754 correctly
// rounded and therefore identical to the host libm's — the intrinsic is
// used directly.  `sin`/`cos` reuse `crate::host_math` (already dlsym'd).
// ---------------------------------------------------------------------------

#[cfg(not(target_arch = "wasm32"))]
type BinaryMathFn = unsafe extern "C" fn(f64, f64) -> f64;

#[cfg(not(target_arch = "wasm32"))]
unsafe extern "C" {
    fn dlsym(handle: *const u8, symbol: *const u8) -> *mut u8;
}

#[cfg(all(not(target_arch = "wasm32"), target_vendor = "apple"))]
const RTLD_DEFAULT: *const u8 = usize::MAX.wrapping_sub(1) as *const u8; // (void *) -2

#[cfg(all(not(target_arch = "wasm32"), not(target_vendor = "apple")))]
const RTLD_DEFAULT: *const u8 = core::ptr::null();

#[cfg(not(target_arch = "wasm32"))]
fn host_atan2() -> &'static BinaryMathFn {
    static F: std::sync::OnceLock<Option<BinaryMathFn>> = std::sync::OnceLock::new();
    F.get_or_init(|| {
        let p = unsafe { dlsym(RTLD_DEFAULT, c"atan2".as_ptr().cast::<u8>()) };
        if p.is_null() {
            None
        } else {
            // SAFETY: the resolved symbol is a C `double(double, double)` from libm.
            Some(unsafe { std::mem::transmute::<*mut u8, BinaryMathFn>(p) })
        }
        .or(Some(fallback_atan2))
    })
    .as_ref()
    .unwrap_or_else(|| unreachable!("fallback always set"))
}

#[cfg(not(target_arch = "wasm32"))]
unsafe extern "C" fn fallback_atan2(y: f64, x: f64) -> f64 {
    f64::atan2(y, x)
}

/// GEOS `std::atan2` (host libm), bit-exact with the reference.
#[cfg(not(target_arch = "wasm32"))]
fn geos_atan2(y: f64, x: f64) -> f64 {
    unsafe { host_atan2()(y, x) }
}

/// `f64::atan2` (wasm32 has no host CPython libm to dlsym against).
#[cfg(target_arch = "wasm32")]
fn geos_atan2(y: f64, x: f64) -> f64 {
    f64::atan2(y, x)
}

/// GEOS `Coordinate::distance` — `sqrt(dx*dx + dy*dy)`, NOT `hypot`
/// (bit-exactness class B6).
fn geos_distance(a: (f64, f64), b: (f64, f64)) -> f64 {
    let dx = a.0 - b.0;
    let dy = a.1 - b.1;
    f64::sqrt(dx * dx + dy * dy)
}

/// GEOS `Angle::sinCosSnap(ang)`: host-libm sin/cos, snapping components
/// with magnitude < 5e-16 to exactly 0.0.  Same transcription as
/// `obstacle_map_kernels.rs` (verified 0/400 there against GEOS 3.13.1).
fn geos_sin_cos_snap(angle: f64) -> (f64, f64) {
    let mut s = crate::host_math::sin(angle);
    let mut c = crate::host_math::cos(angle);
    if s.abs() < 5e-16 {
        s = 0.0;
    }
    if c.abs() < 5e-16 {
        c = 0.0;
    }
    (s, c)
}

// ---------------------------------------------------------------------------
// double-double arithmetic — GEOS `geos/math/DD.h` + `src/math/DD.cpp`
// (Knuth/Kahan/Dekker two-sum / two-product with `SPLIT = 2^27+1`),
// transcribed verbatim for the operations `CGAlgorithmsDD::orientationIndex`
// needs.  Only the f64-correctly-rounded operations matter here: the sign
// of the 106-bit determinant is what the hull scan and the collinear
// cleanup decide on.
// ---------------------------------------------------------------------------

const DD_SPLIT: f64 = 134217729.0; // 2^27+1

/// A double-double: `hi + lo` with `|lo| <= 0.5 ulp(hi)`.
#[derive(Clone, Copy, Debug)]
struct DD {
    hi: f64,
    lo: f64,
}

impl DD {
    fn new(x: f64) -> Self {
        DD { hi: x, lo: 0.0 }
    }

    /// `DD::selfAdd(yhi, ylo)` — compensated two-sum, verbatim.
    fn add_self(&mut self, yhi: f64, ylo: f64) {
        let s = self.hi + yhi;
        let t = self.lo + ylo;
        let e = s - self.hi;
        let f = t - self.lo;
        let s0 = s - e;
        let t0 = t - f;
        let s1 = (yhi - e) + (self.hi - s0);
        let t1 = (ylo - f) + (self.lo - t0);
        let e0 = s1 + t;
        let h = s + e0;
        let h0 = e0 + (s - h);
        let e1 = t1 + h0;
        let zhi = h + e1;
        let zlo = e1 + (h - zhi);
        self.hi = zhi;
        self.lo = zlo;
    }

    /// `DD::selfMultiply(yhi, ylo)` — Dekker two-product, verbatim.
    fn mul_self(&mut self, yhi: f64, ylo: f64) {
        let mut c = DD_SPLIT * self.hi;
        let mut hx = c - self.hi;
        let c0 = DD_SPLIT * yhi;
        hx = c - hx;
        let tx = self.hi - hx;
        let mut hy = c0 - yhi;
        c = self.hi * yhi;
        hy = c0 - hy;
        let ty = yhi - hy;
        let c1 = ((((hx * hy - c) + hx * ty) + tx * hy) + tx * ty)
            + (self.hi * ylo + self.lo * yhi);
        let zhi = c + c1;
        hx = c - zhi;
        let zlo = c1 + hx;
        self.hi = zhi;
        self.lo = zlo;
    }

    fn add(a: DD, b: DD) -> DD {
        let mut r = a;
        r.add_self(b.hi, b.lo);
        r
    }

    /// `DD::selfSubtract` — `selfAdd(-1*hi, -1*lo)`; the `-1 *` expression
    /// shape is GEOS's own (bit-exactness class B7, negation is exact).
    #[allow(clippy::neg_multiply)]
    fn sub(a: DD, b: DD) -> DD {
        let mut r = a;
        r.add_self(-1.0 * b.hi, -1.0 * b.lo);
        r
    }

    fn mul(a: DD, b: DD) -> DD {
        let mut r = a;
        r.mul_self(b.hi, b.lo);
        r
    }

    /// `DD::operator<`.
    fn lt(&self, rhs: &DD) -> bool {
        (self.hi < rhs.hi) || (self.hi == rhs.hi && self.lo < rhs.lo)
    }

    /// `DD::operator>`.
    fn gt(&self, rhs: &DD) -> bool {
        (self.hi > rhs.hi) || (self.hi == rhs.hi && self.lo > rhs.lo)
    }
}

// ---------------------------------------------------------------------------
// orientation predicate — GEOS `Orientation::index` =
// `CGAlgorithmsDD::orientationIndex` (fast filter + DD fallback).
// Returns 1 (LEFT/CCW), -1 (RIGHT/CW), or 0 (STRAIGHT/collinear).
// ---------------------------------------------------------------------------

/// Shewchuk's `DP_SAFE_EPSILON` band used by
/// `CGAlgorithmsDD::orientationIndexFilter`.
const DP_SAFE_EPSILON: f64 = 1e-15;

fn orientation(x: f64) -> i32 {
    if x < 0.0 {
        -1
    } else if x > 0.0 {
        1
    } else {
        0
    }
}

/// `CGAlgorithmsDD::orientationIndexFilter` verbatim.  Returns `2`
/// (`FAILURE`) when f64 arithmetic cannot be trusted and the caller must
/// use the DD fallback.
fn orientation_index_filter(pax: f64, pay: f64, pbx: f64, pby: f64, pcx: f64, pcy: f64) -> i32 {
    let detleft = (pax - pcx) * (pby - pcy);
    let detright = (pay - pcy) * (pbx - pcx);
    let det = detleft - detright;

    let detsum;
    if detleft > 0.0 {
        if detright <= 0.0 {
            return orientation(det);
        }
        detsum = detleft + detright;
    } else if detleft < 0.0 {
        if detright >= 0.0 {
            return orientation(det);
        }
        detsum = -detleft - detright;
    } else {
        return orientation(det);
    }

    let errbound = DP_SAFE_EPSILON * detsum;
    if (det >= errbound) || (-det >= errbound) {
        return orientation(det);
    }
    2 // CGAlgorithmsDD::FAILURE
}

/// `CGAlgorithmsDD::orientationIndex` verbatim.
fn orientation_index(p1x: f64, p1y: f64, p2x: f64, p2y: f64, qx: f64, qy: f64) -> i32 {
    let index = orientation_index_filter(p1x, p1y, p2x, p2y, qx, qy);
    if index <= 1 {
        return index;
    }

    let dx1 = DD::add(DD::new(p2x), DD::new(-p1x));
    let dy1 = DD::add(DD::new(p2y), DD::new(-p1y));
    let dx2 = DD::add(DD::new(qx), DD::new(-p2x));
    let dy2 = DD::add(DD::new(qy), DD::new(-p2y));

    let mx1y2 = DD::mul(dx1, dy2);
    let my1x2 = DD::mul(dy1, dx2);
    let d = DD::sub(mx1y2, my1x2);

    let zero = DD::new(0.0);
    if d.lt(&zero) {
        -1
    } else if d.gt(&zero) {
        1
    } else {
        0
    }
}

// ---------------------------------------------------------------------------
// convex hull — GEOS `algorithm/ConvexHull.cpp` r407 verbatim
// (`extractUnique` -> `preSort` -> `grahamScan` -> `cleanRing`, with
// `lineOrPolygon`'s non-polygon outcome mapped to the empty ring).
// ---------------------------------------------------------------------------

/// The lowest point (min y, then min x) is moved to the front; the rest are
/// sorted radially CW around it (`RadiallyLessThen`'s `polarCompare`).
fn pre_sort(pts: &mut [(f64, f64)]) {
    for i in 1..pts.len() {
        let p0 = pts[0];
        let pi = pts[i];
        if (pi.1 < p0.1) || (pi.1 == p0.1 && pi.0 < p0.0) {
            pts.swap(0, i);
        }
    }
    let origin = pts[0];
    pts[1..].sort_by(|p, q| match polar_compare(&origin, p, q) {
        -1 => Ordering::Less,
        1 => Ordering::Greater,
        _ => Ordering::Equal,
    });
}

/// `RadiallyLessThen::polarCompare` — radial order around the origin.
fn polar_compare(o: &(f64, f64), p: &(f64, f64), q: &(f64, f64)) -> i32 {
    let orient = orientation_index(o.0, o.1, p.0, p.1, q.0, q.1);
    if orient == 1 {
        return 1; // CCW
    }
    if orient == -1 {
        return -1; // CW
    }
    // collinear — compare by distance from the origin: the y ordinate first
    // (more robust than computing the distance), then x for horizontal lines.
    if p.1 > q.1 {
        return 1;
    }
    if p.1 < q.1 {
        return -1;
    }
    if p.0 > q.0 {
        return 1;
    }
    if p.0 < q.0 {
        return -1;
    }
    0
}

/// `ConvexHull::grahamScan` verbatim — produces a CW ring.
fn graham_scan(c: &[(f64, f64)]) -> Vec<(f64, f64)> {
    let mut ps: Vec<(f64, f64)> = vec![c[0], c[1], c[2]];
    for &ci in &c[3..] {
        let mut p = ps.pop().unwrap_or_else(|| unreachable!("ps holds c[0..2] at entry"));
        while let Some(last) = ps.last().copied() {
            if orientation_index(last.0, last.1, p.0, p.1, ci.0, ci.1) > 0 {
                p = ps.pop().unwrap_or_else(|| unreachable!("ps non-empty in loop"));
            } else {
                break;
            }
        }
        ps.push(p);
        ps.push(ci);
    }
    ps.push(c[0]);
    ps
}

/// `ConvexHull::isBetween` — c2 collinear with and between c1 and c3.
fn is_between(c1: (f64, f64), c2: (f64, f64), c3: (f64, f64)) -> bool {
    if orientation_index(c1.0, c1.1, c2.0, c2.1, c3.0, c3.1) != 0 {
        return false;
    }
    if c1.0 != c3.0
        && ((c1.0 <= c2.0 && c2.0 <= c3.0) || (c3.0 <= c2.0 && c2.0 <= c1.0))
    {
        return true;
    }
    if c1.1 != c3.1
        && ((c1.1 <= c2.1 && c2.1 <= c3.1) || (c3.1 <= c2.1 && c2.1 <= c1.1))
    {
        return true;
    }
    false
}

/// `ConvexHull::cleanRing` — drop consecutive duplicates and collinear
/// (`isBetween`) points; the first point is never dropped.
fn clean_ring(original: &[(f64, f64)]) -> Vec<(f64, f64)> {
    let npts = original.len();
    let last = original[npts - 1];
    let mut cleaned: Vec<(f64, f64)> = Vec::new();
    let mut prev: Option<(f64, f64)> = None;
    for i in 0..(npts - 1) {
        let curr = original[i];
        let next = original[i + 1];
        if curr == next {
            continue;
        }
        if prev.is_some_and(|pv| is_between(pv, curr, next)) {
            continue;
        }
        cleaned.push(curr);
        prev = Some(curr);
    }
    cleaned.push(last);
    cleaned
}

/// GEOS `MultiPoint(pads).convex_hull` exterior ring (closed, CW), or the
/// empty ring when the hull is not a polygon (0-2 unique points, or the
/// `lineOrPolygon` degenerate-3 branch which produces a LineString).
///
/// The vertex *set* is exactly GEOS's: collinear boundary points are
/// dropped by `cleanRing`, duplicate points by `extractUnique`, and the
/// orientation decisions use GEOS's own filter + double-double predicate.
pub fn convex_hull_ring(points: &[(f64, f64)]) -> Vec<(f64, f64)> {
    let mut unique: Vec<(f64, f64)> = Vec::new();
    for &p in points {
        if !unique.contains(&p) {
            unique.push(p);
        }
    }
    // `createFewPointsResult`: <= 2 unique points -> Point or LineString.
    if unique.len() < 3 {
        return Vec::new();
    }
    pre_sort(&mut unique);
    let hull = graham_scan(&unique);
    let cleaned = clean_ring(&hull);
    // `lineOrPolygon`: a cleaned ring of size 3 is a degenerate LineString
    // (two distinct points) after the `resize(2)`, not a polygon.
    if cleaned.len() < 4 {
        return Vec::new();
    }
    cleaned
}

// ---------------------------------------------------------------------------
// convex-ring buffer — GEOS `OffsetCurveBuilder::computeRingBufferCurve` +
// `OffsetSegmentGenerator` verbatim for a CW ring buffered on the LEFT.
// ---------------------------------------------------------------------------

/// `OffsetSegmentGenerator::computeOffsetSegment` (side LEFT, `sideSign=1`):
/// the left offset segment endpoints of edge `a -> b` at distance `d`.
fn offset_endpoints(a: (f64, f64), b: (f64, f64), d: f64) -> ((f64, f64), (f64, f64)) {
    let dx = b.0 - a.0;
    let dy = b.1 - a.1;
    let len = f64::sqrt(dx * dx + dy * dy);
    let ux = d * dx / len;
    let uy = d * dy / len;
    ((a.0 - uy, a.1 + ux), (b.0 - uy, b.1 + ux))
}

/// `OffsetSegmentString::addPt` — drop a point closer than `min_d` to the
/// current last point (dedup / vertex snap).
fn add_pt(pts: &mut Vec<(f64, f64)>, p: (f64, f64), min_d: f64) {
    if pts.last().is_some_and(|&last| geos_distance(last, p) < min_d) {
        return;
    }
    pts.push(p);
}

/// The closed ring whose region is exactly GEOS's
/// `convex_hull(pads).buffer(distance)` for `distance > 0`, and the input
/// ring itself for `distance == 0` (GEOS `getRingCurve`'s zero-distance
/// fast path returns the input unchanged).  `distance < 0` (the erosion
/// path, which the caller never reaches — `m` is a median of non-negative
/// edge lengths) returns the empty ring.
pub fn hull_buffer_ring(ring: &[(f64, f64)], distance: f64) -> Vec<(f64, f64)> {
    if distance == 0.0 {
        return ring.to_vec();
    }
    if distance < 0.0 {
        return Vec::new();
    }
    if ring.len() < 4 {
        return Vec::new();
    }

    let fillet = PI_OVER_2 / QUAD_SEGS;
    let min_d = distance * CURVE_VERTEX_SNAP_DISTANCE_FACTOR;
    let collapse_d = distance * OFFSET_SEGMENT_SEPARATION_FACTOR;

    let verts = &ring[..ring.len() - 1];
    let n = verts.len();
    let seg_off: Vec<((f64, f64), (f64, f64))> = (0..n)
        .map(|i| offset_endpoints(verts[i], verts[(i + 1) % n], distance))
        .collect();

    let mut pts: Vec<(f64, f64)> = Vec::new();
    for i in 0..n {
        let v = verts[i];
        // offset0.p1 = offset of edge (v_{i-1}, v_i) at v; offset1.p0 =
        // offset of edge (v_i, v_{i+1}) at v.
        let p_in = seg_off[(i + n - 1) % n].1;
        let p_out = seg_off[i].0;

        // `addOutsideTurn`: if the two offset endpoints are very close
        // (nearly-parallel edges) the corner collapses to a single point.
        if geos_distance(p_in, p_out) < collapse_d {
            add_pt(&mut pts, p_in, min_d);
            continue;
        }

        // `addDirectedFillet(p, p0, p1, CW, radius)`: the round join.  The
        // outer overload emits p0, the fillet arc, then p1.
        let a0_raw = geos_atan2(p_in.1 - v.1, p_in.0 - v.0);
        let a1 = geos_atan2(p_out.1 - v.1, p_out.0 - v.0);
        let mut a0 = a0_raw;
        if a0 <= a1 {
            a0 += PI_TIMES_2;
        }
        let total = (a0 - a1).abs();
        let n_seg = (total / fillet + 0.5) as i64;
        if n_seg < 1 {
            // inner `addDirectedFillet` adds no arc points (nSegs < 1
            // returns early), but the outer overload still adds both
            // endpoints.
            add_pt(&mut pts, p_in, min_d);
            add_pt(&mut pts, p_out, min_d);
            continue;
        }
        let angle_inc = total / n_seg as f64;
        add_pt(&mut pts, p_in, min_d);
        for k in 0..n_seg {
            // `startAngle + directionFactor * i * angleInc` with
            // directionFactor = -1.0 (CLOCKWISE).
            #[allow(clippy::neg_multiply)]
            let angle = a0 + (-1.0 * k as f64) * angle_inc;
            let (s, c) = geos_sin_cos_snap(angle);
            add_pt(&mut pts, (v.0 + distance * c, v.1 + distance * s), min_d);
        }
        add_pt(&mut pts, p_out, min_d);
    }

    // `OffsetSegmentString::closeRing`.
    if let (Some(&first), Some(&last)) = (pts.first(), pts.last())
        && first != last
    {
        pts.push(first);
    }
    pts
}

// ---------------------------------------------------------------------------
// edge coverage — the STRtree `predicate="contains"` replacement.  The
// result set is a pure function of the region: candidates are prefiltered
// by the footprint's bounding box (the STRtree's pruning did the same and
// never changes the outcome), then a strict point-in-convex-polygon test
// decides interior membership (contains = interior; boundary is excluded).
// ---------------------------------------------------------------------------

/// Indices of `(xs[i], ys[i])` strictly inside the closed convex `ring`.
pub fn covered_edge_indices(ring: &[(f64, f64)], xs: &[f64], ys: &[f64]) -> Vec<usize> {
    if ring.len() < 4 {
        return Vec::new();
    }
    let mut minx = f64::INFINITY;
    let mut miny = f64::INFINITY;
    let mut maxx = f64::NEG_INFINITY;
    let mut maxy = f64::NEG_INFINITY;
    for &(x, y) in ring {
        minx = minx.min(x);
        miny = miny.min(y);
        maxx = maxx.max(x);
        maxy = maxy.max(y);
    }

    let mut out: Vec<usize> = Vec::new();
    for (i, (&x, &y)) in xs.iter().zip(ys.iter()).enumerate() {
        if x < minx || x > maxx || y < miny || y > maxy {
            continue;
        }
        if strictly_inside_convex(ring, (x, y)) {
            out.push(i);
        }
    }
    out
}

/// Strict point-in-convex-polygon: every edge cross product must be
/// strictly nonzero and share a sign.  A zero cross product means the
/// point lies on the boundary (or outside), which `contains` excludes.
fn strictly_inside_convex(ring: &[(f64, f64)], p: (f64, f64)) -> bool {
    let mut saw_pos = false;
    let mut saw_neg = false;
    for w in ring.windows(2) {
        let (ax, ay) = w[0];
        let (bx, by) = w[1];
        let cross = (bx - ax) * (p.1 - ay) - (by - ay) * (p.0 - ax);
        if cross > 0.0 {
            saw_pos = true;
        } else if cross < 0.0 {
            saw_neg = true;
        } else {
            return false; // on the boundary -> not contained
        }
        if saw_pos && saw_neg {
            return false;
        }
    }
    saw_pos || saw_neg
}

// ---------------------------------------------------------------------------
// BundleAnalyzer orchestration
// ---------------------------------------------------------------------------

/// Stable deterministic BundleAnalyzer output. Python keeps its public
/// dataclasses (and the dead shapely footprint field) as an API adapter; all
/// decisions affecting the routing model live in this Rust record.
#[derive(Clone, Debug, PartialEq, Eq)]
pub struct BundleRecord {
    pub bundle_id: usize,
    pub net_indices: Vec<usize>,
    pub safety_category: Option<String>,
    pub net_class: String,
    /// The TypeSignature's diff-pair bit.  This is intentionally separate
    /// from `is_diff_pair`: unmatched diff nets can cluster in the ordinary
    /// pool while retaining this signature bit.
    pub signature_has_diff_pair: bool,
    pub is_diff_pair: bool,
    pub constraint_types: Vec<String>,
}

#[derive(Clone, Debug, PartialEq, Eq)]
pub struct BundleManifestRecords {
    pub bundles: Vec<BundleRecord>,
    pub bundle_id_for_net: Vec<(usize, usize)>,
    pub unbundled_net_indices: Vec<usize>,
}

#[derive(Clone, Debug, PartialEq, Eq, Hash)]
struct BundleSignature {
    safety_category: Option<String>,
    net_class: String,
    has_diff_pair: bool,
}

fn bundle_jaccard(a: &HashSet<usize>, b: &HashSet<usize>) -> f64 {
    if a.is_empty() && b.is_empty() {
        return 1.0;
    }
    let intersection = if a.len() <= b.len() {
        a.intersection(b).count()
    } else {
        b.intersection(a).count()
    };
    let union = a.len() + b.len() - intersection;
    if union == 0 {
        0.0
    } else {
        intersection as f64 / union as f64
    }
}

/// BundleAnalyzer's deterministic control flow and manifest records.
///
/// The Python adapter supplies already-resolved pad footprint rings, safety
/// tags, and skeleton midpoint coordinates. Rust computes the v6 type
/// signature, edge covers, strict `jac > threshold` graph, diff-pair
/// handling, connected components, and stable IDs. Group traversal is
/// explicitly first-seen by net index; no hash-map iteration contributes to
/// output ordering.
#[allow(clippy::too_many_arguments)]
pub fn analyze_bundle_manifest(
    net_names: &[String],
    safety_categories: &[Option<String>],
    diff_pairs: &[(String, String, String)],
    footprint_rings: &[Vec<(f64, f64)>],
    edge_ids: &[String],
    mids_x: &[f64],
    mids_y: &[f64],
    jaccard_threshold: f64,
    single_layer_mode: bool,
) -> Result<BundleManifestRecords, &'static str> {
    let n = net_names.len();
    if safety_categories.len() != n || footprint_rings.len() != n {
        return Err("net metadata and footprint arrays must have equal length");
    }
    if edge_ids.len() != mids_x.len() || edge_ids.len() != mids_y.len() {
        return Err("edge ids and midpoint arrays must have equal length");
    }
    if n == 0 {
        return Ok(BundleManifestRecords {
            bundles: Vec::new(),
            bundle_id_for_net: Vec::new(),
            unbundled_net_indices: Vec::new(),
        });
    }

    let diff_pair_names: HashSet<&str> = diff_pairs
        .iter()
        .flat_map(|(p, q, _)| [p.as_str(), q.as_str()])
        .collect();
    let signatures: Vec<BundleSignature> = net_names
        .iter()
        .enumerate()
        .map(|(i, name)| BundleSignature {
            safety_category: safety_categories[i].clone(),
            net_class: if single_layer_mode {
                "signal".to_string()
            } else {
                temper_io_types::placer_core::netclass::classify_net_type_v6(name).to_string()
            },
            has_diff_pair: diff_pair_names.contains(name.as_str()),
        })
        .collect();
    // Canonicalize IDs once.  This both preserves Python's frozenset(edge
    // ID) semantics when IDs are duplicated and avoids cloning a potentially
    // large edge-ID string for every net's cover.
    let mut edge_id_index: HashMap<&str, usize> = HashMap::new();
    let edge_id_keys: Vec<usize> = edge_ids
        .iter()
        .map(|edge_id| {
            let next = edge_id_index.len();
            *edge_id_index.entry(edge_id.as_str()).or_insert(next)
        })
        .collect();
    let edge_covers: Vec<HashSet<usize>> = footprint_rings
        .iter()
        .map(|ring| {
            covered_edge_indices(ring, mids_x, mids_y)
                .into_iter()
                .filter_map(|index| edge_id_keys.get(index).copied())
                .collect()
        })
        .collect();

    // The map indexes groups, but groups are consumed in first-seen order,
    // matching insertion-ordered Python dict semantics.
    let mut group_index: HashMap<BundleSignature, usize> = HashMap::new();
    let mut groups: Vec<(BundleSignature, Vec<usize>)> = Vec::new();
    for (i, signature) in signatures.iter().cloned().enumerate() {
        if let Some(&group) = group_index.get(&signature) {
            groups[group].1.push(i);
        } else {
            group_index.insert(signature.clone(), groups.len());
            groups.push((signature, vec![i]));
        }
    }

    // Python's name-to-index lookup also selects the last duplicate name.
    let net_to_idx: HashMap<&str, usize> = net_names
        .iter()
        .enumerate()
        .map(|(i, name)| (name.as_str(), i))
        .collect();
    let mut bundles = Vec::new();
    let mut bundle_id_for_net = Vec::new();
    let mut unbundled_net_indices = Vec::new();

    for (signature, net_indices) in groups {
        if net_indices.len() == 1 {
            unbundled_net_indices.push(net_indices[0]);
            continue;
        }
        let mut remaining_diff: HashSet<usize> = net_indices
            .iter()
            .copied()
            .filter(|&i| signatures[i].has_diff_pair)
            .collect();
        let mut remaining_non_diff: Vec<usize> = net_indices
            .iter()
            .copied()
            .filter(|&i| !signatures[i].has_diff_pair)
            .collect();

        // Match pairs in caller order, preserving base-name de-duplication.
        let mut matched_bases: HashSet<&str> = HashSet::new();
        for (p_name, n_name, base_name) in diff_pairs {
            if matched_bases.contains(base_name.as_str()) {
                continue;
            }
            let Some(&p_idx) = net_to_idx.get(p_name.as_str()) else { continue };
            let Some(&n_idx) = net_to_idx.get(n_name.as_str()) else { continue };
            if remaining_diff.contains(&p_idx) && remaining_diff.contains(&n_idx) {
                let mut pair = vec![p_idx, n_idx];
                pair.sort_unstable();
                let id = bundles.len();
                bundles.push(BundleRecord {
                    bundle_id: id,
                    net_indices: pair.clone(),
                    safety_category: signature.safety_category.clone(),
                    net_class: signature.net_class.clone(),
                    signature_has_diff_pair: true,
                    is_diff_pair: true,
                    constraint_types: vec!["safety".to_string(), "performance".to_string()],
                });
                bundle_id_for_net.extend(pair.into_iter().map(|i| (i, id)));
                remaining_diff.remove(&p_idx);
                remaining_diff.remove(&n_idx);
                matched_bases.insert(base_name.as_str());
            }
        }

        remaining_non_diff.extend(remaining_diff);
        remaining_non_diff.sort_unstable();
        if remaining_non_diff.is_empty() {
            continue;
        }
        let mut adjacency: HashMap<usize, Vec<usize>> = remaining_non_diff
            .iter()
            .copied()
            .map(|i| (i, Vec::new()))
            .collect();
        for left in 0..remaining_non_diff.len() {
            for right in (left + 1)..remaining_non_diff.len() {
                let a = remaining_non_diff[left];
                let b = remaining_non_diff[right];
                if bundle_jaccard(&edge_covers[a], &edge_covers[b]) > jaccard_threshold {
                    let Some(neighbors) = adjacency.get_mut(&a) else {
                        return Err("bundle adjacency is missing a known net");
                    };
                    neighbors.push(b);
                    let Some(neighbors) = adjacency.get_mut(&b) else {
                        return Err("bundle adjacency is missing a known net");
                    };
                    neighbors.push(a);
                }
            }
        }
        let mut visited = HashSet::new();
        for start in remaining_non_diff {
            if visited.contains(&start) {
                continue;
            }
            let mut component = Vec::new();
            let mut stack = vec![start];
            while let Some(node) = stack.pop() {
                if !visited.insert(node) {
                    continue;
                }
                component.push(node);
                if let Some(neighbors) = adjacency.get(&node) {
                    stack.extend(neighbors.iter().rev().copied());
                }
            }
            component.sort_unstable();
            if component.len() == 1 {
                unbundled_net_indices.push(component[0]);
                continue;
            }
            let id = bundles.len();
            bundles.push(BundleRecord {
                bundle_id: id,
                net_indices: component.clone(),
                safety_category: signature.safety_category.clone(),
                net_class: signature.net_class.clone(),
                signature_has_diff_pair: signature.has_diff_pair,
                is_diff_pair: false,
                constraint_types: Vec::new(),
            });
            bundle_id_for_net.extend(component.into_iter().map(|i| (i, id)));
        }
    }

    unbundled_net_indices.sort_unstable();
    bundle_id_for_net.sort_unstable_by_key(|(net, _)| *net);
    Ok(BundleManifestRecords {
        bundles,
        bundle_id_for_net,
        unbundled_net_indices,
    })
}

// ---------------------------------------------------------------------------
// pyo3 surface
// ---------------------------------------------------------------------------

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

/// GEOS `MultiPoint(points).convex_hull` exterior ring (closed), or the
/// empty ring when the hull is not a polygon.
#[cfg(feature = "python")]
#[pyfunction]
pub fn convex_hull_ring_py(points: Vec<(f64, f64)>) -> PyResult<Vec<(f64, f64)>> {
    temper_py_bridge::catch_unwind(move || convex_hull_ring(&points))
        .map_err(temper_py_bridge::panic_to_err)
}

/// Region-identical ring of `Polygon(ring).buffer(distance)` for a convex
/// ring (GEOS OffsetSegmentGenerator transcription, shapely default
/// `quad_segs=16`).
#[cfg(feature = "python")]
#[pyfunction]
pub fn hull_buffer_ring_py(ring: Vec<(f64, f64)>, distance: f64) -> PyResult<Vec<(f64, f64)>> {
    temper_py_bridge::catch_unwind(move || hull_buffer_ring(&ring, distance))
        .map_err(temper_py_bridge::panic_to_err)
}

/// Indices of the midpoints `(xs[i], ys[i])` strictly inside the closed
/// convex `ring` — the STRtree `predicate="contains"` replacement.
#[cfg(feature = "python")]
#[pyfunction]
pub fn covered_edge_indices_py(
    ring: Vec<(f64, f64)>,
    xs: Vec<f64>,
    ys: Vec<f64>,
) -> PyResult<Vec<usize>> {
    temper_py_bridge::catch_unwind(move || -> PyResult<Vec<usize>> {
        if xs.len() != ys.len() {
            return Err(pyo3::exceptions::PyValueError::new_err(
                "xs and ys must have equal length",
            ));
        }
        Ok(covered_edge_indices(&ring, &xs, &ys))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

/// Rust-owned BundleAnalyzer orchestration.  The tuple records are
/// intentionally plain Python values so the placer shim can preserve its
/// existing dataclass API without reimplementing any decisions.
#[cfg(feature = "python")]
type BundleManifestPyResult = (
    Vec<(usize, Vec<usize>, Option<String>, String, bool, bool, Vec<String>)>,
    Vec<(usize, usize)>,
    Vec<usize>,
);

/// Rust-owned BundleAnalyzer orchestration.  The tuple records are
/// intentionally plain Python values so the placer shim can preserve its
/// existing dataclass API without reimplementing any decisions.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (net_names, safety_categories, diff_pairs, footprint_rings, edge_ids, mids_x, mids_y, jaccard_threshold=0.5, single_layer_mode=false))]
#[allow(clippy::too_many_arguments)]
pub fn analyze_bundle_manifest_py(
    net_names: Vec<String>,
    safety_categories: Vec<Option<String>>,
    diff_pairs: Vec<(String, String, String)>,
    footprint_rings: Vec<Vec<(f64, f64)>>,
    edge_ids: Vec<String>,
    mids_x: Vec<f64>,
    mids_y: Vec<f64>,
    jaccard_threshold: f64,
    single_layer_mode: bool,
) -> PyResult<BundleManifestPyResult> {
    temper_py_bridge::catch_unwind(move || {
        let result = analyze_bundle_manifest(
            &net_names,
            &safety_categories,
            &diff_pairs,
            &footprint_rings,
            &edge_ids,
            &mids_x,
            &mids_y,
            jaccard_threshold,
            single_layer_mode,
        )
        .map_err(pyo3::exceptions::PyValueError::new_err)?;
        let bundles = result
            .bundles
            .into_iter()
            .map(|bundle| {
                (
                    bundle.bundle_id,
                    bundle.net_indices,
                    bundle.safety_category,
                    bundle.net_class,
                    bundle.signature_has_diff_pair,
                    bundle.is_diff_pair,
                    bundle.constraint_types,
                )
            })
            .collect();
        Ok((bundles, result.bundle_id_for_net, result.unbundled_net_indices))
    })
    .map_err(temper_py_bridge::panic_to_err)?
}

/// Compatibility seam for callers that inspect one TypeSignature directly.
/// Production analysis uses the batched path above.
#[cfg(feature = "python")]
#[pyfunction]
pub fn bundle_type_signature_py(
    net_name: String,
    safety_category: Option<String>,
    has_diff_pair: bool,
    single_layer_mode: bool,
) -> PyResult<(Option<String>, String, bool)> {
    temper_py_bridge::catch_unwind(move || {
        (
            safety_category,
            if single_layer_mode {
                "signal".to_string()
            } else {
                temper_io_types::placer_core::netclass::classify_net_type_v6(&net_name).to_string()
            },
            has_diff_pair,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(feature = "python")]
pub fn register(m: &Bound<'_, PyModule>) -> PyResult<()> {
    m.add_function(wrap_pyfunction!(convex_hull_ring_py, m)?)?;
    m.add_function(wrap_pyfunction!(hull_buffer_ring_py, m)?)?;
    m.add_function(wrap_pyfunction!(covered_edge_indices_py, m)?)?;
    m.add_function(wrap_pyfunction!(analyze_bundle_manifest_py, m)?)?;
    m.add_function(wrap_pyfunction!(bundle_type_signature_py, m)?)?;
    Ok(())
}

// ---------------------------------------------------------------------------
// tests
// ---------------------------------------------------------------------------

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    fn canon(ring: &[(f64, f64)]) -> Vec<(f64, f64)> {
        let mut v: Vec<(f64, f64)> = ring[..ring.len() - 1].to_vec();
        v.sort_by(|a, b| {
            (a.0.partial_cmp(&b.0).unwrap_or(Ordering::Equal))
                .then(a.1.partial_cmp(&b.1).unwrap_or(Ordering::Equal))
        });
        v
    }

    #[cfg_attr(test, test)]
    fn orientation_is_straight_for_exact_collinear() {
        assert_eq!(orientation_index(0.0, 0.0, 1.0, 1.0, 2.0, 2.0), 0);
        assert_eq!(orientation_index(0.0, 0.0, 1.0, 0.0, 2.0, 0.0), 0);
    }

    #[cfg_attr(test, test)]
    fn orientation_left_right_basic() {
        assert_eq!(orientation_index(0.0, 0.0, 1.0, 0.0, 0.0, 1.0), 1); // q above -> CCW (left)
        assert_eq!(orientation_index(0.0, 0.0, 1.0, 0.0, 0.0, -1.0), -1); // q below -> CW (right)
        assert_eq!(orientation_index(0.0, 0.0, 1.0, 0.0, 2.0, 1.0), 1);
    }

    #[cfg_attr(test, test)]
    fn orientation_dd_path_exercises_double_double() {
        // Near-collinear along the diagonal at 1e10 scale: the f64 filter is
        // indeterminate (the products nearly cancel), so the sign must come
        // from the DD determinant.  True determinant = 1e10 > 0 -> LEFT.
        assert_eq!(
            orientation_index(0.0, 0.0, 1.0e10, 1.0e10, 2.0e10, 2.0e10 + 1.0),
            1
        );
        // and the same shape just past the line -> RIGHT.
        assert_eq!(
            orientation_index(0.0, 0.0, 1.0e10, 1.0e10, 2.0e10, 2.0e10 - 1.0),
            -1
        );
    }

    #[cfg_attr(test, test)]
    fn hull_triangle_and_rectangle_vertex_sets() {
        // CW rings, GEOS start vertex (lowest).
        let tri = convex_hull_ring(&[(0.0, 0.0), (10.0, 0.0), (5.0, 7.0)]);
        assert_eq!(
            canon(&tri),
            vec![(0.0, 0.0), (5.0, 7.0), (10.0, 0.0)]
        );
        let rect = convex_hull_ring(&[(0.0, 0.0), (4.0, 0.0), (4.0, 3.0), (0.0, 3.0)]);
        assert_eq!(
            canon(&rect),
            vec![(0.0, 0.0), (0.0, 3.0), (4.0, 0.0), (4.0, 3.0)]
        );
    }

    #[cfg_attr(test, test)]
    fn hull_drops_collinear_and_duplicate_points() {
        // Collinear boundary points are dropped by cleanRing; duplicates by
        // extractUnique.
        let hull = convex_hull_ring(&[
            (0.0, 0.0),
            (5.0, 0.0),
            (10.0, 0.0),
            (5.0, 0.5),
            (3.0, 2.0),
        ]);
        assert_eq!(canon(&hull), vec![(0.0, 0.0), (3.0, 2.0), (10.0, 0.0)]);
        let dup = convex_hull_ring(&[(1.0, 1.0), (1.0, 1.0), (5.0, 1.0), (5.0, 5.0), (1.0, 5.0)]);
        assert_eq!(
            canon(&dup),
            vec![(1.0, 1.0), (1.0, 5.0), (5.0, 1.0), (5.0, 5.0)]
        );
    }

    #[cfg_attr(test, test)]
    fn hull_non_polygon_returns_empty() {
        assert!(convex_hull_ring(&[]).is_empty());
        assert!(convex_hull_ring(&[(0.0, 0.0)]).is_empty());
        assert!(convex_hull_ring(&[(0.0, 0.0), (5.0, 0.0)]).is_empty());
        // three collinear points -> GEOS returns a LineString, not a polygon.
        assert!(convex_hull_ring(&[(0.0, 0.0), (5.0, 0.0), (10.0, 0.0)]).is_empty());
    }

    #[cfg_attr(test, test)]
    fn triangle_buffer_ring_matches_measured_geos() {
        // Verified against shapely 2.1.2 / GEOS 3.13.1
        // `MultiPoint([(0,0),(10,0),(5,7)]).convex_hull.buffer(1.5)`.
        let ring = convex_hull_ring(&[(0.0, 0.0), (10.0, 0.0), (5.0, 7.0)]);
        let buf = hull_buffer_ring(&ring, 1.5);
        // The first emitted point is the offset of the closing edge at the
        // first hull vertex.
        assert_eq!(buf[0], (0.0, -1.5));
        assert_eq!(buf[buf.len() - 1], buf[0]);
        // 3 corners * (1 + 21 + 1) arc points each, shared at the offset
        // edges: 23 + 20 + 23 = 66 distinct + 1 closure.
        assert_eq!(buf.len(), 67);
        // Every corner vertex is at radius 1.5 from some hull vertex.
        let verts = [(0.0, 0.0), (10.0, 0.0), (5.0, 7.0)];
        for &(x, y) in &buf[..buf.len() - 1] {
            let min_d = verts
                .iter()
                .map(|&v| geos_distance((x, y), v))
                .fold(f64::INFINITY, f64::min);
            assert!(
                (min_d - 1.5).abs() < 1e-12,
                "buffer point ({x},{y}) not at radius 1.5 of any hull vertex"
            );
        }
    }

    #[cfg_attr(test, test)]
    fn buffer_zero_distance_returns_input_ring() {
        let ring = convex_hull_ring(&[(0.0, 0.0), (10.0, 0.0), (5.0, 7.0)]);
        assert_eq!(hull_buffer_ring(&ring, 0.0), ring);
    }

    #[cfg_attr(test, test)]
    fn covered_edge_indices_basic_and_boundary() {
        let ring = vec![(0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0), (0.0, 0.0)];
        let xs = vec![5.0, 5.0, 5.0, 0.0, 15.0, 5.0, -1.0, 5.0];
        let ys = vec![5.0, 0.0, 10.0, 5.0, 5.0, 12.0, 5.0, -1.0];
        // interior only; on-edge and outside are excluded (contains).
        assert_eq!(covered_edge_indices(&ring, &xs, &ys), vec![0]);
    }

    #[cfg_attr(test, test)]
    fn covered_edge_indices_handles_cw_and_ccw() {
        // The Rust buffer ring is CW; the shim's 1/2-pad box rings are CCW.
        let cw = vec![(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (0.0, 0.0)];
        let ccw = vec![(0.0, 0.0), (0.0, 10.0), (10.0, 10.0), (10.0, 0.0), (0.0, 0.0)];
        let xs = vec![5.0, 5.0];
        let ys = vec![5.0, 20.0];
        assert_eq!(covered_edge_indices(&cw, &xs, &ys), vec![0]);
        assert_eq!(covered_edge_indices(&ccw, &xs, &ys), vec![0]);
    }

    fn rect(min_x: f64, max_x: f64) -> Vec<(f64, f64)> {
        vec![
            (min_x, -1.0),
            (max_x, -1.0),
            (max_x, 1.0),
            (min_x, 1.0),
            (min_x, -1.0),
        ]
    }

    fn analyze_fixture(
        names: &[&str],
        rings: Vec<Vec<(f64, f64)>>,
        threshold: f64,
    ) -> BundleManifestRecords {
        let names = names.iter().map(|s| (*s).to_string()).collect::<Vec<_>>();
        let safety = vec![None; names.len()];
        let xs = vec![0.0, 1.0, 2.0, 3.0, 4.0, 5.0];
        let ys = vec![0.0; xs.len()];
        let ids = (0..xs.len()).map(|i| format!("E{i}")).collect::<Vec<_>>();
        analyze_bundle_manifest(
            &names,
            &safety,
            &[],
            &rings,
            &ids,
            &xs,
            &ys,
            threshold,
            false,
        )
        .unwrap()
    }

    #[cfg_attr(test, test)]
    fn analyze_empty_and_singleton_are_unbundled() {
        let empty = analyze_fixture(&[], Vec::new(), 0.5);
        assert!(empty.bundles.is_empty());
        assert!(empty.unbundled_net_indices.is_empty());
        let one = analyze_fixture(&["SIG"], vec![rect(-1.0, 1.0)], 0.5);
        assert!(one.bundles.is_empty());
        assert_eq!(one.unbundled_net_indices, vec![0]);
    }

    #[cfg_attr(test, test)]
    fn analyze_threshold_is_strict() {
        let rings = vec![rect(-1.0, 1.1), rect(0.9, 1.1)];
        let at_boundary = analyze_fixture(&["SIG_A", "SIG_B"], rings.clone(), 0.5);
        assert!(at_boundary.bundles.is_empty());
        assert_eq!(at_boundary.unbundled_net_indices, vec![0, 1]);
        let above_boundary = analyze_fixture(&["SIG_A", "SIG_B"], rings, 0.499);
        assert_eq!(above_boundary.bundles[0].net_indices, vec![0, 1]);
    }

    #[cfg_attr(test, test)]
    fn analyze_uses_edge_id_set_semantics_for_duplicate_ids() {
        let names = vec!["SIG_A".to_string(), "SIG_B".to_string()];
        let rings = vec![rect(-1.0, 2.1), rect(0.9, 3.1)];
        // Index sets overlap 2/4, but duplicate E1 means ID sets overlap
        // only 1/3.  The former would bundle at .4; the latter correctly
        // preserves Python's frozenset(edge_id) semantics and does not.
        let result = analyze_bundle_manifest(
            &names,
            &[None, None],
            &[],
            &rings,
            &[
                "E0".to_string(),
                "E1".to_string(),
                "E1".to_string(),
                "E2".to_string(),
            ],
            &[0.0, 1.0, 2.0, 3.0],
            &[0.0, 0.0, 0.0, 0.0],
            0.4,
            false,
        )
        .unwrap();
        assert!(result.bundles.is_empty());
        assert_eq!(result.unbundled_net_indices, vec![0, 1]);
    }

    #[cfg_attr(test, test)]
    fn analyze_incompatible_signatures_do_not_bundle() {
        let names = vec!["AC_L".to_string(), "SIG_A".to_string()];
        let rings = vec![rect(-1.0, 2.1), rect(-1.0, 2.1)];
        let result = analyze_bundle_manifest(
            &names,
            &[None, None],
            &[],
            &rings,
            &["E0".to_string()],
            &[0.0],
            &[0.0],
            0.5,
            false,
        )
        .unwrap();
        assert!(result.bundles.is_empty());
        assert_eq!(result.unbundled_net_indices, vec![0, 1]);
    }

    #[cfg_attr(test, test)]
    fn analyze_unmatched_diff_nets_keep_signature_bit_without_pair_flag() {
        let names = vec!["USB_DP".to_string(), "USB_DN".to_string()];
        let rings = vec![rect(-1.0, 2.1), rect(-1.0, 2.1)];
        let result = analyze_bundle_manifest(
            &names,
            &[None, None],
            &[
                ("USB_DP".to_string(), "MISSING_P".to_string(), "DP".to_string()),
                ("USB_DN".to_string(), "MISSING_N".to_string(), "DN".to_string()),
            ],
            &rings,
            &["E0".to_string()],
            &[0.0],
            &[0.0],
            0.5,
            false,
        )
        .unwrap();
        assert_eq!(result.bundles.len(), 1);
        assert!(result.bundles[0].signature_has_diff_pair);
        assert!(!result.bundles[0].is_diff_pair);
    }

    #[cfg_attr(test, test)]
    fn analyze_transitive_grouping_and_order_are_stable() {
        let rings = vec![rect(-1.0, 3.1), rect(0.9, 4.1), rect(1.9, 5.1)];
        let result = analyze_fixture(&["SIG_A", "SIG_B", "SIG_C"], rings, 0.5);
        assert_eq!(result.bundles.len(), 1);
        assert_eq!(result.bundles[0].bundle_id, 0);
        assert_eq!(result.bundles[0].net_indices, vec![0, 1, 2]);
        assert_eq!(result.bundle_id_for_net, vec![(0, 0), (1, 0), (2, 0)]);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("bundle_analyzer::tests::orientation_is_straight_for_exact_collinear", orientation_is_straight_for_exact_collinear),
        ("bundle_analyzer::tests::orientation_left_right_basic", orientation_left_right_basic),
        ("bundle_analyzer::tests::orientation_dd_path_exercises_double_double", orientation_dd_path_exercises_double_double),
        ("bundle_analyzer::tests::hull_triangle_and_rectangle_vertex_sets", hull_triangle_and_rectangle_vertex_sets),
        ("bundle_analyzer::tests::hull_drops_collinear_and_duplicate_points", hull_drops_collinear_and_duplicate_points),
        ("bundle_analyzer::tests::hull_non_polygon_returns_empty", hull_non_polygon_returns_empty),
        ("bundle_analyzer::tests::triangle_buffer_ring_matches_measured_geos", triangle_buffer_ring_matches_measured_geos),
        ("bundle_analyzer::tests::buffer_zero_distance_returns_input_ring", buffer_zero_distance_returns_input_ring),
        ("bundle_analyzer::tests::covered_edge_indices_basic_and_boundary", covered_edge_indices_basic_and_boundary),
        ("bundle_analyzer::tests::covered_edge_indices_handles_cw_and_ccw", covered_edge_indices_handles_cw_and_ccw),
        ("bundle_analyzer::tests::analyze_empty_and_singleton_are_unbundled", analyze_empty_and_singleton_are_unbundled),
        ("bundle_analyzer::tests::analyze_threshold_is_strict", analyze_threshold_is_strict),
        ("bundle_analyzer::tests::analyze_uses_edge_id_set_semantics_for_duplicate_ids", analyze_uses_edge_id_set_semantics_for_duplicate_ids),
        ("bundle_analyzer::tests::analyze_incompatible_signatures_do_not_bundle", analyze_incompatible_signatures_do_not_bundle),
        ("bundle_analyzer::tests::analyze_unmatched_diff_nets_keep_signature_bit_without_pair_flag", analyze_unmatched_diff_nets_keep_signature_bit_without_pair_flag),
        ("bundle_analyzer::tests::analyze_transitive_grouping_and_order_are_stable", analyze_transitive_grouping_and_order_are_stable),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
