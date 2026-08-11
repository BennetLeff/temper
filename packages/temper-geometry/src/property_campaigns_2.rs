// Second property campaign over temper-geometry: metamorphic and invariant
// properties over four independent, pure, deterministic kernels that the
// first campaign (`property_campaigns.rs`, landed a few hours before this
// one) does not touch -- `sdf.rs` (signed distance functions), `polygon.rs`
// (area/centroid/containment/transforms), `overlap.rs` (AABB/Rect
// separation and overlap), and `projections.rs` (constraint-satisfaction
// projection operators). The first campaign already covers
// `kicad_transform.rs`, `convex_hull.rs`, and `connected_components.rs`;
// nothing here repeats a property over any of those three.
//
// Why a *second* module instead of appending to the first
// -----------------------------------------------------------------------
// `property_campaigns.rs`'s own doc comment says its shape copies
// `packages/temper-drc-rs/src/rules/drc/property_campaigns.rs`. Both of
// those are single modules per crate. This crate splits into two instead
// because eleven other agents are working in this repository concurrently
// (see the top-level task boundary) and appending thousands of lines to a
// file another agent might also be mid-edit on is exactly the kind of
// merge collision `kicad_transform.rs`'s own "declared at the tail so
// appends cannot rewrite a parallel agent's lines" comment in `lib.rs`
// warns about. A second, independently-registered module sidesteps that
// without touching the first campaign's file at all.
//
// Relationship to `tests/proptest_equivalence.rs`
// -----------------------------------------------------------------------
// That file already has `proptest!` coverage for several of the same
// kernels (`sdf`, `polygon`, `overlap`, `projections`) -- box_box_distance
// symmetry, polygon area invariance under translation/rotation, SDF
// union/intersection identities, and more. None of that coverage reaches
// the wasm32 Worker tier: `proptest` is a dev-dependency, absent from the
// ordinary (non-test) build `scripts/gen_wasm_test_registry.py` compiles
// into (see `property_campaigns.rs`'s own doc comment for the same
// exclusion). So today the wasm tier has *zero* property coverage of these
// four kernels -- only the hand-written example tests already in each
// module's own `mod tests`. Porting some of the same invariants into this
// SplitMix64-seeded, wasm-compatible harness is not redundant with that
// native suite; it is closing a coverage gap that exists specifically
// because that suite cannot run where this one does. Where a property
// below overlaps conceptually with one in `proptest_equivalence.rs`, its
// doc comment says so; several others (cross-implementation SDF sign
// agreement, fan-triangulation area additivity, the smooth-union/
// -intersection sharp bounds, separation monotonicity under receding
// translation, self-overlap totality) are not in that file at all.
//
// Every property is a metamorphic or invariant relation over the real
// kernel -- never a restatement of the implementation. Each was checked
// against a deliberately broken kernel and shown to fail on exactly the
// cases it targets (and leave every other property green), then the
// kernel was reverted; see this crate's PR body for the mutation-testing
// evidence.
//
// No `proptest`, no RNG crate: `SplitMix64` below is the same small,
// self-contained, portable PRNG `property_campaigns.rs` uses, duplicated
// here rather than imported from that module. It is a private,
// non-`pub` item there (module-local, same as this copy), so nothing
// outside that module can name it; re-deriving a few lines of PRNG code
// keeps this module readable and auditable on its own, the same tradeoff
// `property_campaigns.rs`'s own doc comment makes relative to
// `temper-drc-rs`'s independent copy of the same generator.
//
// Every item below (down to `mod tests`) is reachable ONLY from that
// module's `#[test]` functions -- exactly the same reachability shape
// `property_campaigns.rs` documents, for the same reason (a build with
// neither `test` nor `wasm-registry` active sees everything below as
// unused).
#![allow(dead_code)]

// ---------------------------------------------------------------------------
// Deterministic PRNG (SplitMix64) -- see the module doc above for why this
// is a self-contained duplicate rather than a shared import.
// ---------------------------------------------------------------------------

struct SplitMix64(u64);

impl SplitMix64 {
    fn new(seed: u64) -> Self {
        Self(seed)
    }

    fn next_u64(&mut self) -> u64 {
        self.0 = self.0.wrapping_add(0x9E37_79B9_7F4A_7C15);
        let mut z = self.0;
        z = (z ^ (z >> 30)).wrapping_mul(0xBF58_476D_1CE4_E5B9);
        z = (z ^ (z >> 27)).wrapping_mul(0x94D0_49BB_1331_11EB);
        z ^ (z >> 31)
    }

    /// Uniform float in `[0, 1)`.
    fn next_f64(&mut self) -> f64 {
        (self.next_u64() >> 11) as f64 * (1.0 / (1u64 << 53) as f64)
    }

    /// Uniform float in `[lo, hi)`.
    fn range(&mut self, lo: f64, hi: f64) -> f64 {
        lo + self.next_f64() * (hi - lo)
    }

    /// Uniform index in `[0, n)`. `n` is always a small, non-zero,
    /// compile-time- or generation-bounded count in this module.
    fn index(&mut self, n: usize) -> usize {
        (self.next_u64() % n as u64) as usize
    }
}

/// A property-local PRNG stream, independent of the base-case generator's
/// stream, so a property's own randomized parameters don't correlate with
/// the case `seed` produced. `salt` distinguishes properties sharing the
/// same base seed.
fn sub_rng(seed: u64, salt: u64) -> SplitMix64 {
    SplitMix64::new(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15).wrapping_add(salt))
}

use crate::types::Point;

// ---------------------------------------------------------------------------
// Shared helper: a convex polygon inscribed on a common circle.
//
// Placing every vertex at the SAME radius from a center, at strictly
// increasing angles, always yields a simple, strictly convex polygon --
// this is a geometric fact independent of how the angles are spaced
// (connecting points around a circle in increasing-angle order is a convex
// hull by construction). The jitter amplitude (0.2 of the base slot) is
// chosen so the maximum possible gap between consecutive vertices,
// `slot * (1 + 2*0.2) = 1.4 * slot`, stays under 180 degrees even at the
// smallest generated `n` (3): `1.4 * 120 deg = 168 deg`, comfortably under
// the 180 deg threshold above which the circle's own center could fall
// outside the polygon. Shared by the `sdf` and `polygon` kernel sections
// below. Returns `(vertices, center, radius)`.
fn gen_convex_polygon(seed: u64) -> (Vec<Point>, Point, f64) {
    let mut rng = SplitMix64::new(seed);
    let n = 3 + rng.index(10); // 3..=12
    let cx = rng.range(-300.0, 300.0);
    let cy = rng.range(-300.0, 300.0);
    let r = rng.range(5.0, 200.0);
    let slot = std::f64::consts::TAU / n as f64;
    let verts: Vec<Point> = (0..n)
        .map(|i| {
            let jitter = rng.range(-0.2, 0.2) * slot;
            let theta = i as f64 * slot + jitter;
            Point::new(cx + r * theta.cos(), cy + r * theta.sin())
        })
        .collect();
    (verts, Point::new(cx, cy), r)
}

// ===========================================================================
// Kernel 1: sdf.rs -- signed distance functions for circles, polygons, and
// capsules, plus the polynomial smooth-union/smooth-intersection
// combinators.
// ===========================================================================

use crate::sdf::{
    sdf_capsule, sdf_circle, sdf_convex_polygon, sdf_polygon, sdf_smooth_intersection,
    sdf_smooth_union,
};

const SDF_SALT_ANGLE: u64 = 0xA1;
const SDF_SALT_IN: u64 = 0xA2;
const SDF_SALT_OUT: u64 = 0xA3;
const SDF_SALT_TRANSLATE: u64 = 0xA4;
const SDF_SALT_POLY_TRANSLATE: u64 = 0xA5;

fn sdf_gen_circle(seed: u64) -> (f64, f64, f64) {
    let mut rng = SplitMix64::new(seed);
    let cx = rng.range(-500.0, 500.0);
    let cy = rng.range(-500.0, 500.0);
    let r = rng.range(0.5, 200.0);
    (cx, cy, r)
}

fn sdf_gen_polygon(seed: u64) -> Vec<Point> {
    let mut rng = SplitMix64::new(seed);
    let n = 3 + rng.index(8); // 3..=10
    (0..n)
        .map(|_| Point::new(rng.range(-150.0, 150.0), rng.range(-150.0, 150.0)))
        .collect()
}

/// A circle's SDF must be exactly zero on its own boundary, strictly
/// negative strictly inside, and strictly positive strictly outside --
/// the defining property of a signed distance function.
///
/// Bug this would catch: any sign error in `sdf_circle` (e.g. a refactor
/// that flips `distance - r` to `r - distance`) fails all three checks at
/// once; a subtler bug that only mishandles the boundary case (an
/// off-by-epsilon in how `r` is subtracted) fails only the boundary check
/// while sign checks stay green -- so this single property isolates which
/// failure mode a mutation produces from its assertion message.
pub(crate) fn sdf_circle_sign_and_boundary_impl(seed: u64) {
    let (cx, cy, r) = sdf_gen_circle(seed);

    let mut b_rng = sub_rng(seed, SDF_SALT_ANGLE);
    let theta_b = b_rng.range(0.0, std::f64::consts::TAU);
    let boundary = Point::new(cx + r * theta_b.cos(), cy + r * theta_b.sin());
    let d_boundary = sdf_circle(&boundary, cx, cy, r);
    let tol = 1e-7 * (r + 1.0);
    assert!(
        d_boundary.abs() < tol,
        "sdf_circle nonzero on its own boundary: seed={seed} cx={cx} cy={cy} r={r} d={d_boundary}"
    );

    let mut in_rng = sub_rng(seed, SDF_SALT_IN);
    let theta_in = in_rng.range(0.0, std::f64::consts::TAU);
    let k_in = in_rng.range(0.0, 0.95);
    let inside = Point::new(cx + r * k_in * theta_in.cos(), cy + r * k_in * theta_in.sin());
    let d_in = sdf_circle(&inside, cx, cy, r);
    assert!(
        d_in < 0.0,
        "sdf_circle non-negative strictly inside the circle: seed={seed} k_in={k_in} d={d_in}"
    );

    let mut out_rng = sub_rng(seed, SDF_SALT_OUT);
    let theta_out = out_rng.range(0.0, std::f64::consts::TAU);
    let k_out = out_rng.range(1.05, 20.0);
    let outside = Point::new(cx + r * k_out * theta_out.cos(), cy + r * k_out * theta_out.sin());
    let d_out = sdf_circle(&outside, cx, cy, r);
    assert!(
        d_out > 0.0,
        "sdf_circle non-positive strictly outside the circle: seed={seed} k_out={k_out} d={d_out}"
    );
}

/// `sdf_circle` is equivariant under translation: shifting both the query
/// point and the circle's center by the same vector must not change the
/// returned distance. Distinct from `proptest_equivalence.rs`'s
/// `sdf_circle_center_is_negative_radius` (a single fixed-relationship
/// check at the center only); this exercises arbitrary points anywhere
/// relative to the circle.
///
/// Bug this would catch: any accidental use of an absolute coordinate
/// (e.g. a cached/global origin) instead of the relative `p - center`
/// this kernel is documented to use.
pub(crate) fn sdf_circle_translation_equivariant_impl(seed: u64) {
    let (cx, cy, r) = sdf_gen_circle(seed);
    let mut p_rng = sub_rng(seed, SDF_SALT_ANGLE);
    let p = Point::new(p_rng.range(-800.0, 800.0), p_rng.range(-800.0, 800.0));
    let d0 = sdf_circle(&p, cx, cy, r);

    let mut t_rng = sub_rng(seed, SDF_SALT_TRANSLATE);
    let tx = t_rng.range(-1000.0, 1000.0);
    let ty = t_rng.range(-1000.0, 1000.0);
    let p_t = Point::new(p.x + tx, p.y + ty);
    let d1 = sdf_circle(&p_t, cx + tx, cy + ty, r);

    let tol = 1e-8 * (d0.abs() + r + 1.0);
    assert!(
        (d0 - d1).abs() < tol,
        "sdf_circle not translation-equivariant: seed={seed} d0={d0} d1={d1} tx={tx} ty={ty}"
    );
}

/// `sdf_polygon` is equivariant under translation, for ANY vertex list --
/// convex, concave, even self-intersecting -- because its winding-number
/// and edge-projection arithmetic is built entirely from vertex-to-point
/// differences, which a uniform shift leaves unchanged.
///
/// Bug this would catch: a caching/memoization path keyed on absolute
/// vertex coordinates, or an accidental mix of pre- and post-translation
/// state (e.g. translating the query point but not every vertex).
pub(crate) fn sdf_polygon_translation_equivariant_impl(seed: u64) {
    let verts = sdf_gen_polygon(seed);
    let mut p_rng = sub_rng(seed, SDF_SALT_ANGLE);
    let p = Point::new(p_rng.range(-500.0, 500.0), p_rng.range(-500.0, 500.0));
    let d0 = sdf_polygon(&p, &verts);

    let mut t_rng = sub_rng(seed, SDF_SALT_POLY_TRANSLATE);
    let tx = t_rng.range(-1000.0, 1000.0);
    let ty = t_rng.range(-1000.0, 1000.0);
    let p_t = Point::new(p.x + tx, p.y + ty);
    let verts_t: Vec<Point> = verts.iter().map(|v| Point::new(v.x + tx, v.y + ty)).collect();
    let d1 = sdf_polygon(&p_t, &verts_t);

    let tol = 1e-6 * (d0.abs() + 1.0);
    assert!(
        (d0 - d1).abs() < tol,
        "sdf_polygon not translation-equivariant: seed={seed} d0={d0} d1={d1} tx={tx} ty={ty}"
    );
}

/// `sdf_polygon` (winding-number + clamped-edge-distance) and
/// `sdf_convex_polygon` (max over unclamped supporting half-plane
/// distances) are two independently-coded algorithms that, for a genuinely
/// convex polygon, must agree on which side of the boundary any point is
/// on -- sign agreement for a convex shape is exact regardless of distance
/// to the boundary, so this holds for a fully random point anywhere near
/// the polygon, not just points known in advance to be deep inside or far
/// outside.
///
/// Bug this would catch: a sign error introduced into either algorithm
/// alone (they share no code) -- this is exactly the kind of
/// cross-implementation check the first campaign's kt_isometry /
/// kt_round_trip pair uses for `kicad_transform.rs`, applied here to the
/// two independent SDF-polygon algorithms.
pub(crate) fn sdf_convex_vs_polygon_sign_agreement_impl(seed: u64) {
    let (verts, center, r) = gen_convex_polygon(seed);
    let mut p_rng = sub_rng(seed, SDF_SALT_ANGLE);
    let px = center.x + p_rng.range(-1.5, 1.5) * r;
    let py = center.y + p_rng.range(-1.5, 1.5) * r;
    let p = Point::new(px, py);

    let d_poly = sdf_polygon(&p, &verts);
    let d_conv = sdf_convex_polygon(&p, &verts);
    assert_eq!(
        d_poly < 0.0,
        d_conv < 0.0,
        "sdf_polygon and sdf_convex_polygon disagree on inside/outside for the same convex \
         polygon: seed={seed} p=({px}, {py}) d_poly={d_poly} d_conv={d_conv}"
    );
}

/// A capsule degenerates to a circle when its two endpoints coincide (the
/// module's own doc comment for `sdf_capsule` says as much); this checks
/// the claim as a metamorphic relation between two different functions
/// rather than the single hand-picked point the existing unit test
/// (`test_sdf_capsule_degenerate`) uses.
///
/// Bug this would catch: a change to the zero-length-segment branch in
/// `sdf_capsule` (`ab_len_sq > 1e-15`) that clamps `t` to something other
/// than `0.0`, or any divergence between its distance formula and
/// `sdf_circle`'s.
pub(crate) fn sdf_capsule_degenerate_matches_circle_impl(seed: u64) {
    let mut rng = SplitMix64::new(seed);
    let ax = rng.range(-500.0, 500.0);
    let ay = rng.range(-500.0, 500.0);
    let r = rng.range(0.1, 100.0);
    let mut p_rng = sub_rng(seed, SDF_SALT_ANGLE);
    let p = Point::new(p_rng.range(-800.0, 800.0), p_rng.range(-800.0, 800.0));
    let a = Point::new(ax, ay);

    let d_capsule = sdf_capsule(&p, &a, &a, r);
    let d_circle = sdf_circle(&p, ax, ay, r);
    let tol = 1e-9 * (d_circle.abs() + 1.0);
    assert!(
        (d_capsule - d_circle).abs() < tol,
        "a degenerate capsule (a == b) must equal a circle: seed={seed} d_capsule={d_capsule} \
         d_circle={d_circle}"
    );
}

fn sdf_gen_pair_and_k(seed: u64) -> (f64, f64, f64) {
    let mut rng = SplitMix64::new(seed);
    let d1 = rng.range(-100.0, 100.0);
    let d2 = rng.range(-100.0, 100.0);
    let k = rng.range(0.01, 50.0);
    (d1, d2, k)
}

/// `sdf_smooth_union` (IQ's polynomial smooth-min) is a provable LOWER
/// bound on the sharp union `min(d1, d2)` for any `k > 0`: writing
/// `h = clamp(0.5 + 0.5*(d2-d1)/k, 0, 1)`, the result is
/// `mix(d2, d1, h) - k*h*(1-h)`; the mix term alone is a convex
/// combination of `d1, d2` (so it is between them, hence `<= max(d1,d2)`
/// generally and equals `min(d1,d2)` exactly at the clamped extremes), and
/// the subtracted `k*h*(1-h)` term is always `>= 0`, so the whole
/// expression never exceeds the true minimum.
///
/// Bug this would catch: a sign flip on the `k*h*(1-h)` correction term
/// (turning the smooth union into a smooth OVER-estimate of the sharp
/// union), which would violate this bound for most `(d1, d2, k)` where `h`
/// is not already clamped to 0 or 1.
pub(crate) fn sdf_smooth_union_lower_bound_impl(seed: u64) {
    let (d1, d2, k) = sdf_gen_pair_and_k(seed);
    let result = sdf_smooth_union(d1, d2, k);
    let true_min = d1.min(d2);
    let tol = 1e-9 * (d1.abs() + d2.abs() + k + 1.0);
    assert!(
        result <= true_min + tol,
        "sdf_smooth_union exceeded the sharp union (must always be <= min(d1,d2)): seed={seed} \
         d1={d1} d2={d2} k={k} result={result} true_min={true_min}"
    );
}

/// The dual of the property above: `sdf_smooth_intersection` is a provable
/// UPPER bound on the sharp intersection `max(d1, d2)` for any `k > 0`, by
/// the same mix-plus-non-negative-correction argument with the sign of the
/// correction term flipped.
///
/// Bug this would catch: the mirror-image mutation of the one above (a
/// sign flip that turns the smooth intersection into an under-estimate),
/// or the two smooth combinators' correction terms getting swapped with
/// each other during a refactor.
pub(crate) fn sdf_smooth_intersection_upper_bound_impl(seed: u64) {
    let (d1, d2, k) = sdf_gen_pair_and_k(seed);
    let result = sdf_smooth_intersection(d1, d2, k);
    let true_max = d1.max(d2);
    let tol = 1e-9 * (d1.abs() + d2.abs() + k + 1.0);
    assert!(
        result >= true_max - tol,
        "sdf_smooth_intersection undershot the sharp intersection (must always be >= \
         max(d1,d2)): seed={seed} d1={d1} d2={d2} k={k} result={result} true_max={true_max}"
    );
}

// ===========================================================================
// Kernel 2: polygon.rs -- shoelace area/centroid, point-in-polygon,
// perimeter, and the translate/scale/rotate transforms.
// ===========================================================================

use crate::polygon::{
    point_in_polygon_winding, polygon_area, polygon_orientation, polygon_perimeter,
    polygon_signed_area, rotate_polygon, scale_polygon, translate_polygon, triangle_area,
};

const PG_SALT_TRANSLATE: u64 = 0xA6;
const PG_SALT_ROTATE: u64 = 0xA7;
const PG_SALT_FAR: u64 = 0xA8;
const PG_SALT_SCALE: u64 = 0xA9;

fn pg_gen_arbitrary_polygon(seed: u64) -> Vec<Point> {
    let mut rng = SplitMix64::new(seed);
    let n = 3 + rng.index(10); // 3..=12
    (0..n)
        .map(|_| Point::new(rng.range(-150.0, 150.0), rng.range(-150.0, 150.0)))
        .collect()
}

/// The shoelace formula is translation-invariant by pure algebraic
/// identity (shifting every vertex by the same vector leaves every
/// `x_i*y_j - x_j*y_i` cross term's contribution to total area unchanged),
/// for ANY vertex list, not just convex ones -- so this uses the
/// unconstrained arbitrary-polygon generator. Same relation
/// `proptest_equivalence.rs`'s `polygon_area_translation_invariant` checks
/// natively; this ports it to the wasm-reachable harness (see module doc).
///
/// Bug this would catch: an accumulator that mixes pre- and
/// post-translation vertex coordinates, or an off-by-one in
/// `translate_polygon`'s per-vertex map.
pub(crate) fn poly_translate_area_invariant_impl(seed: u64) {
    let verts = pg_gen_arbitrary_polygon(seed);
    let a0 = polygon_area(&verts);
    let mut rng = sub_rng(seed, PG_SALT_TRANSLATE);
    let dx = rng.range(-500.0, 500.0);
    let dy = rng.range(-500.0, 500.0);
    let moved = translate_polygon(&verts, dx, dy);
    let a1 = polygon_area(&moved);
    let tol = (a0.abs() * 1e-6).max(1e-4);
    assert!(
        (a0 - a1).abs() < tol,
        "polygon_area not translation-invariant: seed={seed} dx={dx} dy={dy} a0={a0} a1={a1}"
    );
}

/// Area is invariant under rotation about any center -- `rotate_polygon`
/// rotates about the polygon's own arithmetic-mean centroid, but the
/// invariant holds regardless of which center is used, since rotation is
/// an isometry. Same relation as `proptest_equivalence.rs`'s
/// `polygon_area_preserved_under_rotation`, ported to the wasm harness.
///
/// Bug this would catch: a rotation matrix typo (a `+` where a `-` is
/// required in the sine term) that turns the rotation into a non-isometric
/// shear, which would change enclosed area.
pub(crate) fn poly_rotate_area_invariant_impl(seed: u64) {
    let verts = pg_gen_arbitrary_polygon(seed);
    let a0 = polygon_area(&verts);
    let mut rng = sub_rng(seed, PG_SALT_ROTATE);
    let angle = rng.range(0.0, std::f64::consts::TAU);
    let rotated = rotate_polygon(&verts, angle);
    let a1 = polygon_area(&rotated);
    let tol = (a0.abs() * 1e-6).max(1e-6);
    assert!(
        (a0 - a1).abs() < tol,
        "polygon_area not rotation-invariant: seed={seed} angle={angle} a0={a0} a1={a1}"
    );
}

/// Reversing vertex order flips winding: `polygon_signed_area` must negate
/// exactly, `polygon_area` (its absolute value) must be unchanged, and
/// `polygon_orientation` must flip sign -- three functions checked
/// together against the same reversal, all three of which must move in
/// lockstep for a correct implementation.
///
/// Bug this would catch: a `polygon_orientation` threshold comparison
/// using the wrong operator (e.g. `>=` vs `>` at the epsilon boundary
/// changing which cases are called "degenerate"), or a `polygon_area`
/// that forgets to take the absolute value in some code path.
pub(crate) fn poly_winding_reversal_sign_flip_impl(seed: u64) {
    let (verts, _, _) = gen_convex_polygon(seed);
    let signed0 = polygon_signed_area(&verts);
    let orient0 = polygon_orientation(&verts);

    let mut reversed = verts.clone();
    reversed.reverse();
    let signed1 = polygon_signed_area(&reversed);
    let orient1 = polygon_orientation(&reversed);

    let tol = (signed0.abs() * 1e-9).max(1e-9);
    assert!(
        (signed0 + signed1).abs() < tol,
        "reversing vertex order did not negate the signed area: seed={seed} signed0={signed0} \
         signed1={signed1}"
    );
    assert!(
        (polygon_area(&verts) - polygon_area(&reversed)).abs() < tol,
        "reversing vertex order changed the unsigned area: seed={seed}"
    );
    assert_eq!(
        orient0, -orient1,
        "reversing vertex order did not flip polygon_orientation: seed={seed} orient0={orient0} \
         orient1={orient1}"
    );
}

/// Fan-triangulating a convex polygon from its own vertex 0 -- summing
/// `triangle_area(v0, v_i, v_{i+1})` for every non-adjacent edge -- must
/// equal `polygon_area`. This holds for a convex polygon fanned from one
/// of its own vertices because every fan triangle then shares the whole
/// polygon's winding sign, so `triangle_area`'s absolute value never flips
/// sign relative to its neighbors the way it would for a concave fan
/// origin; the shoelace formula is itself exactly this decomposition, but
/// from the coordinate origin rather than a polygon vertex.
///
/// Bug this would catch: any discrepancy between `polygon_area`'s direct
/// shoelace computation and `triangle_area`'s cross-product formula (e.g.
/// a stray factor-of-2 in one but not the other).
pub(crate) fn poly_fan_triangulation_additivity_impl(seed: u64) {
    let (verts, _, _) = gen_convex_polygon(seed);
    let n = verts.len();
    let mut sum = 0.0;
    for i in 1..n - 1 {
        sum += triangle_area(&verts[0], &verts[i], &verts[i + 1]);
    }
    let total = polygon_area(&verts);
    let tol = (total.abs() * 1e-6).max(1e-6);
    assert!(
        (sum - total).abs() < tol,
        "fan triangulation from vertex 0 did not sum to polygon_area: seed={seed} sum={sum} \
         total={total}"
    );
}

/// The inscribing circle's own center is always strictly inside a convex
/// polygon whose vertices span the full circle (see `gen_convex_polygon`'s
/// doc comment for why); a point 2x-10x the inscribing radius away is
/// always strictly outside, since the polygon is contained in the closed
/// disk of that radius. Checks `point_in_polygon_winding` against both.
///
/// Bug this would catch: a winding-number sign error, or the "point lies
/// exactly on an edge" first-pass short-circuit in
/// `point_in_polygon_winding` misfiring for points nowhere near an edge.
pub(crate) fn poly_center_and_far_point_containment_impl(seed: u64) {
    let (verts, center, r) = gen_convex_polygon(seed);
    assert!(
        point_in_polygon_winding(&center, &verts),
        "the inscribing circle's own center must lie inside its convex polygon: seed={seed}"
    );

    let mut rng = sub_rng(seed, PG_SALT_FAR);
    let theta = rng.range(0.0, std::f64::consts::TAU);
    let k = rng.range(2.0, 10.0);
    let far = Point::new(center.x + r * k * theta.cos(), center.y + r * k * theta.sin());
    assert!(
        !point_in_polygon_winding(&far, &verts),
        "a point 2x-10x the inscribing radius away must lie outside the polygon: seed={seed} \
         k={k}"
    );
}

/// `scale_polygon` scales uniformly (`sx == sy`) about the polygon's own
/// centroid; perimeter is a LINEAR function of a uniform scale factor
/// (unlike `convex_hull.rs`'s hull area, which the first campaign's
/// `ch_scale_quadratic_impl` shows scales quadratically) -- this is a
/// deliberately different exponent from that first-campaign property, on
/// a different function (perimeter, not area) over a different kernel, so
/// it is not a restatement of it.
///
/// Bug this would catch: `scale_polygon` accidentally scaling around the
/// origin instead of the centroid (perimeter is invariant to which center
/// is used, so this alone would not catch that -- but a version that
/// scaled only one axis, or used `sx` where `sy` belongs, would break the
/// exact `k` factor this property checks).
pub(crate) fn poly_perimeter_scale_linear_impl(seed: u64) {
    let verts = pg_gen_arbitrary_polygon(seed);
    let p0 = polygon_perimeter(&verts);
    let mut rng = sub_rng(seed, PG_SALT_SCALE);
    let k = rng.range(0.1, 5.0);
    let scaled = scale_polygon(&verts, k, k);
    let p1 = polygon_perimeter(&scaled);
    let expected = p0 * k;
    let tol = (expected.abs() * 1e-6).max(1e-6);
    assert!(
        (p1 - expected).abs() < tol,
        "polygon_perimeter did not scale linearly under a uniform scale_polygon: seed={seed} \
         k={k} p0={p0} p1={p1} expected={expected}"
    );
}

// ===========================================================================
// Kernel 3: overlap.rs -- AABB/Rect separation distance and overlap amount.
// ===========================================================================

use crate::overlap::{box_box_distance, component_overlap_amount};
use crate::types::{AABB, Rect};

const OV_SALT_B: u64 = 0xAA;
const OV_SALT_TRANSLATE: u64 = 0xAB;
const OV_SALT_OFFSET: u64 = 0xAC;
const OV_SALT_SCALE: u64 = 0xAD;

fn ov_rect_from_rng(rng: &mut SplitMix64) -> Rect {
    Rect::new(
        rng.range(-300.0, 300.0),
        rng.range(-300.0, 300.0),
        rng.range(1.0, 150.0),
        rng.range(1.0, 150.0),
    )
}

fn ov_aabb_from_rng(rng: &mut SplitMix64) -> AABB {
    let x_min = rng.range(-300.0, 300.0);
    let y_min = rng.range(-300.0, 300.0);
    let w = rng.range(1.0, 150.0);
    let h = rng.range(1.0, 150.0);
    AABB::new(x_min, y_min, x_min + w, y_min + h)
}

fn ov_gen_rect_pair(seed: u64) -> (Rect, Rect) {
    let mut rng = SplitMix64::new(seed);
    let a = ov_rect_from_rng(&mut rng);
    let mut b_rng = sub_rng(seed, OV_SALT_B);
    let b = ov_rect_from_rng(&mut b_rng);
    (a, b)
}

fn ov_gen_aabb_pair(seed: u64) -> (AABB, AABB) {
    let mut rng = SplitMix64::new(seed);
    let a = ov_aabb_from_rng(&mut rng);
    let mut b_rng = sub_rng(seed, OV_SALT_B);
    let b = ov_aabb_from_rng(&mut b_rng);
    (a, b)
}

/// `box_box_distance(a, b) == box_box_distance(b, a)`: nothing about
/// separation between two boxes should depend on which is named first.
/// Same relation as `proptest_equivalence.rs`'s `box_box_distance_symmetric`
/// (ported to the wasm harness -- see module doc); `ov_gen_rect_pair`'s
/// independent `sub_rng` stream for `b` decorrelates its parameters from
/// `a`'s the same way the first campaign's kt/ch/cc generators do.
///
/// Bug this would catch: an unabsoluted difference (`ca.x - cb.x` instead
/// of `(ca.x - cb.x).abs()`) that would make the formula sensitive to
/// argument order.
pub(crate) fn ov_box_box_distance_symmetric_impl(seed: u64) {
    let (a, b) = ov_gen_rect_pair(seed);
    let d1 = box_box_distance(&a, &b);
    let d2 = box_box_distance(&b, &a);
    let tol = 1e-9 * (d1.abs() + d2.abs() + 1.0);
    assert!(
        (d1 - d2).abs() < tol,
        "box_box_distance not symmetric: seed={seed} d1={d1} d2={d2}"
    );
}

/// `component_overlap_amount(a, b) == component_overlap_amount(b, a)`: the
/// ratio is `overlap_area / min(area_a, area_b)`, and both the
/// intersection area and the `min` of the two areas are themselves
/// symmetric, so the whole ratio must be too. Different function from the
/// property above (a ratio over AABBs, not a signed distance over Rects).
///
/// Bug this would catch: computing the denominator as `area_a` (the first
/// argument's area) instead of `min(area_a, area_b)`, which would only
/// misbehave -- and only be caught here -- when the two boxes have
/// different areas.
pub(crate) fn ov_component_overlap_symmetric_impl(seed: u64) {
    let (a, b) = ov_gen_aabb_pair(seed);
    let o1 = component_overlap_amount(&a, &b);
    let o2 = component_overlap_amount(&b, &a);
    assert!(
        (o1 - o2).abs() < 1e-9,
        "component_overlap_amount not symmetric: seed={seed} o1={o1} o2={o2}"
    );
}

/// `box_box_distance` depends only on relative position: translating both
/// rectangles by the same vector must not change their separation.
///
/// Bug this would catch: any code path that reads an absolute coordinate
/// instead of the center-to-center difference (a spatial-bucketing
/// shortcut, an absolute-epsilon comparison that only misfires far from
/// the origin) -- the same bug class the first campaign's
/// `ch_translation_invariant_impl` targets for a different kernel
/// (`convex_hull_area`, not `box_box_distance`).
pub(crate) fn ov_translation_invariant_impl(seed: u64) {
    let (a, b) = ov_gen_rect_pair(seed);
    let d0 = box_box_distance(&a, &b);
    let mut t_rng = sub_rng(seed, OV_SALT_TRANSLATE);
    let dx = t_rng.range(-1000.0, 1000.0);
    let dy = t_rng.range(-1000.0, 1000.0);
    let a_t = Rect::new(a.x + dx, a.y + dy, a.w, a.h);
    let b_t = Rect::new(b.x + dx, b.y + dy, b.w, b.h);
    let d1 = box_box_distance(&a_t, &b_t);
    let tol = 1e-7 * (d0.abs() + 1.0);
    assert!(
        (d0 - d1).abs() < tol,
        "box_box_distance not translation-invariant: seed={seed} dx={dx} dy={dy} d0={d0} d1={d1}"
    );
}

/// Self-overlap is total: an AABB overlapping itself covers exactly
/// 100% of its own (and the other's, since they're identical) area, so
/// `component_overlap_amount(a, a)` must be exactly `1.0` -- the "overlap
/// symmetry ... self-overlap is total" property named directly in the
/// task brief for this kernel.
///
/// Bug this would catch: an off-by-epsilon in `AABB::overlap_area`'s
/// `intersects` guard that (for a degenerate zero-width slice of the
/// computation) reports less than full self-overlap.
pub(crate) fn ov_self_overlap_total_impl(seed: u64) {
    let mut rng = SplitMix64::new(seed);
    let a = ov_aabb_from_rng(&mut rng);
    let o = component_overlap_amount(&a, &a);
    assert!(
        (o - 1.0).abs() < 1e-9,
        "component_overlap_amount(a, a) must be exactly 1.0 (total self-overlap): seed={seed} o={o}"
    );
}

/// A box's signed distance to itself has a closed form:
/// `gap_x = gap_y = -w` and `-h` respectively (both negative since `w, h >
/// 0`), so `box_box_distance(a, a) == -max(w, h)` exactly -- a stronger,
/// exact-value check than the merely-negative "self-overlap" property
/// above, over the sibling `Rect`-based function rather than the
/// `AABB`-based one.
///
/// Bug this would catch: the `if gap_x < 0.0 && gap_y < 0.0 { gap_x.min(gap_y)
/// } else { gap_x.max(gap_y) }` branch picking the wrong arm or the wrong
/// reduction (e.g. `.max` instead of `.min` in the overlapping branch),
/// which self-distance -- always in the overlapping branch for any
/// positive-area box -- exercises on every single generated case.
pub(crate) fn ov_self_distance_exact_impl(seed: u64) {
    let mut rng = SplitMix64::new(seed);
    let a = ov_rect_from_rng(&mut rng);
    let d = box_box_distance(&a, &a);
    let expected = -(a.w.max(a.h));
    let tol = 1e-9 * (expected.abs() + 1.0);
    assert!(
        (d - expected).abs() < tol,
        "box_box_distance(a, a) must equal -max(w, h): seed={seed} d={d} expected={expected}"
    );
}

/// Separation is monotonic in translation distance: moving box `b`
/// directly away from box `a` (scaling the center-to-center offset vector
/// by a factor `k >= 1`, i.e. continuing straight along the same ray)
/// never decreases `box_box_distance`. Provable from the formula's own
/// structure: `box_box_distance` reduces to `f(gap_x, gap_y)` where `f` is
/// `min` in the both-overlapping region and `max` otherwise, and both
/// `gap_x` and `gap_y` are non-decreasing as the offset scales by `k >=
/// 1`; `f` is non-decreasing in each argument separately (checked by case
/// analysis on the branch), so it is non-decreasing along any path where
/// both arguments weakly increase.
///
/// Bug this would catch: a clearance/placement optimizer regression class
/// this task's brief names directly ("separation monotonic in translation
/// distance") -- e.g. a refactor that makes the reported distance
/// oscillate or shrink as two components are pushed further apart, which
/// would silently corrupt any gradient-based solver relying on this
/// kernel.
pub(crate) fn ov_separation_monotonic_impl(seed: u64) {
    let mut rng = SplitMix64::new(seed);
    let aw = rng.range(1.0, 150.0);
    let ah = rng.range(1.0, 150.0);
    let acx = rng.range(-300.0, 300.0);
    let acy = rng.range(-300.0, 300.0);
    let a = Rect::from_center(acx, acy, aw * 0.5, ah * 0.5);

    let mut off_rng = sub_rng(seed, OV_SALT_OFFSET);
    let theta = off_rng.range(0.0, std::f64::consts::TAU);
    let dist = off_rng.range(1.0, 500.0);
    let bw = off_rng.range(1.0, 150.0);
    let bh = off_rng.range(1.0, 150.0);
    let b = Rect::from_center(
        acx + dist * theta.cos(),
        acy + dist * theta.sin(),
        bw * 0.5,
        bh * 0.5,
    );
    let d0 = box_box_distance(&a, &b);

    let mut k_rng = sub_rng(seed, OV_SALT_SCALE);
    let k = k_rng.range(1.0, 5.0);
    let b2 = Rect::from_center(
        acx + k * dist * theta.cos(),
        acy + k * dist * theta.sin(),
        bw * 0.5,
        bh * 0.5,
    );
    let d1 = box_box_distance(&a, &b2);

    let tol = 1e-7 * (d0.abs() + d1.abs() + 1.0);
    assert!(
        d1 + tol >= d0,
        "box_box_distance decreased when b moved directly away from a: seed={seed} k={k} \
         d0={d0} d1={d1}"
    );
}

// ===========================================================================
// Kernel 4: projections.rs -- constraint-satisfaction projection operators.
// ===========================================================================

use crate::projections::{
    project_onto_board, project_onto_half_plane, project_onto_zone, project_outside_keepout,
};
use crate::types::Vec2;

/// `project_onto_board` must land inside its own feasible bounds (the
/// "projected point lies on the target" property the task brief names for
/// this class of kernel -- same relation as `proptest_equivalence.rs`'s
/// `project_onto_board_stays_inside`, ported to the wasm harness), and
/// projecting an already-projected point must be a no-op: a metric
/// projection onto a convex set is always idempotent.
///
/// Bug this would catch: swapped `.clamp(margin, board_w - margin)` /
/// `.clamp(margin, board_h - margin)` arguments between the x and y axes,
/// or a clamp that uses `<` where `<=` is required (which would break
/// idempotence at the exact margin boundary).
pub(crate) fn pj_board_idempotent_and_feasible_impl(seed: u64) {
    let mut rng = SplitMix64::new(seed);
    let board_w = rng.range(10.0, 2000.0);
    let board_h = rng.range(10.0, 2000.0);
    let max_margin = (board_w.min(board_h) / 2.0 - 0.01).max(0.0);
    let margin = rng.range(0.0, max_margin);
    let p = Point::new(rng.range(-2000.0, 2000.0), rng.range(-2000.0, 2000.0));

    let p1 = project_onto_board(&p, board_w, board_h, margin);
    assert!(
        p1.x >= margin - 1e-9
            && p1.x <= board_w - margin + 1e-9
            && p1.y >= margin - 1e-9
            && p1.y <= board_h - margin + 1e-9,
        "project_onto_board result outside the feasible bounds: seed={seed} p1=({}, {})",
        p1.x,
        p1.y
    );
    let p2 = project_onto_board(&p1, board_w, board_h, margin);
    assert!(
        (p1.x - p2.x).abs() < 1e-9 && (p1.y - p2.y).abs() < 1e-9,
        "project_onto_board is not idempotent: seed={seed} p1=({}, {}) p2=({}, {})",
        p1.x,
        p1.y,
        p2.x,
        p2.y
    );
}

/// Same two relations (feasibility + idempotence) over `project_onto_zone`
/// instead of `project_onto_board` -- a different function with different
/// branch structure (an early return for the already-inside case, versus
/// `project_onto_board`'s unconditional double clamp). Same relation as
/// `proptest_equivalence.rs`'s `project_onto_zone_containment` for the
/// feasibility half; idempotence is net-new.
///
/// Bug this would catch: the `zone.contains_point(p)` early-return check
/// using open bounds while the clamp below uses closed bounds (or vice
/// versa), which would make a boundary point either re-clamp unnecessarily
/// or fail the strict feasibility check.
pub(crate) fn pj_zone_idempotent_and_feasible_impl(seed: u64) {
    let mut rng = SplitMix64::new(seed);
    let zone = Rect::new(
        rng.range(-500.0, 500.0),
        rng.range(-500.0, 500.0),
        rng.range(1.0, 300.0),
        rng.range(1.0, 300.0),
    );
    let p = Point::new(rng.range(-1000.0, 1000.0), rng.range(-1000.0, 1000.0));

    let p1 = project_onto_zone(&p, &zone);
    assert!(
        zone.contains_point(&p1),
        "project_onto_zone result outside the zone: seed={seed} p1=({}, {})",
        p1.x,
        p1.y
    );
    let p2 = project_onto_zone(&p1, &zone);
    assert!(
        (p1.x - p2.x).abs() < 1e-9 && (p1.y - p2.y).abs() < 1e-9,
        "project_onto_zone is not idempotent: seed={seed}"
    );
}

/// `project_onto_half_plane`'s result must satisfy the half-plane
/// constraint it was projected onto (`(q - origin) . normal >= 0`), and
/// re-projecting it must be a no-op.
///
/// Bug this would catch: the orthogonal-projection formula
/// `p - t * normal` using the wrong sign of `t` (which would push the
/// point further into violation instead of onto the boundary, failing
/// both the feasibility and idempotence checks at once).
pub(crate) fn pj_half_plane_feasible_and_idempotent_impl(seed: u64) {
    let mut rng = SplitMix64::new(seed);
    let origin = Point::new(rng.range(-500.0, 500.0), rng.range(-500.0, 500.0));
    let n_angle = rng.range(0.0, std::f64::consts::TAU);
    let n_len = rng.range(0.1, 50.0);
    let normal = Vec2::new(n_len * n_angle.cos(), n_len * n_angle.sin());
    let p = Point::new(rng.range(-1000.0, 1000.0), rng.range(-1000.0, 1000.0));

    let p1 = project_onto_half_plane(&p, &origin, &normal);
    let to_p1 = Vec2::new(p1.x - origin.x, p1.y - origin.y);
    let dot1 = normal.dot(&to_p1);
    let tol = 1e-6 * (n_len * (p1.x.abs() + p1.y.abs() + 1.0));
    assert!(
        dot1 >= -tol,
        "project_onto_half_plane result violates its own half-plane: seed={seed} dot={dot1}"
    );

    let p2 = project_onto_half_plane(&p1, &origin, &normal);
    assert!(
        (p1.x - p2.x).abs() < 1e-6 && (p1.y - p2.y).abs() < 1e-6,
        "project_onto_half_plane is not idempotent: seed={seed}"
    );
}

/// `project_outside_keepout`'s result must never be strictly inside the
/// half-size-expanded keepout rectangle, and re-projecting it must be a
/// no-op. Feasibility here is checked against the expanded rectangle's own
/// bounds directly (basic interval arithmetic), not by re-deriving the
/// function's internal four-candidate-edge search -- so this does not
/// restate the implementation under test.
///
/// Bug this would catch: an inverted `inside` guard (projecting a point
/// that was already safely outside, or leaving one that was inside
/// untouched), or a candidate-edge distance comparison that picks a
/// non-nearest edge and lands short of the boundary.
pub(crate) fn pj_keepout_feasible_and_idempotent_impl(seed: u64) {
    let mut rng = SplitMix64::new(seed);
    let keepout = Rect::new(
        rng.range(-300.0, 300.0),
        rng.range(-300.0, 300.0),
        rng.range(1.0, 100.0),
        rng.range(1.0, 100.0),
    );
    let half_w = rng.range(0.0, 50.0);
    let half_h = rng.range(0.0, 50.0);
    // `p` is drawn from a window centered on the keepout itself, sized to
    // extend a bit past the half-size-expanded rectangle on every side --
    // NOT an independent full-board range. An independent wide range would
    // put the query point inside the (typically much smaller) expanded
    // keepout only rarely, so almost every generated case would take the
    // early "already outside" return and never exercise the actual
    // candidate-edge projection logic this property exists to check.
    // Centering the window on the keepout instead gives a healthy mix of
    // already-outside, boundary-straddling, and strictly-inside cases.
    let cx = keepout.x + keepout.w * 0.5;
    let cy = keepout.y + keepout.h * 0.5;
    let win_x = keepout.w * 0.5 + half_w + 60.0;
    let win_y = keepout.h * 0.5 + half_h + 60.0;
    let p = Point::new(cx + rng.range(-win_x, win_x), cy + rng.range(-win_y, win_y));

    let p1 = project_outside_keepout(&p, &keepout, half_w, half_h);

    let ex_min = keepout.x - half_w;
    let ex_max = keepout.x + keepout.w + half_w;
    let ey_min = keepout.y - half_h;
    let ey_max = keepout.y + keepout.h + half_h;
    let tol = 1e-7;
    let strictly_inside =
        p1.x > ex_min + tol && p1.x < ex_max - tol && p1.y > ey_min + tol && p1.y < ey_max - tol;
    assert!(
        !strictly_inside,
        "project_outside_keepout left the result strictly inside the expanded keepout: \
         seed={seed} p1=({}, {})",
        p1.x, p1.y
    );

    let p2 = project_outside_keepout(&p1, &keepout, half_w, half_h);
    assert!(
        (p1.x - p2.x).abs() < 1e-6 && (p1.y - p2.y).abs() < 1e-6,
        "project_outside_keepout is not idempotent: seed={seed}"
    );
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    // -----------------------------------------------------------------
    // Hand-written sanity tests for the generators and helpers above.
    // -----------------------------------------------------------------

    #[cfg_attr(test, test)]
    fn splitmix64_is_deterministic_in_seed() {
        let mut a = SplitMix64::new(2024);
        let mut b = SplitMix64::new(2024);
        for _ in 0..10 {
            assert_eq!(a.next_u64(), b.next_u64());
        }
    }

    #[cfg_attr(test, test)]
    fn splitmix64_varies_with_seed() {
        let mut a = SplitMix64::new(1);
        let mut b = SplitMix64::new(2);
        assert_ne!(a.next_u64(), b.next_u64());
    }

    #[cfg_attr(test, test)]
    fn gen_convex_polygon_vertex_count_in_range() {
        for seed in [0u64, 1, 500, 999_999] {
            let (verts, _, _) = gen_convex_polygon(seed);
            assert!(verts.len() >= 3 && verts.len() <= 12, "seed={seed} n={}", verts.len());
        }
    }

    #[cfg_attr(test, test)]
    fn gen_convex_polygon_is_actually_convex_and_encloses_its_center() {
        // Independent, non-generated cross-check of the geometric claim
        // `gen_convex_polygon`'s doc comment makes: for a range of seeds,
        // the orientation is non-degenerate (a genuine simple polygon, not
        // collinear points) and the center point tests as inside via
        // `point_in_polygon_winding`.
        for seed in [3u64, 42, 7777, 123_456] {
            let (verts, center, _) = gen_convex_polygon(seed);
            assert_ne!(polygon_orientation(&verts), 0, "seed={seed} degenerate polygon");
            assert!(
                point_in_polygon_winding(&center, &verts),
                "seed={seed} center not contained"
            );
        }
    }

    #[cfg_attr(test, test)]
    fn ov_generators_produce_positive_area_shapes() {
        for seed in [0u64, 11, 2222] {
            let mut rng = SplitMix64::new(seed);
            let r = ov_rect_from_rng(&mut rng);
            assert!(r.w > 0.0 && r.h > 0.0, "seed={seed} rect w={} h={}", r.w, r.h);
            let mut rng2 = SplitMix64::new(seed);
            let a = ov_aabb_from_rng(&mut rng2);
            assert!(a.area() > 0.0, "seed={seed} aabb area={}", a.area());
        }
    }

    #[cfg_attr(test, test)]
    fn pg_arbitrary_polygon_vertex_count_in_range() {
        for seed in [0u64, 8, 4321] {
            let verts = pg_gen_arbitrary_polygon(seed);
            assert!(verts.len() >= 3 && verts.len() <= 12, "seed={seed} n={}", verts.len());
        }
    }

    #[cfg_attr(test, test)]
    fn sdf_gen_circle_radius_is_positive() {
        for seed in [0u64, 9, 6543] {
            let (_, _, r) = sdf_gen_circle(seed);
            assert!(r > 0.0, "seed={seed} r={r}");
        }
    }

    // --- BEGIN generated seeded property wrappers (packaged separately below) ---
    // 23 properties x 90 seeds = 2070 distinct-input wasm tests.
    // --- sdf_circle_sign_and_boundary: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000000() { sdf_circle_sign_and_boundary_impl(0); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000001() { sdf_circle_sign_and_boundary_impl(1); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000002() { sdf_circle_sign_and_boundary_impl(2); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000003() { sdf_circle_sign_and_boundary_impl(3); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000004() { sdf_circle_sign_and_boundary_impl(4); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000005() { sdf_circle_sign_and_boundary_impl(5); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000006() { sdf_circle_sign_and_boundary_impl(6); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000007() { sdf_circle_sign_and_boundary_impl(7); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000008() { sdf_circle_sign_and_boundary_impl(8); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000009() { sdf_circle_sign_and_boundary_impl(9); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000010() { sdf_circle_sign_and_boundary_impl(10); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000011() { sdf_circle_sign_and_boundary_impl(11); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000012() { sdf_circle_sign_and_boundary_impl(12); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000013() { sdf_circle_sign_and_boundary_impl(13); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000014() { sdf_circle_sign_and_boundary_impl(14); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000015() { sdf_circle_sign_and_boundary_impl(15); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000016() { sdf_circle_sign_and_boundary_impl(16); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000017() { sdf_circle_sign_and_boundary_impl(17); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000018() { sdf_circle_sign_and_boundary_impl(18); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000019() { sdf_circle_sign_and_boundary_impl(19); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000020() { sdf_circle_sign_and_boundary_impl(20); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000021() { sdf_circle_sign_and_boundary_impl(21); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000022() { sdf_circle_sign_and_boundary_impl(22); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000023() { sdf_circle_sign_and_boundary_impl(23); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000024() { sdf_circle_sign_and_boundary_impl(24); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000025() { sdf_circle_sign_and_boundary_impl(25); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000026() { sdf_circle_sign_and_boundary_impl(26); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000027() { sdf_circle_sign_and_boundary_impl(27); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000028() { sdf_circle_sign_and_boundary_impl(28); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000029() { sdf_circle_sign_and_boundary_impl(29); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000030() { sdf_circle_sign_and_boundary_impl(30); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000031() { sdf_circle_sign_and_boundary_impl(31); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000032() { sdf_circle_sign_and_boundary_impl(32); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000033() { sdf_circle_sign_and_boundary_impl(33); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000034() { sdf_circle_sign_and_boundary_impl(34); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000035() { sdf_circle_sign_and_boundary_impl(35); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000036() { sdf_circle_sign_and_boundary_impl(36); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000037() { sdf_circle_sign_and_boundary_impl(37); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000038() { sdf_circle_sign_and_boundary_impl(38); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000039() { sdf_circle_sign_and_boundary_impl(39); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000040() { sdf_circle_sign_and_boundary_impl(40); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000041() { sdf_circle_sign_and_boundary_impl(41); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000042() { sdf_circle_sign_and_boundary_impl(42); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000043() { sdf_circle_sign_and_boundary_impl(43); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000044() { sdf_circle_sign_and_boundary_impl(44); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000045() { sdf_circle_sign_and_boundary_impl(45); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000046() { sdf_circle_sign_and_boundary_impl(46); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000047() { sdf_circle_sign_and_boundary_impl(47); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000048() { sdf_circle_sign_and_boundary_impl(48); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000049() { sdf_circle_sign_and_boundary_impl(49); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000050() { sdf_circle_sign_and_boundary_impl(50); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000051() { sdf_circle_sign_and_boundary_impl(51); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000052() { sdf_circle_sign_and_boundary_impl(52); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000053() { sdf_circle_sign_and_boundary_impl(53); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000054() { sdf_circle_sign_and_boundary_impl(54); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000055() { sdf_circle_sign_and_boundary_impl(55); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000056() { sdf_circle_sign_and_boundary_impl(56); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000057() { sdf_circle_sign_and_boundary_impl(57); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000058() { sdf_circle_sign_and_boundary_impl(58); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000059() { sdf_circle_sign_and_boundary_impl(59); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000060() { sdf_circle_sign_and_boundary_impl(60); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000061() { sdf_circle_sign_and_boundary_impl(61); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000062() { sdf_circle_sign_and_boundary_impl(62); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000063() { sdf_circle_sign_and_boundary_impl(63); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000064() { sdf_circle_sign_and_boundary_impl(64); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000065() { sdf_circle_sign_and_boundary_impl(65); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000066() { sdf_circle_sign_and_boundary_impl(66); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000067() { sdf_circle_sign_and_boundary_impl(67); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000068() { sdf_circle_sign_and_boundary_impl(68); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000069() { sdf_circle_sign_and_boundary_impl(69); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000070() { sdf_circle_sign_and_boundary_impl(70); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000071() { sdf_circle_sign_and_boundary_impl(71); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000072() { sdf_circle_sign_and_boundary_impl(72); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000073() { sdf_circle_sign_and_boundary_impl(73); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000074() { sdf_circle_sign_and_boundary_impl(74); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000075() { sdf_circle_sign_and_boundary_impl(75); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000076() { sdf_circle_sign_and_boundary_impl(76); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000077() { sdf_circle_sign_and_boundary_impl(77); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000078() { sdf_circle_sign_and_boundary_impl(78); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000079() { sdf_circle_sign_and_boundary_impl(79); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000080() { sdf_circle_sign_and_boundary_impl(80); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000081() { sdf_circle_sign_and_boundary_impl(81); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000082() { sdf_circle_sign_and_boundary_impl(82); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000083() { sdf_circle_sign_and_boundary_impl(83); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000084() { sdf_circle_sign_and_boundary_impl(84); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000085() { sdf_circle_sign_and_boundary_impl(85); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000086() { sdf_circle_sign_and_boundary_impl(86); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000087() { sdf_circle_sign_and_boundary_impl(87); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000088() { sdf_circle_sign_and_boundary_impl(88); }
    #[cfg_attr(test, test)]
    fn sdf_circle_sign_and_boundary_seed_000089() { sdf_circle_sign_and_boundary_impl(89); }
    // --- sdf_circle_translation_equivariant: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000000() { sdf_circle_translation_equivariant_impl(0); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000001() { sdf_circle_translation_equivariant_impl(1); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000002() { sdf_circle_translation_equivariant_impl(2); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000003() { sdf_circle_translation_equivariant_impl(3); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000004() { sdf_circle_translation_equivariant_impl(4); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000005() { sdf_circle_translation_equivariant_impl(5); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000006() { sdf_circle_translation_equivariant_impl(6); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000007() { sdf_circle_translation_equivariant_impl(7); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000008() { sdf_circle_translation_equivariant_impl(8); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000009() { sdf_circle_translation_equivariant_impl(9); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000010() { sdf_circle_translation_equivariant_impl(10); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000011() { sdf_circle_translation_equivariant_impl(11); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000012() { sdf_circle_translation_equivariant_impl(12); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000013() { sdf_circle_translation_equivariant_impl(13); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000014() { sdf_circle_translation_equivariant_impl(14); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000015() { sdf_circle_translation_equivariant_impl(15); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000016() { sdf_circle_translation_equivariant_impl(16); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000017() { sdf_circle_translation_equivariant_impl(17); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000018() { sdf_circle_translation_equivariant_impl(18); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000019() { sdf_circle_translation_equivariant_impl(19); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000020() { sdf_circle_translation_equivariant_impl(20); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000021() { sdf_circle_translation_equivariant_impl(21); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000022() { sdf_circle_translation_equivariant_impl(22); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000023() { sdf_circle_translation_equivariant_impl(23); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000024() { sdf_circle_translation_equivariant_impl(24); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000025() { sdf_circle_translation_equivariant_impl(25); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000026() { sdf_circle_translation_equivariant_impl(26); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000027() { sdf_circle_translation_equivariant_impl(27); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000028() { sdf_circle_translation_equivariant_impl(28); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000029() { sdf_circle_translation_equivariant_impl(29); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000030() { sdf_circle_translation_equivariant_impl(30); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000031() { sdf_circle_translation_equivariant_impl(31); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000032() { sdf_circle_translation_equivariant_impl(32); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000033() { sdf_circle_translation_equivariant_impl(33); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000034() { sdf_circle_translation_equivariant_impl(34); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000035() { sdf_circle_translation_equivariant_impl(35); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000036() { sdf_circle_translation_equivariant_impl(36); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000037() { sdf_circle_translation_equivariant_impl(37); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000038() { sdf_circle_translation_equivariant_impl(38); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000039() { sdf_circle_translation_equivariant_impl(39); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000040() { sdf_circle_translation_equivariant_impl(40); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000041() { sdf_circle_translation_equivariant_impl(41); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000042() { sdf_circle_translation_equivariant_impl(42); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000043() { sdf_circle_translation_equivariant_impl(43); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000044() { sdf_circle_translation_equivariant_impl(44); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000045() { sdf_circle_translation_equivariant_impl(45); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000046() { sdf_circle_translation_equivariant_impl(46); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000047() { sdf_circle_translation_equivariant_impl(47); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000048() { sdf_circle_translation_equivariant_impl(48); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000049() { sdf_circle_translation_equivariant_impl(49); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000050() { sdf_circle_translation_equivariant_impl(50); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000051() { sdf_circle_translation_equivariant_impl(51); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000052() { sdf_circle_translation_equivariant_impl(52); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000053() { sdf_circle_translation_equivariant_impl(53); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000054() { sdf_circle_translation_equivariant_impl(54); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000055() { sdf_circle_translation_equivariant_impl(55); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000056() { sdf_circle_translation_equivariant_impl(56); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000057() { sdf_circle_translation_equivariant_impl(57); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000058() { sdf_circle_translation_equivariant_impl(58); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000059() { sdf_circle_translation_equivariant_impl(59); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000060() { sdf_circle_translation_equivariant_impl(60); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000061() { sdf_circle_translation_equivariant_impl(61); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000062() { sdf_circle_translation_equivariant_impl(62); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000063() { sdf_circle_translation_equivariant_impl(63); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000064() { sdf_circle_translation_equivariant_impl(64); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000065() { sdf_circle_translation_equivariant_impl(65); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000066() { sdf_circle_translation_equivariant_impl(66); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000067() { sdf_circle_translation_equivariant_impl(67); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000068() { sdf_circle_translation_equivariant_impl(68); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000069() { sdf_circle_translation_equivariant_impl(69); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000070() { sdf_circle_translation_equivariant_impl(70); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000071() { sdf_circle_translation_equivariant_impl(71); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000072() { sdf_circle_translation_equivariant_impl(72); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000073() { sdf_circle_translation_equivariant_impl(73); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000074() { sdf_circle_translation_equivariant_impl(74); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000075() { sdf_circle_translation_equivariant_impl(75); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000076() { sdf_circle_translation_equivariant_impl(76); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000077() { sdf_circle_translation_equivariant_impl(77); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000078() { sdf_circle_translation_equivariant_impl(78); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000079() { sdf_circle_translation_equivariant_impl(79); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000080() { sdf_circle_translation_equivariant_impl(80); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000081() { sdf_circle_translation_equivariant_impl(81); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000082() { sdf_circle_translation_equivariant_impl(82); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000083() { sdf_circle_translation_equivariant_impl(83); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000084() { sdf_circle_translation_equivariant_impl(84); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000085() { sdf_circle_translation_equivariant_impl(85); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000086() { sdf_circle_translation_equivariant_impl(86); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000087() { sdf_circle_translation_equivariant_impl(87); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000088() { sdf_circle_translation_equivariant_impl(88); }
    #[cfg_attr(test, test)]
    fn sdf_circle_translation_equivariant_seed_000089() { sdf_circle_translation_equivariant_impl(89); }
    // --- sdf_polygon_translation_equivariant: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000000() { sdf_polygon_translation_equivariant_impl(0); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000001() { sdf_polygon_translation_equivariant_impl(1); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000002() { sdf_polygon_translation_equivariant_impl(2); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000003() { sdf_polygon_translation_equivariant_impl(3); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000004() { sdf_polygon_translation_equivariant_impl(4); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000005() { sdf_polygon_translation_equivariant_impl(5); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000006() { sdf_polygon_translation_equivariant_impl(6); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000007() { sdf_polygon_translation_equivariant_impl(7); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000008() { sdf_polygon_translation_equivariant_impl(8); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000009() { sdf_polygon_translation_equivariant_impl(9); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000010() { sdf_polygon_translation_equivariant_impl(10); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000011() { sdf_polygon_translation_equivariant_impl(11); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000012() { sdf_polygon_translation_equivariant_impl(12); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000013() { sdf_polygon_translation_equivariant_impl(13); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000014() { sdf_polygon_translation_equivariant_impl(14); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000015() { sdf_polygon_translation_equivariant_impl(15); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000016() { sdf_polygon_translation_equivariant_impl(16); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000017() { sdf_polygon_translation_equivariant_impl(17); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000018() { sdf_polygon_translation_equivariant_impl(18); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000019() { sdf_polygon_translation_equivariant_impl(19); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000020() { sdf_polygon_translation_equivariant_impl(20); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000021() { sdf_polygon_translation_equivariant_impl(21); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000022() { sdf_polygon_translation_equivariant_impl(22); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000023() { sdf_polygon_translation_equivariant_impl(23); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000024() { sdf_polygon_translation_equivariant_impl(24); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000025() { sdf_polygon_translation_equivariant_impl(25); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000026() { sdf_polygon_translation_equivariant_impl(26); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000027() { sdf_polygon_translation_equivariant_impl(27); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000028() { sdf_polygon_translation_equivariant_impl(28); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000029() { sdf_polygon_translation_equivariant_impl(29); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000030() { sdf_polygon_translation_equivariant_impl(30); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000031() { sdf_polygon_translation_equivariant_impl(31); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000032() { sdf_polygon_translation_equivariant_impl(32); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000033() { sdf_polygon_translation_equivariant_impl(33); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000034() { sdf_polygon_translation_equivariant_impl(34); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000035() { sdf_polygon_translation_equivariant_impl(35); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000036() { sdf_polygon_translation_equivariant_impl(36); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000037() { sdf_polygon_translation_equivariant_impl(37); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000038() { sdf_polygon_translation_equivariant_impl(38); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000039() { sdf_polygon_translation_equivariant_impl(39); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000040() { sdf_polygon_translation_equivariant_impl(40); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000041() { sdf_polygon_translation_equivariant_impl(41); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000042() { sdf_polygon_translation_equivariant_impl(42); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000043() { sdf_polygon_translation_equivariant_impl(43); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000044() { sdf_polygon_translation_equivariant_impl(44); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000045() { sdf_polygon_translation_equivariant_impl(45); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000046() { sdf_polygon_translation_equivariant_impl(46); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000047() { sdf_polygon_translation_equivariant_impl(47); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000048() { sdf_polygon_translation_equivariant_impl(48); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000049() { sdf_polygon_translation_equivariant_impl(49); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000050() { sdf_polygon_translation_equivariant_impl(50); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000051() { sdf_polygon_translation_equivariant_impl(51); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000052() { sdf_polygon_translation_equivariant_impl(52); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000053() { sdf_polygon_translation_equivariant_impl(53); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000054() { sdf_polygon_translation_equivariant_impl(54); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000055() { sdf_polygon_translation_equivariant_impl(55); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000056() { sdf_polygon_translation_equivariant_impl(56); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000057() { sdf_polygon_translation_equivariant_impl(57); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000058() { sdf_polygon_translation_equivariant_impl(58); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000059() { sdf_polygon_translation_equivariant_impl(59); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000060() { sdf_polygon_translation_equivariant_impl(60); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000061() { sdf_polygon_translation_equivariant_impl(61); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000062() { sdf_polygon_translation_equivariant_impl(62); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000063() { sdf_polygon_translation_equivariant_impl(63); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000064() { sdf_polygon_translation_equivariant_impl(64); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000065() { sdf_polygon_translation_equivariant_impl(65); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000066() { sdf_polygon_translation_equivariant_impl(66); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000067() { sdf_polygon_translation_equivariant_impl(67); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000068() { sdf_polygon_translation_equivariant_impl(68); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000069() { sdf_polygon_translation_equivariant_impl(69); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000070() { sdf_polygon_translation_equivariant_impl(70); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000071() { sdf_polygon_translation_equivariant_impl(71); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000072() { sdf_polygon_translation_equivariant_impl(72); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000073() { sdf_polygon_translation_equivariant_impl(73); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000074() { sdf_polygon_translation_equivariant_impl(74); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000075() { sdf_polygon_translation_equivariant_impl(75); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000076() { sdf_polygon_translation_equivariant_impl(76); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000077() { sdf_polygon_translation_equivariant_impl(77); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000078() { sdf_polygon_translation_equivariant_impl(78); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000079() { sdf_polygon_translation_equivariant_impl(79); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000080() { sdf_polygon_translation_equivariant_impl(80); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000081() { sdf_polygon_translation_equivariant_impl(81); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000082() { sdf_polygon_translation_equivariant_impl(82); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000083() { sdf_polygon_translation_equivariant_impl(83); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000084() { sdf_polygon_translation_equivariant_impl(84); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000085() { sdf_polygon_translation_equivariant_impl(85); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000086() { sdf_polygon_translation_equivariant_impl(86); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000087() { sdf_polygon_translation_equivariant_impl(87); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000088() { sdf_polygon_translation_equivariant_impl(88); }
    #[cfg_attr(test, test)]
    fn sdf_polygon_translation_equivariant_seed_000089() { sdf_polygon_translation_equivariant_impl(89); }
    // --- sdf_convex_vs_polygon_sign_agreement: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000000() { sdf_convex_vs_polygon_sign_agreement_impl(0); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000001() { sdf_convex_vs_polygon_sign_agreement_impl(1); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000002() { sdf_convex_vs_polygon_sign_agreement_impl(2); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000003() { sdf_convex_vs_polygon_sign_agreement_impl(3); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000004() { sdf_convex_vs_polygon_sign_agreement_impl(4); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000005() { sdf_convex_vs_polygon_sign_agreement_impl(5); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000006() { sdf_convex_vs_polygon_sign_agreement_impl(6); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000007() { sdf_convex_vs_polygon_sign_agreement_impl(7); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000008() { sdf_convex_vs_polygon_sign_agreement_impl(8); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000009() { sdf_convex_vs_polygon_sign_agreement_impl(9); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000010() { sdf_convex_vs_polygon_sign_agreement_impl(10); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000011() { sdf_convex_vs_polygon_sign_agreement_impl(11); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000012() { sdf_convex_vs_polygon_sign_agreement_impl(12); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000013() { sdf_convex_vs_polygon_sign_agreement_impl(13); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000014() { sdf_convex_vs_polygon_sign_agreement_impl(14); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000015() { sdf_convex_vs_polygon_sign_agreement_impl(15); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000016() { sdf_convex_vs_polygon_sign_agreement_impl(16); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000017() { sdf_convex_vs_polygon_sign_agreement_impl(17); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000018() { sdf_convex_vs_polygon_sign_agreement_impl(18); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000019() { sdf_convex_vs_polygon_sign_agreement_impl(19); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000020() { sdf_convex_vs_polygon_sign_agreement_impl(20); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000021() { sdf_convex_vs_polygon_sign_agreement_impl(21); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000022() { sdf_convex_vs_polygon_sign_agreement_impl(22); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000023() { sdf_convex_vs_polygon_sign_agreement_impl(23); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000024() { sdf_convex_vs_polygon_sign_agreement_impl(24); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000025() { sdf_convex_vs_polygon_sign_agreement_impl(25); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000026() { sdf_convex_vs_polygon_sign_agreement_impl(26); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000027() { sdf_convex_vs_polygon_sign_agreement_impl(27); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000028() { sdf_convex_vs_polygon_sign_agreement_impl(28); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000029() { sdf_convex_vs_polygon_sign_agreement_impl(29); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000030() { sdf_convex_vs_polygon_sign_agreement_impl(30); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000031() { sdf_convex_vs_polygon_sign_agreement_impl(31); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000032() { sdf_convex_vs_polygon_sign_agreement_impl(32); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000033() { sdf_convex_vs_polygon_sign_agreement_impl(33); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000034() { sdf_convex_vs_polygon_sign_agreement_impl(34); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000035() { sdf_convex_vs_polygon_sign_agreement_impl(35); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000036() { sdf_convex_vs_polygon_sign_agreement_impl(36); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000037() { sdf_convex_vs_polygon_sign_agreement_impl(37); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000038() { sdf_convex_vs_polygon_sign_agreement_impl(38); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000039() { sdf_convex_vs_polygon_sign_agreement_impl(39); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000040() { sdf_convex_vs_polygon_sign_agreement_impl(40); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000041() { sdf_convex_vs_polygon_sign_agreement_impl(41); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000042() { sdf_convex_vs_polygon_sign_agreement_impl(42); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000043() { sdf_convex_vs_polygon_sign_agreement_impl(43); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000044() { sdf_convex_vs_polygon_sign_agreement_impl(44); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000045() { sdf_convex_vs_polygon_sign_agreement_impl(45); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000046() { sdf_convex_vs_polygon_sign_agreement_impl(46); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000047() { sdf_convex_vs_polygon_sign_agreement_impl(47); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000048() { sdf_convex_vs_polygon_sign_agreement_impl(48); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000049() { sdf_convex_vs_polygon_sign_agreement_impl(49); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000050() { sdf_convex_vs_polygon_sign_agreement_impl(50); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000051() { sdf_convex_vs_polygon_sign_agreement_impl(51); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000052() { sdf_convex_vs_polygon_sign_agreement_impl(52); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000053() { sdf_convex_vs_polygon_sign_agreement_impl(53); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000054() { sdf_convex_vs_polygon_sign_agreement_impl(54); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000055() { sdf_convex_vs_polygon_sign_agreement_impl(55); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000056() { sdf_convex_vs_polygon_sign_agreement_impl(56); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000057() { sdf_convex_vs_polygon_sign_agreement_impl(57); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000058() { sdf_convex_vs_polygon_sign_agreement_impl(58); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000059() { sdf_convex_vs_polygon_sign_agreement_impl(59); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000060() { sdf_convex_vs_polygon_sign_agreement_impl(60); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000061() { sdf_convex_vs_polygon_sign_agreement_impl(61); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000062() { sdf_convex_vs_polygon_sign_agreement_impl(62); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000063() { sdf_convex_vs_polygon_sign_agreement_impl(63); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000064() { sdf_convex_vs_polygon_sign_agreement_impl(64); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000065() { sdf_convex_vs_polygon_sign_agreement_impl(65); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000066() { sdf_convex_vs_polygon_sign_agreement_impl(66); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000067() { sdf_convex_vs_polygon_sign_agreement_impl(67); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000068() { sdf_convex_vs_polygon_sign_agreement_impl(68); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000069() { sdf_convex_vs_polygon_sign_agreement_impl(69); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000070() { sdf_convex_vs_polygon_sign_agreement_impl(70); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000071() { sdf_convex_vs_polygon_sign_agreement_impl(71); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000072() { sdf_convex_vs_polygon_sign_agreement_impl(72); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000073() { sdf_convex_vs_polygon_sign_agreement_impl(73); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000074() { sdf_convex_vs_polygon_sign_agreement_impl(74); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000075() { sdf_convex_vs_polygon_sign_agreement_impl(75); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000076() { sdf_convex_vs_polygon_sign_agreement_impl(76); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000077() { sdf_convex_vs_polygon_sign_agreement_impl(77); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000078() { sdf_convex_vs_polygon_sign_agreement_impl(78); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000079() { sdf_convex_vs_polygon_sign_agreement_impl(79); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000080() { sdf_convex_vs_polygon_sign_agreement_impl(80); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000081() { sdf_convex_vs_polygon_sign_agreement_impl(81); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000082() { sdf_convex_vs_polygon_sign_agreement_impl(82); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000083() { sdf_convex_vs_polygon_sign_agreement_impl(83); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000084() { sdf_convex_vs_polygon_sign_agreement_impl(84); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000085() { sdf_convex_vs_polygon_sign_agreement_impl(85); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000086() { sdf_convex_vs_polygon_sign_agreement_impl(86); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000087() { sdf_convex_vs_polygon_sign_agreement_impl(87); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000088() { sdf_convex_vs_polygon_sign_agreement_impl(88); }
    #[cfg_attr(test, test)]
    fn sdf_convex_vs_polygon_sign_agreement_seed_000089() { sdf_convex_vs_polygon_sign_agreement_impl(89); }
    // --- sdf_capsule_degenerate_matches_circle: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000000() { sdf_capsule_degenerate_matches_circle_impl(0); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000001() { sdf_capsule_degenerate_matches_circle_impl(1); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000002() { sdf_capsule_degenerate_matches_circle_impl(2); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000003() { sdf_capsule_degenerate_matches_circle_impl(3); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000004() { sdf_capsule_degenerate_matches_circle_impl(4); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000005() { sdf_capsule_degenerate_matches_circle_impl(5); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000006() { sdf_capsule_degenerate_matches_circle_impl(6); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000007() { sdf_capsule_degenerate_matches_circle_impl(7); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000008() { sdf_capsule_degenerate_matches_circle_impl(8); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000009() { sdf_capsule_degenerate_matches_circle_impl(9); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000010() { sdf_capsule_degenerate_matches_circle_impl(10); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000011() { sdf_capsule_degenerate_matches_circle_impl(11); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000012() { sdf_capsule_degenerate_matches_circle_impl(12); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000013() { sdf_capsule_degenerate_matches_circle_impl(13); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000014() { sdf_capsule_degenerate_matches_circle_impl(14); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000015() { sdf_capsule_degenerate_matches_circle_impl(15); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000016() { sdf_capsule_degenerate_matches_circle_impl(16); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000017() { sdf_capsule_degenerate_matches_circle_impl(17); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000018() { sdf_capsule_degenerate_matches_circle_impl(18); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000019() { sdf_capsule_degenerate_matches_circle_impl(19); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000020() { sdf_capsule_degenerate_matches_circle_impl(20); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000021() { sdf_capsule_degenerate_matches_circle_impl(21); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000022() { sdf_capsule_degenerate_matches_circle_impl(22); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000023() { sdf_capsule_degenerate_matches_circle_impl(23); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000024() { sdf_capsule_degenerate_matches_circle_impl(24); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000025() { sdf_capsule_degenerate_matches_circle_impl(25); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000026() { sdf_capsule_degenerate_matches_circle_impl(26); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000027() { sdf_capsule_degenerate_matches_circle_impl(27); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000028() { sdf_capsule_degenerate_matches_circle_impl(28); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000029() { sdf_capsule_degenerate_matches_circle_impl(29); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000030() { sdf_capsule_degenerate_matches_circle_impl(30); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000031() { sdf_capsule_degenerate_matches_circle_impl(31); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000032() { sdf_capsule_degenerate_matches_circle_impl(32); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000033() { sdf_capsule_degenerate_matches_circle_impl(33); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000034() { sdf_capsule_degenerate_matches_circle_impl(34); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000035() { sdf_capsule_degenerate_matches_circle_impl(35); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000036() { sdf_capsule_degenerate_matches_circle_impl(36); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000037() { sdf_capsule_degenerate_matches_circle_impl(37); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000038() { sdf_capsule_degenerate_matches_circle_impl(38); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000039() { sdf_capsule_degenerate_matches_circle_impl(39); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000040() { sdf_capsule_degenerate_matches_circle_impl(40); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000041() { sdf_capsule_degenerate_matches_circle_impl(41); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000042() { sdf_capsule_degenerate_matches_circle_impl(42); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000043() { sdf_capsule_degenerate_matches_circle_impl(43); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000044() { sdf_capsule_degenerate_matches_circle_impl(44); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000045() { sdf_capsule_degenerate_matches_circle_impl(45); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000046() { sdf_capsule_degenerate_matches_circle_impl(46); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000047() { sdf_capsule_degenerate_matches_circle_impl(47); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000048() { sdf_capsule_degenerate_matches_circle_impl(48); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000049() { sdf_capsule_degenerate_matches_circle_impl(49); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000050() { sdf_capsule_degenerate_matches_circle_impl(50); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000051() { sdf_capsule_degenerate_matches_circle_impl(51); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000052() { sdf_capsule_degenerate_matches_circle_impl(52); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000053() { sdf_capsule_degenerate_matches_circle_impl(53); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000054() { sdf_capsule_degenerate_matches_circle_impl(54); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000055() { sdf_capsule_degenerate_matches_circle_impl(55); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000056() { sdf_capsule_degenerate_matches_circle_impl(56); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000057() { sdf_capsule_degenerate_matches_circle_impl(57); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000058() { sdf_capsule_degenerate_matches_circle_impl(58); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000059() { sdf_capsule_degenerate_matches_circle_impl(59); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000060() { sdf_capsule_degenerate_matches_circle_impl(60); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000061() { sdf_capsule_degenerate_matches_circle_impl(61); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000062() { sdf_capsule_degenerate_matches_circle_impl(62); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000063() { sdf_capsule_degenerate_matches_circle_impl(63); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000064() { sdf_capsule_degenerate_matches_circle_impl(64); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000065() { sdf_capsule_degenerate_matches_circle_impl(65); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000066() { sdf_capsule_degenerate_matches_circle_impl(66); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000067() { sdf_capsule_degenerate_matches_circle_impl(67); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000068() { sdf_capsule_degenerate_matches_circle_impl(68); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000069() { sdf_capsule_degenerate_matches_circle_impl(69); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000070() { sdf_capsule_degenerate_matches_circle_impl(70); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000071() { sdf_capsule_degenerate_matches_circle_impl(71); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000072() { sdf_capsule_degenerate_matches_circle_impl(72); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000073() { sdf_capsule_degenerate_matches_circle_impl(73); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000074() { sdf_capsule_degenerate_matches_circle_impl(74); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000075() { sdf_capsule_degenerate_matches_circle_impl(75); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000076() { sdf_capsule_degenerate_matches_circle_impl(76); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000077() { sdf_capsule_degenerate_matches_circle_impl(77); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000078() { sdf_capsule_degenerate_matches_circle_impl(78); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000079() { sdf_capsule_degenerate_matches_circle_impl(79); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000080() { sdf_capsule_degenerate_matches_circle_impl(80); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000081() { sdf_capsule_degenerate_matches_circle_impl(81); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000082() { sdf_capsule_degenerate_matches_circle_impl(82); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000083() { sdf_capsule_degenerate_matches_circle_impl(83); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000084() { sdf_capsule_degenerate_matches_circle_impl(84); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000085() { sdf_capsule_degenerate_matches_circle_impl(85); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000086() { sdf_capsule_degenerate_matches_circle_impl(86); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000087() { sdf_capsule_degenerate_matches_circle_impl(87); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000088() { sdf_capsule_degenerate_matches_circle_impl(88); }
    #[cfg_attr(test, test)]
    fn sdf_capsule_degenerate_matches_circle_seed_000089() { sdf_capsule_degenerate_matches_circle_impl(89); }
    // --- sdf_smooth_union_lower_bound: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000000() { sdf_smooth_union_lower_bound_impl(0); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000001() { sdf_smooth_union_lower_bound_impl(1); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000002() { sdf_smooth_union_lower_bound_impl(2); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000003() { sdf_smooth_union_lower_bound_impl(3); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000004() { sdf_smooth_union_lower_bound_impl(4); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000005() { sdf_smooth_union_lower_bound_impl(5); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000006() { sdf_smooth_union_lower_bound_impl(6); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000007() { sdf_smooth_union_lower_bound_impl(7); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000008() { sdf_smooth_union_lower_bound_impl(8); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000009() { sdf_smooth_union_lower_bound_impl(9); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000010() { sdf_smooth_union_lower_bound_impl(10); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000011() { sdf_smooth_union_lower_bound_impl(11); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000012() { sdf_smooth_union_lower_bound_impl(12); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000013() { sdf_smooth_union_lower_bound_impl(13); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000014() { sdf_smooth_union_lower_bound_impl(14); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000015() { sdf_smooth_union_lower_bound_impl(15); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000016() { sdf_smooth_union_lower_bound_impl(16); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000017() { sdf_smooth_union_lower_bound_impl(17); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000018() { sdf_smooth_union_lower_bound_impl(18); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000019() { sdf_smooth_union_lower_bound_impl(19); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000020() { sdf_smooth_union_lower_bound_impl(20); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000021() { sdf_smooth_union_lower_bound_impl(21); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000022() { sdf_smooth_union_lower_bound_impl(22); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000023() { sdf_smooth_union_lower_bound_impl(23); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000024() { sdf_smooth_union_lower_bound_impl(24); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000025() { sdf_smooth_union_lower_bound_impl(25); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000026() { sdf_smooth_union_lower_bound_impl(26); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000027() { sdf_smooth_union_lower_bound_impl(27); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000028() { sdf_smooth_union_lower_bound_impl(28); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000029() { sdf_smooth_union_lower_bound_impl(29); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000030() { sdf_smooth_union_lower_bound_impl(30); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000031() { sdf_smooth_union_lower_bound_impl(31); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000032() { sdf_smooth_union_lower_bound_impl(32); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000033() { sdf_smooth_union_lower_bound_impl(33); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000034() { sdf_smooth_union_lower_bound_impl(34); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000035() { sdf_smooth_union_lower_bound_impl(35); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000036() { sdf_smooth_union_lower_bound_impl(36); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000037() { sdf_smooth_union_lower_bound_impl(37); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000038() { sdf_smooth_union_lower_bound_impl(38); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000039() { sdf_smooth_union_lower_bound_impl(39); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000040() { sdf_smooth_union_lower_bound_impl(40); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000041() { sdf_smooth_union_lower_bound_impl(41); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000042() { sdf_smooth_union_lower_bound_impl(42); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000043() { sdf_smooth_union_lower_bound_impl(43); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000044() { sdf_smooth_union_lower_bound_impl(44); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000045() { sdf_smooth_union_lower_bound_impl(45); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000046() { sdf_smooth_union_lower_bound_impl(46); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000047() { sdf_smooth_union_lower_bound_impl(47); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000048() { sdf_smooth_union_lower_bound_impl(48); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000049() { sdf_smooth_union_lower_bound_impl(49); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000050() { sdf_smooth_union_lower_bound_impl(50); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000051() { sdf_smooth_union_lower_bound_impl(51); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000052() { sdf_smooth_union_lower_bound_impl(52); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000053() { sdf_smooth_union_lower_bound_impl(53); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000054() { sdf_smooth_union_lower_bound_impl(54); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000055() { sdf_smooth_union_lower_bound_impl(55); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000056() { sdf_smooth_union_lower_bound_impl(56); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000057() { sdf_smooth_union_lower_bound_impl(57); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000058() { sdf_smooth_union_lower_bound_impl(58); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000059() { sdf_smooth_union_lower_bound_impl(59); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000060() { sdf_smooth_union_lower_bound_impl(60); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000061() { sdf_smooth_union_lower_bound_impl(61); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000062() { sdf_smooth_union_lower_bound_impl(62); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000063() { sdf_smooth_union_lower_bound_impl(63); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000064() { sdf_smooth_union_lower_bound_impl(64); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000065() { sdf_smooth_union_lower_bound_impl(65); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000066() { sdf_smooth_union_lower_bound_impl(66); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000067() { sdf_smooth_union_lower_bound_impl(67); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000068() { sdf_smooth_union_lower_bound_impl(68); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000069() { sdf_smooth_union_lower_bound_impl(69); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000070() { sdf_smooth_union_lower_bound_impl(70); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000071() { sdf_smooth_union_lower_bound_impl(71); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000072() { sdf_smooth_union_lower_bound_impl(72); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000073() { sdf_smooth_union_lower_bound_impl(73); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000074() { sdf_smooth_union_lower_bound_impl(74); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000075() { sdf_smooth_union_lower_bound_impl(75); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000076() { sdf_smooth_union_lower_bound_impl(76); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000077() { sdf_smooth_union_lower_bound_impl(77); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000078() { sdf_smooth_union_lower_bound_impl(78); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000079() { sdf_smooth_union_lower_bound_impl(79); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000080() { sdf_smooth_union_lower_bound_impl(80); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000081() { sdf_smooth_union_lower_bound_impl(81); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000082() { sdf_smooth_union_lower_bound_impl(82); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000083() { sdf_smooth_union_lower_bound_impl(83); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000084() { sdf_smooth_union_lower_bound_impl(84); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000085() { sdf_smooth_union_lower_bound_impl(85); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000086() { sdf_smooth_union_lower_bound_impl(86); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000087() { sdf_smooth_union_lower_bound_impl(87); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000088() { sdf_smooth_union_lower_bound_impl(88); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_union_lower_bound_seed_000089() { sdf_smooth_union_lower_bound_impl(89); }
    // --- sdf_smooth_intersection_upper_bound: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000000() { sdf_smooth_intersection_upper_bound_impl(0); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000001() { sdf_smooth_intersection_upper_bound_impl(1); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000002() { sdf_smooth_intersection_upper_bound_impl(2); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000003() { sdf_smooth_intersection_upper_bound_impl(3); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000004() { sdf_smooth_intersection_upper_bound_impl(4); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000005() { sdf_smooth_intersection_upper_bound_impl(5); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000006() { sdf_smooth_intersection_upper_bound_impl(6); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000007() { sdf_smooth_intersection_upper_bound_impl(7); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000008() { sdf_smooth_intersection_upper_bound_impl(8); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000009() { sdf_smooth_intersection_upper_bound_impl(9); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000010() { sdf_smooth_intersection_upper_bound_impl(10); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000011() { sdf_smooth_intersection_upper_bound_impl(11); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000012() { sdf_smooth_intersection_upper_bound_impl(12); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000013() { sdf_smooth_intersection_upper_bound_impl(13); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000014() { sdf_smooth_intersection_upper_bound_impl(14); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000015() { sdf_smooth_intersection_upper_bound_impl(15); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000016() { sdf_smooth_intersection_upper_bound_impl(16); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000017() { sdf_smooth_intersection_upper_bound_impl(17); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000018() { sdf_smooth_intersection_upper_bound_impl(18); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000019() { sdf_smooth_intersection_upper_bound_impl(19); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000020() { sdf_smooth_intersection_upper_bound_impl(20); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000021() { sdf_smooth_intersection_upper_bound_impl(21); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000022() { sdf_smooth_intersection_upper_bound_impl(22); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000023() { sdf_smooth_intersection_upper_bound_impl(23); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000024() { sdf_smooth_intersection_upper_bound_impl(24); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000025() { sdf_smooth_intersection_upper_bound_impl(25); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000026() { sdf_smooth_intersection_upper_bound_impl(26); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000027() { sdf_smooth_intersection_upper_bound_impl(27); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000028() { sdf_smooth_intersection_upper_bound_impl(28); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000029() { sdf_smooth_intersection_upper_bound_impl(29); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000030() { sdf_smooth_intersection_upper_bound_impl(30); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000031() { sdf_smooth_intersection_upper_bound_impl(31); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000032() { sdf_smooth_intersection_upper_bound_impl(32); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000033() { sdf_smooth_intersection_upper_bound_impl(33); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000034() { sdf_smooth_intersection_upper_bound_impl(34); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000035() { sdf_smooth_intersection_upper_bound_impl(35); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000036() { sdf_smooth_intersection_upper_bound_impl(36); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000037() { sdf_smooth_intersection_upper_bound_impl(37); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000038() { sdf_smooth_intersection_upper_bound_impl(38); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000039() { sdf_smooth_intersection_upper_bound_impl(39); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000040() { sdf_smooth_intersection_upper_bound_impl(40); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000041() { sdf_smooth_intersection_upper_bound_impl(41); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000042() { sdf_smooth_intersection_upper_bound_impl(42); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000043() { sdf_smooth_intersection_upper_bound_impl(43); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000044() { sdf_smooth_intersection_upper_bound_impl(44); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000045() { sdf_smooth_intersection_upper_bound_impl(45); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000046() { sdf_smooth_intersection_upper_bound_impl(46); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000047() { sdf_smooth_intersection_upper_bound_impl(47); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000048() { sdf_smooth_intersection_upper_bound_impl(48); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000049() { sdf_smooth_intersection_upper_bound_impl(49); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000050() { sdf_smooth_intersection_upper_bound_impl(50); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000051() { sdf_smooth_intersection_upper_bound_impl(51); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000052() { sdf_smooth_intersection_upper_bound_impl(52); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000053() { sdf_smooth_intersection_upper_bound_impl(53); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000054() { sdf_smooth_intersection_upper_bound_impl(54); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000055() { sdf_smooth_intersection_upper_bound_impl(55); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000056() { sdf_smooth_intersection_upper_bound_impl(56); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000057() { sdf_smooth_intersection_upper_bound_impl(57); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000058() { sdf_smooth_intersection_upper_bound_impl(58); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000059() { sdf_smooth_intersection_upper_bound_impl(59); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000060() { sdf_smooth_intersection_upper_bound_impl(60); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000061() { sdf_smooth_intersection_upper_bound_impl(61); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000062() { sdf_smooth_intersection_upper_bound_impl(62); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000063() { sdf_smooth_intersection_upper_bound_impl(63); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000064() { sdf_smooth_intersection_upper_bound_impl(64); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000065() { sdf_smooth_intersection_upper_bound_impl(65); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000066() { sdf_smooth_intersection_upper_bound_impl(66); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000067() { sdf_smooth_intersection_upper_bound_impl(67); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000068() { sdf_smooth_intersection_upper_bound_impl(68); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000069() { sdf_smooth_intersection_upper_bound_impl(69); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000070() { sdf_smooth_intersection_upper_bound_impl(70); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000071() { sdf_smooth_intersection_upper_bound_impl(71); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000072() { sdf_smooth_intersection_upper_bound_impl(72); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000073() { sdf_smooth_intersection_upper_bound_impl(73); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000074() { sdf_smooth_intersection_upper_bound_impl(74); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000075() { sdf_smooth_intersection_upper_bound_impl(75); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000076() { sdf_smooth_intersection_upper_bound_impl(76); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000077() { sdf_smooth_intersection_upper_bound_impl(77); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000078() { sdf_smooth_intersection_upper_bound_impl(78); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000079() { sdf_smooth_intersection_upper_bound_impl(79); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000080() { sdf_smooth_intersection_upper_bound_impl(80); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000081() { sdf_smooth_intersection_upper_bound_impl(81); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000082() { sdf_smooth_intersection_upper_bound_impl(82); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000083() { sdf_smooth_intersection_upper_bound_impl(83); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000084() { sdf_smooth_intersection_upper_bound_impl(84); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000085() { sdf_smooth_intersection_upper_bound_impl(85); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000086() { sdf_smooth_intersection_upper_bound_impl(86); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000087() { sdf_smooth_intersection_upper_bound_impl(87); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000088() { sdf_smooth_intersection_upper_bound_impl(88); }
    #[cfg_attr(test, test)]
    fn sdf_smooth_intersection_upper_bound_seed_000089() { sdf_smooth_intersection_upper_bound_impl(89); }
    // --- poly_translate_area_invariant: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000000() { poly_translate_area_invariant_impl(0); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000001() { poly_translate_area_invariant_impl(1); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000002() { poly_translate_area_invariant_impl(2); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000003() { poly_translate_area_invariant_impl(3); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000004() { poly_translate_area_invariant_impl(4); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000005() { poly_translate_area_invariant_impl(5); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000006() { poly_translate_area_invariant_impl(6); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000007() { poly_translate_area_invariant_impl(7); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000008() { poly_translate_area_invariant_impl(8); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000009() { poly_translate_area_invariant_impl(9); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000010() { poly_translate_area_invariant_impl(10); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000011() { poly_translate_area_invariant_impl(11); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000012() { poly_translate_area_invariant_impl(12); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000013() { poly_translate_area_invariant_impl(13); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000014() { poly_translate_area_invariant_impl(14); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000015() { poly_translate_area_invariant_impl(15); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000016() { poly_translate_area_invariant_impl(16); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000017() { poly_translate_area_invariant_impl(17); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000018() { poly_translate_area_invariant_impl(18); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000019() { poly_translate_area_invariant_impl(19); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000020() { poly_translate_area_invariant_impl(20); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000021() { poly_translate_area_invariant_impl(21); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000022() { poly_translate_area_invariant_impl(22); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000023() { poly_translate_area_invariant_impl(23); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000024() { poly_translate_area_invariant_impl(24); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000025() { poly_translate_area_invariant_impl(25); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000026() { poly_translate_area_invariant_impl(26); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000027() { poly_translate_area_invariant_impl(27); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000028() { poly_translate_area_invariant_impl(28); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000029() { poly_translate_area_invariant_impl(29); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000030() { poly_translate_area_invariant_impl(30); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000031() { poly_translate_area_invariant_impl(31); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000032() { poly_translate_area_invariant_impl(32); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000033() { poly_translate_area_invariant_impl(33); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000034() { poly_translate_area_invariant_impl(34); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000035() { poly_translate_area_invariant_impl(35); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000036() { poly_translate_area_invariant_impl(36); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000037() { poly_translate_area_invariant_impl(37); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000038() { poly_translate_area_invariant_impl(38); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000039() { poly_translate_area_invariant_impl(39); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000040() { poly_translate_area_invariant_impl(40); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000041() { poly_translate_area_invariant_impl(41); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000042() { poly_translate_area_invariant_impl(42); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000043() { poly_translate_area_invariant_impl(43); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000044() { poly_translate_area_invariant_impl(44); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000045() { poly_translate_area_invariant_impl(45); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000046() { poly_translate_area_invariant_impl(46); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000047() { poly_translate_area_invariant_impl(47); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000048() { poly_translate_area_invariant_impl(48); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000049() { poly_translate_area_invariant_impl(49); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000050() { poly_translate_area_invariant_impl(50); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000051() { poly_translate_area_invariant_impl(51); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000052() { poly_translate_area_invariant_impl(52); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000053() { poly_translate_area_invariant_impl(53); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000054() { poly_translate_area_invariant_impl(54); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000055() { poly_translate_area_invariant_impl(55); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000056() { poly_translate_area_invariant_impl(56); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000057() { poly_translate_area_invariant_impl(57); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000058() { poly_translate_area_invariant_impl(58); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000059() { poly_translate_area_invariant_impl(59); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000060() { poly_translate_area_invariant_impl(60); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000061() { poly_translate_area_invariant_impl(61); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000062() { poly_translate_area_invariant_impl(62); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000063() { poly_translate_area_invariant_impl(63); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000064() { poly_translate_area_invariant_impl(64); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000065() { poly_translate_area_invariant_impl(65); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000066() { poly_translate_area_invariant_impl(66); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000067() { poly_translate_area_invariant_impl(67); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000068() { poly_translate_area_invariant_impl(68); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000069() { poly_translate_area_invariant_impl(69); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000070() { poly_translate_area_invariant_impl(70); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000071() { poly_translate_area_invariant_impl(71); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000072() { poly_translate_area_invariant_impl(72); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000073() { poly_translate_area_invariant_impl(73); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000074() { poly_translate_area_invariant_impl(74); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000075() { poly_translate_area_invariant_impl(75); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000076() { poly_translate_area_invariant_impl(76); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000077() { poly_translate_area_invariant_impl(77); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000078() { poly_translate_area_invariant_impl(78); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000079() { poly_translate_area_invariant_impl(79); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000080() { poly_translate_area_invariant_impl(80); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000081() { poly_translate_area_invariant_impl(81); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000082() { poly_translate_area_invariant_impl(82); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000083() { poly_translate_area_invariant_impl(83); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000084() { poly_translate_area_invariant_impl(84); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000085() { poly_translate_area_invariant_impl(85); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000086() { poly_translate_area_invariant_impl(86); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000087() { poly_translate_area_invariant_impl(87); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000088() { poly_translate_area_invariant_impl(88); }
    #[cfg_attr(test, test)]
    fn poly_translate_area_invariant_seed_000089() { poly_translate_area_invariant_impl(89); }
    // --- poly_rotate_area_invariant: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000000() { poly_rotate_area_invariant_impl(0); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000001() { poly_rotate_area_invariant_impl(1); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000002() { poly_rotate_area_invariant_impl(2); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000003() { poly_rotate_area_invariant_impl(3); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000004() { poly_rotate_area_invariant_impl(4); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000005() { poly_rotate_area_invariant_impl(5); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000006() { poly_rotate_area_invariant_impl(6); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000007() { poly_rotate_area_invariant_impl(7); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000008() { poly_rotate_area_invariant_impl(8); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000009() { poly_rotate_area_invariant_impl(9); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000010() { poly_rotate_area_invariant_impl(10); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000011() { poly_rotate_area_invariant_impl(11); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000012() { poly_rotate_area_invariant_impl(12); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000013() { poly_rotate_area_invariant_impl(13); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000014() { poly_rotate_area_invariant_impl(14); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000015() { poly_rotate_area_invariant_impl(15); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000016() { poly_rotate_area_invariant_impl(16); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000017() { poly_rotate_area_invariant_impl(17); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000018() { poly_rotate_area_invariant_impl(18); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000019() { poly_rotate_area_invariant_impl(19); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000020() { poly_rotate_area_invariant_impl(20); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000021() { poly_rotate_area_invariant_impl(21); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000022() { poly_rotate_area_invariant_impl(22); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000023() { poly_rotate_area_invariant_impl(23); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000024() { poly_rotate_area_invariant_impl(24); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000025() { poly_rotate_area_invariant_impl(25); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000026() { poly_rotate_area_invariant_impl(26); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000027() { poly_rotate_area_invariant_impl(27); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000028() { poly_rotate_area_invariant_impl(28); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000029() { poly_rotate_area_invariant_impl(29); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000030() { poly_rotate_area_invariant_impl(30); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000031() { poly_rotate_area_invariant_impl(31); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000032() { poly_rotate_area_invariant_impl(32); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000033() { poly_rotate_area_invariant_impl(33); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000034() { poly_rotate_area_invariant_impl(34); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000035() { poly_rotate_area_invariant_impl(35); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000036() { poly_rotate_area_invariant_impl(36); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000037() { poly_rotate_area_invariant_impl(37); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000038() { poly_rotate_area_invariant_impl(38); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000039() { poly_rotate_area_invariant_impl(39); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000040() { poly_rotate_area_invariant_impl(40); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000041() { poly_rotate_area_invariant_impl(41); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000042() { poly_rotate_area_invariant_impl(42); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000043() { poly_rotate_area_invariant_impl(43); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000044() { poly_rotate_area_invariant_impl(44); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000045() { poly_rotate_area_invariant_impl(45); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000046() { poly_rotate_area_invariant_impl(46); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000047() { poly_rotate_area_invariant_impl(47); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000048() { poly_rotate_area_invariant_impl(48); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000049() { poly_rotate_area_invariant_impl(49); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000050() { poly_rotate_area_invariant_impl(50); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000051() { poly_rotate_area_invariant_impl(51); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000052() { poly_rotate_area_invariant_impl(52); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000053() { poly_rotate_area_invariant_impl(53); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000054() { poly_rotate_area_invariant_impl(54); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000055() { poly_rotate_area_invariant_impl(55); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000056() { poly_rotate_area_invariant_impl(56); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000057() { poly_rotate_area_invariant_impl(57); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000058() { poly_rotate_area_invariant_impl(58); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000059() { poly_rotate_area_invariant_impl(59); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000060() { poly_rotate_area_invariant_impl(60); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000061() { poly_rotate_area_invariant_impl(61); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000062() { poly_rotate_area_invariant_impl(62); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000063() { poly_rotate_area_invariant_impl(63); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000064() { poly_rotate_area_invariant_impl(64); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000065() { poly_rotate_area_invariant_impl(65); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000066() { poly_rotate_area_invariant_impl(66); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000067() { poly_rotate_area_invariant_impl(67); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000068() { poly_rotate_area_invariant_impl(68); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000069() { poly_rotate_area_invariant_impl(69); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000070() { poly_rotate_area_invariant_impl(70); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000071() { poly_rotate_area_invariant_impl(71); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000072() { poly_rotate_area_invariant_impl(72); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000073() { poly_rotate_area_invariant_impl(73); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000074() { poly_rotate_area_invariant_impl(74); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000075() { poly_rotate_area_invariant_impl(75); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000076() { poly_rotate_area_invariant_impl(76); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000077() { poly_rotate_area_invariant_impl(77); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000078() { poly_rotate_area_invariant_impl(78); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000079() { poly_rotate_area_invariant_impl(79); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000080() { poly_rotate_area_invariant_impl(80); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000081() { poly_rotate_area_invariant_impl(81); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000082() { poly_rotate_area_invariant_impl(82); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000083() { poly_rotate_area_invariant_impl(83); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000084() { poly_rotate_area_invariant_impl(84); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000085() { poly_rotate_area_invariant_impl(85); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000086() { poly_rotate_area_invariant_impl(86); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000087() { poly_rotate_area_invariant_impl(87); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000088() { poly_rotate_area_invariant_impl(88); }
    #[cfg_attr(test, test)]
    fn poly_rotate_area_invariant_seed_000089() { poly_rotate_area_invariant_impl(89); }
    // --- poly_winding_reversal_sign_flip: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000000() { poly_winding_reversal_sign_flip_impl(0); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000001() { poly_winding_reversal_sign_flip_impl(1); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000002() { poly_winding_reversal_sign_flip_impl(2); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000003() { poly_winding_reversal_sign_flip_impl(3); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000004() { poly_winding_reversal_sign_flip_impl(4); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000005() { poly_winding_reversal_sign_flip_impl(5); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000006() { poly_winding_reversal_sign_flip_impl(6); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000007() { poly_winding_reversal_sign_flip_impl(7); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000008() { poly_winding_reversal_sign_flip_impl(8); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000009() { poly_winding_reversal_sign_flip_impl(9); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000010() { poly_winding_reversal_sign_flip_impl(10); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000011() { poly_winding_reversal_sign_flip_impl(11); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000012() { poly_winding_reversal_sign_flip_impl(12); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000013() { poly_winding_reversal_sign_flip_impl(13); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000014() { poly_winding_reversal_sign_flip_impl(14); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000015() { poly_winding_reversal_sign_flip_impl(15); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000016() { poly_winding_reversal_sign_flip_impl(16); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000017() { poly_winding_reversal_sign_flip_impl(17); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000018() { poly_winding_reversal_sign_flip_impl(18); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000019() { poly_winding_reversal_sign_flip_impl(19); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000020() { poly_winding_reversal_sign_flip_impl(20); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000021() { poly_winding_reversal_sign_flip_impl(21); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000022() { poly_winding_reversal_sign_flip_impl(22); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000023() { poly_winding_reversal_sign_flip_impl(23); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000024() { poly_winding_reversal_sign_flip_impl(24); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000025() { poly_winding_reversal_sign_flip_impl(25); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000026() { poly_winding_reversal_sign_flip_impl(26); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000027() { poly_winding_reversal_sign_flip_impl(27); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000028() { poly_winding_reversal_sign_flip_impl(28); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000029() { poly_winding_reversal_sign_flip_impl(29); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000030() { poly_winding_reversal_sign_flip_impl(30); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000031() { poly_winding_reversal_sign_flip_impl(31); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000032() { poly_winding_reversal_sign_flip_impl(32); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000033() { poly_winding_reversal_sign_flip_impl(33); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000034() { poly_winding_reversal_sign_flip_impl(34); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000035() { poly_winding_reversal_sign_flip_impl(35); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000036() { poly_winding_reversal_sign_flip_impl(36); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000037() { poly_winding_reversal_sign_flip_impl(37); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000038() { poly_winding_reversal_sign_flip_impl(38); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000039() { poly_winding_reversal_sign_flip_impl(39); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000040() { poly_winding_reversal_sign_flip_impl(40); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000041() { poly_winding_reversal_sign_flip_impl(41); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000042() { poly_winding_reversal_sign_flip_impl(42); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000043() { poly_winding_reversal_sign_flip_impl(43); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000044() { poly_winding_reversal_sign_flip_impl(44); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000045() { poly_winding_reversal_sign_flip_impl(45); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000046() { poly_winding_reversal_sign_flip_impl(46); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000047() { poly_winding_reversal_sign_flip_impl(47); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000048() { poly_winding_reversal_sign_flip_impl(48); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000049() { poly_winding_reversal_sign_flip_impl(49); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000050() { poly_winding_reversal_sign_flip_impl(50); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000051() { poly_winding_reversal_sign_flip_impl(51); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000052() { poly_winding_reversal_sign_flip_impl(52); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000053() { poly_winding_reversal_sign_flip_impl(53); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000054() { poly_winding_reversal_sign_flip_impl(54); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000055() { poly_winding_reversal_sign_flip_impl(55); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000056() { poly_winding_reversal_sign_flip_impl(56); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000057() { poly_winding_reversal_sign_flip_impl(57); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000058() { poly_winding_reversal_sign_flip_impl(58); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000059() { poly_winding_reversal_sign_flip_impl(59); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000060() { poly_winding_reversal_sign_flip_impl(60); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000061() { poly_winding_reversal_sign_flip_impl(61); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000062() { poly_winding_reversal_sign_flip_impl(62); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000063() { poly_winding_reversal_sign_flip_impl(63); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000064() { poly_winding_reversal_sign_flip_impl(64); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000065() { poly_winding_reversal_sign_flip_impl(65); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000066() { poly_winding_reversal_sign_flip_impl(66); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000067() { poly_winding_reversal_sign_flip_impl(67); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000068() { poly_winding_reversal_sign_flip_impl(68); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000069() { poly_winding_reversal_sign_flip_impl(69); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000070() { poly_winding_reversal_sign_flip_impl(70); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000071() { poly_winding_reversal_sign_flip_impl(71); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000072() { poly_winding_reversal_sign_flip_impl(72); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000073() { poly_winding_reversal_sign_flip_impl(73); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000074() { poly_winding_reversal_sign_flip_impl(74); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000075() { poly_winding_reversal_sign_flip_impl(75); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000076() { poly_winding_reversal_sign_flip_impl(76); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000077() { poly_winding_reversal_sign_flip_impl(77); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000078() { poly_winding_reversal_sign_flip_impl(78); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000079() { poly_winding_reversal_sign_flip_impl(79); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000080() { poly_winding_reversal_sign_flip_impl(80); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000081() { poly_winding_reversal_sign_flip_impl(81); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000082() { poly_winding_reversal_sign_flip_impl(82); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000083() { poly_winding_reversal_sign_flip_impl(83); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000084() { poly_winding_reversal_sign_flip_impl(84); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000085() { poly_winding_reversal_sign_flip_impl(85); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000086() { poly_winding_reversal_sign_flip_impl(86); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000087() { poly_winding_reversal_sign_flip_impl(87); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000088() { poly_winding_reversal_sign_flip_impl(88); }
    #[cfg_attr(test, test)]
    fn poly_winding_reversal_sign_flip_seed_000089() { poly_winding_reversal_sign_flip_impl(89); }
    // --- poly_fan_triangulation_additivity: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000000() { poly_fan_triangulation_additivity_impl(0); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000001() { poly_fan_triangulation_additivity_impl(1); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000002() { poly_fan_triangulation_additivity_impl(2); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000003() { poly_fan_triangulation_additivity_impl(3); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000004() { poly_fan_triangulation_additivity_impl(4); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000005() { poly_fan_triangulation_additivity_impl(5); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000006() { poly_fan_triangulation_additivity_impl(6); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000007() { poly_fan_triangulation_additivity_impl(7); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000008() { poly_fan_triangulation_additivity_impl(8); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000009() { poly_fan_triangulation_additivity_impl(9); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000010() { poly_fan_triangulation_additivity_impl(10); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000011() { poly_fan_triangulation_additivity_impl(11); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000012() { poly_fan_triangulation_additivity_impl(12); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000013() { poly_fan_triangulation_additivity_impl(13); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000014() { poly_fan_triangulation_additivity_impl(14); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000015() { poly_fan_triangulation_additivity_impl(15); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000016() { poly_fan_triangulation_additivity_impl(16); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000017() { poly_fan_triangulation_additivity_impl(17); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000018() { poly_fan_triangulation_additivity_impl(18); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000019() { poly_fan_triangulation_additivity_impl(19); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000020() { poly_fan_triangulation_additivity_impl(20); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000021() { poly_fan_triangulation_additivity_impl(21); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000022() { poly_fan_triangulation_additivity_impl(22); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000023() { poly_fan_triangulation_additivity_impl(23); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000024() { poly_fan_triangulation_additivity_impl(24); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000025() { poly_fan_triangulation_additivity_impl(25); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000026() { poly_fan_triangulation_additivity_impl(26); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000027() { poly_fan_triangulation_additivity_impl(27); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000028() { poly_fan_triangulation_additivity_impl(28); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000029() { poly_fan_triangulation_additivity_impl(29); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000030() { poly_fan_triangulation_additivity_impl(30); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000031() { poly_fan_triangulation_additivity_impl(31); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000032() { poly_fan_triangulation_additivity_impl(32); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000033() { poly_fan_triangulation_additivity_impl(33); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000034() { poly_fan_triangulation_additivity_impl(34); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000035() { poly_fan_triangulation_additivity_impl(35); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000036() { poly_fan_triangulation_additivity_impl(36); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000037() { poly_fan_triangulation_additivity_impl(37); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000038() { poly_fan_triangulation_additivity_impl(38); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000039() { poly_fan_triangulation_additivity_impl(39); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000040() { poly_fan_triangulation_additivity_impl(40); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000041() { poly_fan_triangulation_additivity_impl(41); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000042() { poly_fan_triangulation_additivity_impl(42); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000043() { poly_fan_triangulation_additivity_impl(43); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000044() { poly_fan_triangulation_additivity_impl(44); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000045() { poly_fan_triangulation_additivity_impl(45); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000046() { poly_fan_triangulation_additivity_impl(46); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000047() { poly_fan_triangulation_additivity_impl(47); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000048() { poly_fan_triangulation_additivity_impl(48); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000049() { poly_fan_triangulation_additivity_impl(49); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000050() { poly_fan_triangulation_additivity_impl(50); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000051() { poly_fan_triangulation_additivity_impl(51); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000052() { poly_fan_triangulation_additivity_impl(52); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000053() { poly_fan_triangulation_additivity_impl(53); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000054() { poly_fan_triangulation_additivity_impl(54); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000055() { poly_fan_triangulation_additivity_impl(55); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000056() { poly_fan_triangulation_additivity_impl(56); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000057() { poly_fan_triangulation_additivity_impl(57); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000058() { poly_fan_triangulation_additivity_impl(58); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000059() { poly_fan_triangulation_additivity_impl(59); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000060() { poly_fan_triangulation_additivity_impl(60); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000061() { poly_fan_triangulation_additivity_impl(61); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000062() { poly_fan_triangulation_additivity_impl(62); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000063() { poly_fan_triangulation_additivity_impl(63); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000064() { poly_fan_triangulation_additivity_impl(64); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000065() { poly_fan_triangulation_additivity_impl(65); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000066() { poly_fan_triangulation_additivity_impl(66); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000067() { poly_fan_triangulation_additivity_impl(67); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000068() { poly_fan_triangulation_additivity_impl(68); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000069() { poly_fan_triangulation_additivity_impl(69); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000070() { poly_fan_triangulation_additivity_impl(70); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000071() { poly_fan_triangulation_additivity_impl(71); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000072() { poly_fan_triangulation_additivity_impl(72); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000073() { poly_fan_triangulation_additivity_impl(73); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000074() { poly_fan_triangulation_additivity_impl(74); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000075() { poly_fan_triangulation_additivity_impl(75); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000076() { poly_fan_triangulation_additivity_impl(76); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000077() { poly_fan_triangulation_additivity_impl(77); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000078() { poly_fan_triangulation_additivity_impl(78); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000079() { poly_fan_triangulation_additivity_impl(79); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000080() { poly_fan_triangulation_additivity_impl(80); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000081() { poly_fan_triangulation_additivity_impl(81); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000082() { poly_fan_triangulation_additivity_impl(82); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000083() { poly_fan_triangulation_additivity_impl(83); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000084() { poly_fan_triangulation_additivity_impl(84); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000085() { poly_fan_triangulation_additivity_impl(85); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000086() { poly_fan_triangulation_additivity_impl(86); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000087() { poly_fan_triangulation_additivity_impl(87); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000088() { poly_fan_triangulation_additivity_impl(88); }
    #[cfg_attr(test, test)]
    fn poly_fan_triangulation_additivity_seed_000089() { poly_fan_triangulation_additivity_impl(89); }
    // --- poly_center_and_far_point_containment: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000000() { poly_center_and_far_point_containment_impl(0); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000001() { poly_center_and_far_point_containment_impl(1); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000002() { poly_center_and_far_point_containment_impl(2); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000003() { poly_center_and_far_point_containment_impl(3); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000004() { poly_center_and_far_point_containment_impl(4); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000005() { poly_center_and_far_point_containment_impl(5); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000006() { poly_center_and_far_point_containment_impl(6); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000007() { poly_center_and_far_point_containment_impl(7); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000008() { poly_center_and_far_point_containment_impl(8); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000009() { poly_center_and_far_point_containment_impl(9); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000010() { poly_center_and_far_point_containment_impl(10); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000011() { poly_center_and_far_point_containment_impl(11); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000012() { poly_center_and_far_point_containment_impl(12); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000013() { poly_center_and_far_point_containment_impl(13); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000014() { poly_center_and_far_point_containment_impl(14); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000015() { poly_center_and_far_point_containment_impl(15); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000016() { poly_center_and_far_point_containment_impl(16); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000017() { poly_center_and_far_point_containment_impl(17); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000018() { poly_center_and_far_point_containment_impl(18); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000019() { poly_center_and_far_point_containment_impl(19); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000020() { poly_center_and_far_point_containment_impl(20); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000021() { poly_center_and_far_point_containment_impl(21); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000022() { poly_center_and_far_point_containment_impl(22); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000023() { poly_center_and_far_point_containment_impl(23); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000024() { poly_center_and_far_point_containment_impl(24); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000025() { poly_center_and_far_point_containment_impl(25); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000026() { poly_center_and_far_point_containment_impl(26); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000027() { poly_center_and_far_point_containment_impl(27); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000028() { poly_center_and_far_point_containment_impl(28); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000029() { poly_center_and_far_point_containment_impl(29); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000030() { poly_center_and_far_point_containment_impl(30); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000031() { poly_center_and_far_point_containment_impl(31); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000032() { poly_center_and_far_point_containment_impl(32); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000033() { poly_center_and_far_point_containment_impl(33); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000034() { poly_center_and_far_point_containment_impl(34); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000035() { poly_center_and_far_point_containment_impl(35); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000036() { poly_center_and_far_point_containment_impl(36); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000037() { poly_center_and_far_point_containment_impl(37); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000038() { poly_center_and_far_point_containment_impl(38); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000039() { poly_center_and_far_point_containment_impl(39); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000040() { poly_center_and_far_point_containment_impl(40); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000041() { poly_center_and_far_point_containment_impl(41); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000042() { poly_center_and_far_point_containment_impl(42); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000043() { poly_center_and_far_point_containment_impl(43); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000044() { poly_center_and_far_point_containment_impl(44); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000045() { poly_center_and_far_point_containment_impl(45); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000046() { poly_center_and_far_point_containment_impl(46); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000047() { poly_center_and_far_point_containment_impl(47); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000048() { poly_center_and_far_point_containment_impl(48); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000049() { poly_center_and_far_point_containment_impl(49); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000050() { poly_center_and_far_point_containment_impl(50); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000051() { poly_center_and_far_point_containment_impl(51); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000052() { poly_center_and_far_point_containment_impl(52); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000053() { poly_center_and_far_point_containment_impl(53); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000054() { poly_center_and_far_point_containment_impl(54); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000055() { poly_center_and_far_point_containment_impl(55); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000056() { poly_center_and_far_point_containment_impl(56); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000057() { poly_center_and_far_point_containment_impl(57); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000058() { poly_center_and_far_point_containment_impl(58); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000059() { poly_center_and_far_point_containment_impl(59); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000060() { poly_center_and_far_point_containment_impl(60); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000061() { poly_center_and_far_point_containment_impl(61); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000062() { poly_center_and_far_point_containment_impl(62); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000063() { poly_center_and_far_point_containment_impl(63); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000064() { poly_center_and_far_point_containment_impl(64); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000065() { poly_center_and_far_point_containment_impl(65); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000066() { poly_center_and_far_point_containment_impl(66); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000067() { poly_center_and_far_point_containment_impl(67); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000068() { poly_center_and_far_point_containment_impl(68); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000069() { poly_center_and_far_point_containment_impl(69); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000070() { poly_center_and_far_point_containment_impl(70); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000071() { poly_center_and_far_point_containment_impl(71); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000072() { poly_center_and_far_point_containment_impl(72); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000073() { poly_center_and_far_point_containment_impl(73); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000074() { poly_center_and_far_point_containment_impl(74); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000075() { poly_center_and_far_point_containment_impl(75); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000076() { poly_center_and_far_point_containment_impl(76); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000077() { poly_center_and_far_point_containment_impl(77); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000078() { poly_center_and_far_point_containment_impl(78); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000079() { poly_center_and_far_point_containment_impl(79); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000080() { poly_center_and_far_point_containment_impl(80); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000081() { poly_center_and_far_point_containment_impl(81); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000082() { poly_center_and_far_point_containment_impl(82); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000083() { poly_center_and_far_point_containment_impl(83); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000084() { poly_center_and_far_point_containment_impl(84); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000085() { poly_center_and_far_point_containment_impl(85); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000086() { poly_center_and_far_point_containment_impl(86); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000087() { poly_center_and_far_point_containment_impl(87); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000088() { poly_center_and_far_point_containment_impl(88); }
    #[cfg_attr(test, test)]
    fn poly_center_and_far_point_containment_seed_000089() { poly_center_and_far_point_containment_impl(89); }
    // --- poly_perimeter_scale_linear: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000000() { poly_perimeter_scale_linear_impl(0); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000001() { poly_perimeter_scale_linear_impl(1); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000002() { poly_perimeter_scale_linear_impl(2); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000003() { poly_perimeter_scale_linear_impl(3); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000004() { poly_perimeter_scale_linear_impl(4); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000005() { poly_perimeter_scale_linear_impl(5); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000006() { poly_perimeter_scale_linear_impl(6); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000007() { poly_perimeter_scale_linear_impl(7); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000008() { poly_perimeter_scale_linear_impl(8); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000009() { poly_perimeter_scale_linear_impl(9); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000010() { poly_perimeter_scale_linear_impl(10); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000011() { poly_perimeter_scale_linear_impl(11); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000012() { poly_perimeter_scale_linear_impl(12); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000013() { poly_perimeter_scale_linear_impl(13); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000014() { poly_perimeter_scale_linear_impl(14); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000015() { poly_perimeter_scale_linear_impl(15); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000016() { poly_perimeter_scale_linear_impl(16); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000017() { poly_perimeter_scale_linear_impl(17); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000018() { poly_perimeter_scale_linear_impl(18); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000019() { poly_perimeter_scale_linear_impl(19); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000020() { poly_perimeter_scale_linear_impl(20); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000021() { poly_perimeter_scale_linear_impl(21); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000022() { poly_perimeter_scale_linear_impl(22); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000023() { poly_perimeter_scale_linear_impl(23); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000024() { poly_perimeter_scale_linear_impl(24); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000025() { poly_perimeter_scale_linear_impl(25); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000026() { poly_perimeter_scale_linear_impl(26); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000027() { poly_perimeter_scale_linear_impl(27); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000028() { poly_perimeter_scale_linear_impl(28); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000029() { poly_perimeter_scale_linear_impl(29); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000030() { poly_perimeter_scale_linear_impl(30); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000031() { poly_perimeter_scale_linear_impl(31); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000032() { poly_perimeter_scale_linear_impl(32); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000033() { poly_perimeter_scale_linear_impl(33); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000034() { poly_perimeter_scale_linear_impl(34); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000035() { poly_perimeter_scale_linear_impl(35); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000036() { poly_perimeter_scale_linear_impl(36); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000037() { poly_perimeter_scale_linear_impl(37); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000038() { poly_perimeter_scale_linear_impl(38); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000039() { poly_perimeter_scale_linear_impl(39); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000040() { poly_perimeter_scale_linear_impl(40); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000041() { poly_perimeter_scale_linear_impl(41); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000042() { poly_perimeter_scale_linear_impl(42); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000043() { poly_perimeter_scale_linear_impl(43); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000044() { poly_perimeter_scale_linear_impl(44); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000045() { poly_perimeter_scale_linear_impl(45); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000046() { poly_perimeter_scale_linear_impl(46); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000047() { poly_perimeter_scale_linear_impl(47); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000048() { poly_perimeter_scale_linear_impl(48); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000049() { poly_perimeter_scale_linear_impl(49); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000050() { poly_perimeter_scale_linear_impl(50); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000051() { poly_perimeter_scale_linear_impl(51); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000052() { poly_perimeter_scale_linear_impl(52); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000053() { poly_perimeter_scale_linear_impl(53); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000054() { poly_perimeter_scale_linear_impl(54); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000055() { poly_perimeter_scale_linear_impl(55); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000056() { poly_perimeter_scale_linear_impl(56); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000057() { poly_perimeter_scale_linear_impl(57); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000058() { poly_perimeter_scale_linear_impl(58); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000059() { poly_perimeter_scale_linear_impl(59); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000060() { poly_perimeter_scale_linear_impl(60); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000061() { poly_perimeter_scale_linear_impl(61); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000062() { poly_perimeter_scale_linear_impl(62); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000063() { poly_perimeter_scale_linear_impl(63); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000064() { poly_perimeter_scale_linear_impl(64); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000065() { poly_perimeter_scale_linear_impl(65); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000066() { poly_perimeter_scale_linear_impl(66); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000067() { poly_perimeter_scale_linear_impl(67); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000068() { poly_perimeter_scale_linear_impl(68); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000069() { poly_perimeter_scale_linear_impl(69); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000070() { poly_perimeter_scale_linear_impl(70); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000071() { poly_perimeter_scale_linear_impl(71); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000072() { poly_perimeter_scale_linear_impl(72); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000073() { poly_perimeter_scale_linear_impl(73); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000074() { poly_perimeter_scale_linear_impl(74); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000075() { poly_perimeter_scale_linear_impl(75); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000076() { poly_perimeter_scale_linear_impl(76); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000077() { poly_perimeter_scale_linear_impl(77); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000078() { poly_perimeter_scale_linear_impl(78); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000079() { poly_perimeter_scale_linear_impl(79); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000080() { poly_perimeter_scale_linear_impl(80); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000081() { poly_perimeter_scale_linear_impl(81); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000082() { poly_perimeter_scale_linear_impl(82); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000083() { poly_perimeter_scale_linear_impl(83); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000084() { poly_perimeter_scale_linear_impl(84); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000085() { poly_perimeter_scale_linear_impl(85); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000086() { poly_perimeter_scale_linear_impl(86); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000087() { poly_perimeter_scale_linear_impl(87); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000088() { poly_perimeter_scale_linear_impl(88); }
    #[cfg_attr(test, test)]
    fn poly_perimeter_scale_linear_seed_000089() { poly_perimeter_scale_linear_impl(89); }
    // --- ov_box_box_distance_symmetric: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000000() { ov_box_box_distance_symmetric_impl(0); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000001() { ov_box_box_distance_symmetric_impl(1); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000002() { ov_box_box_distance_symmetric_impl(2); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000003() { ov_box_box_distance_symmetric_impl(3); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000004() { ov_box_box_distance_symmetric_impl(4); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000005() { ov_box_box_distance_symmetric_impl(5); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000006() { ov_box_box_distance_symmetric_impl(6); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000007() { ov_box_box_distance_symmetric_impl(7); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000008() { ov_box_box_distance_symmetric_impl(8); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000009() { ov_box_box_distance_symmetric_impl(9); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000010() { ov_box_box_distance_symmetric_impl(10); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000011() { ov_box_box_distance_symmetric_impl(11); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000012() { ov_box_box_distance_symmetric_impl(12); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000013() { ov_box_box_distance_symmetric_impl(13); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000014() { ov_box_box_distance_symmetric_impl(14); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000015() { ov_box_box_distance_symmetric_impl(15); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000016() { ov_box_box_distance_symmetric_impl(16); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000017() { ov_box_box_distance_symmetric_impl(17); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000018() { ov_box_box_distance_symmetric_impl(18); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000019() { ov_box_box_distance_symmetric_impl(19); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000020() { ov_box_box_distance_symmetric_impl(20); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000021() { ov_box_box_distance_symmetric_impl(21); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000022() { ov_box_box_distance_symmetric_impl(22); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000023() { ov_box_box_distance_symmetric_impl(23); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000024() { ov_box_box_distance_symmetric_impl(24); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000025() { ov_box_box_distance_symmetric_impl(25); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000026() { ov_box_box_distance_symmetric_impl(26); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000027() { ov_box_box_distance_symmetric_impl(27); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000028() { ov_box_box_distance_symmetric_impl(28); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000029() { ov_box_box_distance_symmetric_impl(29); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000030() { ov_box_box_distance_symmetric_impl(30); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000031() { ov_box_box_distance_symmetric_impl(31); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000032() { ov_box_box_distance_symmetric_impl(32); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000033() { ov_box_box_distance_symmetric_impl(33); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000034() { ov_box_box_distance_symmetric_impl(34); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000035() { ov_box_box_distance_symmetric_impl(35); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000036() { ov_box_box_distance_symmetric_impl(36); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000037() { ov_box_box_distance_symmetric_impl(37); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000038() { ov_box_box_distance_symmetric_impl(38); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000039() { ov_box_box_distance_symmetric_impl(39); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000040() { ov_box_box_distance_symmetric_impl(40); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000041() { ov_box_box_distance_symmetric_impl(41); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000042() { ov_box_box_distance_symmetric_impl(42); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000043() { ov_box_box_distance_symmetric_impl(43); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000044() { ov_box_box_distance_symmetric_impl(44); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000045() { ov_box_box_distance_symmetric_impl(45); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000046() { ov_box_box_distance_symmetric_impl(46); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000047() { ov_box_box_distance_symmetric_impl(47); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000048() { ov_box_box_distance_symmetric_impl(48); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000049() { ov_box_box_distance_symmetric_impl(49); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000050() { ov_box_box_distance_symmetric_impl(50); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000051() { ov_box_box_distance_symmetric_impl(51); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000052() { ov_box_box_distance_symmetric_impl(52); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000053() { ov_box_box_distance_symmetric_impl(53); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000054() { ov_box_box_distance_symmetric_impl(54); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000055() { ov_box_box_distance_symmetric_impl(55); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000056() { ov_box_box_distance_symmetric_impl(56); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000057() { ov_box_box_distance_symmetric_impl(57); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000058() { ov_box_box_distance_symmetric_impl(58); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000059() { ov_box_box_distance_symmetric_impl(59); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000060() { ov_box_box_distance_symmetric_impl(60); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000061() { ov_box_box_distance_symmetric_impl(61); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000062() { ov_box_box_distance_symmetric_impl(62); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000063() { ov_box_box_distance_symmetric_impl(63); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000064() { ov_box_box_distance_symmetric_impl(64); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000065() { ov_box_box_distance_symmetric_impl(65); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000066() { ov_box_box_distance_symmetric_impl(66); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000067() { ov_box_box_distance_symmetric_impl(67); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000068() { ov_box_box_distance_symmetric_impl(68); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000069() { ov_box_box_distance_symmetric_impl(69); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000070() { ov_box_box_distance_symmetric_impl(70); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000071() { ov_box_box_distance_symmetric_impl(71); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000072() { ov_box_box_distance_symmetric_impl(72); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000073() { ov_box_box_distance_symmetric_impl(73); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000074() { ov_box_box_distance_symmetric_impl(74); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000075() { ov_box_box_distance_symmetric_impl(75); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000076() { ov_box_box_distance_symmetric_impl(76); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000077() { ov_box_box_distance_symmetric_impl(77); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000078() { ov_box_box_distance_symmetric_impl(78); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000079() { ov_box_box_distance_symmetric_impl(79); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000080() { ov_box_box_distance_symmetric_impl(80); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000081() { ov_box_box_distance_symmetric_impl(81); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000082() { ov_box_box_distance_symmetric_impl(82); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000083() { ov_box_box_distance_symmetric_impl(83); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000084() { ov_box_box_distance_symmetric_impl(84); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000085() { ov_box_box_distance_symmetric_impl(85); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000086() { ov_box_box_distance_symmetric_impl(86); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000087() { ov_box_box_distance_symmetric_impl(87); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000088() { ov_box_box_distance_symmetric_impl(88); }
    #[cfg_attr(test, test)]
    fn ov_box_box_distance_symmetric_seed_000089() { ov_box_box_distance_symmetric_impl(89); }
    // --- ov_component_overlap_symmetric: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000000() { ov_component_overlap_symmetric_impl(0); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000001() { ov_component_overlap_symmetric_impl(1); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000002() { ov_component_overlap_symmetric_impl(2); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000003() { ov_component_overlap_symmetric_impl(3); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000004() { ov_component_overlap_symmetric_impl(4); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000005() { ov_component_overlap_symmetric_impl(5); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000006() { ov_component_overlap_symmetric_impl(6); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000007() { ov_component_overlap_symmetric_impl(7); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000008() { ov_component_overlap_symmetric_impl(8); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000009() { ov_component_overlap_symmetric_impl(9); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000010() { ov_component_overlap_symmetric_impl(10); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000011() { ov_component_overlap_symmetric_impl(11); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000012() { ov_component_overlap_symmetric_impl(12); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000013() { ov_component_overlap_symmetric_impl(13); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000014() { ov_component_overlap_symmetric_impl(14); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000015() { ov_component_overlap_symmetric_impl(15); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000016() { ov_component_overlap_symmetric_impl(16); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000017() { ov_component_overlap_symmetric_impl(17); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000018() { ov_component_overlap_symmetric_impl(18); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000019() { ov_component_overlap_symmetric_impl(19); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000020() { ov_component_overlap_symmetric_impl(20); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000021() { ov_component_overlap_symmetric_impl(21); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000022() { ov_component_overlap_symmetric_impl(22); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000023() { ov_component_overlap_symmetric_impl(23); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000024() { ov_component_overlap_symmetric_impl(24); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000025() { ov_component_overlap_symmetric_impl(25); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000026() { ov_component_overlap_symmetric_impl(26); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000027() { ov_component_overlap_symmetric_impl(27); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000028() { ov_component_overlap_symmetric_impl(28); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000029() { ov_component_overlap_symmetric_impl(29); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000030() { ov_component_overlap_symmetric_impl(30); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000031() { ov_component_overlap_symmetric_impl(31); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000032() { ov_component_overlap_symmetric_impl(32); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000033() { ov_component_overlap_symmetric_impl(33); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000034() { ov_component_overlap_symmetric_impl(34); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000035() { ov_component_overlap_symmetric_impl(35); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000036() { ov_component_overlap_symmetric_impl(36); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000037() { ov_component_overlap_symmetric_impl(37); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000038() { ov_component_overlap_symmetric_impl(38); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000039() { ov_component_overlap_symmetric_impl(39); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000040() { ov_component_overlap_symmetric_impl(40); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000041() { ov_component_overlap_symmetric_impl(41); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000042() { ov_component_overlap_symmetric_impl(42); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000043() { ov_component_overlap_symmetric_impl(43); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000044() { ov_component_overlap_symmetric_impl(44); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000045() { ov_component_overlap_symmetric_impl(45); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000046() { ov_component_overlap_symmetric_impl(46); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000047() { ov_component_overlap_symmetric_impl(47); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000048() { ov_component_overlap_symmetric_impl(48); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000049() { ov_component_overlap_symmetric_impl(49); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000050() { ov_component_overlap_symmetric_impl(50); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000051() { ov_component_overlap_symmetric_impl(51); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000052() { ov_component_overlap_symmetric_impl(52); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000053() { ov_component_overlap_symmetric_impl(53); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000054() { ov_component_overlap_symmetric_impl(54); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000055() { ov_component_overlap_symmetric_impl(55); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000056() { ov_component_overlap_symmetric_impl(56); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000057() { ov_component_overlap_symmetric_impl(57); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000058() { ov_component_overlap_symmetric_impl(58); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000059() { ov_component_overlap_symmetric_impl(59); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000060() { ov_component_overlap_symmetric_impl(60); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000061() { ov_component_overlap_symmetric_impl(61); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000062() { ov_component_overlap_symmetric_impl(62); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000063() { ov_component_overlap_symmetric_impl(63); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000064() { ov_component_overlap_symmetric_impl(64); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000065() { ov_component_overlap_symmetric_impl(65); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000066() { ov_component_overlap_symmetric_impl(66); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000067() { ov_component_overlap_symmetric_impl(67); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000068() { ov_component_overlap_symmetric_impl(68); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000069() { ov_component_overlap_symmetric_impl(69); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000070() { ov_component_overlap_symmetric_impl(70); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000071() { ov_component_overlap_symmetric_impl(71); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000072() { ov_component_overlap_symmetric_impl(72); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000073() { ov_component_overlap_symmetric_impl(73); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000074() { ov_component_overlap_symmetric_impl(74); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000075() { ov_component_overlap_symmetric_impl(75); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000076() { ov_component_overlap_symmetric_impl(76); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000077() { ov_component_overlap_symmetric_impl(77); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000078() { ov_component_overlap_symmetric_impl(78); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000079() { ov_component_overlap_symmetric_impl(79); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000080() { ov_component_overlap_symmetric_impl(80); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000081() { ov_component_overlap_symmetric_impl(81); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000082() { ov_component_overlap_symmetric_impl(82); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000083() { ov_component_overlap_symmetric_impl(83); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000084() { ov_component_overlap_symmetric_impl(84); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000085() { ov_component_overlap_symmetric_impl(85); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000086() { ov_component_overlap_symmetric_impl(86); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000087() { ov_component_overlap_symmetric_impl(87); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000088() { ov_component_overlap_symmetric_impl(88); }
    #[cfg_attr(test, test)]
    fn ov_component_overlap_symmetric_seed_000089() { ov_component_overlap_symmetric_impl(89); }
    // --- ov_translation_invariant: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000000() { ov_translation_invariant_impl(0); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000001() { ov_translation_invariant_impl(1); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000002() { ov_translation_invariant_impl(2); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000003() { ov_translation_invariant_impl(3); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000004() { ov_translation_invariant_impl(4); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000005() { ov_translation_invariant_impl(5); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000006() { ov_translation_invariant_impl(6); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000007() { ov_translation_invariant_impl(7); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000008() { ov_translation_invariant_impl(8); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000009() { ov_translation_invariant_impl(9); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000010() { ov_translation_invariant_impl(10); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000011() { ov_translation_invariant_impl(11); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000012() { ov_translation_invariant_impl(12); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000013() { ov_translation_invariant_impl(13); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000014() { ov_translation_invariant_impl(14); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000015() { ov_translation_invariant_impl(15); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000016() { ov_translation_invariant_impl(16); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000017() { ov_translation_invariant_impl(17); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000018() { ov_translation_invariant_impl(18); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000019() { ov_translation_invariant_impl(19); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000020() { ov_translation_invariant_impl(20); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000021() { ov_translation_invariant_impl(21); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000022() { ov_translation_invariant_impl(22); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000023() { ov_translation_invariant_impl(23); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000024() { ov_translation_invariant_impl(24); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000025() { ov_translation_invariant_impl(25); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000026() { ov_translation_invariant_impl(26); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000027() { ov_translation_invariant_impl(27); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000028() { ov_translation_invariant_impl(28); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000029() { ov_translation_invariant_impl(29); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000030() { ov_translation_invariant_impl(30); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000031() { ov_translation_invariant_impl(31); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000032() { ov_translation_invariant_impl(32); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000033() { ov_translation_invariant_impl(33); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000034() { ov_translation_invariant_impl(34); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000035() { ov_translation_invariant_impl(35); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000036() { ov_translation_invariant_impl(36); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000037() { ov_translation_invariant_impl(37); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000038() { ov_translation_invariant_impl(38); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000039() { ov_translation_invariant_impl(39); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000040() { ov_translation_invariant_impl(40); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000041() { ov_translation_invariant_impl(41); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000042() { ov_translation_invariant_impl(42); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000043() { ov_translation_invariant_impl(43); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000044() { ov_translation_invariant_impl(44); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000045() { ov_translation_invariant_impl(45); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000046() { ov_translation_invariant_impl(46); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000047() { ov_translation_invariant_impl(47); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000048() { ov_translation_invariant_impl(48); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000049() { ov_translation_invariant_impl(49); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000050() { ov_translation_invariant_impl(50); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000051() { ov_translation_invariant_impl(51); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000052() { ov_translation_invariant_impl(52); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000053() { ov_translation_invariant_impl(53); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000054() { ov_translation_invariant_impl(54); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000055() { ov_translation_invariant_impl(55); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000056() { ov_translation_invariant_impl(56); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000057() { ov_translation_invariant_impl(57); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000058() { ov_translation_invariant_impl(58); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000059() { ov_translation_invariant_impl(59); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000060() { ov_translation_invariant_impl(60); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000061() { ov_translation_invariant_impl(61); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000062() { ov_translation_invariant_impl(62); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000063() { ov_translation_invariant_impl(63); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000064() { ov_translation_invariant_impl(64); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000065() { ov_translation_invariant_impl(65); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000066() { ov_translation_invariant_impl(66); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000067() { ov_translation_invariant_impl(67); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000068() { ov_translation_invariant_impl(68); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000069() { ov_translation_invariant_impl(69); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000070() { ov_translation_invariant_impl(70); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000071() { ov_translation_invariant_impl(71); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000072() { ov_translation_invariant_impl(72); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000073() { ov_translation_invariant_impl(73); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000074() { ov_translation_invariant_impl(74); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000075() { ov_translation_invariant_impl(75); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000076() { ov_translation_invariant_impl(76); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000077() { ov_translation_invariant_impl(77); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000078() { ov_translation_invariant_impl(78); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000079() { ov_translation_invariant_impl(79); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000080() { ov_translation_invariant_impl(80); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000081() { ov_translation_invariant_impl(81); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000082() { ov_translation_invariant_impl(82); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000083() { ov_translation_invariant_impl(83); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000084() { ov_translation_invariant_impl(84); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000085() { ov_translation_invariant_impl(85); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000086() { ov_translation_invariant_impl(86); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000087() { ov_translation_invariant_impl(87); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000088() { ov_translation_invariant_impl(88); }
    #[cfg_attr(test, test)]
    fn ov_translation_invariant_seed_000089() { ov_translation_invariant_impl(89); }
    // --- ov_self_overlap_total: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000000() { ov_self_overlap_total_impl(0); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000001() { ov_self_overlap_total_impl(1); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000002() { ov_self_overlap_total_impl(2); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000003() { ov_self_overlap_total_impl(3); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000004() { ov_self_overlap_total_impl(4); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000005() { ov_self_overlap_total_impl(5); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000006() { ov_self_overlap_total_impl(6); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000007() { ov_self_overlap_total_impl(7); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000008() { ov_self_overlap_total_impl(8); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000009() { ov_self_overlap_total_impl(9); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000010() { ov_self_overlap_total_impl(10); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000011() { ov_self_overlap_total_impl(11); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000012() { ov_self_overlap_total_impl(12); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000013() { ov_self_overlap_total_impl(13); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000014() { ov_self_overlap_total_impl(14); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000015() { ov_self_overlap_total_impl(15); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000016() { ov_self_overlap_total_impl(16); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000017() { ov_self_overlap_total_impl(17); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000018() { ov_self_overlap_total_impl(18); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000019() { ov_self_overlap_total_impl(19); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000020() { ov_self_overlap_total_impl(20); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000021() { ov_self_overlap_total_impl(21); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000022() { ov_self_overlap_total_impl(22); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000023() { ov_self_overlap_total_impl(23); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000024() { ov_self_overlap_total_impl(24); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000025() { ov_self_overlap_total_impl(25); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000026() { ov_self_overlap_total_impl(26); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000027() { ov_self_overlap_total_impl(27); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000028() { ov_self_overlap_total_impl(28); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000029() { ov_self_overlap_total_impl(29); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000030() { ov_self_overlap_total_impl(30); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000031() { ov_self_overlap_total_impl(31); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000032() { ov_self_overlap_total_impl(32); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000033() { ov_self_overlap_total_impl(33); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000034() { ov_self_overlap_total_impl(34); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000035() { ov_self_overlap_total_impl(35); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000036() { ov_self_overlap_total_impl(36); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000037() { ov_self_overlap_total_impl(37); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000038() { ov_self_overlap_total_impl(38); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000039() { ov_self_overlap_total_impl(39); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000040() { ov_self_overlap_total_impl(40); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000041() { ov_self_overlap_total_impl(41); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000042() { ov_self_overlap_total_impl(42); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000043() { ov_self_overlap_total_impl(43); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000044() { ov_self_overlap_total_impl(44); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000045() { ov_self_overlap_total_impl(45); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000046() { ov_self_overlap_total_impl(46); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000047() { ov_self_overlap_total_impl(47); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000048() { ov_self_overlap_total_impl(48); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000049() { ov_self_overlap_total_impl(49); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000050() { ov_self_overlap_total_impl(50); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000051() { ov_self_overlap_total_impl(51); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000052() { ov_self_overlap_total_impl(52); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000053() { ov_self_overlap_total_impl(53); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000054() { ov_self_overlap_total_impl(54); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000055() { ov_self_overlap_total_impl(55); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000056() { ov_self_overlap_total_impl(56); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000057() { ov_self_overlap_total_impl(57); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000058() { ov_self_overlap_total_impl(58); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000059() { ov_self_overlap_total_impl(59); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000060() { ov_self_overlap_total_impl(60); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000061() { ov_self_overlap_total_impl(61); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000062() { ov_self_overlap_total_impl(62); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000063() { ov_self_overlap_total_impl(63); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000064() { ov_self_overlap_total_impl(64); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000065() { ov_self_overlap_total_impl(65); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000066() { ov_self_overlap_total_impl(66); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000067() { ov_self_overlap_total_impl(67); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000068() { ov_self_overlap_total_impl(68); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000069() { ov_self_overlap_total_impl(69); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000070() { ov_self_overlap_total_impl(70); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000071() { ov_self_overlap_total_impl(71); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000072() { ov_self_overlap_total_impl(72); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000073() { ov_self_overlap_total_impl(73); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000074() { ov_self_overlap_total_impl(74); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000075() { ov_self_overlap_total_impl(75); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000076() { ov_self_overlap_total_impl(76); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000077() { ov_self_overlap_total_impl(77); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000078() { ov_self_overlap_total_impl(78); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000079() { ov_self_overlap_total_impl(79); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000080() { ov_self_overlap_total_impl(80); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000081() { ov_self_overlap_total_impl(81); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000082() { ov_self_overlap_total_impl(82); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000083() { ov_self_overlap_total_impl(83); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000084() { ov_self_overlap_total_impl(84); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000085() { ov_self_overlap_total_impl(85); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000086() { ov_self_overlap_total_impl(86); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000087() { ov_self_overlap_total_impl(87); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000088() { ov_self_overlap_total_impl(88); }
    #[cfg_attr(test, test)]
    fn ov_self_overlap_total_seed_000089() { ov_self_overlap_total_impl(89); }
    // --- ov_self_distance_exact: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000000() { ov_self_distance_exact_impl(0); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000001() { ov_self_distance_exact_impl(1); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000002() { ov_self_distance_exact_impl(2); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000003() { ov_self_distance_exact_impl(3); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000004() { ov_self_distance_exact_impl(4); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000005() { ov_self_distance_exact_impl(5); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000006() { ov_self_distance_exact_impl(6); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000007() { ov_self_distance_exact_impl(7); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000008() { ov_self_distance_exact_impl(8); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000009() { ov_self_distance_exact_impl(9); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000010() { ov_self_distance_exact_impl(10); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000011() { ov_self_distance_exact_impl(11); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000012() { ov_self_distance_exact_impl(12); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000013() { ov_self_distance_exact_impl(13); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000014() { ov_self_distance_exact_impl(14); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000015() { ov_self_distance_exact_impl(15); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000016() { ov_self_distance_exact_impl(16); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000017() { ov_self_distance_exact_impl(17); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000018() { ov_self_distance_exact_impl(18); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000019() { ov_self_distance_exact_impl(19); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000020() { ov_self_distance_exact_impl(20); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000021() { ov_self_distance_exact_impl(21); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000022() { ov_self_distance_exact_impl(22); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000023() { ov_self_distance_exact_impl(23); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000024() { ov_self_distance_exact_impl(24); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000025() { ov_self_distance_exact_impl(25); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000026() { ov_self_distance_exact_impl(26); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000027() { ov_self_distance_exact_impl(27); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000028() { ov_self_distance_exact_impl(28); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000029() { ov_self_distance_exact_impl(29); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000030() { ov_self_distance_exact_impl(30); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000031() { ov_self_distance_exact_impl(31); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000032() { ov_self_distance_exact_impl(32); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000033() { ov_self_distance_exact_impl(33); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000034() { ov_self_distance_exact_impl(34); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000035() { ov_self_distance_exact_impl(35); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000036() { ov_self_distance_exact_impl(36); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000037() { ov_self_distance_exact_impl(37); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000038() { ov_self_distance_exact_impl(38); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000039() { ov_self_distance_exact_impl(39); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000040() { ov_self_distance_exact_impl(40); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000041() { ov_self_distance_exact_impl(41); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000042() { ov_self_distance_exact_impl(42); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000043() { ov_self_distance_exact_impl(43); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000044() { ov_self_distance_exact_impl(44); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000045() { ov_self_distance_exact_impl(45); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000046() { ov_self_distance_exact_impl(46); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000047() { ov_self_distance_exact_impl(47); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000048() { ov_self_distance_exact_impl(48); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000049() { ov_self_distance_exact_impl(49); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000050() { ov_self_distance_exact_impl(50); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000051() { ov_self_distance_exact_impl(51); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000052() { ov_self_distance_exact_impl(52); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000053() { ov_self_distance_exact_impl(53); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000054() { ov_self_distance_exact_impl(54); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000055() { ov_self_distance_exact_impl(55); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000056() { ov_self_distance_exact_impl(56); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000057() { ov_self_distance_exact_impl(57); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000058() { ov_self_distance_exact_impl(58); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000059() { ov_self_distance_exact_impl(59); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000060() { ov_self_distance_exact_impl(60); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000061() { ov_self_distance_exact_impl(61); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000062() { ov_self_distance_exact_impl(62); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000063() { ov_self_distance_exact_impl(63); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000064() { ov_self_distance_exact_impl(64); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000065() { ov_self_distance_exact_impl(65); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000066() { ov_self_distance_exact_impl(66); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000067() { ov_self_distance_exact_impl(67); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000068() { ov_self_distance_exact_impl(68); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000069() { ov_self_distance_exact_impl(69); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000070() { ov_self_distance_exact_impl(70); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000071() { ov_self_distance_exact_impl(71); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000072() { ov_self_distance_exact_impl(72); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000073() { ov_self_distance_exact_impl(73); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000074() { ov_self_distance_exact_impl(74); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000075() { ov_self_distance_exact_impl(75); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000076() { ov_self_distance_exact_impl(76); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000077() { ov_self_distance_exact_impl(77); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000078() { ov_self_distance_exact_impl(78); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000079() { ov_self_distance_exact_impl(79); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000080() { ov_self_distance_exact_impl(80); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000081() { ov_self_distance_exact_impl(81); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000082() { ov_self_distance_exact_impl(82); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000083() { ov_self_distance_exact_impl(83); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000084() { ov_self_distance_exact_impl(84); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000085() { ov_self_distance_exact_impl(85); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000086() { ov_self_distance_exact_impl(86); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000087() { ov_self_distance_exact_impl(87); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000088() { ov_self_distance_exact_impl(88); }
    #[cfg_attr(test, test)]
    fn ov_self_distance_exact_seed_000089() { ov_self_distance_exact_impl(89); }
    // --- ov_separation_monotonic: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000000() { ov_separation_monotonic_impl(0); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000001() { ov_separation_monotonic_impl(1); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000002() { ov_separation_monotonic_impl(2); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000003() { ov_separation_monotonic_impl(3); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000004() { ov_separation_monotonic_impl(4); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000005() { ov_separation_monotonic_impl(5); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000006() { ov_separation_monotonic_impl(6); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000007() { ov_separation_monotonic_impl(7); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000008() { ov_separation_monotonic_impl(8); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000009() { ov_separation_monotonic_impl(9); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000010() { ov_separation_monotonic_impl(10); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000011() { ov_separation_monotonic_impl(11); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000012() { ov_separation_monotonic_impl(12); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000013() { ov_separation_monotonic_impl(13); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000014() { ov_separation_monotonic_impl(14); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000015() { ov_separation_monotonic_impl(15); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000016() { ov_separation_monotonic_impl(16); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000017() { ov_separation_monotonic_impl(17); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000018() { ov_separation_monotonic_impl(18); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000019() { ov_separation_monotonic_impl(19); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000020() { ov_separation_monotonic_impl(20); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000021() { ov_separation_monotonic_impl(21); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000022() { ov_separation_monotonic_impl(22); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000023() { ov_separation_monotonic_impl(23); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000024() { ov_separation_monotonic_impl(24); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000025() { ov_separation_monotonic_impl(25); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000026() { ov_separation_monotonic_impl(26); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000027() { ov_separation_monotonic_impl(27); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000028() { ov_separation_monotonic_impl(28); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000029() { ov_separation_monotonic_impl(29); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000030() { ov_separation_monotonic_impl(30); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000031() { ov_separation_monotonic_impl(31); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000032() { ov_separation_monotonic_impl(32); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000033() { ov_separation_monotonic_impl(33); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000034() { ov_separation_monotonic_impl(34); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000035() { ov_separation_monotonic_impl(35); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000036() { ov_separation_monotonic_impl(36); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000037() { ov_separation_monotonic_impl(37); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000038() { ov_separation_monotonic_impl(38); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000039() { ov_separation_monotonic_impl(39); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000040() { ov_separation_monotonic_impl(40); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000041() { ov_separation_monotonic_impl(41); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000042() { ov_separation_monotonic_impl(42); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000043() { ov_separation_monotonic_impl(43); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000044() { ov_separation_monotonic_impl(44); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000045() { ov_separation_monotonic_impl(45); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000046() { ov_separation_monotonic_impl(46); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000047() { ov_separation_monotonic_impl(47); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000048() { ov_separation_monotonic_impl(48); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000049() { ov_separation_monotonic_impl(49); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000050() { ov_separation_monotonic_impl(50); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000051() { ov_separation_monotonic_impl(51); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000052() { ov_separation_monotonic_impl(52); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000053() { ov_separation_monotonic_impl(53); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000054() { ov_separation_monotonic_impl(54); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000055() { ov_separation_monotonic_impl(55); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000056() { ov_separation_monotonic_impl(56); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000057() { ov_separation_monotonic_impl(57); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000058() { ov_separation_monotonic_impl(58); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000059() { ov_separation_monotonic_impl(59); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000060() { ov_separation_monotonic_impl(60); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000061() { ov_separation_monotonic_impl(61); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000062() { ov_separation_monotonic_impl(62); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000063() { ov_separation_monotonic_impl(63); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000064() { ov_separation_monotonic_impl(64); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000065() { ov_separation_monotonic_impl(65); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000066() { ov_separation_monotonic_impl(66); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000067() { ov_separation_monotonic_impl(67); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000068() { ov_separation_monotonic_impl(68); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000069() { ov_separation_monotonic_impl(69); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000070() { ov_separation_monotonic_impl(70); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000071() { ov_separation_monotonic_impl(71); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000072() { ov_separation_monotonic_impl(72); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000073() { ov_separation_monotonic_impl(73); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000074() { ov_separation_monotonic_impl(74); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000075() { ov_separation_monotonic_impl(75); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000076() { ov_separation_monotonic_impl(76); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000077() { ov_separation_monotonic_impl(77); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000078() { ov_separation_monotonic_impl(78); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000079() { ov_separation_monotonic_impl(79); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000080() { ov_separation_monotonic_impl(80); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000081() { ov_separation_monotonic_impl(81); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000082() { ov_separation_monotonic_impl(82); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000083() { ov_separation_monotonic_impl(83); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000084() { ov_separation_monotonic_impl(84); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000085() { ov_separation_monotonic_impl(85); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000086() { ov_separation_monotonic_impl(86); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000087() { ov_separation_monotonic_impl(87); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000088() { ov_separation_monotonic_impl(88); }
    #[cfg_attr(test, test)]
    fn ov_separation_monotonic_seed_000089() { ov_separation_monotonic_impl(89); }
    // --- pj_board_idempotent_and_feasible: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000000() { pj_board_idempotent_and_feasible_impl(0); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000001() { pj_board_idempotent_and_feasible_impl(1); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000002() { pj_board_idempotent_and_feasible_impl(2); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000003() { pj_board_idempotent_and_feasible_impl(3); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000004() { pj_board_idempotent_and_feasible_impl(4); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000005() { pj_board_idempotent_and_feasible_impl(5); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000006() { pj_board_idempotent_and_feasible_impl(6); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000007() { pj_board_idempotent_and_feasible_impl(7); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000008() { pj_board_idempotent_and_feasible_impl(8); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000009() { pj_board_idempotent_and_feasible_impl(9); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000010() { pj_board_idempotent_and_feasible_impl(10); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000011() { pj_board_idempotent_and_feasible_impl(11); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000012() { pj_board_idempotent_and_feasible_impl(12); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000013() { pj_board_idempotent_and_feasible_impl(13); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000014() { pj_board_idempotent_and_feasible_impl(14); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000015() { pj_board_idempotent_and_feasible_impl(15); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000016() { pj_board_idempotent_and_feasible_impl(16); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000017() { pj_board_idempotent_and_feasible_impl(17); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000018() { pj_board_idempotent_and_feasible_impl(18); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000019() { pj_board_idempotent_and_feasible_impl(19); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000020() { pj_board_idempotent_and_feasible_impl(20); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000021() { pj_board_idempotent_and_feasible_impl(21); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000022() { pj_board_idempotent_and_feasible_impl(22); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000023() { pj_board_idempotent_and_feasible_impl(23); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000024() { pj_board_idempotent_and_feasible_impl(24); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000025() { pj_board_idempotent_and_feasible_impl(25); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000026() { pj_board_idempotent_and_feasible_impl(26); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000027() { pj_board_idempotent_and_feasible_impl(27); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000028() { pj_board_idempotent_and_feasible_impl(28); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000029() { pj_board_idempotent_and_feasible_impl(29); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000030() { pj_board_idempotent_and_feasible_impl(30); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000031() { pj_board_idempotent_and_feasible_impl(31); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000032() { pj_board_idempotent_and_feasible_impl(32); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000033() { pj_board_idempotent_and_feasible_impl(33); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000034() { pj_board_idempotent_and_feasible_impl(34); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000035() { pj_board_idempotent_and_feasible_impl(35); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000036() { pj_board_idempotent_and_feasible_impl(36); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000037() { pj_board_idempotent_and_feasible_impl(37); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000038() { pj_board_idempotent_and_feasible_impl(38); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000039() { pj_board_idempotent_and_feasible_impl(39); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000040() { pj_board_idempotent_and_feasible_impl(40); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000041() { pj_board_idempotent_and_feasible_impl(41); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000042() { pj_board_idempotent_and_feasible_impl(42); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000043() { pj_board_idempotent_and_feasible_impl(43); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000044() { pj_board_idempotent_and_feasible_impl(44); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000045() { pj_board_idempotent_and_feasible_impl(45); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000046() { pj_board_idempotent_and_feasible_impl(46); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000047() { pj_board_idempotent_and_feasible_impl(47); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000048() { pj_board_idempotent_and_feasible_impl(48); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000049() { pj_board_idempotent_and_feasible_impl(49); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000050() { pj_board_idempotent_and_feasible_impl(50); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000051() { pj_board_idempotent_and_feasible_impl(51); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000052() { pj_board_idempotent_and_feasible_impl(52); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000053() { pj_board_idempotent_and_feasible_impl(53); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000054() { pj_board_idempotent_and_feasible_impl(54); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000055() { pj_board_idempotent_and_feasible_impl(55); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000056() { pj_board_idempotent_and_feasible_impl(56); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000057() { pj_board_idempotent_and_feasible_impl(57); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000058() { pj_board_idempotent_and_feasible_impl(58); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000059() { pj_board_idempotent_and_feasible_impl(59); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000060() { pj_board_idempotent_and_feasible_impl(60); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000061() { pj_board_idempotent_and_feasible_impl(61); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000062() { pj_board_idempotent_and_feasible_impl(62); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000063() { pj_board_idempotent_and_feasible_impl(63); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000064() { pj_board_idempotent_and_feasible_impl(64); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000065() { pj_board_idempotent_and_feasible_impl(65); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000066() { pj_board_idempotent_and_feasible_impl(66); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000067() { pj_board_idempotent_and_feasible_impl(67); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000068() { pj_board_idempotent_and_feasible_impl(68); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000069() { pj_board_idempotent_and_feasible_impl(69); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000070() { pj_board_idempotent_and_feasible_impl(70); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000071() { pj_board_idempotent_and_feasible_impl(71); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000072() { pj_board_idempotent_and_feasible_impl(72); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000073() { pj_board_idempotent_and_feasible_impl(73); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000074() { pj_board_idempotent_and_feasible_impl(74); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000075() { pj_board_idempotent_and_feasible_impl(75); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000076() { pj_board_idempotent_and_feasible_impl(76); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000077() { pj_board_idempotent_and_feasible_impl(77); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000078() { pj_board_idempotent_and_feasible_impl(78); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000079() { pj_board_idempotent_and_feasible_impl(79); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000080() { pj_board_idempotent_and_feasible_impl(80); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000081() { pj_board_idempotent_and_feasible_impl(81); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000082() { pj_board_idempotent_and_feasible_impl(82); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000083() { pj_board_idempotent_and_feasible_impl(83); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000084() { pj_board_idempotent_and_feasible_impl(84); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000085() { pj_board_idempotent_and_feasible_impl(85); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000086() { pj_board_idempotent_and_feasible_impl(86); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000087() { pj_board_idempotent_and_feasible_impl(87); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000088() { pj_board_idempotent_and_feasible_impl(88); }
    #[cfg_attr(test, test)]
    fn pj_board_idempotent_and_feasible_seed_000089() { pj_board_idempotent_and_feasible_impl(89); }
    // --- pj_zone_idempotent_and_feasible: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000000() { pj_zone_idempotent_and_feasible_impl(0); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000001() { pj_zone_idempotent_and_feasible_impl(1); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000002() { pj_zone_idempotent_and_feasible_impl(2); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000003() { pj_zone_idempotent_and_feasible_impl(3); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000004() { pj_zone_idempotent_and_feasible_impl(4); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000005() { pj_zone_idempotent_and_feasible_impl(5); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000006() { pj_zone_idempotent_and_feasible_impl(6); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000007() { pj_zone_idempotent_and_feasible_impl(7); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000008() { pj_zone_idempotent_and_feasible_impl(8); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000009() { pj_zone_idempotent_and_feasible_impl(9); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000010() { pj_zone_idempotent_and_feasible_impl(10); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000011() { pj_zone_idempotent_and_feasible_impl(11); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000012() { pj_zone_idempotent_and_feasible_impl(12); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000013() { pj_zone_idempotent_and_feasible_impl(13); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000014() { pj_zone_idempotent_and_feasible_impl(14); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000015() { pj_zone_idempotent_and_feasible_impl(15); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000016() { pj_zone_idempotent_and_feasible_impl(16); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000017() { pj_zone_idempotent_and_feasible_impl(17); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000018() { pj_zone_idempotent_and_feasible_impl(18); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000019() { pj_zone_idempotent_and_feasible_impl(19); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000020() { pj_zone_idempotent_and_feasible_impl(20); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000021() { pj_zone_idempotent_and_feasible_impl(21); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000022() { pj_zone_idempotent_and_feasible_impl(22); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000023() { pj_zone_idempotent_and_feasible_impl(23); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000024() { pj_zone_idempotent_and_feasible_impl(24); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000025() { pj_zone_idempotent_and_feasible_impl(25); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000026() { pj_zone_idempotent_and_feasible_impl(26); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000027() { pj_zone_idempotent_and_feasible_impl(27); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000028() { pj_zone_idempotent_and_feasible_impl(28); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000029() { pj_zone_idempotent_and_feasible_impl(29); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000030() { pj_zone_idempotent_and_feasible_impl(30); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000031() { pj_zone_idempotent_and_feasible_impl(31); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000032() { pj_zone_idempotent_and_feasible_impl(32); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000033() { pj_zone_idempotent_and_feasible_impl(33); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000034() { pj_zone_idempotent_and_feasible_impl(34); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000035() { pj_zone_idempotent_and_feasible_impl(35); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000036() { pj_zone_idempotent_and_feasible_impl(36); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000037() { pj_zone_idempotent_and_feasible_impl(37); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000038() { pj_zone_idempotent_and_feasible_impl(38); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000039() { pj_zone_idempotent_and_feasible_impl(39); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000040() { pj_zone_idempotent_and_feasible_impl(40); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000041() { pj_zone_idempotent_and_feasible_impl(41); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000042() { pj_zone_idempotent_and_feasible_impl(42); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000043() { pj_zone_idempotent_and_feasible_impl(43); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000044() { pj_zone_idempotent_and_feasible_impl(44); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000045() { pj_zone_idempotent_and_feasible_impl(45); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000046() { pj_zone_idempotent_and_feasible_impl(46); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000047() { pj_zone_idempotent_and_feasible_impl(47); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000048() { pj_zone_idempotent_and_feasible_impl(48); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000049() { pj_zone_idempotent_and_feasible_impl(49); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000050() { pj_zone_idempotent_and_feasible_impl(50); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000051() { pj_zone_idempotent_and_feasible_impl(51); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000052() { pj_zone_idempotent_and_feasible_impl(52); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000053() { pj_zone_idempotent_and_feasible_impl(53); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000054() { pj_zone_idempotent_and_feasible_impl(54); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000055() { pj_zone_idempotent_and_feasible_impl(55); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000056() { pj_zone_idempotent_and_feasible_impl(56); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000057() { pj_zone_idempotent_and_feasible_impl(57); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000058() { pj_zone_idempotent_and_feasible_impl(58); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000059() { pj_zone_idempotent_and_feasible_impl(59); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000060() { pj_zone_idempotent_and_feasible_impl(60); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000061() { pj_zone_idempotent_and_feasible_impl(61); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000062() { pj_zone_idempotent_and_feasible_impl(62); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000063() { pj_zone_idempotent_and_feasible_impl(63); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000064() { pj_zone_idempotent_and_feasible_impl(64); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000065() { pj_zone_idempotent_and_feasible_impl(65); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000066() { pj_zone_idempotent_and_feasible_impl(66); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000067() { pj_zone_idempotent_and_feasible_impl(67); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000068() { pj_zone_idempotent_and_feasible_impl(68); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000069() { pj_zone_idempotent_and_feasible_impl(69); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000070() { pj_zone_idempotent_and_feasible_impl(70); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000071() { pj_zone_idempotent_and_feasible_impl(71); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000072() { pj_zone_idempotent_and_feasible_impl(72); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000073() { pj_zone_idempotent_and_feasible_impl(73); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000074() { pj_zone_idempotent_and_feasible_impl(74); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000075() { pj_zone_idempotent_and_feasible_impl(75); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000076() { pj_zone_idempotent_and_feasible_impl(76); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000077() { pj_zone_idempotent_and_feasible_impl(77); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000078() { pj_zone_idempotent_and_feasible_impl(78); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000079() { pj_zone_idempotent_and_feasible_impl(79); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000080() { pj_zone_idempotent_and_feasible_impl(80); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000081() { pj_zone_idempotent_and_feasible_impl(81); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000082() { pj_zone_idempotent_and_feasible_impl(82); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000083() { pj_zone_idempotent_and_feasible_impl(83); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000084() { pj_zone_idempotent_and_feasible_impl(84); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000085() { pj_zone_idempotent_and_feasible_impl(85); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000086() { pj_zone_idempotent_and_feasible_impl(86); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000087() { pj_zone_idempotent_and_feasible_impl(87); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000088() { pj_zone_idempotent_and_feasible_impl(88); }
    #[cfg_attr(test, test)]
    fn pj_zone_idempotent_and_feasible_seed_000089() { pj_zone_idempotent_and_feasible_impl(89); }
    // --- pj_half_plane_feasible_and_idempotent: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000000() { pj_half_plane_feasible_and_idempotent_impl(0); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000001() { pj_half_plane_feasible_and_idempotent_impl(1); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000002() { pj_half_plane_feasible_and_idempotent_impl(2); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000003() { pj_half_plane_feasible_and_idempotent_impl(3); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000004() { pj_half_plane_feasible_and_idempotent_impl(4); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000005() { pj_half_plane_feasible_and_idempotent_impl(5); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000006() { pj_half_plane_feasible_and_idempotent_impl(6); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000007() { pj_half_plane_feasible_and_idempotent_impl(7); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000008() { pj_half_plane_feasible_and_idempotent_impl(8); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000009() { pj_half_plane_feasible_and_idempotent_impl(9); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000010() { pj_half_plane_feasible_and_idempotent_impl(10); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000011() { pj_half_plane_feasible_and_idempotent_impl(11); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000012() { pj_half_plane_feasible_and_idempotent_impl(12); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000013() { pj_half_plane_feasible_and_idempotent_impl(13); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000014() { pj_half_plane_feasible_and_idempotent_impl(14); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000015() { pj_half_plane_feasible_and_idempotent_impl(15); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000016() { pj_half_plane_feasible_and_idempotent_impl(16); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000017() { pj_half_plane_feasible_and_idempotent_impl(17); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000018() { pj_half_plane_feasible_and_idempotent_impl(18); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000019() { pj_half_plane_feasible_and_idempotent_impl(19); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000020() { pj_half_plane_feasible_and_idempotent_impl(20); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000021() { pj_half_plane_feasible_and_idempotent_impl(21); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000022() { pj_half_plane_feasible_and_idempotent_impl(22); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000023() { pj_half_plane_feasible_and_idempotent_impl(23); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000024() { pj_half_plane_feasible_and_idempotent_impl(24); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000025() { pj_half_plane_feasible_and_idempotent_impl(25); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000026() { pj_half_plane_feasible_and_idempotent_impl(26); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000027() { pj_half_plane_feasible_and_idempotent_impl(27); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000028() { pj_half_plane_feasible_and_idempotent_impl(28); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000029() { pj_half_plane_feasible_and_idempotent_impl(29); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000030() { pj_half_plane_feasible_and_idempotent_impl(30); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000031() { pj_half_plane_feasible_and_idempotent_impl(31); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000032() { pj_half_plane_feasible_and_idempotent_impl(32); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000033() { pj_half_plane_feasible_and_idempotent_impl(33); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000034() { pj_half_plane_feasible_and_idempotent_impl(34); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000035() { pj_half_plane_feasible_and_idempotent_impl(35); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000036() { pj_half_plane_feasible_and_idempotent_impl(36); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000037() { pj_half_plane_feasible_and_idempotent_impl(37); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000038() { pj_half_plane_feasible_and_idempotent_impl(38); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000039() { pj_half_plane_feasible_and_idempotent_impl(39); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000040() { pj_half_plane_feasible_and_idempotent_impl(40); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000041() { pj_half_plane_feasible_and_idempotent_impl(41); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000042() { pj_half_plane_feasible_and_idempotent_impl(42); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000043() { pj_half_plane_feasible_and_idempotent_impl(43); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000044() { pj_half_plane_feasible_and_idempotent_impl(44); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000045() { pj_half_plane_feasible_and_idempotent_impl(45); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000046() { pj_half_plane_feasible_and_idempotent_impl(46); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000047() { pj_half_plane_feasible_and_idempotent_impl(47); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000048() { pj_half_plane_feasible_and_idempotent_impl(48); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000049() { pj_half_plane_feasible_and_idempotent_impl(49); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000050() { pj_half_plane_feasible_and_idempotent_impl(50); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000051() { pj_half_plane_feasible_and_idempotent_impl(51); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000052() { pj_half_plane_feasible_and_idempotent_impl(52); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000053() { pj_half_plane_feasible_and_idempotent_impl(53); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000054() { pj_half_plane_feasible_and_idempotent_impl(54); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000055() { pj_half_plane_feasible_and_idempotent_impl(55); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000056() { pj_half_plane_feasible_and_idempotent_impl(56); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000057() { pj_half_plane_feasible_and_idempotent_impl(57); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000058() { pj_half_plane_feasible_and_idempotent_impl(58); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000059() { pj_half_plane_feasible_and_idempotent_impl(59); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000060() { pj_half_plane_feasible_and_idempotent_impl(60); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000061() { pj_half_plane_feasible_and_idempotent_impl(61); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000062() { pj_half_plane_feasible_and_idempotent_impl(62); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000063() { pj_half_plane_feasible_and_idempotent_impl(63); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000064() { pj_half_plane_feasible_and_idempotent_impl(64); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000065() { pj_half_plane_feasible_and_idempotent_impl(65); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000066() { pj_half_plane_feasible_and_idempotent_impl(66); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000067() { pj_half_plane_feasible_and_idempotent_impl(67); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000068() { pj_half_plane_feasible_and_idempotent_impl(68); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000069() { pj_half_plane_feasible_and_idempotent_impl(69); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000070() { pj_half_plane_feasible_and_idempotent_impl(70); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000071() { pj_half_plane_feasible_and_idempotent_impl(71); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000072() { pj_half_plane_feasible_and_idempotent_impl(72); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000073() { pj_half_plane_feasible_and_idempotent_impl(73); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000074() { pj_half_plane_feasible_and_idempotent_impl(74); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000075() { pj_half_plane_feasible_and_idempotent_impl(75); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000076() { pj_half_plane_feasible_and_idempotent_impl(76); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000077() { pj_half_plane_feasible_and_idempotent_impl(77); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000078() { pj_half_plane_feasible_and_idempotent_impl(78); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000079() { pj_half_plane_feasible_and_idempotent_impl(79); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000080() { pj_half_plane_feasible_and_idempotent_impl(80); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000081() { pj_half_plane_feasible_and_idempotent_impl(81); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000082() { pj_half_plane_feasible_and_idempotent_impl(82); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000083() { pj_half_plane_feasible_and_idempotent_impl(83); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000084() { pj_half_plane_feasible_and_idempotent_impl(84); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000085() { pj_half_plane_feasible_and_idempotent_impl(85); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000086() { pj_half_plane_feasible_and_idempotent_impl(86); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000087() { pj_half_plane_feasible_and_idempotent_impl(87); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000088() { pj_half_plane_feasible_and_idempotent_impl(88); }
    #[cfg_attr(test, test)]
    fn pj_half_plane_feasible_and_idempotent_seed_000089() { pj_half_plane_feasible_and_idempotent_impl(89); }
    // --- pj_keepout_feasible_and_idempotent: 90 generated seeds ---
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000000() { pj_keepout_feasible_and_idempotent_impl(0); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000001() { pj_keepout_feasible_and_idempotent_impl(1); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000002() { pj_keepout_feasible_and_idempotent_impl(2); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000003() { pj_keepout_feasible_and_idempotent_impl(3); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000004() { pj_keepout_feasible_and_idempotent_impl(4); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000005() { pj_keepout_feasible_and_idempotent_impl(5); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000006() { pj_keepout_feasible_and_idempotent_impl(6); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000007() { pj_keepout_feasible_and_idempotent_impl(7); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000008() { pj_keepout_feasible_and_idempotent_impl(8); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000009() { pj_keepout_feasible_and_idempotent_impl(9); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000010() { pj_keepout_feasible_and_idempotent_impl(10); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000011() { pj_keepout_feasible_and_idempotent_impl(11); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000012() { pj_keepout_feasible_and_idempotent_impl(12); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000013() { pj_keepout_feasible_and_idempotent_impl(13); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000014() { pj_keepout_feasible_and_idempotent_impl(14); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000015() { pj_keepout_feasible_and_idempotent_impl(15); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000016() { pj_keepout_feasible_and_idempotent_impl(16); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000017() { pj_keepout_feasible_and_idempotent_impl(17); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000018() { pj_keepout_feasible_and_idempotent_impl(18); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000019() { pj_keepout_feasible_and_idempotent_impl(19); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000020() { pj_keepout_feasible_and_idempotent_impl(20); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000021() { pj_keepout_feasible_and_idempotent_impl(21); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000022() { pj_keepout_feasible_and_idempotent_impl(22); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000023() { pj_keepout_feasible_and_idempotent_impl(23); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000024() { pj_keepout_feasible_and_idempotent_impl(24); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000025() { pj_keepout_feasible_and_idempotent_impl(25); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000026() { pj_keepout_feasible_and_idempotent_impl(26); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000027() { pj_keepout_feasible_and_idempotent_impl(27); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000028() { pj_keepout_feasible_and_idempotent_impl(28); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000029() { pj_keepout_feasible_and_idempotent_impl(29); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000030() { pj_keepout_feasible_and_idempotent_impl(30); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000031() { pj_keepout_feasible_and_idempotent_impl(31); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000032() { pj_keepout_feasible_and_idempotent_impl(32); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000033() { pj_keepout_feasible_and_idempotent_impl(33); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000034() { pj_keepout_feasible_and_idempotent_impl(34); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000035() { pj_keepout_feasible_and_idempotent_impl(35); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000036() { pj_keepout_feasible_and_idempotent_impl(36); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000037() { pj_keepout_feasible_and_idempotent_impl(37); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000038() { pj_keepout_feasible_and_idempotent_impl(38); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000039() { pj_keepout_feasible_and_idempotent_impl(39); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000040() { pj_keepout_feasible_and_idempotent_impl(40); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000041() { pj_keepout_feasible_and_idempotent_impl(41); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000042() { pj_keepout_feasible_and_idempotent_impl(42); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000043() { pj_keepout_feasible_and_idempotent_impl(43); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000044() { pj_keepout_feasible_and_idempotent_impl(44); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000045() { pj_keepout_feasible_and_idempotent_impl(45); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000046() { pj_keepout_feasible_and_idempotent_impl(46); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000047() { pj_keepout_feasible_and_idempotent_impl(47); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000048() { pj_keepout_feasible_and_idempotent_impl(48); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000049() { pj_keepout_feasible_and_idempotent_impl(49); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000050() { pj_keepout_feasible_and_idempotent_impl(50); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000051() { pj_keepout_feasible_and_idempotent_impl(51); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000052() { pj_keepout_feasible_and_idempotent_impl(52); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000053() { pj_keepout_feasible_and_idempotent_impl(53); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000054() { pj_keepout_feasible_and_idempotent_impl(54); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000055() { pj_keepout_feasible_and_idempotent_impl(55); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000056() { pj_keepout_feasible_and_idempotent_impl(56); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000057() { pj_keepout_feasible_and_idempotent_impl(57); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000058() { pj_keepout_feasible_and_idempotent_impl(58); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000059() { pj_keepout_feasible_and_idempotent_impl(59); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000060() { pj_keepout_feasible_and_idempotent_impl(60); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000061() { pj_keepout_feasible_and_idempotent_impl(61); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000062() { pj_keepout_feasible_and_idempotent_impl(62); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000063() { pj_keepout_feasible_and_idempotent_impl(63); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000064() { pj_keepout_feasible_and_idempotent_impl(64); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000065() { pj_keepout_feasible_and_idempotent_impl(65); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000066() { pj_keepout_feasible_and_idempotent_impl(66); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000067() { pj_keepout_feasible_and_idempotent_impl(67); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000068() { pj_keepout_feasible_and_idempotent_impl(68); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000069() { pj_keepout_feasible_and_idempotent_impl(69); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000070() { pj_keepout_feasible_and_idempotent_impl(70); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000071() { pj_keepout_feasible_and_idempotent_impl(71); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000072() { pj_keepout_feasible_and_idempotent_impl(72); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000073() { pj_keepout_feasible_and_idempotent_impl(73); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000074() { pj_keepout_feasible_and_idempotent_impl(74); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000075() { pj_keepout_feasible_and_idempotent_impl(75); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000076() { pj_keepout_feasible_and_idempotent_impl(76); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000077() { pj_keepout_feasible_and_idempotent_impl(77); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000078() { pj_keepout_feasible_and_idempotent_impl(78); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000079() { pj_keepout_feasible_and_idempotent_impl(79); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000080() { pj_keepout_feasible_and_idempotent_impl(80); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000081() { pj_keepout_feasible_and_idempotent_impl(81); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000082() { pj_keepout_feasible_and_idempotent_impl(82); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000083() { pj_keepout_feasible_and_idempotent_impl(83); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000084() { pj_keepout_feasible_and_idempotent_impl(84); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000085() { pj_keepout_feasible_and_idempotent_impl(85); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000086() { pj_keepout_feasible_and_idempotent_impl(86); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000087() { pj_keepout_feasible_and_idempotent_impl(87); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000088() { pj_keepout_feasible_and_idempotent_impl(88); }
    #[cfg_attr(test, test)]
    fn pj_keepout_feasible_and_idempotent_seed_000089() { pj_keepout_feasible_and_idempotent_impl(89); }

    // --- END generated seeded property wrappers ---

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("property_campaigns_2::tests::splitmix64_is_deterministic_in_seed", splitmix64_is_deterministic_in_seed),
        ("property_campaigns_2::tests::splitmix64_varies_with_seed", splitmix64_varies_with_seed),
        ("property_campaigns_2::tests::gen_convex_polygon_vertex_count_in_range", gen_convex_polygon_vertex_count_in_range),
        ("property_campaigns_2::tests::gen_convex_polygon_is_actually_convex_and_encloses_its_center", gen_convex_polygon_is_actually_convex_and_encloses_its_center),
        ("property_campaigns_2::tests::ov_generators_produce_positive_area_shapes", ov_generators_produce_positive_area_shapes),
        ("property_campaigns_2::tests::pg_arbitrary_polygon_vertex_count_in_range", pg_arbitrary_polygon_vertex_count_in_range),
        ("property_campaigns_2::tests::sdf_gen_circle_radius_is_positive", sdf_gen_circle_radius_is_positive),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000000", sdf_circle_sign_and_boundary_seed_000000),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000001", sdf_circle_sign_and_boundary_seed_000001),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000002", sdf_circle_sign_and_boundary_seed_000002),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000003", sdf_circle_sign_and_boundary_seed_000003),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000004", sdf_circle_sign_and_boundary_seed_000004),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000005", sdf_circle_sign_and_boundary_seed_000005),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000006", sdf_circle_sign_and_boundary_seed_000006),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000007", sdf_circle_sign_and_boundary_seed_000007),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000008", sdf_circle_sign_and_boundary_seed_000008),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000009", sdf_circle_sign_and_boundary_seed_000009),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000010", sdf_circle_sign_and_boundary_seed_000010),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000011", sdf_circle_sign_and_boundary_seed_000011),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000012", sdf_circle_sign_and_boundary_seed_000012),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000013", sdf_circle_sign_and_boundary_seed_000013),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000014", sdf_circle_sign_and_boundary_seed_000014),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000015", sdf_circle_sign_and_boundary_seed_000015),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000016", sdf_circle_sign_and_boundary_seed_000016),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000017", sdf_circle_sign_and_boundary_seed_000017),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000018", sdf_circle_sign_and_boundary_seed_000018),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000019", sdf_circle_sign_and_boundary_seed_000019),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000020", sdf_circle_sign_and_boundary_seed_000020),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000021", sdf_circle_sign_and_boundary_seed_000021),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000022", sdf_circle_sign_and_boundary_seed_000022),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000023", sdf_circle_sign_and_boundary_seed_000023),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000024", sdf_circle_sign_and_boundary_seed_000024),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000025", sdf_circle_sign_and_boundary_seed_000025),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000026", sdf_circle_sign_and_boundary_seed_000026),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000027", sdf_circle_sign_and_boundary_seed_000027),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000028", sdf_circle_sign_and_boundary_seed_000028),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000029", sdf_circle_sign_and_boundary_seed_000029),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000030", sdf_circle_sign_and_boundary_seed_000030),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000031", sdf_circle_sign_and_boundary_seed_000031),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000032", sdf_circle_sign_and_boundary_seed_000032),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000033", sdf_circle_sign_and_boundary_seed_000033),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000034", sdf_circle_sign_and_boundary_seed_000034),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000035", sdf_circle_sign_and_boundary_seed_000035),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000036", sdf_circle_sign_and_boundary_seed_000036),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000037", sdf_circle_sign_and_boundary_seed_000037),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000038", sdf_circle_sign_and_boundary_seed_000038),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000039", sdf_circle_sign_and_boundary_seed_000039),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000040", sdf_circle_sign_and_boundary_seed_000040),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000041", sdf_circle_sign_and_boundary_seed_000041),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000042", sdf_circle_sign_and_boundary_seed_000042),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000043", sdf_circle_sign_and_boundary_seed_000043),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000044", sdf_circle_sign_and_boundary_seed_000044),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000045", sdf_circle_sign_and_boundary_seed_000045),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000046", sdf_circle_sign_and_boundary_seed_000046),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000047", sdf_circle_sign_and_boundary_seed_000047),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000048", sdf_circle_sign_and_boundary_seed_000048),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000049", sdf_circle_sign_and_boundary_seed_000049),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000050", sdf_circle_sign_and_boundary_seed_000050),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000051", sdf_circle_sign_and_boundary_seed_000051),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000052", sdf_circle_sign_and_boundary_seed_000052),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000053", sdf_circle_sign_and_boundary_seed_000053),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000054", sdf_circle_sign_and_boundary_seed_000054),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000055", sdf_circle_sign_and_boundary_seed_000055),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000056", sdf_circle_sign_and_boundary_seed_000056),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000057", sdf_circle_sign_and_boundary_seed_000057),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000058", sdf_circle_sign_and_boundary_seed_000058),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000059", sdf_circle_sign_and_boundary_seed_000059),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000060", sdf_circle_sign_and_boundary_seed_000060),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000061", sdf_circle_sign_and_boundary_seed_000061),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000062", sdf_circle_sign_and_boundary_seed_000062),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000063", sdf_circle_sign_and_boundary_seed_000063),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000064", sdf_circle_sign_and_boundary_seed_000064),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000065", sdf_circle_sign_and_boundary_seed_000065),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000066", sdf_circle_sign_and_boundary_seed_000066),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000067", sdf_circle_sign_and_boundary_seed_000067),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000068", sdf_circle_sign_and_boundary_seed_000068),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000069", sdf_circle_sign_and_boundary_seed_000069),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000070", sdf_circle_sign_and_boundary_seed_000070),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000071", sdf_circle_sign_and_boundary_seed_000071),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000072", sdf_circle_sign_and_boundary_seed_000072),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000073", sdf_circle_sign_and_boundary_seed_000073),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000074", sdf_circle_sign_and_boundary_seed_000074),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000075", sdf_circle_sign_and_boundary_seed_000075),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000076", sdf_circle_sign_and_boundary_seed_000076),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000077", sdf_circle_sign_and_boundary_seed_000077),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000078", sdf_circle_sign_and_boundary_seed_000078),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000079", sdf_circle_sign_and_boundary_seed_000079),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000080", sdf_circle_sign_and_boundary_seed_000080),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000081", sdf_circle_sign_and_boundary_seed_000081),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000082", sdf_circle_sign_and_boundary_seed_000082),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000083", sdf_circle_sign_and_boundary_seed_000083),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000084", sdf_circle_sign_and_boundary_seed_000084),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000085", sdf_circle_sign_and_boundary_seed_000085),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000086", sdf_circle_sign_and_boundary_seed_000086),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000087", sdf_circle_sign_and_boundary_seed_000087),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000088", sdf_circle_sign_and_boundary_seed_000088),
        ("property_campaigns_2::tests::sdf_circle_sign_and_boundary_seed_000089", sdf_circle_sign_and_boundary_seed_000089),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000000", sdf_circle_translation_equivariant_seed_000000),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000001", sdf_circle_translation_equivariant_seed_000001),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000002", sdf_circle_translation_equivariant_seed_000002),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000003", sdf_circle_translation_equivariant_seed_000003),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000004", sdf_circle_translation_equivariant_seed_000004),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000005", sdf_circle_translation_equivariant_seed_000005),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000006", sdf_circle_translation_equivariant_seed_000006),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000007", sdf_circle_translation_equivariant_seed_000007),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000008", sdf_circle_translation_equivariant_seed_000008),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000009", sdf_circle_translation_equivariant_seed_000009),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000010", sdf_circle_translation_equivariant_seed_000010),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000011", sdf_circle_translation_equivariant_seed_000011),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000012", sdf_circle_translation_equivariant_seed_000012),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000013", sdf_circle_translation_equivariant_seed_000013),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000014", sdf_circle_translation_equivariant_seed_000014),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000015", sdf_circle_translation_equivariant_seed_000015),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000016", sdf_circle_translation_equivariant_seed_000016),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000017", sdf_circle_translation_equivariant_seed_000017),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000018", sdf_circle_translation_equivariant_seed_000018),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000019", sdf_circle_translation_equivariant_seed_000019),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000020", sdf_circle_translation_equivariant_seed_000020),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000021", sdf_circle_translation_equivariant_seed_000021),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000022", sdf_circle_translation_equivariant_seed_000022),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000023", sdf_circle_translation_equivariant_seed_000023),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000024", sdf_circle_translation_equivariant_seed_000024),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000025", sdf_circle_translation_equivariant_seed_000025),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000026", sdf_circle_translation_equivariant_seed_000026),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000027", sdf_circle_translation_equivariant_seed_000027),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000028", sdf_circle_translation_equivariant_seed_000028),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000029", sdf_circle_translation_equivariant_seed_000029),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000030", sdf_circle_translation_equivariant_seed_000030),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000031", sdf_circle_translation_equivariant_seed_000031),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000032", sdf_circle_translation_equivariant_seed_000032),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000033", sdf_circle_translation_equivariant_seed_000033),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000034", sdf_circle_translation_equivariant_seed_000034),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000035", sdf_circle_translation_equivariant_seed_000035),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000036", sdf_circle_translation_equivariant_seed_000036),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000037", sdf_circle_translation_equivariant_seed_000037),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000038", sdf_circle_translation_equivariant_seed_000038),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000039", sdf_circle_translation_equivariant_seed_000039),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000040", sdf_circle_translation_equivariant_seed_000040),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000041", sdf_circle_translation_equivariant_seed_000041),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000042", sdf_circle_translation_equivariant_seed_000042),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000043", sdf_circle_translation_equivariant_seed_000043),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000044", sdf_circle_translation_equivariant_seed_000044),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000045", sdf_circle_translation_equivariant_seed_000045),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000046", sdf_circle_translation_equivariant_seed_000046),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000047", sdf_circle_translation_equivariant_seed_000047),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000048", sdf_circle_translation_equivariant_seed_000048),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000049", sdf_circle_translation_equivariant_seed_000049),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000050", sdf_circle_translation_equivariant_seed_000050),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000051", sdf_circle_translation_equivariant_seed_000051),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000052", sdf_circle_translation_equivariant_seed_000052),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000053", sdf_circle_translation_equivariant_seed_000053),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000054", sdf_circle_translation_equivariant_seed_000054),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000055", sdf_circle_translation_equivariant_seed_000055),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000056", sdf_circle_translation_equivariant_seed_000056),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000057", sdf_circle_translation_equivariant_seed_000057),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000058", sdf_circle_translation_equivariant_seed_000058),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000059", sdf_circle_translation_equivariant_seed_000059),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000060", sdf_circle_translation_equivariant_seed_000060),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000061", sdf_circle_translation_equivariant_seed_000061),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000062", sdf_circle_translation_equivariant_seed_000062),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000063", sdf_circle_translation_equivariant_seed_000063),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000064", sdf_circle_translation_equivariant_seed_000064),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000065", sdf_circle_translation_equivariant_seed_000065),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000066", sdf_circle_translation_equivariant_seed_000066),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000067", sdf_circle_translation_equivariant_seed_000067),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000068", sdf_circle_translation_equivariant_seed_000068),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000069", sdf_circle_translation_equivariant_seed_000069),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000070", sdf_circle_translation_equivariant_seed_000070),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000071", sdf_circle_translation_equivariant_seed_000071),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000072", sdf_circle_translation_equivariant_seed_000072),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000073", sdf_circle_translation_equivariant_seed_000073),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000074", sdf_circle_translation_equivariant_seed_000074),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000075", sdf_circle_translation_equivariant_seed_000075),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000076", sdf_circle_translation_equivariant_seed_000076),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000077", sdf_circle_translation_equivariant_seed_000077),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000078", sdf_circle_translation_equivariant_seed_000078),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000079", sdf_circle_translation_equivariant_seed_000079),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000080", sdf_circle_translation_equivariant_seed_000080),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000081", sdf_circle_translation_equivariant_seed_000081),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000082", sdf_circle_translation_equivariant_seed_000082),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000083", sdf_circle_translation_equivariant_seed_000083),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000084", sdf_circle_translation_equivariant_seed_000084),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000085", sdf_circle_translation_equivariant_seed_000085),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000086", sdf_circle_translation_equivariant_seed_000086),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000087", sdf_circle_translation_equivariant_seed_000087),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000088", sdf_circle_translation_equivariant_seed_000088),
        ("property_campaigns_2::tests::sdf_circle_translation_equivariant_seed_000089", sdf_circle_translation_equivariant_seed_000089),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000000", sdf_polygon_translation_equivariant_seed_000000),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000001", sdf_polygon_translation_equivariant_seed_000001),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000002", sdf_polygon_translation_equivariant_seed_000002),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000003", sdf_polygon_translation_equivariant_seed_000003),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000004", sdf_polygon_translation_equivariant_seed_000004),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000005", sdf_polygon_translation_equivariant_seed_000005),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000006", sdf_polygon_translation_equivariant_seed_000006),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000007", sdf_polygon_translation_equivariant_seed_000007),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000008", sdf_polygon_translation_equivariant_seed_000008),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000009", sdf_polygon_translation_equivariant_seed_000009),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000010", sdf_polygon_translation_equivariant_seed_000010),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000011", sdf_polygon_translation_equivariant_seed_000011),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000012", sdf_polygon_translation_equivariant_seed_000012),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000013", sdf_polygon_translation_equivariant_seed_000013),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000014", sdf_polygon_translation_equivariant_seed_000014),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000015", sdf_polygon_translation_equivariant_seed_000015),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000016", sdf_polygon_translation_equivariant_seed_000016),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000017", sdf_polygon_translation_equivariant_seed_000017),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000018", sdf_polygon_translation_equivariant_seed_000018),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000019", sdf_polygon_translation_equivariant_seed_000019),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000020", sdf_polygon_translation_equivariant_seed_000020),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000021", sdf_polygon_translation_equivariant_seed_000021),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000022", sdf_polygon_translation_equivariant_seed_000022),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000023", sdf_polygon_translation_equivariant_seed_000023),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000024", sdf_polygon_translation_equivariant_seed_000024),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000025", sdf_polygon_translation_equivariant_seed_000025),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000026", sdf_polygon_translation_equivariant_seed_000026),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000027", sdf_polygon_translation_equivariant_seed_000027),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000028", sdf_polygon_translation_equivariant_seed_000028),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000029", sdf_polygon_translation_equivariant_seed_000029),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000030", sdf_polygon_translation_equivariant_seed_000030),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000031", sdf_polygon_translation_equivariant_seed_000031),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000032", sdf_polygon_translation_equivariant_seed_000032),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000033", sdf_polygon_translation_equivariant_seed_000033),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000034", sdf_polygon_translation_equivariant_seed_000034),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000035", sdf_polygon_translation_equivariant_seed_000035),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000036", sdf_polygon_translation_equivariant_seed_000036),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000037", sdf_polygon_translation_equivariant_seed_000037),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000038", sdf_polygon_translation_equivariant_seed_000038),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000039", sdf_polygon_translation_equivariant_seed_000039),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000040", sdf_polygon_translation_equivariant_seed_000040),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000041", sdf_polygon_translation_equivariant_seed_000041),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000042", sdf_polygon_translation_equivariant_seed_000042),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000043", sdf_polygon_translation_equivariant_seed_000043),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000044", sdf_polygon_translation_equivariant_seed_000044),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000045", sdf_polygon_translation_equivariant_seed_000045),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000046", sdf_polygon_translation_equivariant_seed_000046),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000047", sdf_polygon_translation_equivariant_seed_000047),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000048", sdf_polygon_translation_equivariant_seed_000048),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000049", sdf_polygon_translation_equivariant_seed_000049),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000050", sdf_polygon_translation_equivariant_seed_000050),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000051", sdf_polygon_translation_equivariant_seed_000051),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000052", sdf_polygon_translation_equivariant_seed_000052),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000053", sdf_polygon_translation_equivariant_seed_000053),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000054", sdf_polygon_translation_equivariant_seed_000054),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000055", sdf_polygon_translation_equivariant_seed_000055),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000056", sdf_polygon_translation_equivariant_seed_000056),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000057", sdf_polygon_translation_equivariant_seed_000057),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000058", sdf_polygon_translation_equivariant_seed_000058),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000059", sdf_polygon_translation_equivariant_seed_000059),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000060", sdf_polygon_translation_equivariant_seed_000060),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000061", sdf_polygon_translation_equivariant_seed_000061),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000062", sdf_polygon_translation_equivariant_seed_000062),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000063", sdf_polygon_translation_equivariant_seed_000063),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000064", sdf_polygon_translation_equivariant_seed_000064),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000065", sdf_polygon_translation_equivariant_seed_000065),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000066", sdf_polygon_translation_equivariant_seed_000066),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000067", sdf_polygon_translation_equivariant_seed_000067),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000068", sdf_polygon_translation_equivariant_seed_000068),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000069", sdf_polygon_translation_equivariant_seed_000069),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000070", sdf_polygon_translation_equivariant_seed_000070),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000071", sdf_polygon_translation_equivariant_seed_000071),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000072", sdf_polygon_translation_equivariant_seed_000072),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000073", sdf_polygon_translation_equivariant_seed_000073),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000074", sdf_polygon_translation_equivariant_seed_000074),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000075", sdf_polygon_translation_equivariant_seed_000075),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000076", sdf_polygon_translation_equivariant_seed_000076),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000077", sdf_polygon_translation_equivariant_seed_000077),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000078", sdf_polygon_translation_equivariant_seed_000078),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000079", sdf_polygon_translation_equivariant_seed_000079),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000080", sdf_polygon_translation_equivariant_seed_000080),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000081", sdf_polygon_translation_equivariant_seed_000081),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000082", sdf_polygon_translation_equivariant_seed_000082),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000083", sdf_polygon_translation_equivariant_seed_000083),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000084", sdf_polygon_translation_equivariant_seed_000084),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000085", sdf_polygon_translation_equivariant_seed_000085),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000086", sdf_polygon_translation_equivariant_seed_000086),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000087", sdf_polygon_translation_equivariant_seed_000087),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000088", sdf_polygon_translation_equivariant_seed_000088),
        ("property_campaigns_2::tests::sdf_polygon_translation_equivariant_seed_000089", sdf_polygon_translation_equivariant_seed_000089),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000000", sdf_convex_vs_polygon_sign_agreement_seed_000000),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000001", sdf_convex_vs_polygon_sign_agreement_seed_000001),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000002", sdf_convex_vs_polygon_sign_agreement_seed_000002),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000003", sdf_convex_vs_polygon_sign_agreement_seed_000003),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000004", sdf_convex_vs_polygon_sign_agreement_seed_000004),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000005", sdf_convex_vs_polygon_sign_agreement_seed_000005),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000006", sdf_convex_vs_polygon_sign_agreement_seed_000006),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000007", sdf_convex_vs_polygon_sign_agreement_seed_000007),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000008", sdf_convex_vs_polygon_sign_agreement_seed_000008),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000009", sdf_convex_vs_polygon_sign_agreement_seed_000009),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000010", sdf_convex_vs_polygon_sign_agreement_seed_000010),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000011", sdf_convex_vs_polygon_sign_agreement_seed_000011),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000012", sdf_convex_vs_polygon_sign_agreement_seed_000012),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000013", sdf_convex_vs_polygon_sign_agreement_seed_000013),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000014", sdf_convex_vs_polygon_sign_agreement_seed_000014),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000015", sdf_convex_vs_polygon_sign_agreement_seed_000015),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000016", sdf_convex_vs_polygon_sign_agreement_seed_000016),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000017", sdf_convex_vs_polygon_sign_agreement_seed_000017),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000018", sdf_convex_vs_polygon_sign_agreement_seed_000018),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000019", sdf_convex_vs_polygon_sign_agreement_seed_000019),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000020", sdf_convex_vs_polygon_sign_agreement_seed_000020),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000021", sdf_convex_vs_polygon_sign_agreement_seed_000021),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000022", sdf_convex_vs_polygon_sign_agreement_seed_000022),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000023", sdf_convex_vs_polygon_sign_agreement_seed_000023),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000024", sdf_convex_vs_polygon_sign_agreement_seed_000024),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000025", sdf_convex_vs_polygon_sign_agreement_seed_000025),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000026", sdf_convex_vs_polygon_sign_agreement_seed_000026),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000027", sdf_convex_vs_polygon_sign_agreement_seed_000027),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000028", sdf_convex_vs_polygon_sign_agreement_seed_000028),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000029", sdf_convex_vs_polygon_sign_agreement_seed_000029),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000030", sdf_convex_vs_polygon_sign_agreement_seed_000030),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000031", sdf_convex_vs_polygon_sign_agreement_seed_000031),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000032", sdf_convex_vs_polygon_sign_agreement_seed_000032),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000033", sdf_convex_vs_polygon_sign_agreement_seed_000033),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000034", sdf_convex_vs_polygon_sign_agreement_seed_000034),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000035", sdf_convex_vs_polygon_sign_agreement_seed_000035),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000036", sdf_convex_vs_polygon_sign_agreement_seed_000036),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000037", sdf_convex_vs_polygon_sign_agreement_seed_000037),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000038", sdf_convex_vs_polygon_sign_agreement_seed_000038),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000039", sdf_convex_vs_polygon_sign_agreement_seed_000039),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000040", sdf_convex_vs_polygon_sign_agreement_seed_000040),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000041", sdf_convex_vs_polygon_sign_agreement_seed_000041),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000042", sdf_convex_vs_polygon_sign_agreement_seed_000042),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000043", sdf_convex_vs_polygon_sign_agreement_seed_000043),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000044", sdf_convex_vs_polygon_sign_agreement_seed_000044),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000045", sdf_convex_vs_polygon_sign_agreement_seed_000045),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000046", sdf_convex_vs_polygon_sign_agreement_seed_000046),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000047", sdf_convex_vs_polygon_sign_agreement_seed_000047),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000048", sdf_convex_vs_polygon_sign_agreement_seed_000048),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000049", sdf_convex_vs_polygon_sign_agreement_seed_000049),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000050", sdf_convex_vs_polygon_sign_agreement_seed_000050),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000051", sdf_convex_vs_polygon_sign_agreement_seed_000051),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000052", sdf_convex_vs_polygon_sign_agreement_seed_000052),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000053", sdf_convex_vs_polygon_sign_agreement_seed_000053),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000054", sdf_convex_vs_polygon_sign_agreement_seed_000054),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000055", sdf_convex_vs_polygon_sign_agreement_seed_000055),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000056", sdf_convex_vs_polygon_sign_agreement_seed_000056),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000057", sdf_convex_vs_polygon_sign_agreement_seed_000057),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000058", sdf_convex_vs_polygon_sign_agreement_seed_000058),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000059", sdf_convex_vs_polygon_sign_agreement_seed_000059),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000060", sdf_convex_vs_polygon_sign_agreement_seed_000060),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000061", sdf_convex_vs_polygon_sign_agreement_seed_000061),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000062", sdf_convex_vs_polygon_sign_agreement_seed_000062),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000063", sdf_convex_vs_polygon_sign_agreement_seed_000063),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000064", sdf_convex_vs_polygon_sign_agreement_seed_000064),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000065", sdf_convex_vs_polygon_sign_agreement_seed_000065),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000066", sdf_convex_vs_polygon_sign_agreement_seed_000066),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000067", sdf_convex_vs_polygon_sign_agreement_seed_000067),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000068", sdf_convex_vs_polygon_sign_agreement_seed_000068),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000069", sdf_convex_vs_polygon_sign_agreement_seed_000069),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000070", sdf_convex_vs_polygon_sign_agreement_seed_000070),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000071", sdf_convex_vs_polygon_sign_agreement_seed_000071),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000072", sdf_convex_vs_polygon_sign_agreement_seed_000072),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000073", sdf_convex_vs_polygon_sign_agreement_seed_000073),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000074", sdf_convex_vs_polygon_sign_agreement_seed_000074),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000075", sdf_convex_vs_polygon_sign_agreement_seed_000075),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000076", sdf_convex_vs_polygon_sign_agreement_seed_000076),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000077", sdf_convex_vs_polygon_sign_agreement_seed_000077),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000078", sdf_convex_vs_polygon_sign_agreement_seed_000078),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000079", sdf_convex_vs_polygon_sign_agreement_seed_000079),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000080", sdf_convex_vs_polygon_sign_agreement_seed_000080),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000081", sdf_convex_vs_polygon_sign_agreement_seed_000081),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000082", sdf_convex_vs_polygon_sign_agreement_seed_000082),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000083", sdf_convex_vs_polygon_sign_agreement_seed_000083),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000084", sdf_convex_vs_polygon_sign_agreement_seed_000084),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000085", sdf_convex_vs_polygon_sign_agreement_seed_000085),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000086", sdf_convex_vs_polygon_sign_agreement_seed_000086),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000087", sdf_convex_vs_polygon_sign_agreement_seed_000087),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000088", sdf_convex_vs_polygon_sign_agreement_seed_000088),
        ("property_campaigns_2::tests::sdf_convex_vs_polygon_sign_agreement_seed_000089", sdf_convex_vs_polygon_sign_agreement_seed_000089),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000000", sdf_capsule_degenerate_matches_circle_seed_000000),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000001", sdf_capsule_degenerate_matches_circle_seed_000001),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000002", sdf_capsule_degenerate_matches_circle_seed_000002),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000003", sdf_capsule_degenerate_matches_circle_seed_000003),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000004", sdf_capsule_degenerate_matches_circle_seed_000004),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000005", sdf_capsule_degenerate_matches_circle_seed_000005),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000006", sdf_capsule_degenerate_matches_circle_seed_000006),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000007", sdf_capsule_degenerate_matches_circle_seed_000007),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000008", sdf_capsule_degenerate_matches_circle_seed_000008),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000009", sdf_capsule_degenerate_matches_circle_seed_000009),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000010", sdf_capsule_degenerate_matches_circle_seed_000010),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000011", sdf_capsule_degenerate_matches_circle_seed_000011),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000012", sdf_capsule_degenerate_matches_circle_seed_000012),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000013", sdf_capsule_degenerate_matches_circle_seed_000013),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000014", sdf_capsule_degenerate_matches_circle_seed_000014),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000015", sdf_capsule_degenerate_matches_circle_seed_000015),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000016", sdf_capsule_degenerate_matches_circle_seed_000016),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000017", sdf_capsule_degenerate_matches_circle_seed_000017),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000018", sdf_capsule_degenerate_matches_circle_seed_000018),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000019", sdf_capsule_degenerate_matches_circle_seed_000019),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000020", sdf_capsule_degenerate_matches_circle_seed_000020),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000021", sdf_capsule_degenerate_matches_circle_seed_000021),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000022", sdf_capsule_degenerate_matches_circle_seed_000022),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000023", sdf_capsule_degenerate_matches_circle_seed_000023),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000024", sdf_capsule_degenerate_matches_circle_seed_000024),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000025", sdf_capsule_degenerate_matches_circle_seed_000025),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000026", sdf_capsule_degenerate_matches_circle_seed_000026),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000027", sdf_capsule_degenerate_matches_circle_seed_000027),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000028", sdf_capsule_degenerate_matches_circle_seed_000028),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000029", sdf_capsule_degenerate_matches_circle_seed_000029),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000030", sdf_capsule_degenerate_matches_circle_seed_000030),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000031", sdf_capsule_degenerate_matches_circle_seed_000031),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000032", sdf_capsule_degenerate_matches_circle_seed_000032),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000033", sdf_capsule_degenerate_matches_circle_seed_000033),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000034", sdf_capsule_degenerate_matches_circle_seed_000034),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000035", sdf_capsule_degenerate_matches_circle_seed_000035),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000036", sdf_capsule_degenerate_matches_circle_seed_000036),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000037", sdf_capsule_degenerate_matches_circle_seed_000037),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000038", sdf_capsule_degenerate_matches_circle_seed_000038),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000039", sdf_capsule_degenerate_matches_circle_seed_000039),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000040", sdf_capsule_degenerate_matches_circle_seed_000040),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000041", sdf_capsule_degenerate_matches_circle_seed_000041),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000042", sdf_capsule_degenerate_matches_circle_seed_000042),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000043", sdf_capsule_degenerate_matches_circle_seed_000043),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000044", sdf_capsule_degenerate_matches_circle_seed_000044),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000045", sdf_capsule_degenerate_matches_circle_seed_000045),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000046", sdf_capsule_degenerate_matches_circle_seed_000046),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000047", sdf_capsule_degenerate_matches_circle_seed_000047),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000048", sdf_capsule_degenerate_matches_circle_seed_000048),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000049", sdf_capsule_degenerate_matches_circle_seed_000049),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000050", sdf_capsule_degenerate_matches_circle_seed_000050),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000051", sdf_capsule_degenerate_matches_circle_seed_000051),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000052", sdf_capsule_degenerate_matches_circle_seed_000052),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000053", sdf_capsule_degenerate_matches_circle_seed_000053),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000054", sdf_capsule_degenerate_matches_circle_seed_000054),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000055", sdf_capsule_degenerate_matches_circle_seed_000055),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000056", sdf_capsule_degenerate_matches_circle_seed_000056),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000057", sdf_capsule_degenerate_matches_circle_seed_000057),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000058", sdf_capsule_degenerate_matches_circle_seed_000058),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000059", sdf_capsule_degenerate_matches_circle_seed_000059),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000060", sdf_capsule_degenerate_matches_circle_seed_000060),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000061", sdf_capsule_degenerate_matches_circle_seed_000061),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000062", sdf_capsule_degenerate_matches_circle_seed_000062),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000063", sdf_capsule_degenerate_matches_circle_seed_000063),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000064", sdf_capsule_degenerate_matches_circle_seed_000064),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000065", sdf_capsule_degenerate_matches_circle_seed_000065),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000066", sdf_capsule_degenerate_matches_circle_seed_000066),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000067", sdf_capsule_degenerate_matches_circle_seed_000067),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000068", sdf_capsule_degenerate_matches_circle_seed_000068),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000069", sdf_capsule_degenerate_matches_circle_seed_000069),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000070", sdf_capsule_degenerate_matches_circle_seed_000070),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000071", sdf_capsule_degenerate_matches_circle_seed_000071),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000072", sdf_capsule_degenerate_matches_circle_seed_000072),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000073", sdf_capsule_degenerate_matches_circle_seed_000073),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000074", sdf_capsule_degenerate_matches_circle_seed_000074),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000075", sdf_capsule_degenerate_matches_circle_seed_000075),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000076", sdf_capsule_degenerate_matches_circle_seed_000076),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000077", sdf_capsule_degenerate_matches_circle_seed_000077),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000078", sdf_capsule_degenerate_matches_circle_seed_000078),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000079", sdf_capsule_degenerate_matches_circle_seed_000079),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000080", sdf_capsule_degenerate_matches_circle_seed_000080),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000081", sdf_capsule_degenerate_matches_circle_seed_000081),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000082", sdf_capsule_degenerate_matches_circle_seed_000082),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000083", sdf_capsule_degenerate_matches_circle_seed_000083),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000084", sdf_capsule_degenerate_matches_circle_seed_000084),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000085", sdf_capsule_degenerate_matches_circle_seed_000085),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000086", sdf_capsule_degenerate_matches_circle_seed_000086),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000087", sdf_capsule_degenerate_matches_circle_seed_000087),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000088", sdf_capsule_degenerate_matches_circle_seed_000088),
        ("property_campaigns_2::tests::sdf_capsule_degenerate_matches_circle_seed_000089", sdf_capsule_degenerate_matches_circle_seed_000089),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000000", sdf_smooth_union_lower_bound_seed_000000),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000001", sdf_smooth_union_lower_bound_seed_000001),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000002", sdf_smooth_union_lower_bound_seed_000002),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000003", sdf_smooth_union_lower_bound_seed_000003),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000004", sdf_smooth_union_lower_bound_seed_000004),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000005", sdf_smooth_union_lower_bound_seed_000005),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000006", sdf_smooth_union_lower_bound_seed_000006),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000007", sdf_smooth_union_lower_bound_seed_000007),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000008", sdf_smooth_union_lower_bound_seed_000008),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000009", sdf_smooth_union_lower_bound_seed_000009),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000010", sdf_smooth_union_lower_bound_seed_000010),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000011", sdf_smooth_union_lower_bound_seed_000011),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000012", sdf_smooth_union_lower_bound_seed_000012),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000013", sdf_smooth_union_lower_bound_seed_000013),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000014", sdf_smooth_union_lower_bound_seed_000014),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000015", sdf_smooth_union_lower_bound_seed_000015),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000016", sdf_smooth_union_lower_bound_seed_000016),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000017", sdf_smooth_union_lower_bound_seed_000017),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000018", sdf_smooth_union_lower_bound_seed_000018),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000019", sdf_smooth_union_lower_bound_seed_000019),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000020", sdf_smooth_union_lower_bound_seed_000020),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000021", sdf_smooth_union_lower_bound_seed_000021),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000022", sdf_smooth_union_lower_bound_seed_000022),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000023", sdf_smooth_union_lower_bound_seed_000023),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000024", sdf_smooth_union_lower_bound_seed_000024),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000025", sdf_smooth_union_lower_bound_seed_000025),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000026", sdf_smooth_union_lower_bound_seed_000026),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000027", sdf_smooth_union_lower_bound_seed_000027),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000028", sdf_smooth_union_lower_bound_seed_000028),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000029", sdf_smooth_union_lower_bound_seed_000029),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000030", sdf_smooth_union_lower_bound_seed_000030),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000031", sdf_smooth_union_lower_bound_seed_000031),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000032", sdf_smooth_union_lower_bound_seed_000032),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000033", sdf_smooth_union_lower_bound_seed_000033),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000034", sdf_smooth_union_lower_bound_seed_000034),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000035", sdf_smooth_union_lower_bound_seed_000035),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000036", sdf_smooth_union_lower_bound_seed_000036),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000037", sdf_smooth_union_lower_bound_seed_000037),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000038", sdf_smooth_union_lower_bound_seed_000038),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000039", sdf_smooth_union_lower_bound_seed_000039),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000040", sdf_smooth_union_lower_bound_seed_000040),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000041", sdf_smooth_union_lower_bound_seed_000041),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000042", sdf_smooth_union_lower_bound_seed_000042),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000043", sdf_smooth_union_lower_bound_seed_000043),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000044", sdf_smooth_union_lower_bound_seed_000044),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000045", sdf_smooth_union_lower_bound_seed_000045),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000046", sdf_smooth_union_lower_bound_seed_000046),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000047", sdf_smooth_union_lower_bound_seed_000047),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000048", sdf_smooth_union_lower_bound_seed_000048),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000049", sdf_smooth_union_lower_bound_seed_000049),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000050", sdf_smooth_union_lower_bound_seed_000050),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000051", sdf_smooth_union_lower_bound_seed_000051),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000052", sdf_smooth_union_lower_bound_seed_000052),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000053", sdf_smooth_union_lower_bound_seed_000053),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000054", sdf_smooth_union_lower_bound_seed_000054),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000055", sdf_smooth_union_lower_bound_seed_000055),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000056", sdf_smooth_union_lower_bound_seed_000056),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000057", sdf_smooth_union_lower_bound_seed_000057),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000058", sdf_smooth_union_lower_bound_seed_000058),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000059", sdf_smooth_union_lower_bound_seed_000059),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000060", sdf_smooth_union_lower_bound_seed_000060),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000061", sdf_smooth_union_lower_bound_seed_000061),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000062", sdf_smooth_union_lower_bound_seed_000062),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000063", sdf_smooth_union_lower_bound_seed_000063),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000064", sdf_smooth_union_lower_bound_seed_000064),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000065", sdf_smooth_union_lower_bound_seed_000065),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000066", sdf_smooth_union_lower_bound_seed_000066),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000067", sdf_smooth_union_lower_bound_seed_000067),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000068", sdf_smooth_union_lower_bound_seed_000068),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000069", sdf_smooth_union_lower_bound_seed_000069),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000070", sdf_smooth_union_lower_bound_seed_000070),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000071", sdf_smooth_union_lower_bound_seed_000071),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000072", sdf_smooth_union_lower_bound_seed_000072),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000073", sdf_smooth_union_lower_bound_seed_000073),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000074", sdf_smooth_union_lower_bound_seed_000074),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000075", sdf_smooth_union_lower_bound_seed_000075),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000076", sdf_smooth_union_lower_bound_seed_000076),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000077", sdf_smooth_union_lower_bound_seed_000077),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000078", sdf_smooth_union_lower_bound_seed_000078),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000079", sdf_smooth_union_lower_bound_seed_000079),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000080", sdf_smooth_union_lower_bound_seed_000080),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000081", sdf_smooth_union_lower_bound_seed_000081),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000082", sdf_smooth_union_lower_bound_seed_000082),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000083", sdf_smooth_union_lower_bound_seed_000083),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000084", sdf_smooth_union_lower_bound_seed_000084),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000085", sdf_smooth_union_lower_bound_seed_000085),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000086", sdf_smooth_union_lower_bound_seed_000086),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000087", sdf_smooth_union_lower_bound_seed_000087),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000088", sdf_smooth_union_lower_bound_seed_000088),
        ("property_campaigns_2::tests::sdf_smooth_union_lower_bound_seed_000089", sdf_smooth_union_lower_bound_seed_000089),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000000", sdf_smooth_intersection_upper_bound_seed_000000),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000001", sdf_smooth_intersection_upper_bound_seed_000001),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000002", sdf_smooth_intersection_upper_bound_seed_000002),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000003", sdf_smooth_intersection_upper_bound_seed_000003),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000004", sdf_smooth_intersection_upper_bound_seed_000004),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000005", sdf_smooth_intersection_upper_bound_seed_000005),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000006", sdf_smooth_intersection_upper_bound_seed_000006),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000007", sdf_smooth_intersection_upper_bound_seed_000007),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000008", sdf_smooth_intersection_upper_bound_seed_000008),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000009", sdf_smooth_intersection_upper_bound_seed_000009),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000010", sdf_smooth_intersection_upper_bound_seed_000010),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000011", sdf_smooth_intersection_upper_bound_seed_000011),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000012", sdf_smooth_intersection_upper_bound_seed_000012),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000013", sdf_smooth_intersection_upper_bound_seed_000013),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000014", sdf_smooth_intersection_upper_bound_seed_000014),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000015", sdf_smooth_intersection_upper_bound_seed_000015),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000016", sdf_smooth_intersection_upper_bound_seed_000016),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000017", sdf_smooth_intersection_upper_bound_seed_000017),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000018", sdf_smooth_intersection_upper_bound_seed_000018),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000019", sdf_smooth_intersection_upper_bound_seed_000019),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000020", sdf_smooth_intersection_upper_bound_seed_000020),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000021", sdf_smooth_intersection_upper_bound_seed_000021),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000022", sdf_smooth_intersection_upper_bound_seed_000022),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000023", sdf_smooth_intersection_upper_bound_seed_000023),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000024", sdf_smooth_intersection_upper_bound_seed_000024),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000025", sdf_smooth_intersection_upper_bound_seed_000025),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000026", sdf_smooth_intersection_upper_bound_seed_000026),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000027", sdf_smooth_intersection_upper_bound_seed_000027),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000028", sdf_smooth_intersection_upper_bound_seed_000028),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000029", sdf_smooth_intersection_upper_bound_seed_000029),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000030", sdf_smooth_intersection_upper_bound_seed_000030),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000031", sdf_smooth_intersection_upper_bound_seed_000031),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000032", sdf_smooth_intersection_upper_bound_seed_000032),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000033", sdf_smooth_intersection_upper_bound_seed_000033),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000034", sdf_smooth_intersection_upper_bound_seed_000034),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000035", sdf_smooth_intersection_upper_bound_seed_000035),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000036", sdf_smooth_intersection_upper_bound_seed_000036),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000037", sdf_smooth_intersection_upper_bound_seed_000037),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000038", sdf_smooth_intersection_upper_bound_seed_000038),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000039", sdf_smooth_intersection_upper_bound_seed_000039),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000040", sdf_smooth_intersection_upper_bound_seed_000040),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000041", sdf_smooth_intersection_upper_bound_seed_000041),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000042", sdf_smooth_intersection_upper_bound_seed_000042),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000043", sdf_smooth_intersection_upper_bound_seed_000043),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000044", sdf_smooth_intersection_upper_bound_seed_000044),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000045", sdf_smooth_intersection_upper_bound_seed_000045),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000046", sdf_smooth_intersection_upper_bound_seed_000046),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000047", sdf_smooth_intersection_upper_bound_seed_000047),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000048", sdf_smooth_intersection_upper_bound_seed_000048),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000049", sdf_smooth_intersection_upper_bound_seed_000049),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000050", sdf_smooth_intersection_upper_bound_seed_000050),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000051", sdf_smooth_intersection_upper_bound_seed_000051),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000052", sdf_smooth_intersection_upper_bound_seed_000052),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000053", sdf_smooth_intersection_upper_bound_seed_000053),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000054", sdf_smooth_intersection_upper_bound_seed_000054),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000055", sdf_smooth_intersection_upper_bound_seed_000055),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000056", sdf_smooth_intersection_upper_bound_seed_000056),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000057", sdf_smooth_intersection_upper_bound_seed_000057),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000058", sdf_smooth_intersection_upper_bound_seed_000058),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000059", sdf_smooth_intersection_upper_bound_seed_000059),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000060", sdf_smooth_intersection_upper_bound_seed_000060),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000061", sdf_smooth_intersection_upper_bound_seed_000061),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000062", sdf_smooth_intersection_upper_bound_seed_000062),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000063", sdf_smooth_intersection_upper_bound_seed_000063),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000064", sdf_smooth_intersection_upper_bound_seed_000064),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000065", sdf_smooth_intersection_upper_bound_seed_000065),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000066", sdf_smooth_intersection_upper_bound_seed_000066),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000067", sdf_smooth_intersection_upper_bound_seed_000067),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000068", sdf_smooth_intersection_upper_bound_seed_000068),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000069", sdf_smooth_intersection_upper_bound_seed_000069),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000070", sdf_smooth_intersection_upper_bound_seed_000070),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000071", sdf_smooth_intersection_upper_bound_seed_000071),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000072", sdf_smooth_intersection_upper_bound_seed_000072),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000073", sdf_smooth_intersection_upper_bound_seed_000073),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000074", sdf_smooth_intersection_upper_bound_seed_000074),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000075", sdf_smooth_intersection_upper_bound_seed_000075),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000076", sdf_smooth_intersection_upper_bound_seed_000076),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000077", sdf_smooth_intersection_upper_bound_seed_000077),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000078", sdf_smooth_intersection_upper_bound_seed_000078),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000079", sdf_smooth_intersection_upper_bound_seed_000079),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000080", sdf_smooth_intersection_upper_bound_seed_000080),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000081", sdf_smooth_intersection_upper_bound_seed_000081),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000082", sdf_smooth_intersection_upper_bound_seed_000082),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000083", sdf_smooth_intersection_upper_bound_seed_000083),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000084", sdf_smooth_intersection_upper_bound_seed_000084),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000085", sdf_smooth_intersection_upper_bound_seed_000085),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000086", sdf_smooth_intersection_upper_bound_seed_000086),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000087", sdf_smooth_intersection_upper_bound_seed_000087),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000088", sdf_smooth_intersection_upper_bound_seed_000088),
        ("property_campaigns_2::tests::sdf_smooth_intersection_upper_bound_seed_000089", sdf_smooth_intersection_upper_bound_seed_000089),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000000", poly_translate_area_invariant_seed_000000),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000001", poly_translate_area_invariant_seed_000001),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000002", poly_translate_area_invariant_seed_000002),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000003", poly_translate_area_invariant_seed_000003),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000004", poly_translate_area_invariant_seed_000004),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000005", poly_translate_area_invariant_seed_000005),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000006", poly_translate_area_invariant_seed_000006),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000007", poly_translate_area_invariant_seed_000007),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000008", poly_translate_area_invariant_seed_000008),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000009", poly_translate_area_invariant_seed_000009),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000010", poly_translate_area_invariant_seed_000010),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000011", poly_translate_area_invariant_seed_000011),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000012", poly_translate_area_invariant_seed_000012),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000013", poly_translate_area_invariant_seed_000013),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000014", poly_translate_area_invariant_seed_000014),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000015", poly_translate_area_invariant_seed_000015),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000016", poly_translate_area_invariant_seed_000016),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000017", poly_translate_area_invariant_seed_000017),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000018", poly_translate_area_invariant_seed_000018),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000019", poly_translate_area_invariant_seed_000019),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000020", poly_translate_area_invariant_seed_000020),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000021", poly_translate_area_invariant_seed_000021),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000022", poly_translate_area_invariant_seed_000022),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000023", poly_translate_area_invariant_seed_000023),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000024", poly_translate_area_invariant_seed_000024),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000025", poly_translate_area_invariant_seed_000025),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000026", poly_translate_area_invariant_seed_000026),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000027", poly_translate_area_invariant_seed_000027),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000028", poly_translate_area_invariant_seed_000028),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000029", poly_translate_area_invariant_seed_000029),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000030", poly_translate_area_invariant_seed_000030),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000031", poly_translate_area_invariant_seed_000031),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000032", poly_translate_area_invariant_seed_000032),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000033", poly_translate_area_invariant_seed_000033),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000034", poly_translate_area_invariant_seed_000034),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000035", poly_translate_area_invariant_seed_000035),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000036", poly_translate_area_invariant_seed_000036),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000037", poly_translate_area_invariant_seed_000037),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000038", poly_translate_area_invariant_seed_000038),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000039", poly_translate_area_invariant_seed_000039),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000040", poly_translate_area_invariant_seed_000040),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000041", poly_translate_area_invariant_seed_000041),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000042", poly_translate_area_invariant_seed_000042),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000043", poly_translate_area_invariant_seed_000043),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000044", poly_translate_area_invariant_seed_000044),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000045", poly_translate_area_invariant_seed_000045),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000046", poly_translate_area_invariant_seed_000046),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000047", poly_translate_area_invariant_seed_000047),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000048", poly_translate_area_invariant_seed_000048),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000049", poly_translate_area_invariant_seed_000049),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000050", poly_translate_area_invariant_seed_000050),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000051", poly_translate_area_invariant_seed_000051),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000052", poly_translate_area_invariant_seed_000052),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000053", poly_translate_area_invariant_seed_000053),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000054", poly_translate_area_invariant_seed_000054),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000055", poly_translate_area_invariant_seed_000055),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000056", poly_translate_area_invariant_seed_000056),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000057", poly_translate_area_invariant_seed_000057),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000058", poly_translate_area_invariant_seed_000058),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000059", poly_translate_area_invariant_seed_000059),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000060", poly_translate_area_invariant_seed_000060),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000061", poly_translate_area_invariant_seed_000061),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000062", poly_translate_area_invariant_seed_000062),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000063", poly_translate_area_invariant_seed_000063),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000064", poly_translate_area_invariant_seed_000064),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000065", poly_translate_area_invariant_seed_000065),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000066", poly_translate_area_invariant_seed_000066),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000067", poly_translate_area_invariant_seed_000067),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000068", poly_translate_area_invariant_seed_000068),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000069", poly_translate_area_invariant_seed_000069),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000070", poly_translate_area_invariant_seed_000070),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000071", poly_translate_area_invariant_seed_000071),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000072", poly_translate_area_invariant_seed_000072),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000073", poly_translate_area_invariant_seed_000073),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000074", poly_translate_area_invariant_seed_000074),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000075", poly_translate_area_invariant_seed_000075),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000076", poly_translate_area_invariant_seed_000076),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000077", poly_translate_area_invariant_seed_000077),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000078", poly_translate_area_invariant_seed_000078),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000079", poly_translate_area_invariant_seed_000079),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000080", poly_translate_area_invariant_seed_000080),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000081", poly_translate_area_invariant_seed_000081),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000082", poly_translate_area_invariant_seed_000082),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000083", poly_translate_area_invariant_seed_000083),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000084", poly_translate_area_invariant_seed_000084),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000085", poly_translate_area_invariant_seed_000085),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000086", poly_translate_area_invariant_seed_000086),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000087", poly_translate_area_invariant_seed_000087),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000088", poly_translate_area_invariant_seed_000088),
        ("property_campaigns_2::tests::poly_translate_area_invariant_seed_000089", poly_translate_area_invariant_seed_000089),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000000", poly_rotate_area_invariant_seed_000000),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000001", poly_rotate_area_invariant_seed_000001),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000002", poly_rotate_area_invariant_seed_000002),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000003", poly_rotate_area_invariant_seed_000003),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000004", poly_rotate_area_invariant_seed_000004),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000005", poly_rotate_area_invariant_seed_000005),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000006", poly_rotate_area_invariant_seed_000006),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000007", poly_rotate_area_invariant_seed_000007),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000008", poly_rotate_area_invariant_seed_000008),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000009", poly_rotate_area_invariant_seed_000009),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000010", poly_rotate_area_invariant_seed_000010),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000011", poly_rotate_area_invariant_seed_000011),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000012", poly_rotate_area_invariant_seed_000012),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000013", poly_rotate_area_invariant_seed_000013),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000014", poly_rotate_area_invariant_seed_000014),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000015", poly_rotate_area_invariant_seed_000015),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000016", poly_rotate_area_invariant_seed_000016),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000017", poly_rotate_area_invariant_seed_000017),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000018", poly_rotate_area_invariant_seed_000018),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000019", poly_rotate_area_invariant_seed_000019),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000020", poly_rotate_area_invariant_seed_000020),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000021", poly_rotate_area_invariant_seed_000021),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000022", poly_rotate_area_invariant_seed_000022),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000023", poly_rotate_area_invariant_seed_000023),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000024", poly_rotate_area_invariant_seed_000024),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000025", poly_rotate_area_invariant_seed_000025),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000026", poly_rotate_area_invariant_seed_000026),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000027", poly_rotate_area_invariant_seed_000027),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000028", poly_rotate_area_invariant_seed_000028),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000029", poly_rotate_area_invariant_seed_000029),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000030", poly_rotate_area_invariant_seed_000030),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000031", poly_rotate_area_invariant_seed_000031),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000032", poly_rotate_area_invariant_seed_000032),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000033", poly_rotate_area_invariant_seed_000033),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000034", poly_rotate_area_invariant_seed_000034),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000035", poly_rotate_area_invariant_seed_000035),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000036", poly_rotate_area_invariant_seed_000036),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000037", poly_rotate_area_invariant_seed_000037),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000038", poly_rotate_area_invariant_seed_000038),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000039", poly_rotate_area_invariant_seed_000039),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000040", poly_rotate_area_invariant_seed_000040),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000041", poly_rotate_area_invariant_seed_000041),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000042", poly_rotate_area_invariant_seed_000042),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000043", poly_rotate_area_invariant_seed_000043),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000044", poly_rotate_area_invariant_seed_000044),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000045", poly_rotate_area_invariant_seed_000045),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000046", poly_rotate_area_invariant_seed_000046),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000047", poly_rotate_area_invariant_seed_000047),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000048", poly_rotate_area_invariant_seed_000048),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000049", poly_rotate_area_invariant_seed_000049),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000050", poly_rotate_area_invariant_seed_000050),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000051", poly_rotate_area_invariant_seed_000051),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000052", poly_rotate_area_invariant_seed_000052),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000053", poly_rotate_area_invariant_seed_000053),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000054", poly_rotate_area_invariant_seed_000054),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000055", poly_rotate_area_invariant_seed_000055),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000056", poly_rotate_area_invariant_seed_000056),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000057", poly_rotate_area_invariant_seed_000057),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000058", poly_rotate_area_invariant_seed_000058),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000059", poly_rotate_area_invariant_seed_000059),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000060", poly_rotate_area_invariant_seed_000060),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000061", poly_rotate_area_invariant_seed_000061),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000062", poly_rotate_area_invariant_seed_000062),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000063", poly_rotate_area_invariant_seed_000063),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000064", poly_rotate_area_invariant_seed_000064),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000065", poly_rotate_area_invariant_seed_000065),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000066", poly_rotate_area_invariant_seed_000066),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000067", poly_rotate_area_invariant_seed_000067),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000068", poly_rotate_area_invariant_seed_000068),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000069", poly_rotate_area_invariant_seed_000069),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000070", poly_rotate_area_invariant_seed_000070),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000071", poly_rotate_area_invariant_seed_000071),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000072", poly_rotate_area_invariant_seed_000072),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000073", poly_rotate_area_invariant_seed_000073),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000074", poly_rotate_area_invariant_seed_000074),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000075", poly_rotate_area_invariant_seed_000075),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000076", poly_rotate_area_invariant_seed_000076),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000077", poly_rotate_area_invariant_seed_000077),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000078", poly_rotate_area_invariant_seed_000078),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000079", poly_rotate_area_invariant_seed_000079),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000080", poly_rotate_area_invariant_seed_000080),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000081", poly_rotate_area_invariant_seed_000081),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000082", poly_rotate_area_invariant_seed_000082),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000083", poly_rotate_area_invariant_seed_000083),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000084", poly_rotate_area_invariant_seed_000084),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000085", poly_rotate_area_invariant_seed_000085),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000086", poly_rotate_area_invariant_seed_000086),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000087", poly_rotate_area_invariant_seed_000087),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000088", poly_rotate_area_invariant_seed_000088),
        ("property_campaigns_2::tests::poly_rotate_area_invariant_seed_000089", poly_rotate_area_invariant_seed_000089),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000000", poly_winding_reversal_sign_flip_seed_000000),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000001", poly_winding_reversal_sign_flip_seed_000001),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000002", poly_winding_reversal_sign_flip_seed_000002),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000003", poly_winding_reversal_sign_flip_seed_000003),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000004", poly_winding_reversal_sign_flip_seed_000004),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000005", poly_winding_reversal_sign_flip_seed_000005),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000006", poly_winding_reversal_sign_flip_seed_000006),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000007", poly_winding_reversal_sign_flip_seed_000007),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000008", poly_winding_reversal_sign_flip_seed_000008),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000009", poly_winding_reversal_sign_flip_seed_000009),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000010", poly_winding_reversal_sign_flip_seed_000010),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000011", poly_winding_reversal_sign_flip_seed_000011),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000012", poly_winding_reversal_sign_flip_seed_000012),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000013", poly_winding_reversal_sign_flip_seed_000013),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000014", poly_winding_reversal_sign_flip_seed_000014),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000015", poly_winding_reversal_sign_flip_seed_000015),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000016", poly_winding_reversal_sign_flip_seed_000016),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000017", poly_winding_reversal_sign_flip_seed_000017),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000018", poly_winding_reversal_sign_flip_seed_000018),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000019", poly_winding_reversal_sign_flip_seed_000019),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000020", poly_winding_reversal_sign_flip_seed_000020),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000021", poly_winding_reversal_sign_flip_seed_000021),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000022", poly_winding_reversal_sign_flip_seed_000022),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000023", poly_winding_reversal_sign_flip_seed_000023),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000024", poly_winding_reversal_sign_flip_seed_000024),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000025", poly_winding_reversal_sign_flip_seed_000025),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000026", poly_winding_reversal_sign_flip_seed_000026),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000027", poly_winding_reversal_sign_flip_seed_000027),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000028", poly_winding_reversal_sign_flip_seed_000028),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000029", poly_winding_reversal_sign_flip_seed_000029),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000030", poly_winding_reversal_sign_flip_seed_000030),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000031", poly_winding_reversal_sign_flip_seed_000031),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000032", poly_winding_reversal_sign_flip_seed_000032),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000033", poly_winding_reversal_sign_flip_seed_000033),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000034", poly_winding_reversal_sign_flip_seed_000034),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000035", poly_winding_reversal_sign_flip_seed_000035),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000036", poly_winding_reversal_sign_flip_seed_000036),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000037", poly_winding_reversal_sign_flip_seed_000037),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000038", poly_winding_reversal_sign_flip_seed_000038),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000039", poly_winding_reversal_sign_flip_seed_000039),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000040", poly_winding_reversal_sign_flip_seed_000040),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000041", poly_winding_reversal_sign_flip_seed_000041),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000042", poly_winding_reversal_sign_flip_seed_000042),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000043", poly_winding_reversal_sign_flip_seed_000043),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000044", poly_winding_reversal_sign_flip_seed_000044),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000045", poly_winding_reversal_sign_flip_seed_000045),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000046", poly_winding_reversal_sign_flip_seed_000046),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000047", poly_winding_reversal_sign_flip_seed_000047),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000048", poly_winding_reversal_sign_flip_seed_000048),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000049", poly_winding_reversal_sign_flip_seed_000049),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000050", poly_winding_reversal_sign_flip_seed_000050),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000051", poly_winding_reversal_sign_flip_seed_000051),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000052", poly_winding_reversal_sign_flip_seed_000052),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000053", poly_winding_reversal_sign_flip_seed_000053),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000054", poly_winding_reversal_sign_flip_seed_000054),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000055", poly_winding_reversal_sign_flip_seed_000055),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000056", poly_winding_reversal_sign_flip_seed_000056),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000057", poly_winding_reversal_sign_flip_seed_000057),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000058", poly_winding_reversal_sign_flip_seed_000058),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000059", poly_winding_reversal_sign_flip_seed_000059),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000060", poly_winding_reversal_sign_flip_seed_000060),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000061", poly_winding_reversal_sign_flip_seed_000061),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000062", poly_winding_reversal_sign_flip_seed_000062),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000063", poly_winding_reversal_sign_flip_seed_000063),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000064", poly_winding_reversal_sign_flip_seed_000064),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000065", poly_winding_reversal_sign_flip_seed_000065),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000066", poly_winding_reversal_sign_flip_seed_000066),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000067", poly_winding_reversal_sign_flip_seed_000067),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000068", poly_winding_reversal_sign_flip_seed_000068),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000069", poly_winding_reversal_sign_flip_seed_000069),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000070", poly_winding_reversal_sign_flip_seed_000070),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000071", poly_winding_reversal_sign_flip_seed_000071),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000072", poly_winding_reversal_sign_flip_seed_000072),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000073", poly_winding_reversal_sign_flip_seed_000073),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000074", poly_winding_reversal_sign_flip_seed_000074),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000075", poly_winding_reversal_sign_flip_seed_000075),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000076", poly_winding_reversal_sign_flip_seed_000076),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000077", poly_winding_reversal_sign_flip_seed_000077),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000078", poly_winding_reversal_sign_flip_seed_000078),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000079", poly_winding_reversal_sign_flip_seed_000079),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000080", poly_winding_reversal_sign_flip_seed_000080),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000081", poly_winding_reversal_sign_flip_seed_000081),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000082", poly_winding_reversal_sign_flip_seed_000082),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000083", poly_winding_reversal_sign_flip_seed_000083),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000084", poly_winding_reversal_sign_flip_seed_000084),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000085", poly_winding_reversal_sign_flip_seed_000085),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000086", poly_winding_reversal_sign_flip_seed_000086),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000087", poly_winding_reversal_sign_flip_seed_000087),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000088", poly_winding_reversal_sign_flip_seed_000088),
        ("property_campaigns_2::tests::poly_winding_reversal_sign_flip_seed_000089", poly_winding_reversal_sign_flip_seed_000089),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000000", poly_fan_triangulation_additivity_seed_000000),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000001", poly_fan_triangulation_additivity_seed_000001),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000002", poly_fan_triangulation_additivity_seed_000002),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000003", poly_fan_triangulation_additivity_seed_000003),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000004", poly_fan_triangulation_additivity_seed_000004),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000005", poly_fan_triangulation_additivity_seed_000005),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000006", poly_fan_triangulation_additivity_seed_000006),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000007", poly_fan_triangulation_additivity_seed_000007),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000008", poly_fan_triangulation_additivity_seed_000008),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000009", poly_fan_triangulation_additivity_seed_000009),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000010", poly_fan_triangulation_additivity_seed_000010),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000011", poly_fan_triangulation_additivity_seed_000011),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000012", poly_fan_triangulation_additivity_seed_000012),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000013", poly_fan_triangulation_additivity_seed_000013),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000014", poly_fan_triangulation_additivity_seed_000014),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000015", poly_fan_triangulation_additivity_seed_000015),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000016", poly_fan_triangulation_additivity_seed_000016),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000017", poly_fan_triangulation_additivity_seed_000017),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000018", poly_fan_triangulation_additivity_seed_000018),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000019", poly_fan_triangulation_additivity_seed_000019),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000020", poly_fan_triangulation_additivity_seed_000020),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000021", poly_fan_triangulation_additivity_seed_000021),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000022", poly_fan_triangulation_additivity_seed_000022),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000023", poly_fan_triangulation_additivity_seed_000023),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000024", poly_fan_triangulation_additivity_seed_000024),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000025", poly_fan_triangulation_additivity_seed_000025),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000026", poly_fan_triangulation_additivity_seed_000026),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000027", poly_fan_triangulation_additivity_seed_000027),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000028", poly_fan_triangulation_additivity_seed_000028),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000029", poly_fan_triangulation_additivity_seed_000029),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000030", poly_fan_triangulation_additivity_seed_000030),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000031", poly_fan_triangulation_additivity_seed_000031),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000032", poly_fan_triangulation_additivity_seed_000032),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000033", poly_fan_triangulation_additivity_seed_000033),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000034", poly_fan_triangulation_additivity_seed_000034),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000035", poly_fan_triangulation_additivity_seed_000035),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000036", poly_fan_triangulation_additivity_seed_000036),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000037", poly_fan_triangulation_additivity_seed_000037),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000038", poly_fan_triangulation_additivity_seed_000038),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000039", poly_fan_triangulation_additivity_seed_000039),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000040", poly_fan_triangulation_additivity_seed_000040),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000041", poly_fan_triangulation_additivity_seed_000041),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000042", poly_fan_triangulation_additivity_seed_000042),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000043", poly_fan_triangulation_additivity_seed_000043),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000044", poly_fan_triangulation_additivity_seed_000044),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000045", poly_fan_triangulation_additivity_seed_000045),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000046", poly_fan_triangulation_additivity_seed_000046),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000047", poly_fan_triangulation_additivity_seed_000047),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000048", poly_fan_triangulation_additivity_seed_000048),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000049", poly_fan_triangulation_additivity_seed_000049),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000050", poly_fan_triangulation_additivity_seed_000050),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000051", poly_fan_triangulation_additivity_seed_000051),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000052", poly_fan_triangulation_additivity_seed_000052),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000053", poly_fan_triangulation_additivity_seed_000053),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000054", poly_fan_triangulation_additivity_seed_000054),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000055", poly_fan_triangulation_additivity_seed_000055),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000056", poly_fan_triangulation_additivity_seed_000056),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000057", poly_fan_triangulation_additivity_seed_000057),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000058", poly_fan_triangulation_additivity_seed_000058),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000059", poly_fan_triangulation_additivity_seed_000059),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000060", poly_fan_triangulation_additivity_seed_000060),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000061", poly_fan_triangulation_additivity_seed_000061),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000062", poly_fan_triangulation_additivity_seed_000062),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000063", poly_fan_triangulation_additivity_seed_000063),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000064", poly_fan_triangulation_additivity_seed_000064),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000065", poly_fan_triangulation_additivity_seed_000065),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000066", poly_fan_triangulation_additivity_seed_000066),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000067", poly_fan_triangulation_additivity_seed_000067),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000068", poly_fan_triangulation_additivity_seed_000068),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000069", poly_fan_triangulation_additivity_seed_000069),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000070", poly_fan_triangulation_additivity_seed_000070),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000071", poly_fan_triangulation_additivity_seed_000071),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000072", poly_fan_triangulation_additivity_seed_000072),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000073", poly_fan_triangulation_additivity_seed_000073),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000074", poly_fan_triangulation_additivity_seed_000074),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000075", poly_fan_triangulation_additivity_seed_000075),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000076", poly_fan_triangulation_additivity_seed_000076),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000077", poly_fan_triangulation_additivity_seed_000077),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000078", poly_fan_triangulation_additivity_seed_000078),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000079", poly_fan_triangulation_additivity_seed_000079),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000080", poly_fan_triangulation_additivity_seed_000080),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000081", poly_fan_triangulation_additivity_seed_000081),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000082", poly_fan_triangulation_additivity_seed_000082),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000083", poly_fan_triangulation_additivity_seed_000083),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000084", poly_fan_triangulation_additivity_seed_000084),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000085", poly_fan_triangulation_additivity_seed_000085),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000086", poly_fan_triangulation_additivity_seed_000086),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000087", poly_fan_triangulation_additivity_seed_000087),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000088", poly_fan_triangulation_additivity_seed_000088),
        ("property_campaigns_2::tests::poly_fan_triangulation_additivity_seed_000089", poly_fan_triangulation_additivity_seed_000089),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000000", poly_center_and_far_point_containment_seed_000000),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000001", poly_center_and_far_point_containment_seed_000001),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000002", poly_center_and_far_point_containment_seed_000002),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000003", poly_center_and_far_point_containment_seed_000003),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000004", poly_center_and_far_point_containment_seed_000004),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000005", poly_center_and_far_point_containment_seed_000005),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000006", poly_center_and_far_point_containment_seed_000006),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000007", poly_center_and_far_point_containment_seed_000007),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000008", poly_center_and_far_point_containment_seed_000008),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000009", poly_center_and_far_point_containment_seed_000009),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000010", poly_center_and_far_point_containment_seed_000010),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000011", poly_center_and_far_point_containment_seed_000011),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000012", poly_center_and_far_point_containment_seed_000012),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000013", poly_center_and_far_point_containment_seed_000013),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000014", poly_center_and_far_point_containment_seed_000014),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000015", poly_center_and_far_point_containment_seed_000015),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000016", poly_center_and_far_point_containment_seed_000016),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000017", poly_center_and_far_point_containment_seed_000017),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000018", poly_center_and_far_point_containment_seed_000018),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000019", poly_center_and_far_point_containment_seed_000019),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000020", poly_center_and_far_point_containment_seed_000020),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000021", poly_center_and_far_point_containment_seed_000021),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000022", poly_center_and_far_point_containment_seed_000022),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000023", poly_center_and_far_point_containment_seed_000023),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000024", poly_center_and_far_point_containment_seed_000024),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000025", poly_center_and_far_point_containment_seed_000025),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000026", poly_center_and_far_point_containment_seed_000026),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000027", poly_center_and_far_point_containment_seed_000027),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000028", poly_center_and_far_point_containment_seed_000028),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000029", poly_center_and_far_point_containment_seed_000029),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000030", poly_center_and_far_point_containment_seed_000030),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000031", poly_center_and_far_point_containment_seed_000031),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000032", poly_center_and_far_point_containment_seed_000032),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000033", poly_center_and_far_point_containment_seed_000033),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000034", poly_center_and_far_point_containment_seed_000034),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000035", poly_center_and_far_point_containment_seed_000035),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000036", poly_center_and_far_point_containment_seed_000036),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000037", poly_center_and_far_point_containment_seed_000037),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000038", poly_center_and_far_point_containment_seed_000038),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000039", poly_center_and_far_point_containment_seed_000039),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000040", poly_center_and_far_point_containment_seed_000040),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000041", poly_center_and_far_point_containment_seed_000041),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000042", poly_center_and_far_point_containment_seed_000042),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000043", poly_center_and_far_point_containment_seed_000043),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000044", poly_center_and_far_point_containment_seed_000044),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000045", poly_center_and_far_point_containment_seed_000045),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000046", poly_center_and_far_point_containment_seed_000046),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000047", poly_center_and_far_point_containment_seed_000047),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000048", poly_center_and_far_point_containment_seed_000048),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000049", poly_center_and_far_point_containment_seed_000049),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000050", poly_center_and_far_point_containment_seed_000050),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000051", poly_center_and_far_point_containment_seed_000051),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000052", poly_center_and_far_point_containment_seed_000052),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000053", poly_center_and_far_point_containment_seed_000053),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000054", poly_center_and_far_point_containment_seed_000054),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000055", poly_center_and_far_point_containment_seed_000055),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000056", poly_center_and_far_point_containment_seed_000056),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000057", poly_center_and_far_point_containment_seed_000057),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000058", poly_center_and_far_point_containment_seed_000058),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000059", poly_center_and_far_point_containment_seed_000059),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000060", poly_center_and_far_point_containment_seed_000060),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000061", poly_center_and_far_point_containment_seed_000061),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000062", poly_center_and_far_point_containment_seed_000062),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000063", poly_center_and_far_point_containment_seed_000063),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000064", poly_center_and_far_point_containment_seed_000064),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000065", poly_center_and_far_point_containment_seed_000065),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000066", poly_center_and_far_point_containment_seed_000066),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000067", poly_center_and_far_point_containment_seed_000067),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000068", poly_center_and_far_point_containment_seed_000068),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000069", poly_center_and_far_point_containment_seed_000069),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000070", poly_center_and_far_point_containment_seed_000070),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000071", poly_center_and_far_point_containment_seed_000071),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000072", poly_center_and_far_point_containment_seed_000072),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000073", poly_center_and_far_point_containment_seed_000073),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000074", poly_center_and_far_point_containment_seed_000074),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000075", poly_center_and_far_point_containment_seed_000075),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000076", poly_center_and_far_point_containment_seed_000076),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000077", poly_center_and_far_point_containment_seed_000077),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000078", poly_center_and_far_point_containment_seed_000078),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000079", poly_center_and_far_point_containment_seed_000079),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000080", poly_center_and_far_point_containment_seed_000080),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000081", poly_center_and_far_point_containment_seed_000081),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000082", poly_center_and_far_point_containment_seed_000082),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000083", poly_center_and_far_point_containment_seed_000083),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000084", poly_center_and_far_point_containment_seed_000084),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000085", poly_center_and_far_point_containment_seed_000085),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000086", poly_center_and_far_point_containment_seed_000086),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000087", poly_center_and_far_point_containment_seed_000087),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000088", poly_center_and_far_point_containment_seed_000088),
        ("property_campaigns_2::tests::poly_center_and_far_point_containment_seed_000089", poly_center_and_far_point_containment_seed_000089),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000000", poly_perimeter_scale_linear_seed_000000),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000001", poly_perimeter_scale_linear_seed_000001),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000002", poly_perimeter_scale_linear_seed_000002),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000003", poly_perimeter_scale_linear_seed_000003),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000004", poly_perimeter_scale_linear_seed_000004),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000005", poly_perimeter_scale_linear_seed_000005),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000006", poly_perimeter_scale_linear_seed_000006),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000007", poly_perimeter_scale_linear_seed_000007),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000008", poly_perimeter_scale_linear_seed_000008),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000009", poly_perimeter_scale_linear_seed_000009),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000010", poly_perimeter_scale_linear_seed_000010),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000011", poly_perimeter_scale_linear_seed_000011),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000012", poly_perimeter_scale_linear_seed_000012),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000013", poly_perimeter_scale_linear_seed_000013),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000014", poly_perimeter_scale_linear_seed_000014),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000015", poly_perimeter_scale_linear_seed_000015),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000016", poly_perimeter_scale_linear_seed_000016),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000017", poly_perimeter_scale_linear_seed_000017),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000018", poly_perimeter_scale_linear_seed_000018),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000019", poly_perimeter_scale_linear_seed_000019),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000020", poly_perimeter_scale_linear_seed_000020),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000021", poly_perimeter_scale_linear_seed_000021),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000022", poly_perimeter_scale_linear_seed_000022),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000023", poly_perimeter_scale_linear_seed_000023),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000024", poly_perimeter_scale_linear_seed_000024),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000025", poly_perimeter_scale_linear_seed_000025),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000026", poly_perimeter_scale_linear_seed_000026),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000027", poly_perimeter_scale_linear_seed_000027),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000028", poly_perimeter_scale_linear_seed_000028),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000029", poly_perimeter_scale_linear_seed_000029),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000030", poly_perimeter_scale_linear_seed_000030),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000031", poly_perimeter_scale_linear_seed_000031),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000032", poly_perimeter_scale_linear_seed_000032),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000033", poly_perimeter_scale_linear_seed_000033),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000034", poly_perimeter_scale_linear_seed_000034),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000035", poly_perimeter_scale_linear_seed_000035),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000036", poly_perimeter_scale_linear_seed_000036),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000037", poly_perimeter_scale_linear_seed_000037),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000038", poly_perimeter_scale_linear_seed_000038),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000039", poly_perimeter_scale_linear_seed_000039),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000040", poly_perimeter_scale_linear_seed_000040),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000041", poly_perimeter_scale_linear_seed_000041),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000042", poly_perimeter_scale_linear_seed_000042),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000043", poly_perimeter_scale_linear_seed_000043),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000044", poly_perimeter_scale_linear_seed_000044),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000045", poly_perimeter_scale_linear_seed_000045),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000046", poly_perimeter_scale_linear_seed_000046),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000047", poly_perimeter_scale_linear_seed_000047),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000048", poly_perimeter_scale_linear_seed_000048),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000049", poly_perimeter_scale_linear_seed_000049),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000050", poly_perimeter_scale_linear_seed_000050),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000051", poly_perimeter_scale_linear_seed_000051),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000052", poly_perimeter_scale_linear_seed_000052),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000053", poly_perimeter_scale_linear_seed_000053),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000054", poly_perimeter_scale_linear_seed_000054),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000055", poly_perimeter_scale_linear_seed_000055),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000056", poly_perimeter_scale_linear_seed_000056),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000057", poly_perimeter_scale_linear_seed_000057),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000058", poly_perimeter_scale_linear_seed_000058),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000059", poly_perimeter_scale_linear_seed_000059),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000060", poly_perimeter_scale_linear_seed_000060),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000061", poly_perimeter_scale_linear_seed_000061),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000062", poly_perimeter_scale_linear_seed_000062),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000063", poly_perimeter_scale_linear_seed_000063),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000064", poly_perimeter_scale_linear_seed_000064),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000065", poly_perimeter_scale_linear_seed_000065),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000066", poly_perimeter_scale_linear_seed_000066),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000067", poly_perimeter_scale_linear_seed_000067),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000068", poly_perimeter_scale_linear_seed_000068),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000069", poly_perimeter_scale_linear_seed_000069),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000070", poly_perimeter_scale_linear_seed_000070),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000071", poly_perimeter_scale_linear_seed_000071),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000072", poly_perimeter_scale_linear_seed_000072),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000073", poly_perimeter_scale_linear_seed_000073),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000074", poly_perimeter_scale_linear_seed_000074),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000075", poly_perimeter_scale_linear_seed_000075),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000076", poly_perimeter_scale_linear_seed_000076),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000077", poly_perimeter_scale_linear_seed_000077),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000078", poly_perimeter_scale_linear_seed_000078),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000079", poly_perimeter_scale_linear_seed_000079),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000080", poly_perimeter_scale_linear_seed_000080),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000081", poly_perimeter_scale_linear_seed_000081),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000082", poly_perimeter_scale_linear_seed_000082),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000083", poly_perimeter_scale_linear_seed_000083),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000084", poly_perimeter_scale_linear_seed_000084),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000085", poly_perimeter_scale_linear_seed_000085),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000086", poly_perimeter_scale_linear_seed_000086),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000087", poly_perimeter_scale_linear_seed_000087),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000088", poly_perimeter_scale_linear_seed_000088),
        ("property_campaigns_2::tests::poly_perimeter_scale_linear_seed_000089", poly_perimeter_scale_linear_seed_000089),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000000", ov_box_box_distance_symmetric_seed_000000),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000001", ov_box_box_distance_symmetric_seed_000001),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000002", ov_box_box_distance_symmetric_seed_000002),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000003", ov_box_box_distance_symmetric_seed_000003),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000004", ov_box_box_distance_symmetric_seed_000004),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000005", ov_box_box_distance_symmetric_seed_000005),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000006", ov_box_box_distance_symmetric_seed_000006),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000007", ov_box_box_distance_symmetric_seed_000007),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000008", ov_box_box_distance_symmetric_seed_000008),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000009", ov_box_box_distance_symmetric_seed_000009),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000010", ov_box_box_distance_symmetric_seed_000010),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000011", ov_box_box_distance_symmetric_seed_000011),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000012", ov_box_box_distance_symmetric_seed_000012),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000013", ov_box_box_distance_symmetric_seed_000013),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000014", ov_box_box_distance_symmetric_seed_000014),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000015", ov_box_box_distance_symmetric_seed_000015),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000016", ov_box_box_distance_symmetric_seed_000016),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000017", ov_box_box_distance_symmetric_seed_000017),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000018", ov_box_box_distance_symmetric_seed_000018),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000019", ov_box_box_distance_symmetric_seed_000019),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000020", ov_box_box_distance_symmetric_seed_000020),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000021", ov_box_box_distance_symmetric_seed_000021),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000022", ov_box_box_distance_symmetric_seed_000022),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000023", ov_box_box_distance_symmetric_seed_000023),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000024", ov_box_box_distance_symmetric_seed_000024),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000025", ov_box_box_distance_symmetric_seed_000025),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000026", ov_box_box_distance_symmetric_seed_000026),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000027", ov_box_box_distance_symmetric_seed_000027),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000028", ov_box_box_distance_symmetric_seed_000028),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000029", ov_box_box_distance_symmetric_seed_000029),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000030", ov_box_box_distance_symmetric_seed_000030),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000031", ov_box_box_distance_symmetric_seed_000031),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000032", ov_box_box_distance_symmetric_seed_000032),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000033", ov_box_box_distance_symmetric_seed_000033),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000034", ov_box_box_distance_symmetric_seed_000034),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000035", ov_box_box_distance_symmetric_seed_000035),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000036", ov_box_box_distance_symmetric_seed_000036),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000037", ov_box_box_distance_symmetric_seed_000037),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000038", ov_box_box_distance_symmetric_seed_000038),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000039", ov_box_box_distance_symmetric_seed_000039),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000040", ov_box_box_distance_symmetric_seed_000040),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000041", ov_box_box_distance_symmetric_seed_000041),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000042", ov_box_box_distance_symmetric_seed_000042),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000043", ov_box_box_distance_symmetric_seed_000043),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000044", ov_box_box_distance_symmetric_seed_000044),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000045", ov_box_box_distance_symmetric_seed_000045),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000046", ov_box_box_distance_symmetric_seed_000046),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000047", ov_box_box_distance_symmetric_seed_000047),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000048", ov_box_box_distance_symmetric_seed_000048),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000049", ov_box_box_distance_symmetric_seed_000049),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000050", ov_box_box_distance_symmetric_seed_000050),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000051", ov_box_box_distance_symmetric_seed_000051),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000052", ov_box_box_distance_symmetric_seed_000052),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000053", ov_box_box_distance_symmetric_seed_000053),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000054", ov_box_box_distance_symmetric_seed_000054),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000055", ov_box_box_distance_symmetric_seed_000055),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000056", ov_box_box_distance_symmetric_seed_000056),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000057", ov_box_box_distance_symmetric_seed_000057),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000058", ov_box_box_distance_symmetric_seed_000058),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000059", ov_box_box_distance_symmetric_seed_000059),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000060", ov_box_box_distance_symmetric_seed_000060),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000061", ov_box_box_distance_symmetric_seed_000061),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000062", ov_box_box_distance_symmetric_seed_000062),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000063", ov_box_box_distance_symmetric_seed_000063),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000064", ov_box_box_distance_symmetric_seed_000064),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000065", ov_box_box_distance_symmetric_seed_000065),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000066", ov_box_box_distance_symmetric_seed_000066),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000067", ov_box_box_distance_symmetric_seed_000067),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000068", ov_box_box_distance_symmetric_seed_000068),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000069", ov_box_box_distance_symmetric_seed_000069),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000070", ov_box_box_distance_symmetric_seed_000070),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000071", ov_box_box_distance_symmetric_seed_000071),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000072", ov_box_box_distance_symmetric_seed_000072),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000073", ov_box_box_distance_symmetric_seed_000073),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000074", ov_box_box_distance_symmetric_seed_000074),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000075", ov_box_box_distance_symmetric_seed_000075),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000076", ov_box_box_distance_symmetric_seed_000076),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000077", ov_box_box_distance_symmetric_seed_000077),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000078", ov_box_box_distance_symmetric_seed_000078),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000079", ov_box_box_distance_symmetric_seed_000079),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000080", ov_box_box_distance_symmetric_seed_000080),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000081", ov_box_box_distance_symmetric_seed_000081),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000082", ov_box_box_distance_symmetric_seed_000082),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000083", ov_box_box_distance_symmetric_seed_000083),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000084", ov_box_box_distance_symmetric_seed_000084),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000085", ov_box_box_distance_symmetric_seed_000085),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000086", ov_box_box_distance_symmetric_seed_000086),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000087", ov_box_box_distance_symmetric_seed_000087),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000088", ov_box_box_distance_symmetric_seed_000088),
        ("property_campaigns_2::tests::ov_box_box_distance_symmetric_seed_000089", ov_box_box_distance_symmetric_seed_000089),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000000", ov_component_overlap_symmetric_seed_000000),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000001", ov_component_overlap_symmetric_seed_000001),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000002", ov_component_overlap_symmetric_seed_000002),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000003", ov_component_overlap_symmetric_seed_000003),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000004", ov_component_overlap_symmetric_seed_000004),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000005", ov_component_overlap_symmetric_seed_000005),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000006", ov_component_overlap_symmetric_seed_000006),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000007", ov_component_overlap_symmetric_seed_000007),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000008", ov_component_overlap_symmetric_seed_000008),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000009", ov_component_overlap_symmetric_seed_000009),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000010", ov_component_overlap_symmetric_seed_000010),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000011", ov_component_overlap_symmetric_seed_000011),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000012", ov_component_overlap_symmetric_seed_000012),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000013", ov_component_overlap_symmetric_seed_000013),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000014", ov_component_overlap_symmetric_seed_000014),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000015", ov_component_overlap_symmetric_seed_000015),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000016", ov_component_overlap_symmetric_seed_000016),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000017", ov_component_overlap_symmetric_seed_000017),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000018", ov_component_overlap_symmetric_seed_000018),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000019", ov_component_overlap_symmetric_seed_000019),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000020", ov_component_overlap_symmetric_seed_000020),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000021", ov_component_overlap_symmetric_seed_000021),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000022", ov_component_overlap_symmetric_seed_000022),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000023", ov_component_overlap_symmetric_seed_000023),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000024", ov_component_overlap_symmetric_seed_000024),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000025", ov_component_overlap_symmetric_seed_000025),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000026", ov_component_overlap_symmetric_seed_000026),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000027", ov_component_overlap_symmetric_seed_000027),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000028", ov_component_overlap_symmetric_seed_000028),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000029", ov_component_overlap_symmetric_seed_000029),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000030", ov_component_overlap_symmetric_seed_000030),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000031", ov_component_overlap_symmetric_seed_000031),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000032", ov_component_overlap_symmetric_seed_000032),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000033", ov_component_overlap_symmetric_seed_000033),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000034", ov_component_overlap_symmetric_seed_000034),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000035", ov_component_overlap_symmetric_seed_000035),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000036", ov_component_overlap_symmetric_seed_000036),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000037", ov_component_overlap_symmetric_seed_000037),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000038", ov_component_overlap_symmetric_seed_000038),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000039", ov_component_overlap_symmetric_seed_000039),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000040", ov_component_overlap_symmetric_seed_000040),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000041", ov_component_overlap_symmetric_seed_000041),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000042", ov_component_overlap_symmetric_seed_000042),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000043", ov_component_overlap_symmetric_seed_000043),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000044", ov_component_overlap_symmetric_seed_000044),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000045", ov_component_overlap_symmetric_seed_000045),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000046", ov_component_overlap_symmetric_seed_000046),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000047", ov_component_overlap_symmetric_seed_000047),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000048", ov_component_overlap_symmetric_seed_000048),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000049", ov_component_overlap_symmetric_seed_000049),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000050", ov_component_overlap_symmetric_seed_000050),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000051", ov_component_overlap_symmetric_seed_000051),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000052", ov_component_overlap_symmetric_seed_000052),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000053", ov_component_overlap_symmetric_seed_000053),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000054", ov_component_overlap_symmetric_seed_000054),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000055", ov_component_overlap_symmetric_seed_000055),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000056", ov_component_overlap_symmetric_seed_000056),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000057", ov_component_overlap_symmetric_seed_000057),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000058", ov_component_overlap_symmetric_seed_000058),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000059", ov_component_overlap_symmetric_seed_000059),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000060", ov_component_overlap_symmetric_seed_000060),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000061", ov_component_overlap_symmetric_seed_000061),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000062", ov_component_overlap_symmetric_seed_000062),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000063", ov_component_overlap_symmetric_seed_000063),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000064", ov_component_overlap_symmetric_seed_000064),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000065", ov_component_overlap_symmetric_seed_000065),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000066", ov_component_overlap_symmetric_seed_000066),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000067", ov_component_overlap_symmetric_seed_000067),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000068", ov_component_overlap_symmetric_seed_000068),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000069", ov_component_overlap_symmetric_seed_000069),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000070", ov_component_overlap_symmetric_seed_000070),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000071", ov_component_overlap_symmetric_seed_000071),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000072", ov_component_overlap_symmetric_seed_000072),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000073", ov_component_overlap_symmetric_seed_000073),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000074", ov_component_overlap_symmetric_seed_000074),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000075", ov_component_overlap_symmetric_seed_000075),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000076", ov_component_overlap_symmetric_seed_000076),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000077", ov_component_overlap_symmetric_seed_000077),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000078", ov_component_overlap_symmetric_seed_000078),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000079", ov_component_overlap_symmetric_seed_000079),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000080", ov_component_overlap_symmetric_seed_000080),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000081", ov_component_overlap_symmetric_seed_000081),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000082", ov_component_overlap_symmetric_seed_000082),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000083", ov_component_overlap_symmetric_seed_000083),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000084", ov_component_overlap_symmetric_seed_000084),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000085", ov_component_overlap_symmetric_seed_000085),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000086", ov_component_overlap_symmetric_seed_000086),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000087", ov_component_overlap_symmetric_seed_000087),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000088", ov_component_overlap_symmetric_seed_000088),
        ("property_campaigns_2::tests::ov_component_overlap_symmetric_seed_000089", ov_component_overlap_symmetric_seed_000089),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000000", ov_translation_invariant_seed_000000),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000001", ov_translation_invariant_seed_000001),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000002", ov_translation_invariant_seed_000002),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000003", ov_translation_invariant_seed_000003),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000004", ov_translation_invariant_seed_000004),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000005", ov_translation_invariant_seed_000005),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000006", ov_translation_invariant_seed_000006),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000007", ov_translation_invariant_seed_000007),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000008", ov_translation_invariant_seed_000008),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000009", ov_translation_invariant_seed_000009),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000010", ov_translation_invariant_seed_000010),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000011", ov_translation_invariant_seed_000011),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000012", ov_translation_invariant_seed_000012),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000013", ov_translation_invariant_seed_000013),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000014", ov_translation_invariant_seed_000014),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000015", ov_translation_invariant_seed_000015),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000016", ov_translation_invariant_seed_000016),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000017", ov_translation_invariant_seed_000017),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000018", ov_translation_invariant_seed_000018),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000019", ov_translation_invariant_seed_000019),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000020", ov_translation_invariant_seed_000020),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000021", ov_translation_invariant_seed_000021),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000022", ov_translation_invariant_seed_000022),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000023", ov_translation_invariant_seed_000023),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000024", ov_translation_invariant_seed_000024),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000025", ov_translation_invariant_seed_000025),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000026", ov_translation_invariant_seed_000026),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000027", ov_translation_invariant_seed_000027),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000028", ov_translation_invariant_seed_000028),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000029", ov_translation_invariant_seed_000029),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000030", ov_translation_invariant_seed_000030),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000031", ov_translation_invariant_seed_000031),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000032", ov_translation_invariant_seed_000032),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000033", ov_translation_invariant_seed_000033),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000034", ov_translation_invariant_seed_000034),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000035", ov_translation_invariant_seed_000035),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000036", ov_translation_invariant_seed_000036),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000037", ov_translation_invariant_seed_000037),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000038", ov_translation_invariant_seed_000038),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000039", ov_translation_invariant_seed_000039),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000040", ov_translation_invariant_seed_000040),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000041", ov_translation_invariant_seed_000041),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000042", ov_translation_invariant_seed_000042),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000043", ov_translation_invariant_seed_000043),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000044", ov_translation_invariant_seed_000044),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000045", ov_translation_invariant_seed_000045),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000046", ov_translation_invariant_seed_000046),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000047", ov_translation_invariant_seed_000047),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000048", ov_translation_invariant_seed_000048),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000049", ov_translation_invariant_seed_000049),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000050", ov_translation_invariant_seed_000050),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000051", ov_translation_invariant_seed_000051),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000052", ov_translation_invariant_seed_000052),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000053", ov_translation_invariant_seed_000053),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000054", ov_translation_invariant_seed_000054),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000055", ov_translation_invariant_seed_000055),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000056", ov_translation_invariant_seed_000056),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000057", ov_translation_invariant_seed_000057),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000058", ov_translation_invariant_seed_000058),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000059", ov_translation_invariant_seed_000059),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000060", ov_translation_invariant_seed_000060),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000061", ov_translation_invariant_seed_000061),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000062", ov_translation_invariant_seed_000062),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000063", ov_translation_invariant_seed_000063),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000064", ov_translation_invariant_seed_000064),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000065", ov_translation_invariant_seed_000065),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000066", ov_translation_invariant_seed_000066),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000067", ov_translation_invariant_seed_000067),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000068", ov_translation_invariant_seed_000068),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000069", ov_translation_invariant_seed_000069),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000070", ov_translation_invariant_seed_000070),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000071", ov_translation_invariant_seed_000071),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000072", ov_translation_invariant_seed_000072),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000073", ov_translation_invariant_seed_000073),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000074", ov_translation_invariant_seed_000074),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000075", ov_translation_invariant_seed_000075),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000076", ov_translation_invariant_seed_000076),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000077", ov_translation_invariant_seed_000077),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000078", ov_translation_invariant_seed_000078),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000079", ov_translation_invariant_seed_000079),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000080", ov_translation_invariant_seed_000080),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000081", ov_translation_invariant_seed_000081),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000082", ov_translation_invariant_seed_000082),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000083", ov_translation_invariant_seed_000083),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000084", ov_translation_invariant_seed_000084),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000085", ov_translation_invariant_seed_000085),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000086", ov_translation_invariant_seed_000086),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000087", ov_translation_invariant_seed_000087),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000088", ov_translation_invariant_seed_000088),
        ("property_campaigns_2::tests::ov_translation_invariant_seed_000089", ov_translation_invariant_seed_000089),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000000", ov_self_overlap_total_seed_000000),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000001", ov_self_overlap_total_seed_000001),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000002", ov_self_overlap_total_seed_000002),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000003", ov_self_overlap_total_seed_000003),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000004", ov_self_overlap_total_seed_000004),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000005", ov_self_overlap_total_seed_000005),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000006", ov_self_overlap_total_seed_000006),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000007", ov_self_overlap_total_seed_000007),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000008", ov_self_overlap_total_seed_000008),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000009", ov_self_overlap_total_seed_000009),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000010", ov_self_overlap_total_seed_000010),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000011", ov_self_overlap_total_seed_000011),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000012", ov_self_overlap_total_seed_000012),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000013", ov_self_overlap_total_seed_000013),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000014", ov_self_overlap_total_seed_000014),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000015", ov_self_overlap_total_seed_000015),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000016", ov_self_overlap_total_seed_000016),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000017", ov_self_overlap_total_seed_000017),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000018", ov_self_overlap_total_seed_000018),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000019", ov_self_overlap_total_seed_000019),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000020", ov_self_overlap_total_seed_000020),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000021", ov_self_overlap_total_seed_000021),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000022", ov_self_overlap_total_seed_000022),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000023", ov_self_overlap_total_seed_000023),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000024", ov_self_overlap_total_seed_000024),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000025", ov_self_overlap_total_seed_000025),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000026", ov_self_overlap_total_seed_000026),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000027", ov_self_overlap_total_seed_000027),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000028", ov_self_overlap_total_seed_000028),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000029", ov_self_overlap_total_seed_000029),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000030", ov_self_overlap_total_seed_000030),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000031", ov_self_overlap_total_seed_000031),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000032", ov_self_overlap_total_seed_000032),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000033", ov_self_overlap_total_seed_000033),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000034", ov_self_overlap_total_seed_000034),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000035", ov_self_overlap_total_seed_000035),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000036", ov_self_overlap_total_seed_000036),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000037", ov_self_overlap_total_seed_000037),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000038", ov_self_overlap_total_seed_000038),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000039", ov_self_overlap_total_seed_000039),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000040", ov_self_overlap_total_seed_000040),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000041", ov_self_overlap_total_seed_000041),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000042", ov_self_overlap_total_seed_000042),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000043", ov_self_overlap_total_seed_000043),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000044", ov_self_overlap_total_seed_000044),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000045", ov_self_overlap_total_seed_000045),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000046", ov_self_overlap_total_seed_000046),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000047", ov_self_overlap_total_seed_000047),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000048", ov_self_overlap_total_seed_000048),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000049", ov_self_overlap_total_seed_000049),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000050", ov_self_overlap_total_seed_000050),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000051", ov_self_overlap_total_seed_000051),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000052", ov_self_overlap_total_seed_000052),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000053", ov_self_overlap_total_seed_000053),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000054", ov_self_overlap_total_seed_000054),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000055", ov_self_overlap_total_seed_000055),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000056", ov_self_overlap_total_seed_000056),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000057", ov_self_overlap_total_seed_000057),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000058", ov_self_overlap_total_seed_000058),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000059", ov_self_overlap_total_seed_000059),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000060", ov_self_overlap_total_seed_000060),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000061", ov_self_overlap_total_seed_000061),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000062", ov_self_overlap_total_seed_000062),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000063", ov_self_overlap_total_seed_000063),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000064", ov_self_overlap_total_seed_000064),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000065", ov_self_overlap_total_seed_000065),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000066", ov_self_overlap_total_seed_000066),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000067", ov_self_overlap_total_seed_000067),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000068", ov_self_overlap_total_seed_000068),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000069", ov_self_overlap_total_seed_000069),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000070", ov_self_overlap_total_seed_000070),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000071", ov_self_overlap_total_seed_000071),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000072", ov_self_overlap_total_seed_000072),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000073", ov_self_overlap_total_seed_000073),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000074", ov_self_overlap_total_seed_000074),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000075", ov_self_overlap_total_seed_000075),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000076", ov_self_overlap_total_seed_000076),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000077", ov_self_overlap_total_seed_000077),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000078", ov_self_overlap_total_seed_000078),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000079", ov_self_overlap_total_seed_000079),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000080", ov_self_overlap_total_seed_000080),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000081", ov_self_overlap_total_seed_000081),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000082", ov_self_overlap_total_seed_000082),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000083", ov_self_overlap_total_seed_000083),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000084", ov_self_overlap_total_seed_000084),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000085", ov_self_overlap_total_seed_000085),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000086", ov_self_overlap_total_seed_000086),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000087", ov_self_overlap_total_seed_000087),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000088", ov_self_overlap_total_seed_000088),
        ("property_campaigns_2::tests::ov_self_overlap_total_seed_000089", ov_self_overlap_total_seed_000089),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000000", ov_self_distance_exact_seed_000000),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000001", ov_self_distance_exact_seed_000001),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000002", ov_self_distance_exact_seed_000002),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000003", ov_self_distance_exact_seed_000003),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000004", ov_self_distance_exact_seed_000004),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000005", ov_self_distance_exact_seed_000005),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000006", ov_self_distance_exact_seed_000006),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000007", ov_self_distance_exact_seed_000007),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000008", ov_self_distance_exact_seed_000008),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000009", ov_self_distance_exact_seed_000009),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000010", ov_self_distance_exact_seed_000010),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000011", ov_self_distance_exact_seed_000011),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000012", ov_self_distance_exact_seed_000012),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000013", ov_self_distance_exact_seed_000013),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000014", ov_self_distance_exact_seed_000014),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000015", ov_self_distance_exact_seed_000015),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000016", ov_self_distance_exact_seed_000016),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000017", ov_self_distance_exact_seed_000017),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000018", ov_self_distance_exact_seed_000018),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000019", ov_self_distance_exact_seed_000019),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000020", ov_self_distance_exact_seed_000020),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000021", ov_self_distance_exact_seed_000021),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000022", ov_self_distance_exact_seed_000022),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000023", ov_self_distance_exact_seed_000023),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000024", ov_self_distance_exact_seed_000024),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000025", ov_self_distance_exact_seed_000025),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000026", ov_self_distance_exact_seed_000026),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000027", ov_self_distance_exact_seed_000027),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000028", ov_self_distance_exact_seed_000028),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000029", ov_self_distance_exact_seed_000029),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000030", ov_self_distance_exact_seed_000030),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000031", ov_self_distance_exact_seed_000031),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000032", ov_self_distance_exact_seed_000032),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000033", ov_self_distance_exact_seed_000033),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000034", ov_self_distance_exact_seed_000034),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000035", ov_self_distance_exact_seed_000035),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000036", ov_self_distance_exact_seed_000036),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000037", ov_self_distance_exact_seed_000037),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000038", ov_self_distance_exact_seed_000038),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000039", ov_self_distance_exact_seed_000039),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000040", ov_self_distance_exact_seed_000040),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000041", ov_self_distance_exact_seed_000041),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000042", ov_self_distance_exact_seed_000042),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000043", ov_self_distance_exact_seed_000043),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000044", ov_self_distance_exact_seed_000044),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000045", ov_self_distance_exact_seed_000045),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000046", ov_self_distance_exact_seed_000046),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000047", ov_self_distance_exact_seed_000047),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000048", ov_self_distance_exact_seed_000048),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000049", ov_self_distance_exact_seed_000049),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000050", ov_self_distance_exact_seed_000050),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000051", ov_self_distance_exact_seed_000051),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000052", ov_self_distance_exact_seed_000052),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000053", ov_self_distance_exact_seed_000053),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000054", ov_self_distance_exact_seed_000054),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000055", ov_self_distance_exact_seed_000055),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000056", ov_self_distance_exact_seed_000056),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000057", ov_self_distance_exact_seed_000057),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000058", ov_self_distance_exact_seed_000058),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000059", ov_self_distance_exact_seed_000059),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000060", ov_self_distance_exact_seed_000060),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000061", ov_self_distance_exact_seed_000061),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000062", ov_self_distance_exact_seed_000062),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000063", ov_self_distance_exact_seed_000063),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000064", ov_self_distance_exact_seed_000064),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000065", ov_self_distance_exact_seed_000065),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000066", ov_self_distance_exact_seed_000066),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000067", ov_self_distance_exact_seed_000067),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000068", ov_self_distance_exact_seed_000068),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000069", ov_self_distance_exact_seed_000069),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000070", ov_self_distance_exact_seed_000070),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000071", ov_self_distance_exact_seed_000071),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000072", ov_self_distance_exact_seed_000072),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000073", ov_self_distance_exact_seed_000073),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000074", ov_self_distance_exact_seed_000074),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000075", ov_self_distance_exact_seed_000075),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000076", ov_self_distance_exact_seed_000076),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000077", ov_self_distance_exact_seed_000077),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000078", ov_self_distance_exact_seed_000078),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000079", ov_self_distance_exact_seed_000079),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000080", ov_self_distance_exact_seed_000080),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000081", ov_self_distance_exact_seed_000081),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000082", ov_self_distance_exact_seed_000082),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000083", ov_self_distance_exact_seed_000083),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000084", ov_self_distance_exact_seed_000084),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000085", ov_self_distance_exact_seed_000085),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000086", ov_self_distance_exact_seed_000086),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000087", ov_self_distance_exact_seed_000087),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000088", ov_self_distance_exact_seed_000088),
        ("property_campaigns_2::tests::ov_self_distance_exact_seed_000089", ov_self_distance_exact_seed_000089),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000000", ov_separation_monotonic_seed_000000),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000001", ov_separation_monotonic_seed_000001),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000002", ov_separation_monotonic_seed_000002),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000003", ov_separation_monotonic_seed_000003),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000004", ov_separation_monotonic_seed_000004),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000005", ov_separation_monotonic_seed_000005),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000006", ov_separation_monotonic_seed_000006),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000007", ov_separation_monotonic_seed_000007),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000008", ov_separation_monotonic_seed_000008),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000009", ov_separation_monotonic_seed_000009),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000010", ov_separation_monotonic_seed_000010),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000011", ov_separation_monotonic_seed_000011),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000012", ov_separation_monotonic_seed_000012),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000013", ov_separation_monotonic_seed_000013),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000014", ov_separation_monotonic_seed_000014),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000015", ov_separation_monotonic_seed_000015),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000016", ov_separation_monotonic_seed_000016),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000017", ov_separation_monotonic_seed_000017),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000018", ov_separation_monotonic_seed_000018),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000019", ov_separation_monotonic_seed_000019),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000020", ov_separation_monotonic_seed_000020),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000021", ov_separation_monotonic_seed_000021),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000022", ov_separation_monotonic_seed_000022),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000023", ov_separation_monotonic_seed_000023),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000024", ov_separation_monotonic_seed_000024),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000025", ov_separation_monotonic_seed_000025),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000026", ov_separation_monotonic_seed_000026),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000027", ov_separation_monotonic_seed_000027),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000028", ov_separation_monotonic_seed_000028),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000029", ov_separation_monotonic_seed_000029),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000030", ov_separation_monotonic_seed_000030),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000031", ov_separation_monotonic_seed_000031),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000032", ov_separation_monotonic_seed_000032),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000033", ov_separation_monotonic_seed_000033),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000034", ov_separation_monotonic_seed_000034),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000035", ov_separation_monotonic_seed_000035),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000036", ov_separation_monotonic_seed_000036),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000037", ov_separation_monotonic_seed_000037),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000038", ov_separation_monotonic_seed_000038),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000039", ov_separation_monotonic_seed_000039),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000040", ov_separation_monotonic_seed_000040),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000041", ov_separation_monotonic_seed_000041),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000042", ov_separation_monotonic_seed_000042),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000043", ov_separation_monotonic_seed_000043),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000044", ov_separation_monotonic_seed_000044),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000045", ov_separation_monotonic_seed_000045),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000046", ov_separation_monotonic_seed_000046),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000047", ov_separation_monotonic_seed_000047),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000048", ov_separation_monotonic_seed_000048),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000049", ov_separation_monotonic_seed_000049),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000050", ov_separation_monotonic_seed_000050),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000051", ov_separation_monotonic_seed_000051),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000052", ov_separation_monotonic_seed_000052),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000053", ov_separation_monotonic_seed_000053),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000054", ov_separation_monotonic_seed_000054),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000055", ov_separation_monotonic_seed_000055),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000056", ov_separation_monotonic_seed_000056),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000057", ov_separation_monotonic_seed_000057),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000058", ov_separation_monotonic_seed_000058),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000059", ov_separation_monotonic_seed_000059),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000060", ov_separation_monotonic_seed_000060),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000061", ov_separation_monotonic_seed_000061),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000062", ov_separation_monotonic_seed_000062),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000063", ov_separation_monotonic_seed_000063),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000064", ov_separation_monotonic_seed_000064),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000065", ov_separation_monotonic_seed_000065),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000066", ov_separation_monotonic_seed_000066),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000067", ov_separation_monotonic_seed_000067),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000068", ov_separation_monotonic_seed_000068),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000069", ov_separation_monotonic_seed_000069),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000070", ov_separation_monotonic_seed_000070),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000071", ov_separation_monotonic_seed_000071),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000072", ov_separation_monotonic_seed_000072),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000073", ov_separation_monotonic_seed_000073),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000074", ov_separation_monotonic_seed_000074),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000075", ov_separation_monotonic_seed_000075),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000076", ov_separation_monotonic_seed_000076),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000077", ov_separation_monotonic_seed_000077),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000078", ov_separation_monotonic_seed_000078),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000079", ov_separation_monotonic_seed_000079),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000080", ov_separation_monotonic_seed_000080),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000081", ov_separation_monotonic_seed_000081),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000082", ov_separation_monotonic_seed_000082),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000083", ov_separation_monotonic_seed_000083),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000084", ov_separation_monotonic_seed_000084),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000085", ov_separation_monotonic_seed_000085),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000086", ov_separation_monotonic_seed_000086),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000087", ov_separation_monotonic_seed_000087),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000088", ov_separation_monotonic_seed_000088),
        ("property_campaigns_2::tests::ov_separation_monotonic_seed_000089", ov_separation_monotonic_seed_000089),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000000", pj_board_idempotent_and_feasible_seed_000000),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000001", pj_board_idempotent_and_feasible_seed_000001),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000002", pj_board_idempotent_and_feasible_seed_000002),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000003", pj_board_idempotent_and_feasible_seed_000003),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000004", pj_board_idempotent_and_feasible_seed_000004),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000005", pj_board_idempotent_and_feasible_seed_000005),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000006", pj_board_idempotent_and_feasible_seed_000006),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000007", pj_board_idempotent_and_feasible_seed_000007),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000008", pj_board_idempotent_and_feasible_seed_000008),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000009", pj_board_idempotent_and_feasible_seed_000009),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000010", pj_board_idempotent_and_feasible_seed_000010),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000011", pj_board_idempotent_and_feasible_seed_000011),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000012", pj_board_idempotent_and_feasible_seed_000012),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000013", pj_board_idempotent_and_feasible_seed_000013),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000014", pj_board_idempotent_and_feasible_seed_000014),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000015", pj_board_idempotent_and_feasible_seed_000015),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000016", pj_board_idempotent_and_feasible_seed_000016),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000017", pj_board_idempotent_and_feasible_seed_000017),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000018", pj_board_idempotent_and_feasible_seed_000018),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000019", pj_board_idempotent_and_feasible_seed_000019),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000020", pj_board_idempotent_and_feasible_seed_000020),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000021", pj_board_idempotent_and_feasible_seed_000021),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000022", pj_board_idempotent_and_feasible_seed_000022),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000023", pj_board_idempotent_and_feasible_seed_000023),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000024", pj_board_idempotent_and_feasible_seed_000024),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000025", pj_board_idempotent_and_feasible_seed_000025),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000026", pj_board_idempotent_and_feasible_seed_000026),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000027", pj_board_idempotent_and_feasible_seed_000027),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000028", pj_board_idempotent_and_feasible_seed_000028),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000029", pj_board_idempotent_and_feasible_seed_000029),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000030", pj_board_idempotent_and_feasible_seed_000030),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000031", pj_board_idempotent_and_feasible_seed_000031),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000032", pj_board_idempotent_and_feasible_seed_000032),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000033", pj_board_idempotent_and_feasible_seed_000033),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000034", pj_board_idempotent_and_feasible_seed_000034),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000035", pj_board_idempotent_and_feasible_seed_000035),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000036", pj_board_idempotent_and_feasible_seed_000036),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000037", pj_board_idempotent_and_feasible_seed_000037),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000038", pj_board_idempotent_and_feasible_seed_000038),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000039", pj_board_idempotent_and_feasible_seed_000039),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000040", pj_board_idempotent_and_feasible_seed_000040),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000041", pj_board_idempotent_and_feasible_seed_000041),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000042", pj_board_idempotent_and_feasible_seed_000042),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000043", pj_board_idempotent_and_feasible_seed_000043),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000044", pj_board_idempotent_and_feasible_seed_000044),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000045", pj_board_idempotent_and_feasible_seed_000045),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000046", pj_board_idempotent_and_feasible_seed_000046),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000047", pj_board_idempotent_and_feasible_seed_000047),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000048", pj_board_idempotent_and_feasible_seed_000048),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000049", pj_board_idempotent_and_feasible_seed_000049),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000050", pj_board_idempotent_and_feasible_seed_000050),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000051", pj_board_idempotent_and_feasible_seed_000051),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000052", pj_board_idempotent_and_feasible_seed_000052),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000053", pj_board_idempotent_and_feasible_seed_000053),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000054", pj_board_idempotent_and_feasible_seed_000054),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000055", pj_board_idempotent_and_feasible_seed_000055),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000056", pj_board_idempotent_and_feasible_seed_000056),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000057", pj_board_idempotent_and_feasible_seed_000057),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000058", pj_board_idempotent_and_feasible_seed_000058),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000059", pj_board_idempotent_and_feasible_seed_000059),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000060", pj_board_idempotent_and_feasible_seed_000060),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000061", pj_board_idempotent_and_feasible_seed_000061),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000062", pj_board_idempotent_and_feasible_seed_000062),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000063", pj_board_idempotent_and_feasible_seed_000063),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000064", pj_board_idempotent_and_feasible_seed_000064),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000065", pj_board_idempotent_and_feasible_seed_000065),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000066", pj_board_idempotent_and_feasible_seed_000066),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000067", pj_board_idempotent_and_feasible_seed_000067),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000068", pj_board_idempotent_and_feasible_seed_000068),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000069", pj_board_idempotent_and_feasible_seed_000069),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000070", pj_board_idempotent_and_feasible_seed_000070),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000071", pj_board_idempotent_and_feasible_seed_000071),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000072", pj_board_idempotent_and_feasible_seed_000072),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000073", pj_board_idempotent_and_feasible_seed_000073),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000074", pj_board_idempotent_and_feasible_seed_000074),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000075", pj_board_idempotent_and_feasible_seed_000075),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000076", pj_board_idempotent_and_feasible_seed_000076),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000077", pj_board_idempotent_and_feasible_seed_000077),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000078", pj_board_idempotent_and_feasible_seed_000078),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000079", pj_board_idempotent_and_feasible_seed_000079),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000080", pj_board_idempotent_and_feasible_seed_000080),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000081", pj_board_idempotent_and_feasible_seed_000081),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000082", pj_board_idempotent_and_feasible_seed_000082),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000083", pj_board_idempotent_and_feasible_seed_000083),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000084", pj_board_idempotent_and_feasible_seed_000084),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000085", pj_board_idempotent_and_feasible_seed_000085),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000086", pj_board_idempotent_and_feasible_seed_000086),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000087", pj_board_idempotent_and_feasible_seed_000087),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000088", pj_board_idempotent_and_feasible_seed_000088),
        ("property_campaigns_2::tests::pj_board_idempotent_and_feasible_seed_000089", pj_board_idempotent_and_feasible_seed_000089),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000000", pj_zone_idempotent_and_feasible_seed_000000),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000001", pj_zone_idempotent_and_feasible_seed_000001),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000002", pj_zone_idempotent_and_feasible_seed_000002),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000003", pj_zone_idempotent_and_feasible_seed_000003),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000004", pj_zone_idempotent_and_feasible_seed_000004),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000005", pj_zone_idempotent_and_feasible_seed_000005),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000006", pj_zone_idempotent_and_feasible_seed_000006),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000007", pj_zone_idempotent_and_feasible_seed_000007),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000008", pj_zone_idempotent_and_feasible_seed_000008),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000009", pj_zone_idempotent_and_feasible_seed_000009),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000010", pj_zone_idempotent_and_feasible_seed_000010),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000011", pj_zone_idempotent_and_feasible_seed_000011),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000012", pj_zone_idempotent_and_feasible_seed_000012),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000013", pj_zone_idempotent_and_feasible_seed_000013),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000014", pj_zone_idempotent_and_feasible_seed_000014),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000015", pj_zone_idempotent_and_feasible_seed_000015),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000016", pj_zone_idempotent_and_feasible_seed_000016),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000017", pj_zone_idempotent_and_feasible_seed_000017),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000018", pj_zone_idempotent_and_feasible_seed_000018),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000019", pj_zone_idempotent_and_feasible_seed_000019),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000020", pj_zone_idempotent_and_feasible_seed_000020),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000021", pj_zone_idempotent_and_feasible_seed_000021),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000022", pj_zone_idempotent_and_feasible_seed_000022),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000023", pj_zone_idempotent_and_feasible_seed_000023),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000024", pj_zone_idempotent_and_feasible_seed_000024),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000025", pj_zone_idempotent_and_feasible_seed_000025),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000026", pj_zone_idempotent_and_feasible_seed_000026),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000027", pj_zone_idempotent_and_feasible_seed_000027),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000028", pj_zone_idempotent_and_feasible_seed_000028),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000029", pj_zone_idempotent_and_feasible_seed_000029),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000030", pj_zone_idempotent_and_feasible_seed_000030),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000031", pj_zone_idempotent_and_feasible_seed_000031),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000032", pj_zone_idempotent_and_feasible_seed_000032),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000033", pj_zone_idempotent_and_feasible_seed_000033),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000034", pj_zone_idempotent_and_feasible_seed_000034),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000035", pj_zone_idempotent_and_feasible_seed_000035),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000036", pj_zone_idempotent_and_feasible_seed_000036),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000037", pj_zone_idempotent_and_feasible_seed_000037),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000038", pj_zone_idempotent_and_feasible_seed_000038),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000039", pj_zone_idempotent_and_feasible_seed_000039),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000040", pj_zone_idempotent_and_feasible_seed_000040),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000041", pj_zone_idempotent_and_feasible_seed_000041),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000042", pj_zone_idempotent_and_feasible_seed_000042),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000043", pj_zone_idempotent_and_feasible_seed_000043),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000044", pj_zone_idempotent_and_feasible_seed_000044),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000045", pj_zone_idempotent_and_feasible_seed_000045),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000046", pj_zone_idempotent_and_feasible_seed_000046),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000047", pj_zone_idempotent_and_feasible_seed_000047),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000048", pj_zone_idempotent_and_feasible_seed_000048),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000049", pj_zone_idempotent_and_feasible_seed_000049),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000050", pj_zone_idempotent_and_feasible_seed_000050),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000051", pj_zone_idempotent_and_feasible_seed_000051),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000052", pj_zone_idempotent_and_feasible_seed_000052),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000053", pj_zone_idempotent_and_feasible_seed_000053),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000054", pj_zone_idempotent_and_feasible_seed_000054),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000055", pj_zone_idempotent_and_feasible_seed_000055),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000056", pj_zone_idempotent_and_feasible_seed_000056),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000057", pj_zone_idempotent_and_feasible_seed_000057),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000058", pj_zone_idempotent_and_feasible_seed_000058),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000059", pj_zone_idempotent_and_feasible_seed_000059),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000060", pj_zone_idempotent_and_feasible_seed_000060),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000061", pj_zone_idempotent_and_feasible_seed_000061),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000062", pj_zone_idempotent_and_feasible_seed_000062),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000063", pj_zone_idempotent_and_feasible_seed_000063),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000064", pj_zone_idempotent_and_feasible_seed_000064),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000065", pj_zone_idempotent_and_feasible_seed_000065),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000066", pj_zone_idempotent_and_feasible_seed_000066),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000067", pj_zone_idempotent_and_feasible_seed_000067),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000068", pj_zone_idempotent_and_feasible_seed_000068),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000069", pj_zone_idempotent_and_feasible_seed_000069),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000070", pj_zone_idempotent_and_feasible_seed_000070),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000071", pj_zone_idempotent_and_feasible_seed_000071),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000072", pj_zone_idempotent_and_feasible_seed_000072),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000073", pj_zone_idempotent_and_feasible_seed_000073),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000074", pj_zone_idempotent_and_feasible_seed_000074),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000075", pj_zone_idempotent_and_feasible_seed_000075),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000076", pj_zone_idempotent_and_feasible_seed_000076),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000077", pj_zone_idempotent_and_feasible_seed_000077),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000078", pj_zone_idempotent_and_feasible_seed_000078),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000079", pj_zone_idempotent_and_feasible_seed_000079),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000080", pj_zone_idempotent_and_feasible_seed_000080),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000081", pj_zone_idempotent_and_feasible_seed_000081),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000082", pj_zone_idempotent_and_feasible_seed_000082),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000083", pj_zone_idempotent_and_feasible_seed_000083),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000084", pj_zone_idempotent_and_feasible_seed_000084),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000085", pj_zone_idempotent_and_feasible_seed_000085),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000086", pj_zone_idempotent_and_feasible_seed_000086),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000087", pj_zone_idempotent_and_feasible_seed_000087),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000088", pj_zone_idempotent_and_feasible_seed_000088),
        ("property_campaigns_2::tests::pj_zone_idempotent_and_feasible_seed_000089", pj_zone_idempotent_and_feasible_seed_000089),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000000", pj_half_plane_feasible_and_idempotent_seed_000000),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000001", pj_half_plane_feasible_and_idempotent_seed_000001),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000002", pj_half_plane_feasible_and_idempotent_seed_000002),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000003", pj_half_plane_feasible_and_idempotent_seed_000003),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000004", pj_half_plane_feasible_and_idempotent_seed_000004),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000005", pj_half_plane_feasible_and_idempotent_seed_000005),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000006", pj_half_plane_feasible_and_idempotent_seed_000006),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000007", pj_half_plane_feasible_and_idempotent_seed_000007),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000008", pj_half_plane_feasible_and_idempotent_seed_000008),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000009", pj_half_plane_feasible_and_idempotent_seed_000009),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000010", pj_half_plane_feasible_and_idempotent_seed_000010),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000011", pj_half_plane_feasible_and_idempotent_seed_000011),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000012", pj_half_plane_feasible_and_idempotent_seed_000012),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000013", pj_half_plane_feasible_and_idempotent_seed_000013),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000014", pj_half_plane_feasible_and_idempotent_seed_000014),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000015", pj_half_plane_feasible_and_idempotent_seed_000015),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000016", pj_half_plane_feasible_and_idempotent_seed_000016),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000017", pj_half_plane_feasible_and_idempotent_seed_000017),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000018", pj_half_plane_feasible_and_idempotent_seed_000018),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000019", pj_half_plane_feasible_and_idempotent_seed_000019),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000020", pj_half_plane_feasible_and_idempotent_seed_000020),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000021", pj_half_plane_feasible_and_idempotent_seed_000021),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000022", pj_half_plane_feasible_and_idempotent_seed_000022),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000023", pj_half_plane_feasible_and_idempotent_seed_000023),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000024", pj_half_plane_feasible_and_idempotent_seed_000024),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000025", pj_half_plane_feasible_and_idempotent_seed_000025),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000026", pj_half_plane_feasible_and_idempotent_seed_000026),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000027", pj_half_plane_feasible_and_idempotent_seed_000027),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000028", pj_half_plane_feasible_and_idempotent_seed_000028),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000029", pj_half_plane_feasible_and_idempotent_seed_000029),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000030", pj_half_plane_feasible_and_idempotent_seed_000030),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000031", pj_half_plane_feasible_and_idempotent_seed_000031),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000032", pj_half_plane_feasible_and_idempotent_seed_000032),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000033", pj_half_plane_feasible_and_idempotent_seed_000033),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000034", pj_half_plane_feasible_and_idempotent_seed_000034),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000035", pj_half_plane_feasible_and_idempotent_seed_000035),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000036", pj_half_plane_feasible_and_idempotent_seed_000036),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000037", pj_half_plane_feasible_and_idempotent_seed_000037),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000038", pj_half_plane_feasible_and_idempotent_seed_000038),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000039", pj_half_plane_feasible_and_idempotent_seed_000039),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000040", pj_half_plane_feasible_and_idempotent_seed_000040),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000041", pj_half_plane_feasible_and_idempotent_seed_000041),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000042", pj_half_plane_feasible_and_idempotent_seed_000042),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000043", pj_half_plane_feasible_and_idempotent_seed_000043),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000044", pj_half_plane_feasible_and_idempotent_seed_000044),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000045", pj_half_plane_feasible_and_idempotent_seed_000045),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000046", pj_half_plane_feasible_and_idempotent_seed_000046),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000047", pj_half_plane_feasible_and_idempotent_seed_000047),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000048", pj_half_plane_feasible_and_idempotent_seed_000048),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000049", pj_half_plane_feasible_and_idempotent_seed_000049),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000050", pj_half_plane_feasible_and_idempotent_seed_000050),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000051", pj_half_plane_feasible_and_idempotent_seed_000051),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000052", pj_half_plane_feasible_and_idempotent_seed_000052),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000053", pj_half_plane_feasible_and_idempotent_seed_000053),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000054", pj_half_plane_feasible_and_idempotent_seed_000054),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000055", pj_half_plane_feasible_and_idempotent_seed_000055),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000056", pj_half_plane_feasible_and_idempotent_seed_000056),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000057", pj_half_plane_feasible_and_idempotent_seed_000057),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000058", pj_half_plane_feasible_and_idempotent_seed_000058),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000059", pj_half_plane_feasible_and_idempotent_seed_000059),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000060", pj_half_plane_feasible_and_idempotent_seed_000060),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000061", pj_half_plane_feasible_and_idempotent_seed_000061),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000062", pj_half_plane_feasible_and_idempotent_seed_000062),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000063", pj_half_plane_feasible_and_idempotent_seed_000063),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000064", pj_half_plane_feasible_and_idempotent_seed_000064),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000065", pj_half_plane_feasible_and_idempotent_seed_000065),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000066", pj_half_plane_feasible_and_idempotent_seed_000066),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000067", pj_half_plane_feasible_and_idempotent_seed_000067),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000068", pj_half_plane_feasible_and_idempotent_seed_000068),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000069", pj_half_plane_feasible_and_idempotent_seed_000069),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000070", pj_half_plane_feasible_and_idempotent_seed_000070),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000071", pj_half_plane_feasible_and_idempotent_seed_000071),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000072", pj_half_plane_feasible_and_idempotent_seed_000072),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000073", pj_half_plane_feasible_and_idempotent_seed_000073),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000074", pj_half_plane_feasible_and_idempotent_seed_000074),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000075", pj_half_plane_feasible_and_idempotent_seed_000075),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000076", pj_half_plane_feasible_and_idempotent_seed_000076),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000077", pj_half_plane_feasible_and_idempotent_seed_000077),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000078", pj_half_plane_feasible_and_idempotent_seed_000078),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000079", pj_half_plane_feasible_and_idempotent_seed_000079),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000080", pj_half_plane_feasible_and_idempotent_seed_000080),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000081", pj_half_plane_feasible_and_idempotent_seed_000081),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000082", pj_half_plane_feasible_and_idempotent_seed_000082),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000083", pj_half_plane_feasible_and_idempotent_seed_000083),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000084", pj_half_plane_feasible_and_idempotent_seed_000084),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000085", pj_half_plane_feasible_and_idempotent_seed_000085),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000086", pj_half_plane_feasible_and_idempotent_seed_000086),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000087", pj_half_plane_feasible_and_idempotent_seed_000087),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000088", pj_half_plane_feasible_and_idempotent_seed_000088),
        ("property_campaigns_2::tests::pj_half_plane_feasible_and_idempotent_seed_000089", pj_half_plane_feasible_and_idempotent_seed_000089),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000000", pj_keepout_feasible_and_idempotent_seed_000000),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000001", pj_keepout_feasible_and_idempotent_seed_000001),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000002", pj_keepout_feasible_and_idempotent_seed_000002),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000003", pj_keepout_feasible_and_idempotent_seed_000003),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000004", pj_keepout_feasible_and_idempotent_seed_000004),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000005", pj_keepout_feasible_and_idempotent_seed_000005),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000006", pj_keepout_feasible_and_idempotent_seed_000006),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000007", pj_keepout_feasible_and_idempotent_seed_000007),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000008", pj_keepout_feasible_and_idempotent_seed_000008),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000009", pj_keepout_feasible_and_idempotent_seed_000009),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000010", pj_keepout_feasible_and_idempotent_seed_000010),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000011", pj_keepout_feasible_and_idempotent_seed_000011),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000012", pj_keepout_feasible_and_idempotent_seed_000012),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000013", pj_keepout_feasible_and_idempotent_seed_000013),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000014", pj_keepout_feasible_and_idempotent_seed_000014),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000015", pj_keepout_feasible_and_idempotent_seed_000015),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000016", pj_keepout_feasible_and_idempotent_seed_000016),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000017", pj_keepout_feasible_and_idempotent_seed_000017),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000018", pj_keepout_feasible_and_idempotent_seed_000018),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000019", pj_keepout_feasible_and_idempotent_seed_000019),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000020", pj_keepout_feasible_and_idempotent_seed_000020),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000021", pj_keepout_feasible_and_idempotent_seed_000021),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000022", pj_keepout_feasible_and_idempotent_seed_000022),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000023", pj_keepout_feasible_and_idempotent_seed_000023),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000024", pj_keepout_feasible_and_idempotent_seed_000024),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000025", pj_keepout_feasible_and_idempotent_seed_000025),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000026", pj_keepout_feasible_and_idempotent_seed_000026),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000027", pj_keepout_feasible_and_idempotent_seed_000027),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000028", pj_keepout_feasible_and_idempotent_seed_000028),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000029", pj_keepout_feasible_and_idempotent_seed_000029),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000030", pj_keepout_feasible_and_idempotent_seed_000030),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000031", pj_keepout_feasible_and_idempotent_seed_000031),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000032", pj_keepout_feasible_and_idempotent_seed_000032),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000033", pj_keepout_feasible_and_idempotent_seed_000033),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000034", pj_keepout_feasible_and_idempotent_seed_000034),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000035", pj_keepout_feasible_and_idempotent_seed_000035),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000036", pj_keepout_feasible_and_idempotent_seed_000036),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000037", pj_keepout_feasible_and_idempotent_seed_000037),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000038", pj_keepout_feasible_and_idempotent_seed_000038),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000039", pj_keepout_feasible_and_idempotent_seed_000039),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000040", pj_keepout_feasible_and_idempotent_seed_000040),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000041", pj_keepout_feasible_and_idempotent_seed_000041),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000042", pj_keepout_feasible_and_idempotent_seed_000042),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000043", pj_keepout_feasible_and_idempotent_seed_000043),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000044", pj_keepout_feasible_and_idempotent_seed_000044),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000045", pj_keepout_feasible_and_idempotent_seed_000045),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000046", pj_keepout_feasible_and_idempotent_seed_000046),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000047", pj_keepout_feasible_and_idempotent_seed_000047),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000048", pj_keepout_feasible_and_idempotent_seed_000048),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000049", pj_keepout_feasible_and_idempotent_seed_000049),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000050", pj_keepout_feasible_and_idempotent_seed_000050),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000051", pj_keepout_feasible_and_idempotent_seed_000051),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000052", pj_keepout_feasible_and_idempotent_seed_000052),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000053", pj_keepout_feasible_and_idempotent_seed_000053),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000054", pj_keepout_feasible_and_idempotent_seed_000054),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000055", pj_keepout_feasible_and_idempotent_seed_000055),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000056", pj_keepout_feasible_and_idempotent_seed_000056),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000057", pj_keepout_feasible_and_idempotent_seed_000057),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000058", pj_keepout_feasible_and_idempotent_seed_000058),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000059", pj_keepout_feasible_and_idempotent_seed_000059),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000060", pj_keepout_feasible_and_idempotent_seed_000060),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000061", pj_keepout_feasible_and_idempotent_seed_000061),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000062", pj_keepout_feasible_and_idempotent_seed_000062),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000063", pj_keepout_feasible_and_idempotent_seed_000063),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000064", pj_keepout_feasible_and_idempotent_seed_000064),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000065", pj_keepout_feasible_and_idempotent_seed_000065),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000066", pj_keepout_feasible_and_idempotent_seed_000066),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000067", pj_keepout_feasible_and_idempotent_seed_000067),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000068", pj_keepout_feasible_and_idempotent_seed_000068),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000069", pj_keepout_feasible_and_idempotent_seed_000069),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000070", pj_keepout_feasible_and_idempotent_seed_000070),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000071", pj_keepout_feasible_and_idempotent_seed_000071),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000072", pj_keepout_feasible_and_idempotent_seed_000072),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000073", pj_keepout_feasible_and_idempotent_seed_000073),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000074", pj_keepout_feasible_and_idempotent_seed_000074),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000075", pj_keepout_feasible_and_idempotent_seed_000075),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000076", pj_keepout_feasible_and_idempotent_seed_000076),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000077", pj_keepout_feasible_and_idempotent_seed_000077),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000078", pj_keepout_feasible_and_idempotent_seed_000078),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000079", pj_keepout_feasible_and_idempotent_seed_000079),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000080", pj_keepout_feasible_and_idempotent_seed_000080),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000081", pj_keepout_feasible_and_idempotent_seed_000081),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000082", pj_keepout_feasible_and_idempotent_seed_000082),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000083", pj_keepout_feasible_and_idempotent_seed_000083),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000084", pj_keepout_feasible_and_idempotent_seed_000084),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000085", pj_keepout_feasible_and_idempotent_seed_000085),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000086", pj_keepout_feasible_and_idempotent_seed_000086),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000087", pj_keepout_feasible_and_idempotent_seed_000087),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000088", pj_keepout_feasible_and_idempotent_seed_000088),
        ("property_campaigns_2::tests::pj_keepout_feasible_and_idempotent_seed_000089", pj_keepout_feasible_and_idempotent_seed_000089),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
