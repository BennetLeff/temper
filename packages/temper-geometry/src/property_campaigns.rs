// Property-based campaigns over three independent, pure, deterministic
// temper-geometry kernels: KiCad's footprint-rotation convention
// (`kicad_transform.rs`), convex-hull area (`convex_hull.rs`), and
// 8-connected component labeling (`connected_components.rs`).
//
// Why this exists (R7 / the WASM-tier volume payload)
// -----------------------------------------------------------------------
// A fixed, hand-written unit-test fixture explores the same handful of
// inputs every time it runs. This module gives the wasm32 tier a payload
// where each registered test explores a *distinct* generated input: every
// property below is a pure function of a `u64` seed through the
// `SplitMix64` generator below, so `kt_round_trip_seed_000042` and
// `kt_round_trip_seed_000043` exercise different geometry, and a failure
// is reproducible from its seed alone.
//
// Each property is a metamorphic or invariant relation over the real
// kernel -- a relationship that must hold between two *related* calls --
// never a restatement of the implementation (i.e. never "recompute X, and
// assert X equals X"). Every one is picked so that a plausible bug in the
// kernel it covers flips it from green to red; see this crate's PR body
// (or `docs/evidence/` if this lands with one) for the mutation-testing
// evidence: each property was checked against a deliberately broken
// kernel and shown to fail on exactly the cases it should, then the
// kernel was reverted.
//
// No `proptest`: it is a dev-dependency, absent from the ordinary
// (non-test) build this crate's `wasm-registry` feature compiles into
// (see `scripts/gen_wasm_test_registry.py`'s `PROPTEST_USE` exclusion and
// `packages/temper-drc-rs/src/rules/drc/property_campaigns.rs`, the
// module this one copies the shape of). No RNG crate either: `SplitMix64`
// below is a small, self-contained, portable PRNG -- wasm32-unknown-unknown
// has no OS entropy source (see `wasm_entropy.rs`), and fixed seeds are
// what make a wasm32 trap reproducible from its seed by a human reading
// the failing test's name.
//
// Every item below (down to `mod tests`) is reachable ONLY from that
// module's `#[test]` functions -- which `scripts/gen_wasm_test_registry.py`
// turns into `pub(crate)` and reaches indirectly through
// `tests::WASM_TESTS` once this module is registered. A build with neither
// `test` nor `wasm-registry` active (e.g. `--features python` alone, which
// also turns off this crate's blanket `not(feature = "python")` dead-code
// allowance in `lib.rs`) therefore sees every item below as unused -- same
// reason `packages/temper-drc-rs/src/rules/drc/property_campaigns.rs`
// applies this allow to its own equivalent items.
#![allow(dead_code)]

// ---------------------------------------------------------------------------
// Deterministic PRNG (SplitMix64) -- pure, no external dependency, portable
// to wasm32-unknown-unknown without an entropy source. Shared by all three
// kernels' properties below; each property draws its own generated case
// from `seed` directly, and any extra randomized parameter (translation,
// rotation angle, scale factor, extra points, ...) from an independent
// `sub_rng(seed, salt)` stream so a property's own parameters never
// correlate with which base case `seed` produced.
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
/// same base seed (same pattern as `packages/temper-drc-rs/src/rules/drc/
/// property_campaigns.rs`'s `sub_rng`).
fn sub_rng(seed: u64, salt: u64) -> SplitMix64 {
    SplitMix64::new(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15).wrapping_add(salt))
}

// ===========================================================================
// Kernel 1: kicad_transform.rs -- KiCad's R(-theta) footprint-child rotation
// convention (`rotate_local_to_world` / `rotate_world_to_local` /
// `place_local_to_world`).
// ===========================================================================

use crate::kicad_transform::{place_local_to_world, rotate_local_to_world, rotate_world_to_local};

const KT_SALT_COMPOSE: u64 = 0xB1;
const KT_SALT_TRANSLATE: u64 = 0xB2;

/// A `(x, y, theta_rad)` case: a local offset up to +-500mm (well past any
/// real footprint's extent, so the property is not accidentally only
/// exercised near the origin) and a rotation spanning several full turns
/// (so wrap-around behaviour at multiples of 2*pi is exercised, not just
/// the [0, 2*pi) range a naive generator might stick to).
fn kt_gen_case(seed: u64) -> (f64, f64, f64) {
    let mut rng = SplitMix64::new(seed);
    let x = rng.range(-500.0, 500.0);
    let y = rng.range(-500.0, 500.0);
    let theta = rng.range(-4.0 * std::f64::consts::PI, 4.0 * std::f64::consts::PI);
    (x, y, theta)
}

/// `rotate_world_to_local` is the claimed inverse of `rotate_local_to_world`
/// (module doc: "R(+theta) ... is also its exact inverse"). Round-tripping
/// a point through both must recover it.
///
/// Bug this would catch: a sign error introduced into either function that
/// breaks the claimed inverse relationship -- e.g. a refactor that changes
/// `rotate_world_to_local`'s matrix to R(-theta) instead of R(+theta) would
/// make this compose to a *double* rotation instead of the identity, and
/// every seed but theta == 0 (mod pi) would fail.
pub(crate) fn kt_round_trip_impl(seed: u64) {
    let (x, y, theta) = kt_gen_case(seed);
    let (wx, wy) = rotate_local_to_world(x, y, theta);
    let (lx, ly) = rotate_world_to_local(wx, wy, theta);
    let tol = 1e-7 * (x.abs() + y.abs() + 1.0);
    assert!(
        (lx - x).abs() < tol && (ly - y).abs() < tol,
        "round-trip through rotate_local_to_world/rotate_world_to_local failed: \
         seed={seed} theta={theta} in=({x}, {y}) out=({lx}, {ly})"
    );
}

/// A rotation matrix is orthonormal: it preserves vector length. This holds
/// for `rotate_local_to_world` regardless of the sign convention (R(-theta)
/// vs R(+theta)), so it is a genuinely independent check from the round-trip
/// property above -- a bug that broke the round-trip via a
/// length-preserving sign error (e.g. swapping which function is the
/// inverse of which) would NOT be caught by this property, and vice versa a
/// bug that scaled one axis (e.g. a typo duplicating `c` into both matrix
/// diagonal entries when it should be `c` and `-s`/`s`) would break this
/// property while leaving some round-trips coincidentally intact.
///
/// Bug this would catch: any matrix-entry typo that makes the transform
/// non-orthonormal (a stray scale factor, a duplicated term, a `+` where a
/// trig identity requires a `-`).
pub(crate) fn kt_isometry_impl(seed: u64) {
    let (x, y, theta) = kt_gen_case(seed);
    let (wx, wy) = rotate_local_to_world(x, y, theta);
    let orig_len = (x * x + y * y).sqrt();
    let rot_len = (wx * wx + wy * wy).sqrt();
    let tol = 1e-7 * (orig_len + 1.0);
    assert!(
        (orig_len - rot_len).abs() < tol,
        "rotate_local_to_world changed vector length (not an isometry): \
         seed={seed} theta={theta} |in|={orig_len} |out|={rot_len}"
    );
}

/// 2-D rotations compose additively regardless of order: applying
/// `rotate_local_to_world` by `theta1` then `theta2` must equal applying it
/// once by `theta1 + theta2` (rotation matrices of the same handedness
/// always commute and their product is the matrix of the summed angle).
///
/// Bug this would catch: this is the property that would catch a subtle
/// non-linearity -- e.g. an implementation that special-cased "snap to
/// quadrant angles" (a real bug class: KiCad-adjacent code has hard-coded
/// 0/90/180/270 special cases before) would agree with the direct rotation
/// at quadrant angles but diverge once composed through two arbitrary
/// angles whose sum lands off-quadrant.
pub(crate) fn kt_composition_impl(seed: u64) {
    let mut rng = SplitMix64::new(seed);
    let x = rng.range(-500.0, 500.0);
    let y = rng.range(-500.0, 500.0);
    let mut angle_rng = sub_rng(seed, KT_SALT_COMPOSE);
    let theta1 = angle_rng.range(-3.0 * std::f64::consts::PI, 3.0 * std::f64::consts::PI);
    let theta2 = angle_rng.range(-3.0 * std::f64::consts::PI, 3.0 * std::f64::consts::PI);
    let (x1, y1) = rotate_local_to_world(x, y, theta1);
    let (composed_x, composed_y) = rotate_local_to_world(x1, y1, theta2);
    let (direct_x, direct_y) = rotate_local_to_world(x, y, theta1 + theta2);
    let tol = 1e-6 * (x.abs() + y.abs() + 1.0);
    assert!(
        (composed_x - direct_x).abs() < tol && (composed_y - direct_y).abs() < tol,
        "rotate_local_to_world(theta1) then rotate_local_to_world(theta2) != \
         rotate_local_to_world(theta1+theta2): seed={seed} theta1={theta1} theta2={theta2} \
         composed=({composed_x}, {composed_y}) direct=({direct_x}, {direct_y})"
    );
}

/// `place_local_to_world` is documented as "rotate the local offset, then
/// translate by the origin" -- so translating the origin by `(dx, dy)` must
/// translate the placed point by exactly `(dx, dy)`, independent of the
/// rotation angle or local offset.
///
/// Bug this would catch: a refactor that folds the origin into the
/// rotation (e.g. rotating `(local + origin)` as one vector instead of
/// rotating `local` and adding `origin` afterward) would make the output
/// depend on the origin's own rotated position, not just shift linearly
/// with it -- this property fails immediately for any theta not a multiple
/// of 2*pi in that case.
pub(crate) fn kt_place_translation_impl(seed: u64) {
    let mut rng = SplitMix64::new(seed);
    let lx = rng.range(-200.0, 200.0);
    let ly = rng.range(-200.0, 200.0);
    let ox = rng.range(-500.0, 500.0);
    let oy = rng.range(-500.0, 500.0);
    let theta = rng.range(-4.0 * std::f64::consts::PI, 4.0 * std::f64::consts::PI);
    let mut t_rng = sub_rng(seed, KT_SALT_TRANSLATE);
    let dx = t_rng.range(-1000.0, 1000.0);
    let dy = t_rng.range(-1000.0, 1000.0);
    let (p0x, p0y) = place_local_to_world(lx, ly, ox, oy, theta);
    let (p1x, p1y) = place_local_to_world(lx, ly, ox + dx, oy + dy, theta);
    let tol = 1e-7 * (dx.abs() + dy.abs() + 1.0);
    assert!(
        ((p1x - p0x) - dx).abs() < tol && ((p1y - p0y) - dy).abs() < tol,
        "place_local_to_world did not translate linearly with its origin: \
         seed={seed} theta={theta} dx={dx} dy={dy} p0=({p0x}, {p0y}) p1=({p1x}, {p1y})"
    );
}

// ===========================================================================
// Kernel 2: convex_hull.rs -- `convex_hull_area`, the scipy.spatial.ConvexHull
// `.volume` (2-D "volume" == area) replacement.
// ===========================================================================

use crate::convex_hull::convex_hull_area;

const CH_SALT_TRANSLATE: u64 = 0xC1;
const CH_SALT_ROTATE: u64 = 0xC2;
const CH_SALT_SCALE: u64 = 0xC3;
const CH_SALT_SUPERSET: u64 = 0xC4;
const CH_SALT_INTERIOR: u64 = 0xC5;

/// A point cloud of 5-15 points in [-100, 100]^2 -- enough points that the
/// hull is (almost always) a genuine polygon with several vertices, not a
/// degenerate triangle, while staying cheap.
fn ch_gen_points(seed: u64) -> Vec<[f64; 2]> {
    let mut rng = SplitMix64::new(seed);
    let n = 5 + rng.index(11); // 5..=15
    (0..n).map(|_| [rng.range(-100.0, 100.0), rng.range(-100.0, 100.0)]).collect()
}

fn ch_rotate(pts: &[[f64; 2]], angle: f64) -> Vec<[f64; 2]> {
    let (s, c) = angle.sin_cos();
    pts.iter().map(|p| [p[0] * c - p[1] * s, p[0] * s + p[1] * c]).collect()
}

/// Hull area is invariant under translating every point by the same
/// vector -- area is a property of shape, not absolute position.
///
/// Bug this would catch: any absolute-coordinate-dependent code path (a
/// spatial bucketing optimization, a fixed-epsilon comparison that only
/// misfires far from the origin) breaking on the translated corpus while
/// passing on the origin-centered one.
pub(crate) fn ch_translation_invariant_impl(seed: u64) {
    let pts = ch_gen_points(seed);
    let a0 = convex_hull_area(&pts);
    let mut rng = sub_rng(seed, CH_SALT_TRANSLATE);
    let dx = rng.range(-500.0, 500.0);
    let dy = rng.range(-500.0, 500.0);
    let moved: Vec<[f64; 2]> = pts.iter().map(|p| [p[0] + dx, p[1] + dy]).collect();
    let a1 = convex_hull_area(&moved);
    let tol = (a0.abs() * 1e-6).max(1e-6);
    assert!(
        (a0 - a1).abs() < tol,
        "convex_hull_area not translation-invariant: seed={seed} dx={dx} dy={dy} a0={a0} a1={a1}"
    );
}

/// Hull area is invariant under rotating every point by the same angle
/// about the origin -- a rigid motion preserves area.
///
/// Bug this would catch: an axis-aligned-bounding-box shortcut mistakenly
/// used as (or blended into) the hull area at non-axis-aligned angles --
/// exactly the class of bug this repo's rotation-convention incident
/// (`docs/evidence/2026-07-29-cross-domain-creepage-rotation-convention.md`)
/// warns about elsewhere in this codebase.
pub(crate) fn ch_rotation_invariant_impl(seed: u64) {
    let pts = ch_gen_points(seed);
    let a0 = convex_hull_area(&pts);
    let mut rng = sub_rng(seed, CH_SALT_ROTATE);
    let angle = rng.range(0.0, std::f64::consts::TAU);
    let rotated = ch_rotate(&pts, angle);
    let a1 = convex_hull_area(&rotated);
    let tol = (a0.abs().max(a1.abs()) * 1e-6).max(1e-6);
    assert!(
        (a0 - a1).abs() < tol,
        "convex_hull_area not rotation-invariant: seed={seed} angle={angle} a0={a0} a1={a1}"
    );
}

/// Scaling every point by `k` about the origin scales the hull area by
/// exactly `k^2` (area is a quadratic, not linear, function of a linear
/// dimension).
///
/// Bug this would catch: any absolute-epsilon threshold baked into the
/// hull computation would break this quadratic law at small or large `k`
/// -- the same class of bug the task brief names explicitly
/// ("monotonicity under scaling") for a different kernel.
pub(crate) fn ch_scale_quadratic_impl(seed: u64) {
    let pts = ch_gen_points(seed);
    let a0 = convex_hull_area(&pts);
    let mut rng = sub_rng(seed, CH_SALT_SCALE);
    let k = rng.range(0.1, 5.0);
    let scaled: Vec<[f64; 2]> = pts.iter().map(|p| [p[0] * k, p[1] * k]).collect();
    let a1 = convex_hull_area(&scaled);
    let expected = a0 * k * k;
    let tol = (expected.abs() * 1e-6).max(1e-6);
    assert!(
        (a1 - expected).abs() < tol,
        "convex_hull_area did not scale by k^2: seed={seed} k={k} a0={a0} a1={a1} expected={expected}"
    );
}

/// Adding points to a point set never decreases its hull area: the convex
/// hull operator is monotonic under set inclusion (`hull(S) subseteq
/// hull(S union T)` always), so `area(hull(S union T)) >= area(hull(S))`.
///
/// Bug this would catch: an incremental/optimized hull path that discards
/// or mis-merges points when extending an existing hull, silently
/// *shrinking* the reported area instead of only ever growing or holding
/// it steady.
pub(crate) fn ch_superset_monotonic_impl(seed: u64) {
    let pts = ch_gen_points(seed);
    let a0 = convex_hull_area(&pts);
    let mut rng = sub_rng(seed, CH_SALT_SUPERSET);
    let extra_n = 1 + rng.index(5);
    let mut extended = pts.clone();
    for _ in 0..extra_n {
        extended.push([rng.range(-150.0, 150.0), rng.range(-150.0, 150.0)]);
    }
    let a1 = convex_hull_area(&extended);
    assert!(
        a1 + 1e-6 >= a0,
        "convex_hull_area shrank under a superset (monotonicity violated): \
         seed={seed} extra_n={extra_n} a0={a0} a1={a1}"
    );
}

/// Any convex combination of points already in the set lies inside (or on
/// the boundary of) the set's own convex hull, by the definition of convex
/// hull -- so adding such a point can never change the hull's area.
///
/// Bug this would catch: a hull implementation that fails to recognize an
/// interior point as non-extreme (e.g. an epsilon-based extreme-point test
/// that is too permissive near the boundary) would inflate the reported
/// area when this "interior" point is added.
pub(crate) fn ch_interior_point_invariant_impl(seed: u64) {
    let pts = ch_gen_points(seed);
    let a0 = convex_hull_area(&pts);
    let mut rng = sub_rng(seed, CH_SALT_INTERIOR);
    let n = pts.len();
    let i = rng.index(n);
    let j = rng.index(n);
    let k = rng.index(n);
    let raw = [rng.next_f64(), rng.next_f64(), rng.next_f64()];
    let sum: f64 = raw.iter().sum();
    let w = if sum < 1e-9 { [1.0 / 3.0; 3] } else { [raw[0] / sum, raw[1] / sum, raw[2] / sum] };
    let interior = [
        w[0] * pts[i][0] + w[1] * pts[j][0] + w[2] * pts[k][0],
        w[0] * pts[i][1] + w[1] * pts[j][1] + w[2] * pts[k][1],
    ];
    let mut extended = pts.clone();
    extended.push(interior);
    let a1 = convex_hull_area(&extended);
    let tol = (a0.abs() * 1e-6).max(1e-6);
    assert!(
        (a0 - a1).abs() < tol,
        "convex_hull_area changed when a convex combination of existing points was added: \
         seed={seed} i={i} j={j} k={k} w={w:?} a0={a0} a1={a1}"
    );
}

// ===========================================================================
// Kernel 3: connected_components.rs -- exact 8-connected labeling
// (`label_components_8`).
// ===========================================================================

use crate::connected_components::label_components_8;

const CC_SALT_DIHEDRAL: u64 = 0xD1;
const CC_SALT_UNION: u64 = 0xD2;
const CC_SALT_PAD: u64 = 0xD3;

/// A random boolean grid, `4..=10` on a side, fill probability in
/// `[0.25, 0.65)` -- biased toward a mix of foreground and background so
/// most cases have several components, not "all one blob" or "all empty".
fn cc_gen_mask(seed: u64) -> (Vec<u8>, usize, usize) {
    let mut rng = SplitMix64::new(seed);
    let h = 4 + rng.index(7); // 4..=10
    let w = 4 + rng.index(7);
    let p = rng.range(0.25, 0.65);
    let mask: Vec<u8> = (0..h * w).map(|_| u8::from(rng.next_f64() < p)).collect();
    (mask, h, w)
}

/// The new `(height, width)` after applying one of the 8 symmetries of a
/// rectangular grid (the dihedral group of the square, generalized to a
/// rectangle: the 4 "proper" transforms keep dims, the 4 that involve a
/// quarter-turn or a diagonal reflection swap them).
fn dihedral_dims(variant: usize, h: usize, w: usize) -> (usize, usize) {
    match variant {
        0 | 2 | 4 | 5 => (h, w), // identity, rot180, flip-H, flip-V
        _ => (w, h),             // rot90, rot270, transpose, anti-transpose
    }
}

/// Maps source cell `(r, c)` in an `h x w` grid to its position in the
/// transformed grid (whose dims are `dihedral_dims(variant, h, w)`). All 8
/// variants are lattice automorphisms of the 8-neighbor adjacency
/// structure: every one maps the 8 neighbor offsets of a cell to the 8
/// neighbor offsets of its image, so connectivity is preserved exactly.
fn dihedral_index(variant: usize, r: usize, c: usize, h: usize, w: usize) -> (usize, usize) {
    match variant {
        0 => (r, c),                     // identity
        1 => (c, h - 1 - r),             // rotate 90 clockwise
        2 => (h - 1 - r, w - 1 - c),     // rotate 180
        3 => (w - 1 - c, r),             // rotate 270 clockwise (= 90 CCW)
        4 => (r, w - 1 - c),             // flip horizontal (mirror columns)
        5 => (h - 1 - r, c),             // flip vertical (mirror rows)
        6 => (c, r),                     // transpose (main diagonal)
        7 => (w - 1 - c, h - 1 - r),     // anti-transpose (anti-diagonal)
        _ => unreachable!("dihedral variant is always seed.index(8), i.e. 0..8"),
    }
}

/// 8-connectivity treats all 8 neighbor directions symmetrically, so it is
/// invariant under every symmetry of the square lattice: rotating,
/// transposing, or mirroring a grid before labeling must produce the same
/// number of components, and any two foreground cells that were in the
/// same component before the transform must be in the same component
/// (via their mapped positions) after it -- and vice versa.
///
/// Bug this would catch: the four preceding-in-raster-order neighbor
/// offsets `label_components_8` reads (West, North-West, North,
/// North-East -- see that module's Pass-1 comment) are an *asymmetric*
/// subset of the 8 neighbors, chosen only because they precede the current
/// cell in raster order. A bug that dropped one of them (e.g. forgetting
/// North-East) would still pass ordinary tests scanned in the original
/// orientation but would disagree with itself once the grid is rotated 90
/// degrees, because the "preceding" set is a different geometric subset of
/// the 8 neighbors after rotation. Symmetry invariance is exactly the
/// property an orientation-dependent bug like that breaks.
pub(crate) fn cc_dihedral_invariant_impl(seed: u64) {
    let (mask, h, w) = cc_gen_mask(seed);
    let (labels0, n0) = label_components_8(&mask, h, w);
    let mut rng = sub_rng(seed, CC_SALT_DIHEDRAL);
    let variant = rng.index(8);
    let (h2, w2) = dihedral_dims(variant, h, w);
    let mut mask2 = vec![0u8; h2 * w2];
    for r in 0..h {
        for c in 0..w {
            let (nr, nc) = dihedral_index(variant, r, c, h, w);
            mask2[nr * w2 + nc] = mask[r * w + c];
        }
    }
    let (labels1, n1) = label_components_8(&mask2, h2, w2);
    assert_eq!(
        n0, n1,
        "component count changed under a lattice symmetry: seed={seed} variant={variant} h={h} w={w}"
    );
    let n_cells = h * w;
    for i in 0..n_cells {
        if mask[i] == 0 {
            continue;
        }
        let (ri, ci) = (i / w, i % w);
        let (nri, nci) = dihedral_index(variant, ri, ci, h, w);
        let ni = nri * w2 + nci;
        for j in (i + 1)..n_cells {
            if mask[j] == 0 {
                continue;
            }
            let (rj, cj) = (j / w, j % w);
            let (nrj, ncj) = dihedral_index(variant, rj, cj, h, w);
            let nj = nrj * w2 + ncj;
            assert_eq!(
                labels0[i] == labels0[j],
                labels1[ni] == labels1[nj],
                "partition changed under a lattice symmetry: seed={seed} variant={variant} i={i} j={j}"
            );
        }
    }
}

/// Adding foreground cells (a bitwise-OR of two masks) never disconnects
/// two cells that were already connected: connectivity is monotonic under
/// adding foreground, since every union-find edge present in the smaller
/// mask's scan is also present (or redundant) in the union's scan.
///
/// Bug this would catch: a union-find implementation that doesn't
/// propagate a `union` far enough through path compression (a stale
/// `parent` pointer surviving into a later scan) could report two cells
/// as disconnected in a *denser* grid despite being connected in a sparser
/// one built from the same base pattern -- a bug that would never surface
/// on a single fixed fixture, only when the same base connectivity is
/// re-checked under added foreground.
pub(crate) fn cc_union_monotone_impl(seed: u64) {
    let (mask_a, h, w) = cc_gen_mask(seed);
    let mut rng = sub_rng(seed, CC_SALT_UNION);
    let p2 = rng.range(0.15, 0.5);
    let mask_b: Vec<u8> = (0..h * w).map(|_| u8::from(rng.next_f64() < p2)).collect();
    let mask_u: Vec<u8> = (0..h * w).map(|i| u8::from(mask_a[i] != 0 || mask_b[i] != 0)).collect();
    let (labels_a, _) = label_components_8(&mask_a, h, w);
    let (labels_u, _) = label_components_8(&mask_u, h, w);
    let n_cells = h * w;
    for i in 0..n_cells {
        if labels_a[i] == 0 {
            continue;
        }
        for j in (i + 1)..n_cells {
            if labels_a[j] == 0 {
                continue;
            }
            if labels_a[i] == labels_a[j] {
                assert_eq!(
                    labels_u[i], labels_u[j],
                    "connectivity lost under a union (monotonicity violated): seed={seed} i={i} j={j}"
                );
            }
        }
    }
}

/// Embedding a grid inside a larger all-background canvas (a zero border of
/// at least 1 cell on every side) changes neither the number of components
/// nor which foreground cells share a component -- background padding
/// cannot create or remove connectivity.
///
/// Bug this would catch: an off-by-one at the grid *edge* -- e.g. a
/// neighbor-offset check that reads out of bounds and (in a hypothetical
/// unchecked build) picks up stale/adjacent-row data, or a boundary
/// special-case that only activates when a foreground cell sits in row 0
/// or column 0 -- would pass every un-padded fixture but disagree with
/// itself once the same shape no longer touches the grid border.
pub(crate) fn cc_padding_invariant_impl(seed: u64) {
    let (mask, h, w) = cc_gen_mask(seed);
    let (labels0, n0) = label_components_8(&mask, h, w);
    let mut rng = sub_rng(seed, CC_SALT_PAD);
    let pad_top = 1 + rng.index(4);
    let pad_bottom = 1 + rng.index(4);
    let pad_left = 1 + rng.index(4);
    let pad_right = 1 + rng.index(4);
    let h2 = h + pad_top + pad_bottom;
    let w2 = w + pad_left + pad_right;
    let mut mask2 = vec![0u8; h2 * w2];
    for r in 0..h {
        for c in 0..w {
            mask2[(r + pad_top) * w2 + (c + pad_left)] = mask[r * w + c];
        }
    }
    let (labels1, n1) = label_components_8(&mask2, h2, w2);
    assert_eq!(n0, n1, "component count changed under zero-padding: seed={seed} h={h} w={w}");
    let n_cells = h * w;
    for i in 0..n_cells {
        if mask[i] == 0 {
            continue;
        }
        let (ri, ci) = (i / w, i % w);
        let ni = (ri + pad_top) * w2 + (ci + pad_left);
        for j in (i + 1)..n_cells {
            if mask[j] == 0 {
                continue;
            }
            let (rj, cj) = (j / w, j % w);
            let nj = (rj + pad_top) * w2 + (cj + pad_left);
            assert_eq!(
                labels0[i] == labels0[j],
                labels1[ni] == labels1[nj],
                "partition changed under zero-padding: seed={seed} i={i} j={j}"
            );
        }
    }
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
        let mut a = SplitMix64::new(777);
        let mut b = SplitMix64::new(777);
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
    fn kt_gen_case_is_deterministic() {
        assert_eq!(kt_gen_case(42), kt_gen_case(42));
    }

    #[cfg_attr(test, test)]
    fn kt_round_trip_zero_theta_is_exact_identity() {
        // math.cos(0.0) == 1.0 and math.sin(0.0) == 0.0 exactly (see
        // kicad_transform.rs's own zero-rotation test), so this edge case
        // should round-trip with zero error, not just within tolerance.
        let (wx, wy) = rotate_local_to_world(3.0, -2.0, 0.0);
        let (lx, ly) = rotate_world_to_local(wx, wy, 0.0);
        assert_eq!((lx, ly), (3.0, -2.0));
    }

    #[cfg_attr(test, test)]
    fn ch_gen_points_length_in_expected_range() {
        for seed in [0u64, 1, 500, 999_999] {
            let pts = ch_gen_points(seed);
            assert!(pts.len() >= 5 && pts.len() <= 15, "seed={seed} n={}", pts.len());
        }
    }

    #[cfg_attr(test, test)]
    fn ch_interior_combination_sanity_on_a_hand_built_triangle() {
        // Explicit non-random cross-check of the same relation
        // `ch_interior_point_invariant_impl` exercises at volume: the
        // centroid of a triangle's vertices lies strictly inside it, so
        // adding the centroid must not change the hull area.
        let pts = [[0.0, 0.0], [6.0, 0.0], [0.0, 6.0]];
        let a0 = convex_hull_area(&pts);
        let centroid = [(0.0 + 6.0 + 0.0) / 3.0, (0.0 + 0.0 + 6.0) / 3.0];
        let mut extended = pts.to_vec();
        extended.push(centroid);
        let a1 = convex_hull_area(&extended);
        assert!((a0 - a1).abs() < 1e-9, "a0={a0} a1={a1}");
        assert!((a0 - 18.0).abs() < 1e-9, "expected area 18.0, got {a0}");
    }

    #[cfg_attr(test, test)]
    fn dihedral_identity_is_a_noop() {
        for r in 0..4 {
            for c in 0..5 {
                assert_eq!(dihedral_index(0, r, c, 4, 5), (r, c));
            }
        }
        assert_eq!(dihedral_dims(0, 4, 5), (4, 5));
    }

    #[cfg_attr(test, test)]
    fn dihedral_rot90_matches_a_hand_worked_example() {
        // A 2x3 grid rotated 90 degrees clockwise becomes 3x2; (r=1,c=0)
        // (bottom-left) must land at the new grid's top-left (0,0).
        assert_eq!(dihedral_dims(1, 2, 3), (3, 2));
        assert_eq!(dihedral_index(1, 1, 0, 2, 3), (0, 0));
        assert_eq!(dihedral_index(1, 0, 0, 2, 3), (0, 1));
        assert_eq!(dihedral_index(1, 0, 2, 2, 3), (2, 1));
    }

    #[cfg_attr(test, test)]
    fn dihedral_transpose_matches_a_hand_worked_example() {
        assert_eq!(dihedral_dims(6, 2, 3), (3, 2));
        assert_eq!(dihedral_index(6, 1, 2, 2, 3), (2, 1));
    }

    #[cfg_attr(test, test)]
    fn cc_gen_mask_dims_in_expected_range() {
        for seed in [0u64, 3, 12345] {
            let (mask, h, w) = cc_gen_mask(seed);
            assert_eq!(mask.len(), h * w);
            assert!((4..=10).contains(&h), "seed={seed} h={h}");
            assert!((4..=10).contains(&w), "seed={seed} w={w}");
        }
    }

    // --- kt_round_trip: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000000() { kt_round_trip_impl(0); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000001() { kt_round_trip_impl(1); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000002() { kt_round_trip_impl(2); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000003() { kt_round_trip_impl(3); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000004() { kt_round_trip_impl(4); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000005() { kt_round_trip_impl(5); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000006() { kt_round_trip_impl(6); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000007() { kt_round_trip_impl(7); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000008() { kt_round_trip_impl(8); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000009() { kt_round_trip_impl(9); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000010() { kt_round_trip_impl(10); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000011() { kt_round_trip_impl(11); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000012() { kt_round_trip_impl(12); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000013() { kt_round_trip_impl(13); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000014() { kt_round_trip_impl(14); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000015() { kt_round_trip_impl(15); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000016() { kt_round_trip_impl(16); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000017() { kt_round_trip_impl(17); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000018() { kt_round_trip_impl(18); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000019() { kt_round_trip_impl(19); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000020() { kt_round_trip_impl(20); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000021() { kt_round_trip_impl(21); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000022() { kt_round_trip_impl(22); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000023() { kt_round_trip_impl(23); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000024() { kt_round_trip_impl(24); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000025() { kt_round_trip_impl(25); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000026() { kt_round_trip_impl(26); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000027() { kt_round_trip_impl(27); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000028() { kt_round_trip_impl(28); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000029() { kt_round_trip_impl(29); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000030() { kt_round_trip_impl(30); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000031() { kt_round_trip_impl(31); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000032() { kt_round_trip_impl(32); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000033() { kt_round_trip_impl(33); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000034() { kt_round_trip_impl(34); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000035() { kt_round_trip_impl(35); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000036() { kt_round_trip_impl(36); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000037() { kt_round_trip_impl(37); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000038() { kt_round_trip_impl(38); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000039() { kt_round_trip_impl(39); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000040() { kt_round_trip_impl(40); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000041() { kt_round_trip_impl(41); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000042() { kt_round_trip_impl(42); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000043() { kt_round_trip_impl(43); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000044() { kt_round_trip_impl(44); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000045() { kt_round_trip_impl(45); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000046() { kt_round_trip_impl(46); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000047() { kt_round_trip_impl(47); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000048() { kt_round_trip_impl(48); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000049() { kt_round_trip_impl(49); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000050() { kt_round_trip_impl(50); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000051() { kt_round_trip_impl(51); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000052() { kt_round_trip_impl(52); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000053() { kt_round_trip_impl(53); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000054() { kt_round_trip_impl(54); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000055() { kt_round_trip_impl(55); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000056() { kt_round_trip_impl(56); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000057() { kt_round_trip_impl(57); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000058() { kt_round_trip_impl(58); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000059() { kt_round_trip_impl(59); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000060() { kt_round_trip_impl(60); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000061() { kt_round_trip_impl(61); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000062() { kt_round_trip_impl(62); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000063() { kt_round_trip_impl(63); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000064() { kt_round_trip_impl(64); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000065() { kt_round_trip_impl(65); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000066() { kt_round_trip_impl(66); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000067() { kt_round_trip_impl(67); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000068() { kt_round_trip_impl(68); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000069() { kt_round_trip_impl(69); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000070() { kt_round_trip_impl(70); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000071() { kt_round_trip_impl(71); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000072() { kt_round_trip_impl(72); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000073() { kt_round_trip_impl(73); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000074() { kt_round_trip_impl(74); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000075() { kt_round_trip_impl(75); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000076() { kt_round_trip_impl(76); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000077() { kt_round_trip_impl(77); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000078() { kt_round_trip_impl(78); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000079() { kt_round_trip_impl(79); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000080() { kt_round_trip_impl(80); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000081() { kt_round_trip_impl(81); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000082() { kt_round_trip_impl(82); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000083() { kt_round_trip_impl(83); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000084() { kt_round_trip_impl(84); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000085() { kt_round_trip_impl(85); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000086() { kt_round_trip_impl(86); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000087() { kt_round_trip_impl(87); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000088() { kt_round_trip_impl(88); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000089() { kt_round_trip_impl(89); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000090() { kt_round_trip_impl(90); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000091() { kt_round_trip_impl(91); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000092() { kt_round_trip_impl(92); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000093() { kt_round_trip_impl(93); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000094() { kt_round_trip_impl(94); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000095() { kt_round_trip_impl(95); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000096() { kt_round_trip_impl(96); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000097() { kt_round_trip_impl(97); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000098() { kt_round_trip_impl(98); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000099() { kt_round_trip_impl(99); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000100() { kt_round_trip_impl(100); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000101() { kt_round_trip_impl(101); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000102() { kt_round_trip_impl(102); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000103() { kt_round_trip_impl(103); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000104() { kt_round_trip_impl(104); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000105() { kt_round_trip_impl(105); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000106() { kt_round_trip_impl(106); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000107() { kt_round_trip_impl(107); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000108() { kt_round_trip_impl(108); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000109() { kt_round_trip_impl(109); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000110() { kt_round_trip_impl(110); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000111() { kt_round_trip_impl(111); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000112() { kt_round_trip_impl(112); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000113() { kt_round_trip_impl(113); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000114() { kt_round_trip_impl(114); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000115() { kt_round_trip_impl(115); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000116() { kt_round_trip_impl(116); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000117() { kt_round_trip_impl(117); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000118() { kt_round_trip_impl(118); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000119() { kt_round_trip_impl(119); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000120() { kt_round_trip_impl(120); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000121() { kt_round_trip_impl(121); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000122() { kt_round_trip_impl(122); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000123() { kt_round_trip_impl(123); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000124() { kt_round_trip_impl(124); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000125() { kt_round_trip_impl(125); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000126() { kt_round_trip_impl(126); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000127() { kt_round_trip_impl(127); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000128() { kt_round_trip_impl(128); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000129() { kt_round_trip_impl(129); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000130() { kt_round_trip_impl(130); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000131() { kt_round_trip_impl(131); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000132() { kt_round_trip_impl(132); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000133() { kt_round_trip_impl(133); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000134() { kt_round_trip_impl(134); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000135() { kt_round_trip_impl(135); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000136() { kt_round_trip_impl(136); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000137() { kt_round_trip_impl(137); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000138() { kt_round_trip_impl(138); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000139() { kt_round_trip_impl(139); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000140() { kt_round_trip_impl(140); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000141() { kt_round_trip_impl(141); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000142() { kt_round_trip_impl(142); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000143() { kt_round_trip_impl(143); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000144() { kt_round_trip_impl(144); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000145() { kt_round_trip_impl(145); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000146() { kt_round_trip_impl(146); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000147() { kt_round_trip_impl(147); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000148() { kt_round_trip_impl(148); }
    #[cfg_attr(test, test)]
    fn kt_round_trip_seed_000149() { kt_round_trip_impl(149); }
    // --- kt_isometry: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000000() { kt_isometry_impl(0); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000001() { kt_isometry_impl(1); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000002() { kt_isometry_impl(2); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000003() { kt_isometry_impl(3); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000004() { kt_isometry_impl(4); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000005() { kt_isometry_impl(5); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000006() { kt_isometry_impl(6); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000007() { kt_isometry_impl(7); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000008() { kt_isometry_impl(8); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000009() { kt_isometry_impl(9); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000010() { kt_isometry_impl(10); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000011() { kt_isometry_impl(11); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000012() { kt_isometry_impl(12); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000013() { kt_isometry_impl(13); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000014() { kt_isometry_impl(14); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000015() { kt_isometry_impl(15); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000016() { kt_isometry_impl(16); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000017() { kt_isometry_impl(17); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000018() { kt_isometry_impl(18); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000019() { kt_isometry_impl(19); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000020() { kt_isometry_impl(20); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000021() { kt_isometry_impl(21); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000022() { kt_isometry_impl(22); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000023() { kt_isometry_impl(23); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000024() { kt_isometry_impl(24); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000025() { kt_isometry_impl(25); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000026() { kt_isometry_impl(26); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000027() { kt_isometry_impl(27); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000028() { kt_isometry_impl(28); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000029() { kt_isometry_impl(29); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000030() { kt_isometry_impl(30); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000031() { kt_isometry_impl(31); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000032() { kt_isometry_impl(32); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000033() { kt_isometry_impl(33); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000034() { kt_isometry_impl(34); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000035() { kt_isometry_impl(35); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000036() { kt_isometry_impl(36); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000037() { kt_isometry_impl(37); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000038() { kt_isometry_impl(38); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000039() { kt_isometry_impl(39); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000040() { kt_isometry_impl(40); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000041() { kt_isometry_impl(41); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000042() { kt_isometry_impl(42); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000043() { kt_isometry_impl(43); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000044() { kt_isometry_impl(44); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000045() { kt_isometry_impl(45); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000046() { kt_isometry_impl(46); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000047() { kt_isometry_impl(47); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000048() { kt_isometry_impl(48); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000049() { kt_isometry_impl(49); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000050() { kt_isometry_impl(50); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000051() { kt_isometry_impl(51); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000052() { kt_isometry_impl(52); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000053() { kt_isometry_impl(53); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000054() { kt_isometry_impl(54); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000055() { kt_isometry_impl(55); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000056() { kt_isometry_impl(56); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000057() { kt_isometry_impl(57); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000058() { kt_isometry_impl(58); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000059() { kt_isometry_impl(59); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000060() { kt_isometry_impl(60); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000061() { kt_isometry_impl(61); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000062() { kt_isometry_impl(62); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000063() { kt_isometry_impl(63); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000064() { kt_isometry_impl(64); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000065() { kt_isometry_impl(65); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000066() { kt_isometry_impl(66); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000067() { kt_isometry_impl(67); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000068() { kt_isometry_impl(68); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000069() { kt_isometry_impl(69); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000070() { kt_isometry_impl(70); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000071() { kt_isometry_impl(71); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000072() { kt_isometry_impl(72); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000073() { kt_isometry_impl(73); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000074() { kt_isometry_impl(74); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000075() { kt_isometry_impl(75); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000076() { kt_isometry_impl(76); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000077() { kt_isometry_impl(77); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000078() { kt_isometry_impl(78); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000079() { kt_isometry_impl(79); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000080() { kt_isometry_impl(80); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000081() { kt_isometry_impl(81); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000082() { kt_isometry_impl(82); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000083() { kt_isometry_impl(83); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000084() { kt_isometry_impl(84); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000085() { kt_isometry_impl(85); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000086() { kt_isometry_impl(86); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000087() { kt_isometry_impl(87); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000088() { kt_isometry_impl(88); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000089() { kt_isometry_impl(89); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000090() { kt_isometry_impl(90); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000091() { kt_isometry_impl(91); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000092() { kt_isometry_impl(92); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000093() { kt_isometry_impl(93); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000094() { kt_isometry_impl(94); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000095() { kt_isometry_impl(95); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000096() { kt_isometry_impl(96); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000097() { kt_isometry_impl(97); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000098() { kt_isometry_impl(98); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000099() { kt_isometry_impl(99); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000100() { kt_isometry_impl(100); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000101() { kt_isometry_impl(101); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000102() { kt_isometry_impl(102); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000103() { kt_isometry_impl(103); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000104() { kt_isometry_impl(104); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000105() { kt_isometry_impl(105); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000106() { kt_isometry_impl(106); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000107() { kt_isometry_impl(107); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000108() { kt_isometry_impl(108); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000109() { kt_isometry_impl(109); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000110() { kt_isometry_impl(110); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000111() { kt_isometry_impl(111); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000112() { kt_isometry_impl(112); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000113() { kt_isometry_impl(113); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000114() { kt_isometry_impl(114); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000115() { kt_isometry_impl(115); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000116() { kt_isometry_impl(116); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000117() { kt_isometry_impl(117); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000118() { kt_isometry_impl(118); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000119() { kt_isometry_impl(119); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000120() { kt_isometry_impl(120); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000121() { kt_isometry_impl(121); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000122() { kt_isometry_impl(122); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000123() { kt_isometry_impl(123); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000124() { kt_isometry_impl(124); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000125() { kt_isometry_impl(125); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000126() { kt_isometry_impl(126); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000127() { kt_isometry_impl(127); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000128() { kt_isometry_impl(128); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000129() { kt_isometry_impl(129); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000130() { kt_isometry_impl(130); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000131() { kt_isometry_impl(131); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000132() { kt_isometry_impl(132); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000133() { kt_isometry_impl(133); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000134() { kt_isometry_impl(134); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000135() { kt_isometry_impl(135); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000136() { kt_isometry_impl(136); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000137() { kt_isometry_impl(137); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000138() { kt_isometry_impl(138); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000139() { kt_isometry_impl(139); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000140() { kt_isometry_impl(140); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000141() { kt_isometry_impl(141); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000142() { kt_isometry_impl(142); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000143() { kt_isometry_impl(143); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000144() { kt_isometry_impl(144); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000145() { kt_isometry_impl(145); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000146() { kt_isometry_impl(146); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000147() { kt_isometry_impl(147); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000148() { kt_isometry_impl(148); }
    #[cfg_attr(test, test)]
    fn kt_isometry_seed_000149() { kt_isometry_impl(149); }
    // --- kt_composition: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000000() { kt_composition_impl(0); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000001() { kt_composition_impl(1); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000002() { kt_composition_impl(2); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000003() { kt_composition_impl(3); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000004() { kt_composition_impl(4); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000005() { kt_composition_impl(5); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000006() { kt_composition_impl(6); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000007() { kt_composition_impl(7); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000008() { kt_composition_impl(8); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000009() { kt_composition_impl(9); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000010() { kt_composition_impl(10); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000011() { kt_composition_impl(11); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000012() { kt_composition_impl(12); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000013() { kt_composition_impl(13); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000014() { kt_composition_impl(14); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000015() { kt_composition_impl(15); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000016() { kt_composition_impl(16); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000017() { kt_composition_impl(17); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000018() { kt_composition_impl(18); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000019() { kt_composition_impl(19); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000020() { kt_composition_impl(20); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000021() { kt_composition_impl(21); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000022() { kt_composition_impl(22); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000023() { kt_composition_impl(23); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000024() { kt_composition_impl(24); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000025() { kt_composition_impl(25); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000026() { kt_composition_impl(26); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000027() { kt_composition_impl(27); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000028() { kt_composition_impl(28); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000029() { kt_composition_impl(29); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000030() { kt_composition_impl(30); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000031() { kt_composition_impl(31); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000032() { kt_composition_impl(32); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000033() { kt_composition_impl(33); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000034() { kt_composition_impl(34); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000035() { kt_composition_impl(35); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000036() { kt_composition_impl(36); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000037() { kt_composition_impl(37); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000038() { kt_composition_impl(38); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000039() { kt_composition_impl(39); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000040() { kt_composition_impl(40); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000041() { kt_composition_impl(41); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000042() { kt_composition_impl(42); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000043() { kt_composition_impl(43); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000044() { kt_composition_impl(44); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000045() { kt_composition_impl(45); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000046() { kt_composition_impl(46); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000047() { kt_composition_impl(47); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000048() { kt_composition_impl(48); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000049() { kt_composition_impl(49); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000050() { kt_composition_impl(50); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000051() { kt_composition_impl(51); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000052() { kt_composition_impl(52); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000053() { kt_composition_impl(53); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000054() { kt_composition_impl(54); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000055() { kt_composition_impl(55); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000056() { kt_composition_impl(56); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000057() { kt_composition_impl(57); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000058() { kt_composition_impl(58); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000059() { kt_composition_impl(59); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000060() { kt_composition_impl(60); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000061() { kt_composition_impl(61); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000062() { kt_composition_impl(62); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000063() { kt_composition_impl(63); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000064() { kt_composition_impl(64); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000065() { kt_composition_impl(65); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000066() { kt_composition_impl(66); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000067() { kt_composition_impl(67); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000068() { kt_composition_impl(68); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000069() { kt_composition_impl(69); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000070() { kt_composition_impl(70); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000071() { kt_composition_impl(71); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000072() { kt_composition_impl(72); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000073() { kt_composition_impl(73); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000074() { kt_composition_impl(74); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000075() { kt_composition_impl(75); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000076() { kt_composition_impl(76); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000077() { kt_composition_impl(77); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000078() { kt_composition_impl(78); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000079() { kt_composition_impl(79); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000080() { kt_composition_impl(80); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000081() { kt_composition_impl(81); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000082() { kt_composition_impl(82); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000083() { kt_composition_impl(83); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000084() { kt_composition_impl(84); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000085() { kt_composition_impl(85); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000086() { kt_composition_impl(86); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000087() { kt_composition_impl(87); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000088() { kt_composition_impl(88); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000089() { kt_composition_impl(89); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000090() { kt_composition_impl(90); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000091() { kt_composition_impl(91); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000092() { kt_composition_impl(92); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000093() { kt_composition_impl(93); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000094() { kt_composition_impl(94); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000095() { kt_composition_impl(95); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000096() { kt_composition_impl(96); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000097() { kt_composition_impl(97); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000098() { kt_composition_impl(98); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000099() { kt_composition_impl(99); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000100() { kt_composition_impl(100); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000101() { kt_composition_impl(101); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000102() { kt_composition_impl(102); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000103() { kt_composition_impl(103); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000104() { kt_composition_impl(104); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000105() { kt_composition_impl(105); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000106() { kt_composition_impl(106); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000107() { kt_composition_impl(107); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000108() { kt_composition_impl(108); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000109() { kt_composition_impl(109); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000110() { kt_composition_impl(110); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000111() { kt_composition_impl(111); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000112() { kt_composition_impl(112); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000113() { kt_composition_impl(113); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000114() { kt_composition_impl(114); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000115() { kt_composition_impl(115); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000116() { kt_composition_impl(116); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000117() { kt_composition_impl(117); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000118() { kt_composition_impl(118); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000119() { kt_composition_impl(119); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000120() { kt_composition_impl(120); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000121() { kt_composition_impl(121); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000122() { kt_composition_impl(122); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000123() { kt_composition_impl(123); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000124() { kt_composition_impl(124); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000125() { kt_composition_impl(125); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000126() { kt_composition_impl(126); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000127() { kt_composition_impl(127); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000128() { kt_composition_impl(128); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000129() { kt_composition_impl(129); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000130() { kt_composition_impl(130); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000131() { kt_composition_impl(131); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000132() { kt_composition_impl(132); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000133() { kt_composition_impl(133); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000134() { kt_composition_impl(134); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000135() { kt_composition_impl(135); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000136() { kt_composition_impl(136); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000137() { kt_composition_impl(137); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000138() { kt_composition_impl(138); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000139() { kt_composition_impl(139); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000140() { kt_composition_impl(140); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000141() { kt_composition_impl(141); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000142() { kt_composition_impl(142); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000143() { kt_composition_impl(143); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000144() { kt_composition_impl(144); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000145() { kt_composition_impl(145); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000146() { kt_composition_impl(146); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000147() { kt_composition_impl(147); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000148() { kt_composition_impl(148); }
    #[cfg_attr(test, test)]
    fn kt_composition_seed_000149() { kt_composition_impl(149); }
    // --- kt_place_translation: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000000() { kt_place_translation_impl(0); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000001() { kt_place_translation_impl(1); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000002() { kt_place_translation_impl(2); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000003() { kt_place_translation_impl(3); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000004() { kt_place_translation_impl(4); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000005() { kt_place_translation_impl(5); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000006() { kt_place_translation_impl(6); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000007() { kt_place_translation_impl(7); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000008() { kt_place_translation_impl(8); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000009() { kt_place_translation_impl(9); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000010() { kt_place_translation_impl(10); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000011() { kt_place_translation_impl(11); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000012() { kt_place_translation_impl(12); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000013() { kt_place_translation_impl(13); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000014() { kt_place_translation_impl(14); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000015() { kt_place_translation_impl(15); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000016() { kt_place_translation_impl(16); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000017() { kt_place_translation_impl(17); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000018() { kt_place_translation_impl(18); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000019() { kt_place_translation_impl(19); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000020() { kt_place_translation_impl(20); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000021() { kt_place_translation_impl(21); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000022() { kt_place_translation_impl(22); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000023() { kt_place_translation_impl(23); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000024() { kt_place_translation_impl(24); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000025() { kt_place_translation_impl(25); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000026() { kt_place_translation_impl(26); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000027() { kt_place_translation_impl(27); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000028() { kt_place_translation_impl(28); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000029() { kt_place_translation_impl(29); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000030() { kt_place_translation_impl(30); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000031() { kt_place_translation_impl(31); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000032() { kt_place_translation_impl(32); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000033() { kt_place_translation_impl(33); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000034() { kt_place_translation_impl(34); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000035() { kt_place_translation_impl(35); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000036() { kt_place_translation_impl(36); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000037() { kt_place_translation_impl(37); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000038() { kt_place_translation_impl(38); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000039() { kt_place_translation_impl(39); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000040() { kt_place_translation_impl(40); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000041() { kt_place_translation_impl(41); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000042() { kt_place_translation_impl(42); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000043() { kt_place_translation_impl(43); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000044() { kt_place_translation_impl(44); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000045() { kt_place_translation_impl(45); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000046() { kt_place_translation_impl(46); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000047() { kt_place_translation_impl(47); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000048() { kt_place_translation_impl(48); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000049() { kt_place_translation_impl(49); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000050() { kt_place_translation_impl(50); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000051() { kt_place_translation_impl(51); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000052() { kt_place_translation_impl(52); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000053() { kt_place_translation_impl(53); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000054() { kt_place_translation_impl(54); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000055() { kt_place_translation_impl(55); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000056() { kt_place_translation_impl(56); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000057() { kt_place_translation_impl(57); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000058() { kt_place_translation_impl(58); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000059() { kt_place_translation_impl(59); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000060() { kt_place_translation_impl(60); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000061() { kt_place_translation_impl(61); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000062() { kt_place_translation_impl(62); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000063() { kt_place_translation_impl(63); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000064() { kt_place_translation_impl(64); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000065() { kt_place_translation_impl(65); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000066() { kt_place_translation_impl(66); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000067() { kt_place_translation_impl(67); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000068() { kt_place_translation_impl(68); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000069() { kt_place_translation_impl(69); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000070() { kt_place_translation_impl(70); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000071() { kt_place_translation_impl(71); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000072() { kt_place_translation_impl(72); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000073() { kt_place_translation_impl(73); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000074() { kt_place_translation_impl(74); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000075() { kt_place_translation_impl(75); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000076() { kt_place_translation_impl(76); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000077() { kt_place_translation_impl(77); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000078() { kt_place_translation_impl(78); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000079() { kt_place_translation_impl(79); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000080() { kt_place_translation_impl(80); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000081() { kt_place_translation_impl(81); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000082() { kt_place_translation_impl(82); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000083() { kt_place_translation_impl(83); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000084() { kt_place_translation_impl(84); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000085() { kt_place_translation_impl(85); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000086() { kt_place_translation_impl(86); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000087() { kt_place_translation_impl(87); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000088() { kt_place_translation_impl(88); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000089() { kt_place_translation_impl(89); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000090() { kt_place_translation_impl(90); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000091() { kt_place_translation_impl(91); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000092() { kt_place_translation_impl(92); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000093() { kt_place_translation_impl(93); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000094() { kt_place_translation_impl(94); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000095() { kt_place_translation_impl(95); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000096() { kt_place_translation_impl(96); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000097() { kt_place_translation_impl(97); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000098() { kt_place_translation_impl(98); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000099() { kt_place_translation_impl(99); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000100() { kt_place_translation_impl(100); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000101() { kt_place_translation_impl(101); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000102() { kt_place_translation_impl(102); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000103() { kt_place_translation_impl(103); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000104() { kt_place_translation_impl(104); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000105() { kt_place_translation_impl(105); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000106() { kt_place_translation_impl(106); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000107() { kt_place_translation_impl(107); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000108() { kt_place_translation_impl(108); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000109() { kt_place_translation_impl(109); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000110() { kt_place_translation_impl(110); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000111() { kt_place_translation_impl(111); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000112() { kt_place_translation_impl(112); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000113() { kt_place_translation_impl(113); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000114() { kt_place_translation_impl(114); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000115() { kt_place_translation_impl(115); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000116() { kt_place_translation_impl(116); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000117() { kt_place_translation_impl(117); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000118() { kt_place_translation_impl(118); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000119() { kt_place_translation_impl(119); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000120() { kt_place_translation_impl(120); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000121() { kt_place_translation_impl(121); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000122() { kt_place_translation_impl(122); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000123() { kt_place_translation_impl(123); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000124() { kt_place_translation_impl(124); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000125() { kt_place_translation_impl(125); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000126() { kt_place_translation_impl(126); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000127() { kt_place_translation_impl(127); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000128() { kt_place_translation_impl(128); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000129() { kt_place_translation_impl(129); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000130() { kt_place_translation_impl(130); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000131() { kt_place_translation_impl(131); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000132() { kt_place_translation_impl(132); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000133() { kt_place_translation_impl(133); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000134() { kt_place_translation_impl(134); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000135() { kt_place_translation_impl(135); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000136() { kt_place_translation_impl(136); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000137() { kt_place_translation_impl(137); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000138() { kt_place_translation_impl(138); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000139() { kt_place_translation_impl(139); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000140() { kt_place_translation_impl(140); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000141() { kt_place_translation_impl(141); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000142() { kt_place_translation_impl(142); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000143() { kt_place_translation_impl(143); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000144() { kt_place_translation_impl(144); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000145() { kt_place_translation_impl(145); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000146() { kt_place_translation_impl(146); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000147() { kt_place_translation_impl(147); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000148() { kt_place_translation_impl(148); }
    #[cfg_attr(test, test)]
    fn kt_place_translation_seed_000149() { kt_place_translation_impl(149); }
    // --- ch_translation: 120 generated seeds ---
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000000() { ch_translation_invariant_impl(0); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000001() { ch_translation_invariant_impl(1); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000002() { ch_translation_invariant_impl(2); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000003() { ch_translation_invariant_impl(3); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000004() { ch_translation_invariant_impl(4); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000005() { ch_translation_invariant_impl(5); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000006() { ch_translation_invariant_impl(6); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000007() { ch_translation_invariant_impl(7); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000008() { ch_translation_invariant_impl(8); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000009() { ch_translation_invariant_impl(9); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000010() { ch_translation_invariant_impl(10); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000011() { ch_translation_invariant_impl(11); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000012() { ch_translation_invariant_impl(12); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000013() { ch_translation_invariant_impl(13); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000014() { ch_translation_invariant_impl(14); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000015() { ch_translation_invariant_impl(15); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000016() { ch_translation_invariant_impl(16); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000017() { ch_translation_invariant_impl(17); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000018() { ch_translation_invariant_impl(18); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000019() { ch_translation_invariant_impl(19); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000020() { ch_translation_invariant_impl(20); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000021() { ch_translation_invariant_impl(21); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000022() { ch_translation_invariant_impl(22); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000023() { ch_translation_invariant_impl(23); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000024() { ch_translation_invariant_impl(24); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000025() { ch_translation_invariant_impl(25); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000026() { ch_translation_invariant_impl(26); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000027() { ch_translation_invariant_impl(27); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000028() { ch_translation_invariant_impl(28); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000029() { ch_translation_invariant_impl(29); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000030() { ch_translation_invariant_impl(30); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000031() { ch_translation_invariant_impl(31); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000032() { ch_translation_invariant_impl(32); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000033() { ch_translation_invariant_impl(33); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000034() { ch_translation_invariant_impl(34); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000035() { ch_translation_invariant_impl(35); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000036() { ch_translation_invariant_impl(36); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000037() { ch_translation_invariant_impl(37); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000038() { ch_translation_invariant_impl(38); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000039() { ch_translation_invariant_impl(39); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000040() { ch_translation_invariant_impl(40); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000041() { ch_translation_invariant_impl(41); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000042() { ch_translation_invariant_impl(42); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000043() { ch_translation_invariant_impl(43); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000044() { ch_translation_invariant_impl(44); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000045() { ch_translation_invariant_impl(45); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000046() { ch_translation_invariant_impl(46); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000047() { ch_translation_invariant_impl(47); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000048() { ch_translation_invariant_impl(48); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000049() { ch_translation_invariant_impl(49); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000050() { ch_translation_invariant_impl(50); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000051() { ch_translation_invariant_impl(51); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000052() { ch_translation_invariant_impl(52); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000053() { ch_translation_invariant_impl(53); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000054() { ch_translation_invariant_impl(54); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000055() { ch_translation_invariant_impl(55); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000056() { ch_translation_invariant_impl(56); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000057() { ch_translation_invariant_impl(57); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000058() { ch_translation_invariant_impl(58); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000059() { ch_translation_invariant_impl(59); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000060() { ch_translation_invariant_impl(60); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000061() { ch_translation_invariant_impl(61); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000062() { ch_translation_invariant_impl(62); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000063() { ch_translation_invariant_impl(63); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000064() { ch_translation_invariant_impl(64); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000065() { ch_translation_invariant_impl(65); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000066() { ch_translation_invariant_impl(66); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000067() { ch_translation_invariant_impl(67); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000068() { ch_translation_invariant_impl(68); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000069() { ch_translation_invariant_impl(69); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000070() { ch_translation_invariant_impl(70); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000071() { ch_translation_invariant_impl(71); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000072() { ch_translation_invariant_impl(72); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000073() { ch_translation_invariant_impl(73); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000074() { ch_translation_invariant_impl(74); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000075() { ch_translation_invariant_impl(75); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000076() { ch_translation_invariant_impl(76); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000077() { ch_translation_invariant_impl(77); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000078() { ch_translation_invariant_impl(78); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000079() { ch_translation_invariant_impl(79); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000080() { ch_translation_invariant_impl(80); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000081() { ch_translation_invariant_impl(81); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000082() { ch_translation_invariant_impl(82); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000083() { ch_translation_invariant_impl(83); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000084() { ch_translation_invariant_impl(84); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000085() { ch_translation_invariant_impl(85); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000086() { ch_translation_invariant_impl(86); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000087() { ch_translation_invariant_impl(87); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000088() { ch_translation_invariant_impl(88); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000089() { ch_translation_invariant_impl(89); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000090() { ch_translation_invariant_impl(90); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000091() { ch_translation_invariant_impl(91); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000092() { ch_translation_invariant_impl(92); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000093() { ch_translation_invariant_impl(93); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000094() { ch_translation_invariant_impl(94); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000095() { ch_translation_invariant_impl(95); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000096() { ch_translation_invariant_impl(96); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000097() { ch_translation_invariant_impl(97); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000098() { ch_translation_invariant_impl(98); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000099() { ch_translation_invariant_impl(99); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000100() { ch_translation_invariant_impl(100); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000101() { ch_translation_invariant_impl(101); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000102() { ch_translation_invariant_impl(102); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000103() { ch_translation_invariant_impl(103); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000104() { ch_translation_invariant_impl(104); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000105() { ch_translation_invariant_impl(105); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000106() { ch_translation_invariant_impl(106); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000107() { ch_translation_invariant_impl(107); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000108() { ch_translation_invariant_impl(108); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000109() { ch_translation_invariant_impl(109); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000110() { ch_translation_invariant_impl(110); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000111() { ch_translation_invariant_impl(111); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000112() { ch_translation_invariant_impl(112); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000113() { ch_translation_invariant_impl(113); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000114() { ch_translation_invariant_impl(114); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000115() { ch_translation_invariant_impl(115); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000116() { ch_translation_invariant_impl(116); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000117() { ch_translation_invariant_impl(117); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000118() { ch_translation_invariant_impl(118); }
    #[cfg_attr(test, test)]
    fn ch_translation_seed_000119() { ch_translation_invariant_impl(119); }
    // --- ch_rotation: 120 generated seeds ---
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000000() { ch_rotation_invariant_impl(0); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000001() { ch_rotation_invariant_impl(1); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000002() { ch_rotation_invariant_impl(2); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000003() { ch_rotation_invariant_impl(3); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000004() { ch_rotation_invariant_impl(4); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000005() { ch_rotation_invariant_impl(5); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000006() { ch_rotation_invariant_impl(6); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000007() { ch_rotation_invariant_impl(7); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000008() { ch_rotation_invariant_impl(8); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000009() { ch_rotation_invariant_impl(9); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000010() { ch_rotation_invariant_impl(10); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000011() { ch_rotation_invariant_impl(11); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000012() { ch_rotation_invariant_impl(12); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000013() { ch_rotation_invariant_impl(13); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000014() { ch_rotation_invariant_impl(14); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000015() { ch_rotation_invariant_impl(15); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000016() { ch_rotation_invariant_impl(16); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000017() { ch_rotation_invariant_impl(17); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000018() { ch_rotation_invariant_impl(18); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000019() { ch_rotation_invariant_impl(19); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000020() { ch_rotation_invariant_impl(20); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000021() { ch_rotation_invariant_impl(21); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000022() { ch_rotation_invariant_impl(22); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000023() { ch_rotation_invariant_impl(23); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000024() { ch_rotation_invariant_impl(24); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000025() { ch_rotation_invariant_impl(25); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000026() { ch_rotation_invariant_impl(26); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000027() { ch_rotation_invariant_impl(27); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000028() { ch_rotation_invariant_impl(28); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000029() { ch_rotation_invariant_impl(29); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000030() { ch_rotation_invariant_impl(30); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000031() { ch_rotation_invariant_impl(31); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000032() { ch_rotation_invariant_impl(32); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000033() { ch_rotation_invariant_impl(33); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000034() { ch_rotation_invariant_impl(34); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000035() { ch_rotation_invariant_impl(35); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000036() { ch_rotation_invariant_impl(36); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000037() { ch_rotation_invariant_impl(37); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000038() { ch_rotation_invariant_impl(38); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000039() { ch_rotation_invariant_impl(39); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000040() { ch_rotation_invariant_impl(40); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000041() { ch_rotation_invariant_impl(41); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000042() { ch_rotation_invariant_impl(42); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000043() { ch_rotation_invariant_impl(43); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000044() { ch_rotation_invariant_impl(44); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000045() { ch_rotation_invariant_impl(45); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000046() { ch_rotation_invariant_impl(46); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000047() { ch_rotation_invariant_impl(47); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000048() { ch_rotation_invariant_impl(48); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000049() { ch_rotation_invariant_impl(49); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000050() { ch_rotation_invariant_impl(50); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000051() { ch_rotation_invariant_impl(51); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000052() { ch_rotation_invariant_impl(52); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000053() { ch_rotation_invariant_impl(53); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000054() { ch_rotation_invariant_impl(54); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000055() { ch_rotation_invariant_impl(55); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000056() { ch_rotation_invariant_impl(56); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000057() { ch_rotation_invariant_impl(57); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000058() { ch_rotation_invariant_impl(58); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000059() { ch_rotation_invariant_impl(59); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000060() { ch_rotation_invariant_impl(60); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000061() { ch_rotation_invariant_impl(61); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000062() { ch_rotation_invariant_impl(62); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000063() { ch_rotation_invariant_impl(63); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000064() { ch_rotation_invariant_impl(64); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000065() { ch_rotation_invariant_impl(65); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000066() { ch_rotation_invariant_impl(66); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000067() { ch_rotation_invariant_impl(67); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000068() { ch_rotation_invariant_impl(68); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000069() { ch_rotation_invariant_impl(69); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000070() { ch_rotation_invariant_impl(70); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000071() { ch_rotation_invariant_impl(71); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000072() { ch_rotation_invariant_impl(72); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000073() { ch_rotation_invariant_impl(73); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000074() { ch_rotation_invariant_impl(74); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000075() { ch_rotation_invariant_impl(75); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000076() { ch_rotation_invariant_impl(76); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000077() { ch_rotation_invariant_impl(77); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000078() { ch_rotation_invariant_impl(78); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000079() { ch_rotation_invariant_impl(79); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000080() { ch_rotation_invariant_impl(80); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000081() { ch_rotation_invariant_impl(81); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000082() { ch_rotation_invariant_impl(82); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000083() { ch_rotation_invariant_impl(83); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000084() { ch_rotation_invariant_impl(84); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000085() { ch_rotation_invariant_impl(85); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000086() { ch_rotation_invariant_impl(86); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000087() { ch_rotation_invariant_impl(87); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000088() { ch_rotation_invariant_impl(88); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000089() { ch_rotation_invariant_impl(89); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000090() { ch_rotation_invariant_impl(90); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000091() { ch_rotation_invariant_impl(91); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000092() { ch_rotation_invariant_impl(92); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000093() { ch_rotation_invariant_impl(93); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000094() { ch_rotation_invariant_impl(94); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000095() { ch_rotation_invariant_impl(95); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000096() { ch_rotation_invariant_impl(96); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000097() { ch_rotation_invariant_impl(97); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000098() { ch_rotation_invariant_impl(98); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000099() { ch_rotation_invariant_impl(99); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000100() { ch_rotation_invariant_impl(100); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000101() { ch_rotation_invariant_impl(101); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000102() { ch_rotation_invariant_impl(102); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000103() { ch_rotation_invariant_impl(103); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000104() { ch_rotation_invariant_impl(104); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000105() { ch_rotation_invariant_impl(105); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000106() { ch_rotation_invariant_impl(106); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000107() { ch_rotation_invariant_impl(107); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000108() { ch_rotation_invariant_impl(108); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000109() { ch_rotation_invariant_impl(109); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000110() { ch_rotation_invariant_impl(110); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000111() { ch_rotation_invariant_impl(111); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000112() { ch_rotation_invariant_impl(112); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000113() { ch_rotation_invariant_impl(113); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000114() { ch_rotation_invariant_impl(114); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000115() { ch_rotation_invariant_impl(115); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000116() { ch_rotation_invariant_impl(116); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000117() { ch_rotation_invariant_impl(117); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000118() { ch_rotation_invariant_impl(118); }
    #[cfg_attr(test, test)]
    fn ch_rotation_seed_000119() { ch_rotation_invariant_impl(119); }
    // --- ch_scale: 120 generated seeds ---
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000000() { ch_scale_quadratic_impl(0); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000001() { ch_scale_quadratic_impl(1); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000002() { ch_scale_quadratic_impl(2); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000003() { ch_scale_quadratic_impl(3); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000004() { ch_scale_quadratic_impl(4); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000005() { ch_scale_quadratic_impl(5); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000006() { ch_scale_quadratic_impl(6); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000007() { ch_scale_quadratic_impl(7); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000008() { ch_scale_quadratic_impl(8); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000009() { ch_scale_quadratic_impl(9); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000010() { ch_scale_quadratic_impl(10); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000011() { ch_scale_quadratic_impl(11); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000012() { ch_scale_quadratic_impl(12); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000013() { ch_scale_quadratic_impl(13); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000014() { ch_scale_quadratic_impl(14); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000015() { ch_scale_quadratic_impl(15); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000016() { ch_scale_quadratic_impl(16); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000017() { ch_scale_quadratic_impl(17); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000018() { ch_scale_quadratic_impl(18); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000019() { ch_scale_quadratic_impl(19); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000020() { ch_scale_quadratic_impl(20); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000021() { ch_scale_quadratic_impl(21); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000022() { ch_scale_quadratic_impl(22); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000023() { ch_scale_quadratic_impl(23); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000024() { ch_scale_quadratic_impl(24); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000025() { ch_scale_quadratic_impl(25); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000026() { ch_scale_quadratic_impl(26); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000027() { ch_scale_quadratic_impl(27); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000028() { ch_scale_quadratic_impl(28); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000029() { ch_scale_quadratic_impl(29); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000030() { ch_scale_quadratic_impl(30); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000031() { ch_scale_quadratic_impl(31); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000032() { ch_scale_quadratic_impl(32); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000033() { ch_scale_quadratic_impl(33); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000034() { ch_scale_quadratic_impl(34); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000035() { ch_scale_quadratic_impl(35); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000036() { ch_scale_quadratic_impl(36); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000037() { ch_scale_quadratic_impl(37); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000038() { ch_scale_quadratic_impl(38); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000039() { ch_scale_quadratic_impl(39); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000040() { ch_scale_quadratic_impl(40); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000041() { ch_scale_quadratic_impl(41); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000042() { ch_scale_quadratic_impl(42); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000043() { ch_scale_quadratic_impl(43); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000044() { ch_scale_quadratic_impl(44); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000045() { ch_scale_quadratic_impl(45); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000046() { ch_scale_quadratic_impl(46); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000047() { ch_scale_quadratic_impl(47); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000048() { ch_scale_quadratic_impl(48); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000049() { ch_scale_quadratic_impl(49); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000050() { ch_scale_quadratic_impl(50); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000051() { ch_scale_quadratic_impl(51); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000052() { ch_scale_quadratic_impl(52); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000053() { ch_scale_quadratic_impl(53); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000054() { ch_scale_quadratic_impl(54); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000055() { ch_scale_quadratic_impl(55); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000056() { ch_scale_quadratic_impl(56); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000057() { ch_scale_quadratic_impl(57); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000058() { ch_scale_quadratic_impl(58); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000059() { ch_scale_quadratic_impl(59); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000060() { ch_scale_quadratic_impl(60); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000061() { ch_scale_quadratic_impl(61); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000062() { ch_scale_quadratic_impl(62); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000063() { ch_scale_quadratic_impl(63); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000064() { ch_scale_quadratic_impl(64); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000065() { ch_scale_quadratic_impl(65); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000066() { ch_scale_quadratic_impl(66); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000067() { ch_scale_quadratic_impl(67); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000068() { ch_scale_quadratic_impl(68); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000069() { ch_scale_quadratic_impl(69); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000070() { ch_scale_quadratic_impl(70); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000071() { ch_scale_quadratic_impl(71); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000072() { ch_scale_quadratic_impl(72); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000073() { ch_scale_quadratic_impl(73); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000074() { ch_scale_quadratic_impl(74); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000075() { ch_scale_quadratic_impl(75); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000076() { ch_scale_quadratic_impl(76); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000077() { ch_scale_quadratic_impl(77); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000078() { ch_scale_quadratic_impl(78); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000079() { ch_scale_quadratic_impl(79); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000080() { ch_scale_quadratic_impl(80); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000081() { ch_scale_quadratic_impl(81); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000082() { ch_scale_quadratic_impl(82); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000083() { ch_scale_quadratic_impl(83); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000084() { ch_scale_quadratic_impl(84); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000085() { ch_scale_quadratic_impl(85); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000086() { ch_scale_quadratic_impl(86); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000087() { ch_scale_quadratic_impl(87); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000088() { ch_scale_quadratic_impl(88); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000089() { ch_scale_quadratic_impl(89); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000090() { ch_scale_quadratic_impl(90); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000091() { ch_scale_quadratic_impl(91); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000092() { ch_scale_quadratic_impl(92); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000093() { ch_scale_quadratic_impl(93); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000094() { ch_scale_quadratic_impl(94); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000095() { ch_scale_quadratic_impl(95); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000096() { ch_scale_quadratic_impl(96); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000097() { ch_scale_quadratic_impl(97); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000098() { ch_scale_quadratic_impl(98); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000099() { ch_scale_quadratic_impl(99); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000100() { ch_scale_quadratic_impl(100); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000101() { ch_scale_quadratic_impl(101); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000102() { ch_scale_quadratic_impl(102); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000103() { ch_scale_quadratic_impl(103); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000104() { ch_scale_quadratic_impl(104); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000105() { ch_scale_quadratic_impl(105); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000106() { ch_scale_quadratic_impl(106); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000107() { ch_scale_quadratic_impl(107); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000108() { ch_scale_quadratic_impl(108); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000109() { ch_scale_quadratic_impl(109); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000110() { ch_scale_quadratic_impl(110); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000111() { ch_scale_quadratic_impl(111); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000112() { ch_scale_quadratic_impl(112); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000113() { ch_scale_quadratic_impl(113); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000114() { ch_scale_quadratic_impl(114); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000115() { ch_scale_quadratic_impl(115); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000116() { ch_scale_quadratic_impl(116); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000117() { ch_scale_quadratic_impl(117); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000118() { ch_scale_quadratic_impl(118); }
    #[cfg_attr(test, test)]
    fn ch_scale_seed_000119() { ch_scale_quadratic_impl(119); }
    // --- ch_superset: 120 generated seeds ---
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000000() { ch_superset_monotonic_impl(0); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000001() { ch_superset_monotonic_impl(1); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000002() { ch_superset_monotonic_impl(2); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000003() { ch_superset_monotonic_impl(3); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000004() { ch_superset_monotonic_impl(4); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000005() { ch_superset_monotonic_impl(5); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000006() { ch_superset_monotonic_impl(6); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000007() { ch_superset_monotonic_impl(7); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000008() { ch_superset_monotonic_impl(8); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000009() { ch_superset_monotonic_impl(9); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000010() { ch_superset_monotonic_impl(10); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000011() { ch_superset_monotonic_impl(11); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000012() { ch_superset_monotonic_impl(12); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000013() { ch_superset_monotonic_impl(13); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000014() { ch_superset_monotonic_impl(14); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000015() { ch_superset_monotonic_impl(15); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000016() { ch_superset_monotonic_impl(16); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000017() { ch_superset_monotonic_impl(17); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000018() { ch_superset_monotonic_impl(18); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000019() { ch_superset_monotonic_impl(19); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000020() { ch_superset_monotonic_impl(20); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000021() { ch_superset_monotonic_impl(21); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000022() { ch_superset_monotonic_impl(22); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000023() { ch_superset_monotonic_impl(23); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000024() { ch_superset_monotonic_impl(24); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000025() { ch_superset_monotonic_impl(25); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000026() { ch_superset_monotonic_impl(26); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000027() { ch_superset_monotonic_impl(27); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000028() { ch_superset_monotonic_impl(28); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000029() { ch_superset_monotonic_impl(29); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000030() { ch_superset_monotonic_impl(30); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000031() { ch_superset_monotonic_impl(31); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000032() { ch_superset_monotonic_impl(32); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000033() { ch_superset_monotonic_impl(33); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000034() { ch_superset_monotonic_impl(34); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000035() { ch_superset_monotonic_impl(35); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000036() { ch_superset_monotonic_impl(36); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000037() { ch_superset_monotonic_impl(37); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000038() { ch_superset_monotonic_impl(38); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000039() { ch_superset_monotonic_impl(39); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000040() { ch_superset_monotonic_impl(40); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000041() { ch_superset_monotonic_impl(41); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000042() { ch_superset_monotonic_impl(42); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000043() { ch_superset_monotonic_impl(43); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000044() { ch_superset_monotonic_impl(44); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000045() { ch_superset_monotonic_impl(45); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000046() { ch_superset_monotonic_impl(46); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000047() { ch_superset_monotonic_impl(47); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000048() { ch_superset_monotonic_impl(48); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000049() { ch_superset_monotonic_impl(49); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000050() { ch_superset_monotonic_impl(50); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000051() { ch_superset_monotonic_impl(51); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000052() { ch_superset_monotonic_impl(52); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000053() { ch_superset_monotonic_impl(53); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000054() { ch_superset_monotonic_impl(54); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000055() { ch_superset_monotonic_impl(55); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000056() { ch_superset_monotonic_impl(56); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000057() { ch_superset_monotonic_impl(57); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000058() { ch_superset_monotonic_impl(58); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000059() { ch_superset_monotonic_impl(59); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000060() { ch_superset_monotonic_impl(60); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000061() { ch_superset_monotonic_impl(61); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000062() { ch_superset_monotonic_impl(62); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000063() { ch_superset_monotonic_impl(63); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000064() { ch_superset_monotonic_impl(64); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000065() { ch_superset_monotonic_impl(65); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000066() { ch_superset_monotonic_impl(66); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000067() { ch_superset_monotonic_impl(67); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000068() { ch_superset_monotonic_impl(68); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000069() { ch_superset_monotonic_impl(69); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000070() { ch_superset_monotonic_impl(70); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000071() { ch_superset_monotonic_impl(71); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000072() { ch_superset_monotonic_impl(72); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000073() { ch_superset_monotonic_impl(73); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000074() { ch_superset_monotonic_impl(74); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000075() { ch_superset_monotonic_impl(75); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000076() { ch_superset_monotonic_impl(76); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000077() { ch_superset_monotonic_impl(77); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000078() { ch_superset_monotonic_impl(78); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000079() { ch_superset_monotonic_impl(79); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000080() { ch_superset_monotonic_impl(80); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000081() { ch_superset_monotonic_impl(81); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000082() { ch_superset_monotonic_impl(82); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000083() { ch_superset_monotonic_impl(83); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000084() { ch_superset_monotonic_impl(84); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000085() { ch_superset_monotonic_impl(85); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000086() { ch_superset_monotonic_impl(86); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000087() { ch_superset_monotonic_impl(87); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000088() { ch_superset_monotonic_impl(88); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000089() { ch_superset_monotonic_impl(89); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000090() { ch_superset_monotonic_impl(90); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000091() { ch_superset_monotonic_impl(91); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000092() { ch_superset_monotonic_impl(92); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000093() { ch_superset_monotonic_impl(93); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000094() { ch_superset_monotonic_impl(94); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000095() { ch_superset_monotonic_impl(95); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000096() { ch_superset_monotonic_impl(96); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000097() { ch_superset_monotonic_impl(97); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000098() { ch_superset_monotonic_impl(98); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000099() { ch_superset_monotonic_impl(99); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000100() { ch_superset_monotonic_impl(100); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000101() { ch_superset_monotonic_impl(101); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000102() { ch_superset_monotonic_impl(102); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000103() { ch_superset_monotonic_impl(103); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000104() { ch_superset_monotonic_impl(104); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000105() { ch_superset_monotonic_impl(105); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000106() { ch_superset_monotonic_impl(106); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000107() { ch_superset_monotonic_impl(107); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000108() { ch_superset_monotonic_impl(108); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000109() { ch_superset_monotonic_impl(109); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000110() { ch_superset_monotonic_impl(110); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000111() { ch_superset_monotonic_impl(111); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000112() { ch_superset_monotonic_impl(112); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000113() { ch_superset_monotonic_impl(113); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000114() { ch_superset_monotonic_impl(114); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000115() { ch_superset_monotonic_impl(115); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000116() { ch_superset_monotonic_impl(116); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000117() { ch_superset_monotonic_impl(117); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000118() { ch_superset_monotonic_impl(118); }
    #[cfg_attr(test, test)]
    fn ch_superset_seed_000119() { ch_superset_monotonic_impl(119); }
    // --- ch_interior: 120 generated seeds ---
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000000() { ch_interior_point_invariant_impl(0); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000001() { ch_interior_point_invariant_impl(1); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000002() { ch_interior_point_invariant_impl(2); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000003() { ch_interior_point_invariant_impl(3); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000004() { ch_interior_point_invariant_impl(4); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000005() { ch_interior_point_invariant_impl(5); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000006() { ch_interior_point_invariant_impl(6); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000007() { ch_interior_point_invariant_impl(7); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000008() { ch_interior_point_invariant_impl(8); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000009() { ch_interior_point_invariant_impl(9); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000010() { ch_interior_point_invariant_impl(10); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000011() { ch_interior_point_invariant_impl(11); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000012() { ch_interior_point_invariant_impl(12); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000013() { ch_interior_point_invariant_impl(13); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000014() { ch_interior_point_invariant_impl(14); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000015() { ch_interior_point_invariant_impl(15); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000016() { ch_interior_point_invariant_impl(16); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000017() { ch_interior_point_invariant_impl(17); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000018() { ch_interior_point_invariant_impl(18); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000019() { ch_interior_point_invariant_impl(19); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000020() { ch_interior_point_invariant_impl(20); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000021() { ch_interior_point_invariant_impl(21); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000022() { ch_interior_point_invariant_impl(22); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000023() { ch_interior_point_invariant_impl(23); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000024() { ch_interior_point_invariant_impl(24); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000025() { ch_interior_point_invariant_impl(25); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000026() { ch_interior_point_invariant_impl(26); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000027() { ch_interior_point_invariant_impl(27); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000028() { ch_interior_point_invariant_impl(28); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000029() { ch_interior_point_invariant_impl(29); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000030() { ch_interior_point_invariant_impl(30); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000031() { ch_interior_point_invariant_impl(31); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000032() { ch_interior_point_invariant_impl(32); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000033() { ch_interior_point_invariant_impl(33); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000034() { ch_interior_point_invariant_impl(34); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000035() { ch_interior_point_invariant_impl(35); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000036() { ch_interior_point_invariant_impl(36); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000037() { ch_interior_point_invariant_impl(37); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000038() { ch_interior_point_invariant_impl(38); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000039() { ch_interior_point_invariant_impl(39); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000040() { ch_interior_point_invariant_impl(40); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000041() { ch_interior_point_invariant_impl(41); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000042() { ch_interior_point_invariant_impl(42); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000043() { ch_interior_point_invariant_impl(43); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000044() { ch_interior_point_invariant_impl(44); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000045() { ch_interior_point_invariant_impl(45); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000046() { ch_interior_point_invariant_impl(46); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000047() { ch_interior_point_invariant_impl(47); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000048() { ch_interior_point_invariant_impl(48); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000049() { ch_interior_point_invariant_impl(49); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000050() { ch_interior_point_invariant_impl(50); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000051() { ch_interior_point_invariant_impl(51); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000052() { ch_interior_point_invariant_impl(52); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000053() { ch_interior_point_invariant_impl(53); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000054() { ch_interior_point_invariant_impl(54); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000055() { ch_interior_point_invariant_impl(55); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000056() { ch_interior_point_invariant_impl(56); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000057() { ch_interior_point_invariant_impl(57); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000058() { ch_interior_point_invariant_impl(58); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000059() { ch_interior_point_invariant_impl(59); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000060() { ch_interior_point_invariant_impl(60); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000061() { ch_interior_point_invariant_impl(61); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000062() { ch_interior_point_invariant_impl(62); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000063() { ch_interior_point_invariant_impl(63); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000064() { ch_interior_point_invariant_impl(64); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000065() { ch_interior_point_invariant_impl(65); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000066() { ch_interior_point_invariant_impl(66); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000067() { ch_interior_point_invariant_impl(67); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000068() { ch_interior_point_invariant_impl(68); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000069() { ch_interior_point_invariant_impl(69); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000070() { ch_interior_point_invariant_impl(70); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000071() { ch_interior_point_invariant_impl(71); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000072() { ch_interior_point_invariant_impl(72); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000073() { ch_interior_point_invariant_impl(73); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000074() { ch_interior_point_invariant_impl(74); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000075() { ch_interior_point_invariant_impl(75); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000076() { ch_interior_point_invariant_impl(76); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000077() { ch_interior_point_invariant_impl(77); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000078() { ch_interior_point_invariant_impl(78); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000079() { ch_interior_point_invariant_impl(79); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000080() { ch_interior_point_invariant_impl(80); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000081() { ch_interior_point_invariant_impl(81); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000082() { ch_interior_point_invariant_impl(82); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000083() { ch_interior_point_invariant_impl(83); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000084() { ch_interior_point_invariant_impl(84); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000085() { ch_interior_point_invariant_impl(85); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000086() { ch_interior_point_invariant_impl(86); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000087() { ch_interior_point_invariant_impl(87); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000088() { ch_interior_point_invariant_impl(88); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000089() { ch_interior_point_invariant_impl(89); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000090() { ch_interior_point_invariant_impl(90); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000091() { ch_interior_point_invariant_impl(91); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000092() { ch_interior_point_invariant_impl(92); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000093() { ch_interior_point_invariant_impl(93); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000094() { ch_interior_point_invariant_impl(94); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000095() { ch_interior_point_invariant_impl(95); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000096() { ch_interior_point_invariant_impl(96); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000097() { ch_interior_point_invariant_impl(97); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000098() { ch_interior_point_invariant_impl(98); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000099() { ch_interior_point_invariant_impl(99); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000100() { ch_interior_point_invariant_impl(100); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000101() { ch_interior_point_invariant_impl(101); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000102() { ch_interior_point_invariant_impl(102); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000103() { ch_interior_point_invariant_impl(103); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000104() { ch_interior_point_invariant_impl(104); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000105() { ch_interior_point_invariant_impl(105); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000106() { ch_interior_point_invariant_impl(106); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000107() { ch_interior_point_invariant_impl(107); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000108() { ch_interior_point_invariant_impl(108); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000109() { ch_interior_point_invariant_impl(109); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000110() { ch_interior_point_invariant_impl(110); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000111() { ch_interior_point_invariant_impl(111); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000112() { ch_interior_point_invariant_impl(112); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000113() { ch_interior_point_invariant_impl(113); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000114() { ch_interior_point_invariant_impl(114); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000115() { ch_interior_point_invariant_impl(115); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000116() { ch_interior_point_invariant_impl(116); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000117() { ch_interior_point_invariant_impl(117); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000118() { ch_interior_point_invariant_impl(118); }
    #[cfg_attr(test, test)]
    fn ch_interior_seed_000119() { ch_interior_point_invariant_impl(119); }
    // --- cc_dihedral: 100 generated seeds ---
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000000() { cc_dihedral_invariant_impl(0); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000001() { cc_dihedral_invariant_impl(1); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000002() { cc_dihedral_invariant_impl(2); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000003() { cc_dihedral_invariant_impl(3); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000004() { cc_dihedral_invariant_impl(4); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000005() { cc_dihedral_invariant_impl(5); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000006() { cc_dihedral_invariant_impl(6); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000007() { cc_dihedral_invariant_impl(7); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000008() { cc_dihedral_invariant_impl(8); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000009() { cc_dihedral_invariant_impl(9); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000010() { cc_dihedral_invariant_impl(10); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000011() { cc_dihedral_invariant_impl(11); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000012() { cc_dihedral_invariant_impl(12); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000013() { cc_dihedral_invariant_impl(13); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000014() { cc_dihedral_invariant_impl(14); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000015() { cc_dihedral_invariant_impl(15); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000016() { cc_dihedral_invariant_impl(16); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000017() { cc_dihedral_invariant_impl(17); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000018() { cc_dihedral_invariant_impl(18); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000019() { cc_dihedral_invariant_impl(19); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000020() { cc_dihedral_invariant_impl(20); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000021() { cc_dihedral_invariant_impl(21); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000022() { cc_dihedral_invariant_impl(22); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000023() { cc_dihedral_invariant_impl(23); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000024() { cc_dihedral_invariant_impl(24); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000025() { cc_dihedral_invariant_impl(25); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000026() { cc_dihedral_invariant_impl(26); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000027() { cc_dihedral_invariant_impl(27); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000028() { cc_dihedral_invariant_impl(28); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000029() { cc_dihedral_invariant_impl(29); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000030() { cc_dihedral_invariant_impl(30); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000031() { cc_dihedral_invariant_impl(31); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000032() { cc_dihedral_invariant_impl(32); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000033() { cc_dihedral_invariant_impl(33); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000034() { cc_dihedral_invariant_impl(34); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000035() { cc_dihedral_invariant_impl(35); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000036() { cc_dihedral_invariant_impl(36); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000037() { cc_dihedral_invariant_impl(37); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000038() { cc_dihedral_invariant_impl(38); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000039() { cc_dihedral_invariant_impl(39); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000040() { cc_dihedral_invariant_impl(40); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000041() { cc_dihedral_invariant_impl(41); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000042() { cc_dihedral_invariant_impl(42); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000043() { cc_dihedral_invariant_impl(43); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000044() { cc_dihedral_invariant_impl(44); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000045() { cc_dihedral_invariant_impl(45); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000046() { cc_dihedral_invariant_impl(46); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000047() { cc_dihedral_invariant_impl(47); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000048() { cc_dihedral_invariant_impl(48); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000049() { cc_dihedral_invariant_impl(49); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000050() { cc_dihedral_invariant_impl(50); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000051() { cc_dihedral_invariant_impl(51); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000052() { cc_dihedral_invariant_impl(52); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000053() { cc_dihedral_invariant_impl(53); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000054() { cc_dihedral_invariant_impl(54); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000055() { cc_dihedral_invariant_impl(55); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000056() { cc_dihedral_invariant_impl(56); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000057() { cc_dihedral_invariant_impl(57); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000058() { cc_dihedral_invariant_impl(58); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000059() { cc_dihedral_invariant_impl(59); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000060() { cc_dihedral_invariant_impl(60); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000061() { cc_dihedral_invariant_impl(61); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000062() { cc_dihedral_invariant_impl(62); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000063() { cc_dihedral_invariant_impl(63); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000064() { cc_dihedral_invariant_impl(64); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000065() { cc_dihedral_invariant_impl(65); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000066() { cc_dihedral_invariant_impl(66); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000067() { cc_dihedral_invariant_impl(67); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000068() { cc_dihedral_invariant_impl(68); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000069() { cc_dihedral_invariant_impl(69); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000070() { cc_dihedral_invariant_impl(70); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000071() { cc_dihedral_invariant_impl(71); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000072() { cc_dihedral_invariant_impl(72); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000073() { cc_dihedral_invariant_impl(73); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000074() { cc_dihedral_invariant_impl(74); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000075() { cc_dihedral_invariant_impl(75); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000076() { cc_dihedral_invariant_impl(76); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000077() { cc_dihedral_invariant_impl(77); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000078() { cc_dihedral_invariant_impl(78); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000079() { cc_dihedral_invariant_impl(79); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000080() { cc_dihedral_invariant_impl(80); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000081() { cc_dihedral_invariant_impl(81); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000082() { cc_dihedral_invariant_impl(82); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000083() { cc_dihedral_invariant_impl(83); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000084() { cc_dihedral_invariant_impl(84); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000085() { cc_dihedral_invariant_impl(85); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000086() { cc_dihedral_invariant_impl(86); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000087() { cc_dihedral_invariant_impl(87); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000088() { cc_dihedral_invariant_impl(88); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000089() { cc_dihedral_invariant_impl(89); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000090() { cc_dihedral_invariant_impl(90); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000091() { cc_dihedral_invariant_impl(91); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000092() { cc_dihedral_invariant_impl(92); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000093() { cc_dihedral_invariant_impl(93); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000094() { cc_dihedral_invariant_impl(94); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000095() { cc_dihedral_invariant_impl(95); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000096() { cc_dihedral_invariant_impl(96); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000097() { cc_dihedral_invariant_impl(97); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000098() { cc_dihedral_invariant_impl(98); }
    #[cfg_attr(test, test)]
    fn cc_dihedral_seed_000099() { cc_dihedral_invariant_impl(99); }
    // --- cc_union_monotone: 100 generated seeds ---
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000000() { cc_union_monotone_impl(0); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000001() { cc_union_monotone_impl(1); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000002() { cc_union_monotone_impl(2); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000003() { cc_union_monotone_impl(3); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000004() { cc_union_monotone_impl(4); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000005() { cc_union_monotone_impl(5); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000006() { cc_union_monotone_impl(6); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000007() { cc_union_monotone_impl(7); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000008() { cc_union_monotone_impl(8); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000009() { cc_union_monotone_impl(9); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000010() { cc_union_monotone_impl(10); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000011() { cc_union_monotone_impl(11); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000012() { cc_union_monotone_impl(12); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000013() { cc_union_monotone_impl(13); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000014() { cc_union_monotone_impl(14); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000015() { cc_union_monotone_impl(15); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000016() { cc_union_monotone_impl(16); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000017() { cc_union_monotone_impl(17); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000018() { cc_union_monotone_impl(18); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000019() { cc_union_monotone_impl(19); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000020() { cc_union_monotone_impl(20); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000021() { cc_union_monotone_impl(21); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000022() { cc_union_monotone_impl(22); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000023() { cc_union_monotone_impl(23); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000024() { cc_union_monotone_impl(24); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000025() { cc_union_monotone_impl(25); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000026() { cc_union_monotone_impl(26); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000027() { cc_union_monotone_impl(27); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000028() { cc_union_monotone_impl(28); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000029() { cc_union_monotone_impl(29); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000030() { cc_union_monotone_impl(30); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000031() { cc_union_monotone_impl(31); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000032() { cc_union_monotone_impl(32); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000033() { cc_union_monotone_impl(33); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000034() { cc_union_monotone_impl(34); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000035() { cc_union_monotone_impl(35); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000036() { cc_union_monotone_impl(36); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000037() { cc_union_monotone_impl(37); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000038() { cc_union_monotone_impl(38); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000039() { cc_union_monotone_impl(39); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000040() { cc_union_monotone_impl(40); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000041() { cc_union_monotone_impl(41); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000042() { cc_union_monotone_impl(42); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000043() { cc_union_monotone_impl(43); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000044() { cc_union_monotone_impl(44); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000045() { cc_union_monotone_impl(45); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000046() { cc_union_monotone_impl(46); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000047() { cc_union_monotone_impl(47); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000048() { cc_union_monotone_impl(48); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000049() { cc_union_monotone_impl(49); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000050() { cc_union_monotone_impl(50); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000051() { cc_union_monotone_impl(51); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000052() { cc_union_monotone_impl(52); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000053() { cc_union_monotone_impl(53); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000054() { cc_union_monotone_impl(54); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000055() { cc_union_monotone_impl(55); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000056() { cc_union_monotone_impl(56); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000057() { cc_union_monotone_impl(57); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000058() { cc_union_monotone_impl(58); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000059() { cc_union_monotone_impl(59); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000060() { cc_union_monotone_impl(60); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000061() { cc_union_monotone_impl(61); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000062() { cc_union_monotone_impl(62); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000063() { cc_union_monotone_impl(63); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000064() { cc_union_monotone_impl(64); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000065() { cc_union_monotone_impl(65); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000066() { cc_union_monotone_impl(66); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000067() { cc_union_monotone_impl(67); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000068() { cc_union_monotone_impl(68); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000069() { cc_union_monotone_impl(69); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000070() { cc_union_monotone_impl(70); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000071() { cc_union_monotone_impl(71); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000072() { cc_union_monotone_impl(72); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000073() { cc_union_monotone_impl(73); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000074() { cc_union_monotone_impl(74); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000075() { cc_union_monotone_impl(75); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000076() { cc_union_monotone_impl(76); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000077() { cc_union_monotone_impl(77); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000078() { cc_union_monotone_impl(78); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000079() { cc_union_monotone_impl(79); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000080() { cc_union_monotone_impl(80); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000081() { cc_union_monotone_impl(81); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000082() { cc_union_monotone_impl(82); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000083() { cc_union_monotone_impl(83); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000084() { cc_union_monotone_impl(84); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000085() { cc_union_monotone_impl(85); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000086() { cc_union_monotone_impl(86); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000087() { cc_union_monotone_impl(87); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000088() { cc_union_monotone_impl(88); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000089() { cc_union_monotone_impl(89); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000090() { cc_union_monotone_impl(90); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000091() { cc_union_monotone_impl(91); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000092() { cc_union_monotone_impl(92); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000093() { cc_union_monotone_impl(93); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000094() { cc_union_monotone_impl(94); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000095() { cc_union_monotone_impl(95); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000096() { cc_union_monotone_impl(96); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000097() { cc_union_monotone_impl(97); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000098() { cc_union_monotone_impl(98); }
    #[cfg_attr(test, test)]
    fn cc_union_monotone_seed_000099() { cc_union_monotone_impl(99); }
    // --- cc_padding: 100 generated seeds ---
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000000() { cc_padding_invariant_impl(0); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000001() { cc_padding_invariant_impl(1); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000002() { cc_padding_invariant_impl(2); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000003() { cc_padding_invariant_impl(3); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000004() { cc_padding_invariant_impl(4); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000005() { cc_padding_invariant_impl(5); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000006() { cc_padding_invariant_impl(6); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000007() { cc_padding_invariant_impl(7); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000008() { cc_padding_invariant_impl(8); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000009() { cc_padding_invariant_impl(9); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000010() { cc_padding_invariant_impl(10); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000011() { cc_padding_invariant_impl(11); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000012() { cc_padding_invariant_impl(12); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000013() { cc_padding_invariant_impl(13); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000014() { cc_padding_invariant_impl(14); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000015() { cc_padding_invariant_impl(15); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000016() { cc_padding_invariant_impl(16); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000017() { cc_padding_invariant_impl(17); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000018() { cc_padding_invariant_impl(18); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000019() { cc_padding_invariant_impl(19); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000020() { cc_padding_invariant_impl(20); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000021() { cc_padding_invariant_impl(21); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000022() { cc_padding_invariant_impl(22); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000023() { cc_padding_invariant_impl(23); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000024() { cc_padding_invariant_impl(24); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000025() { cc_padding_invariant_impl(25); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000026() { cc_padding_invariant_impl(26); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000027() { cc_padding_invariant_impl(27); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000028() { cc_padding_invariant_impl(28); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000029() { cc_padding_invariant_impl(29); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000030() { cc_padding_invariant_impl(30); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000031() { cc_padding_invariant_impl(31); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000032() { cc_padding_invariant_impl(32); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000033() { cc_padding_invariant_impl(33); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000034() { cc_padding_invariant_impl(34); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000035() { cc_padding_invariant_impl(35); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000036() { cc_padding_invariant_impl(36); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000037() { cc_padding_invariant_impl(37); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000038() { cc_padding_invariant_impl(38); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000039() { cc_padding_invariant_impl(39); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000040() { cc_padding_invariant_impl(40); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000041() { cc_padding_invariant_impl(41); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000042() { cc_padding_invariant_impl(42); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000043() { cc_padding_invariant_impl(43); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000044() { cc_padding_invariant_impl(44); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000045() { cc_padding_invariant_impl(45); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000046() { cc_padding_invariant_impl(46); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000047() { cc_padding_invariant_impl(47); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000048() { cc_padding_invariant_impl(48); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000049() { cc_padding_invariant_impl(49); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000050() { cc_padding_invariant_impl(50); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000051() { cc_padding_invariant_impl(51); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000052() { cc_padding_invariant_impl(52); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000053() { cc_padding_invariant_impl(53); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000054() { cc_padding_invariant_impl(54); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000055() { cc_padding_invariant_impl(55); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000056() { cc_padding_invariant_impl(56); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000057() { cc_padding_invariant_impl(57); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000058() { cc_padding_invariant_impl(58); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000059() { cc_padding_invariant_impl(59); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000060() { cc_padding_invariant_impl(60); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000061() { cc_padding_invariant_impl(61); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000062() { cc_padding_invariant_impl(62); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000063() { cc_padding_invariant_impl(63); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000064() { cc_padding_invariant_impl(64); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000065() { cc_padding_invariant_impl(65); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000066() { cc_padding_invariant_impl(66); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000067() { cc_padding_invariant_impl(67); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000068() { cc_padding_invariant_impl(68); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000069() { cc_padding_invariant_impl(69); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000070() { cc_padding_invariant_impl(70); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000071() { cc_padding_invariant_impl(71); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000072() { cc_padding_invariant_impl(72); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000073() { cc_padding_invariant_impl(73); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000074() { cc_padding_invariant_impl(74); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000075() { cc_padding_invariant_impl(75); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000076() { cc_padding_invariant_impl(76); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000077() { cc_padding_invariant_impl(77); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000078() { cc_padding_invariant_impl(78); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000079() { cc_padding_invariant_impl(79); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000080() { cc_padding_invariant_impl(80); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000081() { cc_padding_invariant_impl(81); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000082() { cc_padding_invariant_impl(82); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000083() { cc_padding_invariant_impl(83); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000084() { cc_padding_invariant_impl(84); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000085() { cc_padding_invariant_impl(85); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000086() { cc_padding_invariant_impl(86); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000087() { cc_padding_invariant_impl(87); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000088() { cc_padding_invariant_impl(88); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000089() { cc_padding_invariant_impl(89); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000090() { cc_padding_invariant_impl(90); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000091() { cc_padding_invariant_impl(91); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000092() { cc_padding_invariant_impl(92); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000093() { cc_padding_invariant_impl(93); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000094() { cc_padding_invariant_impl(94); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000095() { cc_padding_invariant_impl(95); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000096() { cc_padding_invariant_impl(96); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000097() { cc_padding_invariant_impl(97); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000098() { cc_padding_invariant_impl(98); }
    #[cfg_attr(test, test)]
    fn cc_padding_seed_000099() { cc_padding_invariant_impl(99); }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("property_campaigns::tests::splitmix64_is_deterministic_in_seed", splitmix64_is_deterministic_in_seed),
        ("property_campaigns::tests::splitmix64_varies_with_seed", splitmix64_varies_with_seed),
        ("property_campaigns::tests::kt_gen_case_is_deterministic", kt_gen_case_is_deterministic),
        ("property_campaigns::tests::kt_round_trip_zero_theta_is_exact_identity", kt_round_trip_zero_theta_is_exact_identity),
        ("property_campaigns::tests::ch_gen_points_length_in_expected_range", ch_gen_points_length_in_expected_range),
        ("property_campaigns::tests::ch_interior_combination_sanity_on_a_hand_built_triangle", ch_interior_combination_sanity_on_a_hand_built_triangle),
        ("property_campaigns::tests::dihedral_identity_is_a_noop", dihedral_identity_is_a_noop),
        ("property_campaigns::tests::dihedral_rot90_matches_a_hand_worked_example", dihedral_rot90_matches_a_hand_worked_example),
        ("property_campaigns::tests::dihedral_transpose_matches_a_hand_worked_example", dihedral_transpose_matches_a_hand_worked_example),
        ("property_campaigns::tests::cc_gen_mask_dims_in_expected_range", cc_gen_mask_dims_in_expected_range),
        ("property_campaigns::tests::kt_round_trip_seed_000000", kt_round_trip_seed_000000),
        ("property_campaigns::tests::kt_round_trip_seed_000001", kt_round_trip_seed_000001),
        ("property_campaigns::tests::kt_round_trip_seed_000002", kt_round_trip_seed_000002),
        ("property_campaigns::tests::kt_round_trip_seed_000003", kt_round_trip_seed_000003),
        ("property_campaigns::tests::kt_round_trip_seed_000004", kt_round_trip_seed_000004),
        ("property_campaigns::tests::kt_round_trip_seed_000005", kt_round_trip_seed_000005),
        ("property_campaigns::tests::kt_round_trip_seed_000006", kt_round_trip_seed_000006),
        ("property_campaigns::tests::kt_round_trip_seed_000007", kt_round_trip_seed_000007),
        ("property_campaigns::tests::kt_round_trip_seed_000008", kt_round_trip_seed_000008),
        ("property_campaigns::tests::kt_round_trip_seed_000009", kt_round_trip_seed_000009),
        ("property_campaigns::tests::kt_round_trip_seed_000010", kt_round_trip_seed_000010),
        ("property_campaigns::tests::kt_round_trip_seed_000011", kt_round_trip_seed_000011),
        ("property_campaigns::tests::kt_round_trip_seed_000012", kt_round_trip_seed_000012),
        ("property_campaigns::tests::kt_round_trip_seed_000013", kt_round_trip_seed_000013),
        ("property_campaigns::tests::kt_round_trip_seed_000014", kt_round_trip_seed_000014),
        ("property_campaigns::tests::kt_round_trip_seed_000015", kt_round_trip_seed_000015),
        ("property_campaigns::tests::kt_round_trip_seed_000016", kt_round_trip_seed_000016),
        ("property_campaigns::tests::kt_round_trip_seed_000017", kt_round_trip_seed_000017),
        ("property_campaigns::tests::kt_round_trip_seed_000018", kt_round_trip_seed_000018),
        ("property_campaigns::tests::kt_round_trip_seed_000019", kt_round_trip_seed_000019),
        ("property_campaigns::tests::kt_round_trip_seed_000020", kt_round_trip_seed_000020),
        ("property_campaigns::tests::kt_round_trip_seed_000021", kt_round_trip_seed_000021),
        ("property_campaigns::tests::kt_round_trip_seed_000022", kt_round_trip_seed_000022),
        ("property_campaigns::tests::kt_round_trip_seed_000023", kt_round_trip_seed_000023),
        ("property_campaigns::tests::kt_round_trip_seed_000024", kt_round_trip_seed_000024),
        ("property_campaigns::tests::kt_round_trip_seed_000025", kt_round_trip_seed_000025),
        ("property_campaigns::tests::kt_round_trip_seed_000026", kt_round_trip_seed_000026),
        ("property_campaigns::tests::kt_round_trip_seed_000027", kt_round_trip_seed_000027),
        ("property_campaigns::tests::kt_round_trip_seed_000028", kt_round_trip_seed_000028),
        ("property_campaigns::tests::kt_round_trip_seed_000029", kt_round_trip_seed_000029),
        ("property_campaigns::tests::kt_round_trip_seed_000030", kt_round_trip_seed_000030),
        ("property_campaigns::tests::kt_round_trip_seed_000031", kt_round_trip_seed_000031),
        ("property_campaigns::tests::kt_round_trip_seed_000032", kt_round_trip_seed_000032),
        ("property_campaigns::tests::kt_round_trip_seed_000033", kt_round_trip_seed_000033),
        ("property_campaigns::tests::kt_round_trip_seed_000034", kt_round_trip_seed_000034),
        ("property_campaigns::tests::kt_round_trip_seed_000035", kt_round_trip_seed_000035),
        ("property_campaigns::tests::kt_round_trip_seed_000036", kt_round_trip_seed_000036),
        ("property_campaigns::tests::kt_round_trip_seed_000037", kt_round_trip_seed_000037),
        ("property_campaigns::tests::kt_round_trip_seed_000038", kt_round_trip_seed_000038),
        ("property_campaigns::tests::kt_round_trip_seed_000039", kt_round_trip_seed_000039),
        ("property_campaigns::tests::kt_round_trip_seed_000040", kt_round_trip_seed_000040),
        ("property_campaigns::tests::kt_round_trip_seed_000041", kt_round_trip_seed_000041),
        ("property_campaigns::tests::kt_round_trip_seed_000042", kt_round_trip_seed_000042),
        ("property_campaigns::tests::kt_round_trip_seed_000043", kt_round_trip_seed_000043),
        ("property_campaigns::tests::kt_round_trip_seed_000044", kt_round_trip_seed_000044),
        ("property_campaigns::tests::kt_round_trip_seed_000045", kt_round_trip_seed_000045),
        ("property_campaigns::tests::kt_round_trip_seed_000046", kt_round_trip_seed_000046),
        ("property_campaigns::tests::kt_round_trip_seed_000047", kt_round_trip_seed_000047),
        ("property_campaigns::tests::kt_round_trip_seed_000048", kt_round_trip_seed_000048),
        ("property_campaigns::tests::kt_round_trip_seed_000049", kt_round_trip_seed_000049),
        ("property_campaigns::tests::kt_round_trip_seed_000050", kt_round_trip_seed_000050),
        ("property_campaigns::tests::kt_round_trip_seed_000051", kt_round_trip_seed_000051),
        ("property_campaigns::tests::kt_round_trip_seed_000052", kt_round_trip_seed_000052),
        ("property_campaigns::tests::kt_round_trip_seed_000053", kt_round_trip_seed_000053),
        ("property_campaigns::tests::kt_round_trip_seed_000054", kt_round_trip_seed_000054),
        ("property_campaigns::tests::kt_round_trip_seed_000055", kt_round_trip_seed_000055),
        ("property_campaigns::tests::kt_round_trip_seed_000056", kt_round_trip_seed_000056),
        ("property_campaigns::tests::kt_round_trip_seed_000057", kt_round_trip_seed_000057),
        ("property_campaigns::tests::kt_round_trip_seed_000058", kt_round_trip_seed_000058),
        ("property_campaigns::tests::kt_round_trip_seed_000059", kt_round_trip_seed_000059),
        ("property_campaigns::tests::kt_round_trip_seed_000060", kt_round_trip_seed_000060),
        ("property_campaigns::tests::kt_round_trip_seed_000061", kt_round_trip_seed_000061),
        ("property_campaigns::tests::kt_round_trip_seed_000062", kt_round_trip_seed_000062),
        ("property_campaigns::tests::kt_round_trip_seed_000063", kt_round_trip_seed_000063),
        ("property_campaigns::tests::kt_round_trip_seed_000064", kt_round_trip_seed_000064),
        ("property_campaigns::tests::kt_round_trip_seed_000065", kt_round_trip_seed_000065),
        ("property_campaigns::tests::kt_round_trip_seed_000066", kt_round_trip_seed_000066),
        ("property_campaigns::tests::kt_round_trip_seed_000067", kt_round_trip_seed_000067),
        ("property_campaigns::tests::kt_round_trip_seed_000068", kt_round_trip_seed_000068),
        ("property_campaigns::tests::kt_round_trip_seed_000069", kt_round_trip_seed_000069),
        ("property_campaigns::tests::kt_round_trip_seed_000070", kt_round_trip_seed_000070),
        ("property_campaigns::tests::kt_round_trip_seed_000071", kt_round_trip_seed_000071),
        ("property_campaigns::tests::kt_round_trip_seed_000072", kt_round_trip_seed_000072),
        ("property_campaigns::tests::kt_round_trip_seed_000073", kt_round_trip_seed_000073),
        ("property_campaigns::tests::kt_round_trip_seed_000074", kt_round_trip_seed_000074),
        ("property_campaigns::tests::kt_round_trip_seed_000075", kt_round_trip_seed_000075),
        ("property_campaigns::tests::kt_round_trip_seed_000076", kt_round_trip_seed_000076),
        ("property_campaigns::tests::kt_round_trip_seed_000077", kt_round_trip_seed_000077),
        ("property_campaigns::tests::kt_round_trip_seed_000078", kt_round_trip_seed_000078),
        ("property_campaigns::tests::kt_round_trip_seed_000079", kt_round_trip_seed_000079),
        ("property_campaigns::tests::kt_round_trip_seed_000080", kt_round_trip_seed_000080),
        ("property_campaigns::tests::kt_round_trip_seed_000081", kt_round_trip_seed_000081),
        ("property_campaigns::tests::kt_round_trip_seed_000082", kt_round_trip_seed_000082),
        ("property_campaigns::tests::kt_round_trip_seed_000083", kt_round_trip_seed_000083),
        ("property_campaigns::tests::kt_round_trip_seed_000084", kt_round_trip_seed_000084),
        ("property_campaigns::tests::kt_round_trip_seed_000085", kt_round_trip_seed_000085),
        ("property_campaigns::tests::kt_round_trip_seed_000086", kt_round_trip_seed_000086),
        ("property_campaigns::tests::kt_round_trip_seed_000087", kt_round_trip_seed_000087),
        ("property_campaigns::tests::kt_round_trip_seed_000088", kt_round_trip_seed_000088),
        ("property_campaigns::tests::kt_round_trip_seed_000089", kt_round_trip_seed_000089),
        ("property_campaigns::tests::kt_round_trip_seed_000090", kt_round_trip_seed_000090),
        ("property_campaigns::tests::kt_round_trip_seed_000091", kt_round_trip_seed_000091),
        ("property_campaigns::tests::kt_round_trip_seed_000092", kt_round_trip_seed_000092),
        ("property_campaigns::tests::kt_round_trip_seed_000093", kt_round_trip_seed_000093),
        ("property_campaigns::tests::kt_round_trip_seed_000094", kt_round_trip_seed_000094),
        ("property_campaigns::tests::kt_round_trip_seed_000095", kt_round_trip_seed_000095),
        ("property_campaigns::tests::kt_round_trip_seed_000096", kt_round_trip_seed_000096),
        ("property_campaigns::tests::kt_round_trip_seed_000097", kt_round_trip_seed_000097),
        ("property_campaigns::tests::kt_round_trip_seed_000098", kt_round_trip_seed_000098),
        ("property_campaigns::tests::kt_round_trip_seed_000099", kt_round_trip_seed_000099),
        ("property_campaigns::tests::kt_round_trip_seed_000100", kt_round_trip_seed_000100),
        ("property_campaigns::tests::kt_round_trip_seed_000101", kt_round_trip_seed_000101),
        ("property_campaigns::tests::kt_round_trip_seed_000102", kt_round_trip_seed_000102),
        ("property_campaigns::tests::kt_round_trip_seed_000103", kt_round_trip_seed_000103),
        ("property_campaigns::tests::kt_round_trip_seed_000104", kt_round_trip_seed_000104),
        ("property_campaigns::tests::kt_round_trip_seed_000105", kt_round_trip_seed_000105),
        ("property_campaigns::tests::kt_round_trip_seed_000106", kt_round_trip_seed_000106),
        ("property_campaigns::tests::kt_round_trip_seed_000107", kt_round_trip_seed_000107),
        ("property_campaigns::tests::kt_round_trip_seed_000108", kt_round_trip_seed_000108),
        ("property_campaigns::tests::kt_round_trip_seed_000109", kt_round_trip_seed_000109),
        ("property_campaigns::tests::kt_round_trip_seed_000110", kt_round_trip_seed_000110),
        ("property_campaigns::tests::kt_round_trip_seed_000111", kt_round_trip_seed_000111),
        ("property_campaigns::tests::kt_round_trip_seed_000112", kt_round_trip_seed_000112),
        ("property_campaigns::tests::kt_round_trip_seed_000113", kt_round_trip_seed_000113),
        ("property_campaigns::tests::kt_round_trip_seed_000114", kt_round_trip_seed_000114),
        ("property_campaigns::tests::kt_round_trip_seed_000115", kt_round_trip_seed_000115),
        ("property_campaigns::tests::kt_round_trip_seed_000116", kt_round_trip_seed_000116),
        ("property_campaigns::tests::kt_round_trip_seed_000117", kt_round_trip_seed_000117),
        ("property_campaigns::tests::kt_round_trip_seed_000118", kt_round_trip_seed_000118),
        ("property_campaigns::tests::kt_round_trip_seed_000119", kt_round_trip_seed_000119),
        ("property_campaigns::tests::kt_round_trip_seed_000120", kt_round_trip_seed_000120),
        ("property_campaigns::tests::kt_round_trip_seed_000121", kt_round_trip_seed_000121),
        ("property_campaigns::tests::kt_round_trip_seed_000122", kt_round_trip_seed_000122),
        ("property_campaigns::tests::kt_round_trip_seed_000123", kt_round_trip_seed_000123),
        ("property_campaigns::tests::kt_round_trip_seed_000124", kt_round_trip_seed_000124),
        ("property_campaigns::tests::kt_round_trip_seed_000125", kt_round_trip_seed_000125),
        ("property_campaigns::tests::kt_round_trip_seed_000126", kt_round_trip_seed_000126),
        ("property_campaigns::tests::kt_round_trip_seed_000127", kt_round_trip_seed_000127),
        ("property_campaigns::tests::kt_round_trip_seed_000128", kt_round_trip_seed_000128),
        ("property_campaigns::tests::kt_round_trip_seed_000129", kt_round_trip_seed_000129),
        ("property_campaigns::tests::kt_round_trip_seed_000130", kt_round_trip_seed_000130),
        ("property_campaigns::tests::kt_round_trip_seed_000131", kt_round_trip_seed_000131),
        ("property_campaigns::tests::kt_round_trip_seed_000132", kt_round_trip_seed_000132),
        ("property_campaigns::tests::kt_round_trip_seed_000133", kt_round_trip_seed_000133),
        ("property_campaigns::tests::kt_round_trip_seed_000134", kt_round_trip_seed_000134),
        ("property_campaigns::tests::kt_round_trip_seed_000135", kt_round_trip_seed_000135),
        ("property_campaigns::tests::kt_round_trip_seed_000136", kt_round_trip_seed_000136),
        ("property_campaigns::tests::kt_round_trip_seed_000137", kt_round_trip_seed_000137),
        ("property_campaigns::tests::kt_round_trip_seed_000138", kt_round_trip_seed_000138),
        ("property_campaigns::tests::kt_round_trip_seed_000139", kt_round_trip_seed_000139),
        ("property_campaigns::tests::kt_round_trip_seed_000140", kt_round_trip_seed_000140),
        ("property_campaigns::tests::kt_round_trip_seed_000141", kt_round_trip_seed_000141),
        ("property_campaigns::tests::kt_round_trip_seed_000142", kt_round_trip_seed_000142),
        ("property_campaigns::tests::kt_round_trip_seed_000143", kt_round_trip_seed_000143),
        ("property_campaigns::tests::kt_round_trip_seed_000144", kt_round_trip_seed_000144),
        ("property_campaigns::tests::kt_round_trip_seed_000145", kt_round_trip_seed_000145),
        ("property_campaigns::tests::kt_round_trip_seed_000146", kt_round_trip_seed_000146),
        ("property_campaigns::tests::kt_round_trip_seed_000147", kt_round_trip_seed_000147),
        ("property_campaigns::tests::kt_round_trip_seed_000148", kt_round_trip_seed_000148),
        ("property_campaigns::tests::kt_round_trip_seed_000149", kt_round_trip_seed_000149),
        ("property_campaigns::tests::kt_isometry_seed_000000", kt_isometry_seed_000000),
        ("property_campaigns::tests::kt_isometry_seed_000001", kt_isometry_seed_000001),
        ("property_campaigns::tests::kt_isometry_seed_000002", kt_isometry_seed_000002),
        ("property_campaigns::tests::kt_isometry_seed_000003", kt_isometry_seed_000003),
        ("property_campaigns::tests::kt_isometry_seed_000004", kt_isometry_seed_000004),
        ("property_campaigns::tests::kt_isometry_seed_000005", kt_isometry_seed_000005),
        ("property_campaigns::tests::kt_isometry_seed_000006", kt_isometry_seed_000006),
        ("property_campaigns::tests::kt_isometry_seed_000007", kt_isometry_seed_000007),
        ("property_campaigns::tests::kt_isometry_seed_000008", kt_isometry_seed_000008),
        ("property_campaigns::tests::kt_isometry_seed_000009", kt_isometry_seed_000009),
        ("property_campaigns::tests::kt_isometry_seed_000010", kt_isometry_seed_000010),
        ("property_campaigns::tests::kt_isometry_seed_000011", kt_isometry_seed_000011),
        ("property_campaigns::tests::kt_isometry_seed_000012", kt_isometry_seed_000012),
        ("property_campaigns::tests::kt_isometry_seed_000013", kt_isometry_seed_000013),
        ("property_campaigns::tests::kt_isometry_seed_000014", kt_isometry_seed_000014),
        ("property_campaigns::tests::kt_isometry_seed_000015", kt_isometry_seed_000015),
        ("property_campaigns::tests::kt_isometry_seed_000016", kt_isometry_seed_000016),
        ("property_campaigns::tests::kt_isometry_seed_000017", kt_isometry_seed_000017),
        ("property_campaigns::tests::kt_isometry_seed_000018", kt_isometry_seed_000018),
        ("property_campaigns::tests::kt_isometry_seed_000019", kt_isometry_seed_000019),
        ("property_campaigns::tests::kt_isometry_seed_000020", kt_isometry_seed_000020),
        ("property_campaigns::tests::kt_isometry_seed_000021", kt_isometry_seed_000021),
        ("property_campaigns::tests::kt_isometry_seed_000022", kt_isometry_seed_000022),
        ("property_campaigns::tests::kt_isometry_seed_000023", kt_isometry_seed_000023),
        ("property_campaigns::tests::kt_isometry_seed_000024", kt_isometry_seed_000024),
        ("property_campaigns::tests::kt_isometry_seed_000025", kt_isometry_seed_000025),
        ("property_campaigns::tests::kt_isometry_seed_000026", kt_isometry_seed_000026),
        ("property_campaigns::tests::kt_isometry_seed_000027", kt_isometry_seed_000027),
        ("property_campaigns::tests::kt_isometry_seed_000028", kt_isometry_seed_000028),
        ("property_campaigns::tests::kt_isometry_seed_000029", kt_isometry_seed_000029),
        ("property_campaigns::tests::kt_isometry_seed_000030", kt_isometry_seed_000030),
        ("property_campaigns::tests::kt_isometry_seed_000031", kt_isometry_seed_000031),
        ("property_campaigns::tests::kt_isometry_seed_000032", kt_isometry_seed_000032),
        ("property_campaigns::tests::kt_isometry_seed_000033", kt_isometry_seed_000033),
        ("property_campaigns::tests::kt_isometry_seed_000034", kt_isometry_seed_000034),
        ("property_campaigns::tests::kt_isometry_seed_000035", kt_isometry_seed_000035),
        ("property_campaigns::tests::kt_isometry_seed_000036", kt_isometry_seed_000036),
        ("property_campaigns::tests::kt_isometry_seed_000037", kt_isometry_seed_000037),
        ("property_campaigns::tests::kt_isometry_seed_000038", kt_isometry_seed_000038),
        ("property_campaigns::tests::kt_isometry_seed_000039", kt_isometry_seed_000039),
        ("property_campaigns::tests::kt_isometry_seed_000040", kt_isometry_seed_000040),
        ("property_campaigns::tests::kt_isometry_seed_000041", kt_isometry_seed_000041),
        ("property_campaigns::tests::kt_isometry_seed_000042", kt_isometry_seed_000042),
        ("property_campaigns::tests::kt_isometry_seed_000043", kt_isometry_seed_000043),
        ("property_campaigns::tests::kt_isometry_seed_000044", kt_isometry_seed_000044),
        ("property_campaigns::tests::kt_isometry_seed_000045", kt_isometry_seed_000045),
        ("property_campaigns::tests::kt_isometry_seed_000046", kt_isometry_seed_000046),
        ("property_campaigns::tests::kt_isometry_seed_000047", kt_isometry_seed_000047),
        ("property_campaigns::tests::kt_isometry_seed_000048", kt_isometry_seed_000048),
        ("property_campaigns::tests::kt_isometry_seed_000049", kt_isometry_seed_000049),
        ("property_campaigns::tests::kt_isometry_seed_000050", kt_isometry_seed_000050),
        ("property_campaigns::tests::kt_isometry_seed_000051", kt_isometry_seed_000051),
        ("property_campaigns::tests::kt_isometry_seed_000052", kt_isometry_seed_000052),
        ("property_campaigns::tests::kt_isometry_seed_000053", kt_isometry_seed_000053),
        ("property_campaigns::tests::kt_isometry_seed_000054", kt_isometry_seed_000054),
        ("property_campaigns::tests::kt_isometry_seed_000055", kt_isometry_seed_000055),
        ("property_campaigns::tests::kt_isometry_seed_000056", kt_isometry_seed_000056),
        ("property_campaigns::tests::kt_isometry_seed_000057", kt_isometry_seed_000057),
        ("property_campaigns::tests::kt_isometry_seed_000058", kt_isometry_seed_000058),
        ("property_campaigns::tests::kt_isometry_seed_000059", kt_isometry_seed_000059),
        ("property_campaigns::tests::kt_isometry_seed_000060", kt_isometry_seed_000060),
        ("property_campaigns::tests::kt_isometry_seed_000061", kt_isometry_seed_000061),
        ("property_campaigns::tests::kt_isometry_seed_000062", kt_isometry_seed_000062),
        ("property_campaigns::tests::kt_isometry_seed_000063", kt_isometry_seed_000063),
        ("property_campaigns::tests::kt_isometry_seed_000064", kt_isometry_seed_000064),
        ("property_campaigns::tests::kt_isometry_seed_000065", kt_isometry_seed_000065),
        ("property_campaigns::tests::kt_isometry_seed_000066", kt_isometry_seed_000066),
        ("property_campaigns::tests::kt_isometry_seed_000067", kt_isometry_seed_000067),
        ("property_campaigns::tests::kt_isometry_seed_000068", kt_isometry_seed_000068),
        ("property_campaigns::tests::kt_isometry_seed_000069", kt_isometry_seed_000069),
        ("property_campaigns::tests::kt_isometry_seed_000070", kt_isometry_seed_000070),
        ("property_campaigns::tests::kt_isometry_seed_000071", kt_isometry_seed_000071),
        ("property_campaigns::tests::kt_isometry_seed_000072", kt_isometry_seed_000072),
        ("property_campaigns::tests::kt_isometry_seed_000073", kt_isometry_seed_000073),
        ("property_campaigns::tests::kt_isometry_seed_000074", kt_isometry_seed_000074),
        ("property_campaigns::tests::kt_isometry_seed_000075", kt_isometry_seed_000075),
        ("property_campaigns::tests::kt_isometry_seed_000076", kt_isometry_seed_000076),
        ("property_campaigns::tests::kt_isometry_seed_000077", kt_isometry_seed_000077),
        ("property_campaigns::tests::kt_isometry_seed_000078", kt_isometry_seed_000078),
        ("property_campaigns::tests::kt_isometry_seed_000079", kt_isometry_seed_000079),
        ("property_campaigns::tests::kt_isometry_seed_000080", kt_isometry_seed_000080),
        ("property_campaigns::tests::kt_isometry_seed_000081", kt_isometry_seed_000081),
        ("property_campaigns::tests::kt_isometry_seed_000082", kt_isometry_seed_000082),
        ("property_campaigns::tests::kt_isometry_seed_000083", kt_isometry_seed_000083),
        ("property_campaigns::tests::kt_isometry_seed_000084", kt_isometry_seed_000084),
        ("property_campaigns::tests::kt_isometry_seed_000085", kt_isometry_seed_000085),
        ("property_campaigns::tests::kt_isometry_seed_000086", kt_isometry_seed_000086),
        ("property_campaigns::tests::kt_isometry_seed_000087", kt_isometry_seed_000087),
        ("property_campaigns::tests::kt_isometry_seed_000088", kt_isometry_seed_000088),
        ("property_campaigns::tests::kt_isometry_seed_000089", kt_isometry_seed_000089),
        ("property_campaigns::tests::kt_isometry_seed_000090", kt_isometry_seed_000090),
        ("property_campaigns::tests::kt_isometry_seed_000091", kt_isometry_seed_000091),
        ("property_campaigns::tests::kt_isometry_seed_000092", kt_isometry_seed_000092),
        ("property_campaigns::tests::kt_isometry_seed_000093", kt_isometry_seed_000093),
        ("property_campaigns::tests::kt_isometry_seed_000094", kt_isometry_seed_000094),
        ("property_campaigns::tests::kt_isometry_seed_000095", kt_isometry_seed_000095),
        ("property_campaigns::tests::kt_isometry_seed_000096", kt_isometry_seed_000096),
        ("property_campaigns::tests::kt_isometry_seed_000097", kt_isometry_seed_000097),
        ("property_campaigns::tests::kt_isometry_seed_000098", kt_isometry_seed_000098),
        ("property_campaigns::tests::kt_isometry_seed_000099", kt_isometry_seed_000099),
        ("property_campaigns::tests::kt_isometry_seed_000100", kt_isometry_seed_000100),
        ("property_campaigns::tests::kt_isometry_seed_000101", kt_isometry_seed_000101),
        ("property_campaigns::tests::kt_isometry_seed_000102", kt_isometry_seed_000102),
        ("property_campaigns::tests::kt_isometry_seed_000103", kt_isometry_seed_000103),
        ("property_campaigns::tests::kt_isometry_seed_000104", kt_isometry_seed_000104),
        ("property_campaigns::tests::kt_isometry_seed_000105", kt_isometry_seed_000105),
        ("property_campaigns::tests::kt_isometry_seed_000106", kt_isometry_seed_000106),
        ("property_campaigns::tests::kt_isometry_seed_000107", kt_isometry_seed_000107),
        ("property_campaigns::tests::kt_isometry_seed_000108", kt_isometry_seed_000108),
        ("property_campaigns::tests::kt_isometry_seed_000109", kt_isometry_seed_000109),
        ("property_campaigns::tests::kt_isometry_seed_000110", kt_isometry_seed_000110),
        ("property_campaigns::tests::kt_isometry_seed_000111", kt_isometry_seed_000111),
        ("property_campaigns::tests::kt_isometry_seed_000112", kt_isometry_seed_000112),
        ("property_campaigns::tests::kt_isometry_seed_000113", kt_isometry_seed_000113),
        ("property_campaigns::tests::kt_isometry_seed_000114", kt_isometry_seed_000114),
        ("property_campaigns::tests::kt_isometry_seed_000115", kt_isometry_seed_000115),
        ("property_campaigns::tests::kt_isometry_seed_000116", kt_isometry_seed_000116),
        ("property_campaigns::tests::kt_isometry_seed_000117", kt_isometry_seed_000117),
        ("property_campaigns::tests::kt_isometry_seed_000118", kt_isometry_seed_000118),
        ("property_campaigns::tests::kt_isometry_seed_000119", kt_isometry_seed_000119),
        ("property_campaigns::tests::kt_isometry_seed_000120", kt_isometry_seed_000120),
        ("property_campaigns::tests::kt_isometry_seed_000121", kt_isometry_seed_000121),
        ("property_campaigns::tests::kt_isometry_seed_000122", kt_isometry_seed_000122),
        ("property_campaigns::tests::kt_isometry_seed_000123", kt_isometry_seed_000123),
        ("property_campaigns::tests::kt_isometry_seed_000124", kt_isometry_seed_000124),
        ("property_campaigns::tests::kt_isometry_seed_000125", kt_isometry_seed_000125),
        ("property_campaigns::tests::kt_isometry_seed_000126", kt_isometry_seed_000126),
        ("property_campaigns::tests::kt_isometry_seed_000127", kt_isometry_seed_000127),
        ("property_campaigns::tests::kt_isometry_seed_000128", kt_isometry_seed_000128),
        ("property_campaigns::tests::kt_isometry_seed_000129", kt_isometry_seed_000129),
        ("property_campaigns::tests::kt_isometry_seed_000130", kt_isometry_seed_000130),
        ("property_campaigns::tests::kt_isometry_seed_000131", kt_isometry_seed_000131),
        ("property_campaigns::tests::kt_isometry_seed_000132", kt_isometry_seed_000132),
        ("property_campaigns::tests::kt_isometry_seed_000133", kt_isometry_seed_000133),
        ("property_campaigns::tests::kt_isometry_seed_000134", kt_isometry_seed_000134),
        ("property_campaigns::tests::kt_isometry_seed_000135", kt_isometry_seed_000135),
        ("property_campaigns::tests::kt_isometry_seed_000136", kt_isometry_seed_000136),
        ("property_campaigns::tests::kt_isometry_seed_000137", kt_isometry_seed_000137),
        ("property_campaigns::tests::kt_isometry_seed_000138", kt_isometry_seed_000138),
        ("property_campaigns::tests::kt_isometry_seed_000139", kt_isometry_seed_000139),
        ("property_campaigns::tests::kt_isometry_seed_000140", kt_isometry_seed_000140),
        ("property_campaigns::tests::kt_isometry_seed_000141", kt_isometry_seed_000141),
        ("property_campaigns::tests::kt_isometry_seed_000142", kt_isometry_seed_000142),
        ("property_campaigns::tests::kt_isometry_seed_000143", kt_isometry_seed_000143),
        ("property_campaigns::tests::kt_isometry_seed_000144", kt_isometry_seed_000144),
        ("property_campaigns::tests::kt_isometry_seed_000145", kt_isometry_seed_000145),
        ("property_campaigns::tests::kt_isometry_seed_000146", kt_isometry_seed_000146),
        ("property_campaigns::tests::kt_isometry_seed_000147", kt_isometry_seed_000147),
        ("property_campaigns::tests::kt_isometry_seed_000148", kt_isometry_seed_000148),
        ("property_campaigns::tests::kt_isometry_seed_000149", kt_isometry_seed_000149),
        ("property_campaigns::tests::kt_composition_seed_000000", kt_composition_seed_000000),
        ("property_campaigns::tests::kt_composition_seed_000001", kt_composition_seed_000001),
        ("property_campaigns::tests::kt_composition_seed_000002", kt_composition_seed_000002),
        ("property_campaigns::tests::kt_composition_seed_000003", kt_composition_seed_000003),
        ("property_campaigns::tests::kt_composition_seed_000004", kt_composition_seed_000004),
        ("property_campaigns::tests::kt_composition_seed_000005", kt_composition_seed_000005),
        ("property_campaigns::tests::kt_composition_seed_000006", kt_composition_seed_000006),
        ("property_campaigns::tests::kt_composition_seed_000007", kt_composition_seed_000007),
        ("property_campaigns::tests::kt_composition_seed_000008", kt_composition_seed_000008),
        ("property_campaigns::tests::kt_composition_seed_000009", kt_composition_seed_000009),
        ("property_campaigns::tests::kt_composition_seed_000010", kt_composition_seed_000010),
        ("property_campaigns::tests::kt_composition_seed_000011", kt_composition_seed_000011),
        ("property_campaigns::tests::kt_composition_seed_000012", kt_composition_seed_000012),
        ("property_campaigns::tests::kt_composition_seed_000013", kt_composition_seed_000013),
        ("property_campaigns::tests::kt_composition_seed_000014", kt_composition_seed_000014),
        ("property_campaigns::tests::kt_composition_seed_000015", kt_composition_seed_000015),
        ("property_campaigns::tests::kt_composition_seed_000016", kt_composition_seed_000016),
        ("property_campaigns::tests::kt_composition_seed_000017", kt_composition_seed_000017),
        ("property_campaigns::tests::kt_composition_seed_000018", kt_composition_seed_000018),
        ("property_campaigns::tests::kt_composition_seed_000019", kt_composition_seed_000019),
        ("property_campaigns::tests::kt_composition_seed_000020", kt_composition_seed_000020),
        ("property_campaigns::tests::kt_composition_seed_000021", kt_composition_seed_000021),
        ("property_campaigns::tests::kt_composition_seed_000022", kt_composition_seed_000022),
        ("property_campaigns::tests::kt_composition_seed_000023", kt_composition_seed_000023),
        ("property_campaigns::tests::kt_composition_seed_000024", kt_composition_seed_000024),
        ("property_campaigns::tests::kt_composition_seed_000025", kt_composition_seed_000025),
        ("property_campaigns::tests::kt_composition_seed_000026", kt_composition_seed_000026),
        ("property_campaigns::tests::kt_composition_seed_000027", kt_composition_seed_000027),
        ("property_campaigns::tests::kt_composition_seed_000028", kt_composition_seed_000028),
        ("property_campaigns::tests::kt_composition_seed_000029", kt_composition_seed_000029),
        ("property_campaigns::tests::kt_composition_seed_000030", kt_composition_seed_000030),
        ("property_campaigns::tests::kt_composition_seed_000031", kt_composition_seed_000031),
        ("property_campaigns::tests::kt_composition_seed_000032", kt_composition_seed_000032),
        ("property_campaigns::tests::kt_composition_seed_000033", kt_composition_seed_000033),
        ("property_campaigns::tests::kt_composition_seed_000034", kt_composition_seed_000034),
        ("property_campaigns::tests::kt_composition_seed_000035", kt_composition_seed_000035),
        ("property_campaigns::tests::kt_composition_seed_000036", kt_composition_seed_000036),
        ("property_campaigns::tests::kt_composition_seed_000037", kt_composition_seed_000037),
        ("property_campaigns::tests::kt_composition_seed_000038", kt_composition_seed_000038),
        ("property_campaigns::tests::kt_composition_seed_000039", kt_composition_seed_000039),
        ("property_campaigns::tests::kt_composition_seed_000040", kt_composition_seed_000040),
        ("property_campaigns::tests::kt_composition_seed_000041", kt_composition_seed_000041),
        ("property_campaigns::tests::kt_composition_seed_000042", kt_composition_seed_000042),
        ("property_campaigns::tests::kt_composition_seed_000043", kt_composition_seed_000043),
        ("property_campaigns::tests::kt_composition_seed_000044", kt_composition_seed_000044),
        ("property_campaigns::tests::kt_composition_seed_000045", kt_composition_seed_000045),
        ("property_campaigns::tests::kt_composition_seed_000046", kt_composition_seed_000046),
        ("property_campaigns::tests::kt_composition_seed_000047", kt_composition_seed_000047),
        ("property_campaigns::tests::kt_composition_seed_000048", kt_composition_seed_000048),
        ("property_campaigns::tests::kt_composition_seed_000049", kt_composition_seed_000049),
        ("property_campaigns::tests::kt_composition_seed_000050", kt_composition_seed_000050),
        ("property_campaigns::tests::kt_composition_seed_000051", kt_composition_seed_000051),
        ("property_campaigns::tests::kt_composition_seed_000052", kt_composition_seed_000052),
        ("property_campaigns::tests::kt_composition_seed_000053", kt_composition_seed_000053),
        ("property_campaigns::tests::kt_composition_seed_000054", kt_composition_seed_000054),
        ("property_campaigns::tests::kt_composition_seed_000055", kt_composition_seed_000055),
        ("property_campaigns::tests::kt_composition_seed_000056", kt_composition_seed_000056),
        ("property_campaigns::tests::kt_composition_seed_000057", kt_composition_seed_000057),
        ("property_campaigns::tests::kt_composition_seed_000058", kt_composition_seed_000058),
        ("property_campaigns::tests::kt_composition_seed_000059", kt_composition_seed_000059),
        ("property_campaigns::tests::kt_composition_seed_000060", kt_composition_seed_000060),
        ("property_campaigns::tests::kt_composition_seed_000061", kt_composition_seed_000061),
        ("property_campaigns::tests::kt_composition_seed_000062", kt_composition_seed_000062),
        ("property_campaigns::tests::kt_composition_seed_000063", kt_composition_seed_000063),
        ("property_campaigns::tests::kt_composition_seed_000064", kt_composition_seed_000064),
        ("property_campaigns::tests::kt_composition_seed_000065", kt_composition_seed_000065),
        ("property_campaigns::tests::kt_composition_seed_000066", kt_composition_seed_000066),
        ("property_campaigns::tests::kt_composition_seed_000067", kt_composition_seed_000067),
        ("property_campaigns::tests::kt_composition_seed_000068", kt_composition_seed_000068),
        ("property_campaigns::tests::kt_composition_seed_000069", kt_composition_seed_000069),
        ("property_campaigns::tests::kt_composition_seed_000070", kt_composition_seed_000070),
        ("property_campaigns::tests::kt_composition_seed_000071", kt_composition_seed_000071),
        ("property_campaigns::tests::kt_composition_seed_000072", kt_composition_seed_000072),
        ("property_campaigns::tests::kt_composition_seed_000073", kt_composition_seed_000073),
        ("property_campaigns::tests::kt_composition_seed_000074", kt_composition_seed_000074),
        ("property_campaigns::tests::kt_composition_seed_000075", kt_composition_seed_000075),
        ("property_campaigns::tests::kt_composition_seed_000076", kt_composition_seed_000076),
        ("property_campaigns::tests::kt_composition_seed_000077", kt_composition_seed_000077),
        ("property_campaigns::tests::kt_composition_seed_000078", kt_composition_seed_000078),
        ("property_campaigns::tests::kt_composition_seed_000079", kt_composition_seed_000079),
        ("property_campaigns::tests::kt_composition_seed_000080", kt_composition_seed_000080),
        ("property_campaigns::tests::kt_composition_seed_000081", kt_composition_seed_000081),
        ("property_campaigns::tests::kt_composition_seed_000082", kt_composition_seed_000082),
        ("property_campaigns::tests::kt_composition_seed_000083", kt_composition_seed_000083),
        ("property_campaigns::tests::kt_composition_seed_000084", kt_composition_seed_000084),
        ("property_campaigns::tests::kt_composition_seed_000085", kt_composition_seed_000085),
        ("property_campaigns::tests::kt_composition_seed_000086", kt_composition_seed_000086),
        ("property_campaigns::tests::kt_composition_seed_000087", kt_composition_seed_000087),
        ("property_campaigns::tests::kt_composition_seed_000088", kt_composition_seed_000088),
        ("property_campaigns::tests::kt_composition_seed_000089", kt_composition_seed_000089),
        ("property_campaigns::tests::kt_composition_seed_000090", kt_composition_seed_000090),
        ("property_campaigns::tests::kt_composition_seed_000091", kt_composition_seed_000091),
        ("property_campaigns::tests::kt_composition_seed_000092", kt_composition_seed_000092),
        ("property_campaigns::tests::kt_composition_seed_000093", kt_composition_seed_000093),
        ("property_campaigns::tests::kt_composition_seed_000094", kt_composition_seed_000094),
        ("property_campaigns::tests::kt_composition_seed_000095", kt_composition_seed_000095),
        ("property_campaigns::tests::kt_composition_seed_000096", kt_composition_seed_000096),
        ("property_campaigns::tests::kt_composition_seed_000097", kt_composition_seed_000097),
        ("property_campaigns::tests::kt_composition_seed_000098", kt_composition_seed_000098),
        ("property_campaigns::tests::kt_composition_seed_000099", kt_composition_seed_000099),
        ("property_campaigns::tests::kt_composition_seed_000100", kt_composition_seed_000100),
        ("property_campaigns::tests::kt_composition_seed_000101", kt_composition_seed_000101),
        ("property_campaigns::tests::kt_composition_seed_000102", kt_composition_seed_000102),
        ("property_campaigns::tests::kt_composition_seed_000103", kt_composition_seed_000103),
        ("property_campaigns::tests::kt_composition_seed_000104", kt_composition_seed_000104),
        ("property_campaigns::tests::kt_composition_seed_000105", kt_composition_seed_000105),
        ("property_campaigns::tests::kt_composition_seed_000106", kt_composition_seed_000106),
        ("property_campaigns::tests::kt_composition_seed_000107", kt_composition_seed_000107),
        ("property_campaigns::tests::kt_composition_seed_000108", kt_composition_seed_000108),
        ("property_campaigns::tests::kt_composition_seed_000109", kt_composition_seed_000109),
        ("property_campaigns::tests::kt_composition_seed_000110", kt_composition_seed_000110),
        ("property_campaigns::tests::kt_composition_seed_000111", kt_composition_seed_000111),
        ("property_campaigns::tests::kt_composition_seed_000112", kt_composition_seed_000112),
        ("property_campaigns::tests::kt_composition_seed_000113", kt_composition_seed_000113),
        ("property_campaigns::tests::kt_composition_seed_000114", kt_composition_seed_000114),
        ("property_campaigns::tests::kt_composition_seed_000115", kt_composition_seed_000115),
        ("property_campaigns::tests::kt_composition_seed_000116", kt_composition_seed_000116),
        ("property_campaigns::tests::kt_composition_seed_000117", kt_composition_seed_000117),
        ("property_campaigns::tests::kt_composition_seed_000118", kt_composition_seed_000118),
        ("property_campaigns::tests::kt_composition_seed_000119", kt_composition_seed_000119),
        ("property_campaigns::tests::kt_composition_seed_000120", kt_composition_seed_000120),
        ("property_campaigns::tests::kt_composition_seed_000121", kt_composition_seed_000121),
        ("property_campaigns::tests::kt_composition_seed_000122", kt_composition_seed_000122),
        ("property_campaigns::tests::kt_composition_seed_000123", kt_composition_seed_000123),
        ("property_campaigns::tests::kt_composition_seed_000124", kt_composition_seed_000124),
        ("property_campaigns::tests::kt_composition_seed_000125", kt_composition_seed_000125),
        ("property_campaigns::tests::kt_composition_seed_000126", kt_composition_seed_000126),
        ("property_campaigns::tests::kt_composition_seed_000127", kt_composition_seed_000127),
        ("property_campaigns::tests::kt_composition_seed_000128", kt_composition_seed_000128),
        ("property_campaigns::tests::kt_composition_seed_000129", kt_composition_seed_000129),
        ("property_campaigns::tests::kt_composition_seed_000130", kt_composition_seed_000130),
        ("property_campaigns::tests::kt_composition_seed_000131", kt_composition_seed_000131),
        ("property_campaigns::tests::kt_composition_seed_000132", kt_composition_seed_000132),
        ("property_campaigns::tests::kt_composition_seed_000133", kt_composition_seed_000133),
        ("property_campaigns::tests::kt_composition_seed_000134", kt_composition_seed_000134),
        ("property_campaigns::tests::kt_composition_seed_000135", kt_composition_seed_000135),
        ("property_campaigns::tests::kt_composition_seed_000136", kt_composition_seed_000136),
        ("property_campaigns::tests::kt_composition_seed_000137", kt_composition_seed_000137),
        ("property_campaigns::tests::kt_composition_seed_000138", kt_composition_seed_000138),
        ("property_campaigns::tests::kt_composition_seed_000139", kt_composition_seed_000139),
        ("property_campaigns::tests::kt_composition_seed_000140", kt_composition_seed_000140),
        ("property_campaigns::tests::kt_composition_seed_000141", kt_composition_seed_000141),
        ("property_campaigns::tests::kt_composition_seed_000142", kt_composition_seed_000142),
        ("property_campaigns::tests::kt_composition_seed_000143", kt_composition_seed_000143),
        ("property_campaigns::tests::kt_composition_seed_000144", kt_composition_seed_000144),
        ("property_campaigns::tests::kt_composition_seed_000145", kt_composition_seed_000145),
        ("property_campaigns::tests::kt_composition_seed_000146", kt_composition_seed_000146),
        ("property_campaigns::tests::kt_composition_seed_000147", kt_composition_seed_000147),
        ("property_campaigns::tests::kt_composition_seed_000148", kt_composition_seed_000148),
        ("property_campaigns::tests::kt_composition_seed_000149", kt_composition_seed_000149),
        ("property_campaigns::tests::kt_place_translation_seed_000000", kt_place_translation_seed_000000),
        ("property_campaigns::tests::kt_place_translation_seed_000001", kt_place_translation_seed_000001),
        ("property_campaigns::tests::kt_place_translation_seed_000002", kt_place_translation_seed_000002),
        ("property_campaigns::tests::kt_place_translation_seed_000003", kt_place_translation_seed_000003),
        ("property_campaigns::tests::kt_place_translation_seed_000004", kt_place_translation_seed_000004),
        ("property_campaigns::tests::kt_place_translation_seed_000005", kt_place_translation_seed_000005),
        ("property_campaigns::tests::kt_place_translation_seed_000006", kt_place_translation_seed_000006),
        ("property_campaigns::tests::kt_place_translation_seed_000007", kt_place_translation_seed_000007),
        ("property_campaigns::tests::kt_place_translation_seed_000008", kt_place_translation_seed_000008),
        ("property_campaigns::tests::kt_place_translation_seed_000009", kt_place_translation_seed_000009),
        ("property_campaigns::tests::kt_place_translation_seed_000010", kt_place_translation_seed_000010),
        ("property_campaigns::tests::kt_place_translation_seed_000011", kt_place_translation_seed_000011),
        ("property_campaigns::tests::kt_place_translation_seed_000012", kt_place_translation_seed_000012),
        ("property_campaigns::tests::kt_place_translation_seed_000013", kt_place_translation_seed_000013),
        ("property_campaigns::tests::kt_place_translation_seed_000014", kt_place_translation_seed_000014),
        ("property_campaigns::tests::kt_place_translation_seed_000015", kt_place_translation_seed_000015),
        ("property_campaigns::tests::kt_place_translation_seed_000016", kt_place_translation_seed_000016),
        ("property_campaigns::tests::kt_place_translation_seed_000017", kt_place_translation_seed_000017),
        ("property_campaigns::tests::kt_place_translation_seed_000018", kt_place_translation_seed_000018),
        ("property_campaigns::tests::kt_place_translation_seed_000019", kt_place_translation_seed_000019),
        ("property_campaigns::tests::kt_place_translation_seed_000020", kt_place_translation_seed_000020),
        ("property_campaigns::tests::kt_place_translation_seed_000021", kt_place_translation_seed_000021),
        ("property_campaigns::tests::kt_place_translation_seed_000022", kt_place_translation_seed_000022),
        ("property_campaigns::tests::kt_place_translation_seed_000023", kt_place_translation_seed_000023),
        ("property_campaigns::tests::kt_place_translation_seed_000024", kt_place_translation_seed_000024),
        ("property_campaigns::tests::kt_place_translation_seed_000025", kt_place_translation_seed_000025),
        ("property_campaigns::tests::kt_place_translation_seed_000026", kt_place_translation_seed_000026),
        ("property_campaigns::tests::kt_place_translation_seed_000027", kt_place_translation_seed_000027),
        ("property_campaigns::tests::kt_place_translation_seed_000028", kt_place_translation_seed_000028),
        ("property_campaigns::tests::kt_place_translation_seed_000029", kt_place_translation_seed_000029),
        ("property_campaigns::tests::kt_place_translation_seed_000030", kt_place_translation_seed_000030),
        ("property_campaigns::tests::kt_place_translation_seed_000031", kt_place_translation_seed_000031),
        ("property_campaigns::tests::kt_place_translation_seed_000032", kt_place_translation_seed_000032),
        ("property_campaigns::tests::kt_place_translation_seed_000033", kt_place_translation_seed_000033),
        ("property_campaigns::tests::kt_place_translation_seed_000034", kt_place_translation_seed_000034),
        ("property_campaigns::tests::kt_place_translation_seed_000035", kt_place_translation_seed_000035),
        ("property_campaigns::tests::kt_place_translation_seed_000036", kt_place_translation_seed_000036),
        ("property_campaigns::tests::kt_place_translation_seed_000037", kt_place_translation_seed_000037),
        ("property_campaigns::tests::kt_place_translation_seed_000038", kt_place_translation_seed_000038),
        ("property_campaigns::tests::kt_place_translation_seed_000039", kt_place_translation_seed_000039),
        ("property_campaigns::tests::kt_place_translation_seed_000040", kt_place_translation_seed_000040),
        ("property_campaigns::tests::kt_place_translation_seed_000041", kt_place_translation_seed_000041),
        ("property_campaigns::tests::kt_place_translation_seed_000042", kt_place_translation_seed_000042),
        ("property_campaigns::tests::kt_place_translation_seed_000043", kt_place_translation_seed_000043),
        ("property_campaigns::tests::kt_place_translation_seed_000044", kt_place_translation_seed_000044),
        ("property_campaigns::tests::kt_place_translation_seed_000045", kt_place_translation_seed_000045),
        ("property_campaigns::tests::kt_place_translation_seed_000046", kt_place_translation_seed_000046),
        ("property_campaigns::tests::kt_place_translation_seed_000047", kt_place_translation_seed_000047),
        ("property_campaigns::tests::kt_place_translation_seed_000048", kt_place_translation_seed_000048),
        ("property_campaigns::tests::kt_place_translation_seed_000049", kt_place_translation_seed_000049),
        ("property_campaigns::tests::kt_place_translation_seed_000050", kt_place_translation_seed_000050),
        ("property_campaigns::tests::kt_place_translation_seed_000051", kt_place_translation_seed_000051),
        ("property_campaigns::tests::kt_place_translation_seed_000052", kt_place_translation_seed_000052),
        ("property_campaigns::tests::kt_place_translation_seed_000053", kt_place_translation_seed_000053),
        ("property_campaigns::tests::kt_place_translation_seed_000054", kt_place_translation_seed_000054),
        ("property_campaigns::tests::kt_place_translation_seed_000055", kt_place_translation_seed_000055),
        ("property_campaigns::tests::kt_place_translation_seed_000056", kt_place_translation_seed_000056),
        ("property_campaigns::tests::kt_place_translation_seed_000057", kt_place_translation_seed_000057),
        ("property_campaigns::tests::kt_place_translation_seed_000058", kt_place_translation_seed_000058),
        ("property_campaigns::tests::kt_place_translation_seed_000059", kt_place_translation_seed_000059),
        ("property_campaigns::tests::kt_place_translation_seed_000060", kt_place_translation_seed_000060),
        ("property_campaigns::tests::kt_place_translation_seed_000061", kt_place_translation_seed_000061),
        ("property_campaigns::tests::kt_place_translation_seed_000062", kt_place_translation_seed_000062),
        ("property_campaigns::tests::kt_place_translation_seed_000063", kt_place_translation_seed_000063),
        ("property_campaigns::tests::kt_place_translation_seed_000064", kt_place_translation_seed_000064),
        ("property_campaigns::tests::kt_place_translation_seed_000065", kt_place_translation_seed_000065),
        ("property_campaigns::tests::kt_place_translation_seed_000066", kt_place_translation_seed_000066),
        ("property_campaigns::tests::kt_place_translation_seed_000067", kt_place_translation_seed_000067),
        ("property_campaigns::tests::kt_place_translation_seed_000068", kt_place_translation_seed_000068),
        ("property_campaigns::tests::kt_place_translation_seed_000069", kt_place_translation_seed_000069),
        ("property_campaigns::tests::kt_place_translation_seed_000070", kt_place_translation_seed_000070),
        ("property_campaigns::tests::kt_place_translation_seed_000071", kt_place_translation_seed_000071),
        ("property_campaigns::tests::kt_place_translation_seed_000072", kt_place_translation_seed_000072),
        ("property_campaigns::tests::kt_place_translation_seed_000073", kt_place_translation_seed_000073),
        ("property_campaigns::tests::kt_place_translation_seed_000074", kt_place_translation_seed_000074),
        ("property_campaigns::tests::kt_place_translation_seed_000075", kt_place_translation_seed_000075),
        ("property_campaigns::tests::kt_place_translation_seed_000076", kt_place_translation_seed_000076),
        ("property_campaigns::tests::kt_place_translation_seed_000077", kt_place_translation_seed_000077),
        ("property_campaigns::tests::kt_place_translation_seed_000078", kt_place_translation_seed_000078),
        ("property_campaigns::tests::kt_place_translation_seed_000079", kt_place_translation_seed_000079),
        ("property_campaigns::tests::kt_place_translation_seed_000080", kt_place_translation_seed_000080),
        ("property_campaigns::tests::kt_place_translation_seed_000081", kt_place_translation_seed_000081),
        ("property_campaigns::tests::kt_place_translation_seed_000082", kt_place_translation_seed_000082),
        ("property_campaigns::tests::kt_place_translation_seed_000083", kt_place_translation_seed_000083),
        ("property_campaigns::tests::kt_place_translation_seed_000084", kt_place_translation_seed_000084),
        ("property_campaigns::tests::kt_place_translation_seed_000085", kt_place_translation_seed_000085),
        ("property_campaigns::tests::kt_place_translation_seed_000086", kt_place_translation_seed_000086),
        ("property_campaigns::tests::kt_place_translation_seed_000087", kt_place_translation_seed_000087),
        ("property_campaigns::tests::kt_place_translation_seed_000088", kt_place_translation_seed_000088),
        ("property_campaigns::tests::kt_place_translation_seed_000089", kt_place_translation_seed_000089),
        ("property_campaigns::tests::kt_place_translation_seed_000090", kt_place_translation_seed_000090),
        ("property_campaigns::tests::kt_place_translation_seed_000091", kt_place_translation_seed_000091),
        ("property_campaigns::tests::kt_place_translation_seed_000092", kt_place_translation_seed_000092),
        ("property_campaigns::tests::kt_place_translation_seed_000093", kt_place_translation_seed_000093),
        ("property_campaigns::tests::kt_place_translation_seed_000094", kt_place_translation_seed_000094),
        ("property_campaigns::tests::kt_place_translation_seed_000095", kt_place_translation_seed_000095),
        ("property_campaigns::tests::kt_place_translation_seed_000096", kt_place_translation_seed_000096),
        ("property_campaigns::tests::kt_place_translation_seed_000097", kt_place_translation_seed_000097),
        ("property_campaigns::tests::kt_place_translation_seed_000098", kt_place_translation_seed_000098),
        ("property_campaigns::tests::kt_place_translation_seed_000099", kt_place_translation_seed_000099),
        ("property_campaigns::tests::kt_place_translation_seed_000100", kt_place_translation_seed_000100),
        ("property_campaigns::tests::kt_place_translation_seed_000101", kt_place_translation_seed_000101),
        ("property_campaigns::tests::kt_place_translation_seed_000102", kt_place_translation_seed_000102),
        ("property_campaigns::tests::kt_place_translation_seed_000103", kt_place_translation_seed_000103),
        ("property_campaigns::tests::kt_place_translation_seed_000104", kt_place_translation_seed_000104),
        ("property_campaigns::tests::kt_place_translation_seed_000105", kt_place_translation_seed_000105),
        ("property_campaigns::tests::kt_place_translation_seed_000106", kt_place_translation_seed_000106),
        ("property_campaigns::tests::kt_place_translation_seed_000107", kt_place_translation_seed_000107),
        ("property_campaigns::tests::kt_place_translation_seed_000108", kt_place_translation_seed_000108),
        ("property_campaigns::tests::kt_place_translation_seed_000109", kt_place_translation_seed_000109),
        ("property_campaigns::tests::kt_place_translation_seed_000110", kt_place_translation_seed_000110),
        ("property_campaigns::tests::kt_place_translation_seed_000111", kt_place_translation_seed_000111),
        ("property_campaigns::tests::kt_place_translation_seed_000112", kt_place_translation_seed_000112),
        ("property_campaigns::tests::kt_place_translation_seed_000113", kt_place_translation_seed_000113),
        ("property_campaigns::tests::kt_place_translation_seed_000114", kt_place_translation_seed_000114),
        ("property_campaigns::tests::kt_place_translation_seed_000115", kt_place_translation_seed_000115),
        ("property_campaigns::tests::kt_place_translation_seed_000116", kt_place_translation_seed_000116),
        ("property_campaigns::tests::kt_place_translation_seed_000117", kt_place_translation_seed_000117),
        ("property_campaigns::tests::kt_place_translation_seed_000118", kt_place_translation_seed_000118),
        ("property_campaigns::tests::kt_place_translation_seed_000119", kt_place_translation_seed_000119),
        ("property_campaigns::tests::kt_place_translation_seed_000120", kt_place_translation_seed_000120),
        ("property_campaigns::tests::kt_place_translation_seed_000121", kt_place_translation_seed_000121),
        ("property_campaigns::tests::kt_place_translation_seed_000122", kt_place_translation_seed_000122),
        ("property_campaigns::tests::kt_place_translation_seed_000123", kt_place_translation_seed_000123),
        ("property_campaigns::tests::kt_place_translation_seed_000124", kt_place_translation_seed_000124),
        ("property_campaigns::tests::kt_place_translation_seed_000125", kt_place_translation_seed_000125),
        ("property_campaigns::tests::kt_place_translation_seed_000126", kt_place_translation_seed_000126),
        ("property_campaigns::tests::kt_place_translation_seed_000127", kt_place_translation_seed_000127),
        ("property_campaigns::tests::kt_place_translation_seed_000128", kt_place_translation_seed_000128),
        ("property_campaigns::tests::kt_place_translation_seed_000129", kt_place_translation_seed_000129),
        ("property_campaigns::tests::kt_place_translation_seed_000130", kt_place_translation_seed_000130),
        ("property_campaigns::tests::kt_place_translation_seed_000131", kt_place_translation_seed_000131),
        ("property_campaigns::tests::kt_place_translation_seed_000132", kt_place_translation_seed_000132),
        ("property_campaigns::tests::kt_place_translation_seed_000133", kt_place_translation_seed_000133),
        ("property_campaigns::tests::kt_place_translation_seed_000134", kt_place_translation_seed_000134),
        ("property_campaigns::tests::kt_place_translation_seed_000135", kt_place_translation_seed_000135),
        ("property_campaigns::tests::kt_place_translation_seed_000136", kt_place_translation_seed_000136),
        ("property_campaigns::tests::kt_place_translation_seed_000137", kt_place_translation_seed_000137),
        ("property_campaigns::tests::kt_place_translation_seed_000138", kt_place_translation_seed_000138),
        ("property_campaigns::tests::kt_place_translation_seed_000139", kt_place_translation_seed_000139),
        ("property_campaigns::tests::kt_place_translation_seed_000140", kt_place_translation_seed_000140),
        ("property_campaigns::tests::kt_place_translation_seed_000141", kt_place_translation_seed_000141),
        ("property_campaigns::tests::kt_place_translation_seed_000142", kt_place_translation_seed_000142),
        ("property_campaigns::tests::kt_place_translation_seed_000143", kt_place_translation_seed_000143),
        ("property_campaigns::tests::kt_place_translation_seed_000144", kt_place_translation_seed_000144),
        ("property_campaigns::tests::kt_place_translation_seed_000145", kt_place_translation_seed_000145),
        ("property_campaigns::tests::kt_place_translation_seed_000146", kt_place_translation_seed_000146),
        ("property_campaigns::tests::kt_place_translation_seed_000147", kt_place_translation_seed_000147),
        ("property_campaigns::tests::kt_place_translation_seed_000148", kt_place_translation_seed_000148),
        ("property_campaigns::tests::kt_place_translation_seed_000149", kt_place_translation_seed_000149),
        ("property_campaigns::tests::ch_translation_seed_000000", ch_translation_seed_000000),
        ("property_campaigns::tests::ch_translation_seed_000001", ch_translation_seed_000001),
        ("property_campaigns::tests::ch_translation_seed_000002", ch_translation_seed_000002),
        ("property_campaigns::tests::ch_translation_seed_000003", ch_translation_seed_000003),
        ("property_campaigns::tests::ch_translation_seed_000004", ch_translation_seed_000004),
        ("property_campaigns::tests::ch_translation_seed_000005", ch_translation_seed_000005),
        ("property_campaigns::tests::ch_translation_seed_000006", ch_translation_seed_000006),
        ("property_campaigns::tests::ch_translation_seed_000007", ch_translation_seed_000007),
        ("property_campaigns::tests::ch_translation_seed_000008", ch_translation_seed_000008),
        ("property_campaigns::tests::ch_translation_seed_000009", ch_translation_seed_000009),
        ("property_campaigns::tests::ch_translation_seed_000010", ch_translation_seed_000010),
        ("property_campaigns::tests::ch_translation_seed_000011", ch_translation_seed_000011),
        ("property_campaigns::tests::ch_translation_seed_000012", ch_translation_seed_000012),
        ("property_campaigns::tests::ch_translation_seed_000013", ch_translation_seed_000013),
        ("property_campaigns::tests::ch_translation_seed_000014", ch_translation_seed_000014),
        ("property_campaigns::tests::ch_translation_seed_000015", ch_translation_seed_000015),
        ("property_campaigns::tests::ch_translation_seed_000016", ch_translation_seed_000016),
        ("property_campaigns::tests::ch_translation_seed_000017", ch_translation_seed_000017),
        ("property_campaigns::tests::ch_translation_seed_000018", ch_translation_seed_000018),
        ("property_campaigns::tests::ch_translation_seed_000019", ch_translation_seed_000019),
        ("property_campaigns::tests::ch_translation_seed_000020", ch_translation_seed_000020),
        ("property_campaigns::tests::ch_translation_seed_000021", ch_translation_seed_000021),
        ("property_campaigns::tests::ch_translation_seed_000022", ch_translation_seed_000022),
        ("property_campaigns::tests::ch_translation_seed_000023", ch_translation_seed_000023),
        ("property_campaigns::tests::ch_translation_seed_000024", ch_translation_seed_000024),
        ("property_campaigns::tests::ch_translation_seed_000025", ch_translation_seed_000025),
        ("property_campaigns::tests::ch_translation_seed_000026", ch_translation_seed_000026),
        ("property_campaigns::tests::ch_translation_seed_000027", ch_translation_seed_000027),
        ("property_campaigns::tests::ch_translation_seed_000028", ch_translation_seed_000028),
        ("property_campaigns::tests::ch_translation_seed_000029", ch_translation_seed_000029),
        ("property_campaigns::tests::ch_translation_seed_000030", ch_translation_seed_000030),
        ("property_campaigns::tests::ch_translation_seed_000031", ch_translation_seed_000031),
        ("property_campaigns::tests::ch_translation_seed_000032", ch_translation_seed_000032),
        ("property_campaigns::tests::ch_translation_seed_000033", ch_translation_seed_000033),
        ("property_campaigns::tests::ch_translation_seed_000034", ch_translation_seed_000034),
        ("property_campaigns::tests::ch_translation_seed_000035", ch_translation_seed_000035),
        ("property_campaigns::tests::ch_translation_seed_000036", ch_translation_seed_000036),
        ("property_campaigns::tests::ch_translation_seed_000037", ch_translation_seed_000037),
        ("property_campaigns::tests::ch_translation_seed_000038", ch_translation_seed_000038),
        ("property_campaigns::tests::ch_translation_seed_000039", ch_translation_seed_000039),
        ("property_campaigns::tests::ch_translation_seed_000040", ch_translation_seed_000040),
        ("property_campaigns::tests::ch_translation_seed_000041", ch_translation_seed_000041),
        ("property_campaigns::tests::ch_translation_seed_000042", ch_translation_seed_000042),
        ("property_campaigns::tests::ch_translation_seed_000043", ch_translation_seed_000043),
        ("property_campaigns::tests::ch_translation_seed_000044", ch_translation_seed_000044),
        ("property_campaigns::tests::ch_translation_seed_000045", ch_translation_seed_000045),
        ("property_campaigns::tests::ch_translation_seed_000046", ch_translation_seed_000046),
        ("property_campaigns::tests::ch_translation_seed_000047", ch_translation_seed_000047),
        ("property_campaigns::tests::ch_translation_seed_000048", ch_translation_seed_000048),
        ("property_campaigns::tests::ch_translation_seed_000049", ch_translation_seed_000049),
        ("property_campaigns::tests::ch_translation_seed_000050", ch_translation_seed_000050),
        ("property_campaigns::tests::ch_translation_seed_000051", ch_translation_seed_000051),
        ("property_campaigns::tests::ch_translation_seed_000052", ch_translation_seed_000052),
        ("property_campaigns::tests::ch_translation_seed_000053", ch_translation_seed_000053),
        ("property_campaigns::tests::ch_translation_seed_000054", ch_translation_seed_000054),
        ("property_campaigns::tests::ch_translation_seed_000055", ch_translation_seed_000055),
        ("property_campaigns::tests::ch_translation_seed_000056", ch_translation_seed_000056),
        ("property_campaigns::tests::ch_translation_seed_000057", ch_translation_seed_000057),
        ("property_campaigns::tests::ch_translation_seed_000058", ch_translation_seed_000058),
        ("property_campaigns::tests::ch_translation_seed_000059", ch_translation_seed_000059),
        ("property_campaigns::tests::ch_translation_seed_000060", ch_translation_seed_000060),
        ("property_campaigns::tests::ch_translation_seed_000061", ch_translation_seed_000061),
        ("property_campaigns::tests::ch_translation_seed_000062", ch_translation_seed_000062),
        ("property_campaigns::tests::ch_translation_seed_000063", ch_translation_seed_000063),
        ("property_campaigns::tests::ch_translation_seed_000064", ch_translation_seed_000064),
        ("property_campaigns::tests::ch_translation_seed_000065", ch_translation_seed_000065),
        ("property_campaigns::tests::ch_translation_seed_000066", ch_translation_seed_000066),
        ("property_campaigns::tests::ch_translation_seed_000067", ch_translation_seed_000067),
        ("property_campaigns::tests::ch_translation_seed_000068", ch_translation_seed_000068),
        ("property_campaigns::tests::ch_translation_seed_000069", ch_translation_seed_000069),
        ("property_campaigns::tests::ch_translation_seed_000070", ch_translation_seed_000070),
        ("property_campaigns::tests::ch_translation_seed_000071", ch_translation_seed_000071),
        ("property_campaigns::tests::ch_translation_seed_000072", ch_translation_seed_000072),
        ("property_campaigns::tests::ch_translation_seed_000073", ch_translation_seed_000073),
        ("property_campaigns::tests::ch_translation_seed_000074", ch_translation_seed_000074),
        ("property_campaigns::tests::ch_translation_seed_000075", ch_translation_seed_000075),
        ("property_campaigns::tests::ch_translation_seed_000076", ch_translation_seed_000076),
        ("property_campaigns::tests::ch_translation_seed_000077", ch_translation_seed_000077),
        ("property_campaigns::tests::ch_translation_seed_000078", ch_translation_seed_000078),
        ("property_campaigns::tests::ch_translation_seed_000079", ch_translation_seed_000079),
        ("property_campaigns::tests::ch_translation_seed_000080", ch_translation_seed_000080),
        ("property_campaigns::tests::ch_translation_seed_000081", ch_translation_seed_000081),
        ("property_campaigns::tests::ch_translation_seed_000082", ch_translation_seed_000082),
        ("property_campaigns::tests::ch_translation_seed_000083", ch_translation_seed_000083),
        ("property_campaigns::tests::ch_translation_seed_000084", ch_translation_seed_000084),
        ("property_campaigns::tests::ch_translation_seed_000085", ch_translation_seed_000085),
        ("property_campaigns::tests::ch_translation_seed_000086", ch_translation_seed_000086),
        ("property_campaigns::tests::ch_translation_seed_000087", ch_translation_seed_000087),
        ("property_campaigns::tests::ch_translation_seed_000088", ch_translation_seed_000088),
        ("property_campaigns::tests::ch_translation_seed_000089", ch_translation_seed_000089),
        ("property_campaigns::tests::ch_translation_seed_000090", ch_translation_seed_000090),
        ("property_campaigns::tests::ch_translation_seed_000091", ch_translation_seed_000091),
        ("property_campaigns::tests::ch_translation_seed_000092", ch_translation_seed_000092),
        ("property_campaigns::tests::ch_translation_seed_000093", ch_translation_seed_000093),
        ("property_campaigns::tests::ch_translation_seed_000094", ch_translation_seed_000094),
        ("property_campaigns::tests::ch_translation_seed_000095", ch_translation_seed_000095),
        ("property_campaigns::tests::ch_translation_seed_000096", ch_translation_seed_000096),
        ("property_campaigns::tests::ch_translation_seed_000097", ch_translation_seed_000097),
        ("property_campaigns::tests::ch_translation_seed_000098", ch_translation_seed_000098),
        ("property_campaigns::tests::ch_translation_seed_000099", ch_translation_seed_000099),
        ("property_campaigns::tests::ch_translation_seed_000100", ch_translation_seed_000100),
        ("property_campaigns::tests::ch_translation_seed_000101", ch_translation_seed_000101),
        ("property_campaigns::tests::ch_translation_seed_000102", ch_translation_seed_000102),
        ("property_campaigns::tests::ch_translation_seed_000103", ch_translation_seed_000103),
        ("property_campaigns::tests::ch_translation_seed_000104", ch_translation_seed_000104),
        ("property_campaigns::tests::ch_translation_seed_000105", ch_translation_seed_000105),
        ("property_campaigns::tests::ch_translation_seed_000106", ch_translation_seed_000106),
        ("property_campaigns::tests::ch_translation_seed_000107", ch_translation_seed_000107),
        ("property_campaigns::tests::ch_translation_seed_000108", ch_translation_seed_000108),
        ("property_campaigns::tests::ch_translation_seed_000109", ch_translation_seed_000109),
        ("property_campaigns::tests::ch_translation_seed_000110", ch_translation_seed_000110),
        ("property_campaigns::tests::ch_translation_seed_000111", ch_translation_seed_000111),
        ("property_campaigns::tests::ch_translation_seed_000112", ch_translation_seed_000112),
        ("property_campaigns::tests::ch_translation_seed_000113", ch_translation_seed_000113),
        ("property_campaigns::tests::ch_translation_seed_000114", ch_translation_seed_000114),
        ("property_campaigns::tests::ch_translation_seed_000115", ch_translation_seed_000115),
        ("property_campaigns::tests::ch_translation_seed_000116", ch_translation_seed_000116),
        ("property_campaigns::tests::ch_translation_seed_000117", ch_translation_seed_000117),
        ("property_campaigns::tests::ch_translation_seed_000118", ch_translation_seed_000118),
        ("property_campaigns::tests::ch_translation_seed_000119", ch_translation_seed_000119),
        ("property_campaigns::tests::ch_rotation_seed_000000", ch_rotation_seed_000000),
        ("property_campaigns::tests::ch_rotation_seed_000001", ch_rotation_seed_000001),
        ("property_campaigns::tests::ch_rotation_seed_000002", ch_rotation_seed_000002),
        ("property_campaigns::tests::ch_rotation_seed_000003", ch_rotation_seed_000003),
        ("property_campaigns::tests::ch_rotation_seed_000004", ch_rotation_seed_000004),
        ("property_campaigns::tests::ch_rotation_seed_000005", ch_rotation_seed_000005),
        ("property_campaigns::tests::ch_rotation_seed_000006", ch_rotation_seed_000006),
        ("property_campaigns::tests::ch_rotation_seed_000007", ch_rotation_seed_000007),
        ("property_campaigns::tests::ch_rotation_seed_000008", ch_rotation_seed_000008),
        ("property_campaigns::tests::ch_rotation_seed_000009", ch_rotation_seed_000009),
        ("property_campaigns::tests::ch_rotation_seed_000010", ch_rotation_seed_000010),
        ("property_campaigns::tests::ch_rotation_seed_000011", ch_rotation_seed_000011),
        ("property_campaigns::tests::ch_rotation_seed_000012", ch_rotation_seed_000012),
        ("property_campaigns::tests::ch_rotation_seed_000013", ch_rotation_seed_000013),
        ("property_campaigns::tests::ch_rotation_seed_000014", ch_rotation_seed_000014),
        ("property_campaigns::tests::ch_rotation_seed_000015", ch_rotation_seed_000015),
        ("property_campaigns::tests::ch_rotation_seed_000016", ch_rotation_seed_000016),
        ("property_campaigns::tests::ch_rotation_seed_000017", ch_rotation_seed_000017),
        ("property_campaigns::tests::ch_rotation_seed_000018", ch_rotation_seed_000018),
        ("property_campaigns::tests::ch_rotation_seed_000019", ch_rotation_seed_000019),
        ("property_campaigns::tests::ch_rotation_seed_000020", ch_rotation_seed_000020),
        ("property_campaigns::tests::ch_rotation_seed_000021", ch_rotation_seed_000021),
        ("property_campaigns::tests::ch_rotation_seed_000022", ch_rotation_seed_000022),
        ("property_campaigns::tests::ch_rotation_seed_000023", ch_rotation_seed_000023),
        ("property_campaigns::tests::ch_rotation_seed_000024", ch_rotation_seed_000024),
        ("property_campaigns::tests::ch_rotation_seed_000025", ch_rotation_seed_000025),
        ("property_campaigns::tests::ch_rotation_seed_000026", ch_rotation_seed_000026),
        ("property_campaigns::tests::ch_rotation_seed_000027", ch_rotation_seed_000027),
        ("property_campaigns::tests::ch_rotation_seed_000028", ch_rotation_seed_000028),
        ("property_campaigns::tests::ch_rotation_seed_000029", ch_rotation_seed_000029),
        ("property_campaigns::tests::ch_rotation_seed_000030", ch_rotation_seed_000030),
        ("property_campaigns::tests::ch_rotation_seed_000031", ch_rotation_seed_000031),
        ("property_campaigns::tests::ch_rotation_seed_000032", ch_rotation_seed_000032),
        ("property_campaigns::tests::ch_rotation_seed_000033", ch_rotation_seed_000033),
        ("property_campaigns::tests::ch_rotation_seed_000034", ch_rotation_seed_000034),
        ("property_campaigns::tests::ch_rotation_seed_000035", ch_rotation_seed_000035),
        ("property_campaigns::tests::ch_rotation_seed_000036", ch_rotation_seed_000036),
        ("property_campaigns::tests::ch_rotation_seed_000037", ch_rotation_seed_000037),
        ("property_campaigns::tests::ch_rotation_seed_000038", ch_rotation_seed_000038),
        ("property_campaigns::tests::ch_rotation_seed_000039", ch_rotation_seed_000039),
        ("property_campaigns::tests::ch_rotation_seed_000040", ch_rotation_seed_000040),
        ("property_campaigns::tests::ch_rotation_seed_000041", ch_rotation_seed_000041),
        ("property_campaigns::tests::ch_rotation_seed_000042", ch_rotation_seed_000042),
        ("property_campaigns::tests::ch_rotation_seed_000043", ch_rotation_seed_000043),
        ("property_campaigns::tests::ch_rotation_seed_000044", ch_rotation_seed_000044),
        ("property_campaigns::tests::ch_rotation_seed_000045", ch_rotation_seed_000045),
        ("property_campaigns::tests::ch_rotation_seed_000046", ch_rotation_seed_000046),
        ("property_campaigns::tests::ch_rotation_seed_000047", ch_rotation_seed_000047),
        ("property_campaigns::tests::ch_rotation_seed_000048", ch_rotation_seed_000048),
        ("property_campaigns::tests::ch_rotation_seed_000049", ch_rotation_seed_000049),
        ("property_campaigns::tests::ch_rotation_seed_000050", ch_rotation_seed_000050),
        ("property_campaigns::tests::ch_rotation_seed_000051", ch_rotation_seed_000051),
        ("property_campaigns::tests::ch_rotation_seed_000052", ch_rotation_seed_000052),
        ("property_campaigns::tests::ch_rotation_seed_000053", ch_rotation_seed_000053),
        ("property_campaigns::tests::ch_rotation_seed_000054", ch_rotation_seed_000054),
        ("property_campaigns::tests::ch_rotation_seed_000055", ch_rotation_seed_000055),
        ("property_campaigns::tests::ch_rotation_seed_000056", ch_rotation_seed_000056),
        ("property_campaigns::tests::ch_rotation_seed_000057", ch_rotation_seed_000057),
        ("property_campaigns::tests::ch_rotation_seed_000058", ch_rotation_seed_000058),
        ("property_campaigns::tests::ch_rotation_seed_000059", ch_rotation_seed_000059),
        ("property_campaigns::tests::ch_rotation_seed_000060", ch_rotation_seed_000060),
        ("property_campaigns::tests::ch_rotation_seed_000061", ch_rotation_seed_000061),
        ("property_campaigns::tests::ch_rotation_seed_000062", ch_rotation_seed_000062),
        ("property_campaigns::tests::ch_rotation_seed_000063", ch_rotation_seed_000063),
        ("property_campaigns::tests::ch_rotation_seed_000064", ch_rotation_seed_000064),
        ("property_campaigns::tests::ch_rotation_seed_000065", ch_rotation_seed_000065),
        ("property_campaigns::tests::ch_rotation_seed_000066", ch_rotation_seed_000066),
        ("property_campaigns::tests::ch_rotation_seed_000067", ch_rotation_seed_000067),
        ("property_campaigns::tests::ch_rotation_seed_000068", ch_rotation_seed_000068),
        ("property_campaigns::tests::ch_rotation_seed_000069", ch_rotation_seed_000069),
        ("property_campaigns::tests::ch_rotation_seed_000070", ch_rotation_seed_000070),
        ("property_campaigns::tests::ch_rotation_seed_000071", ch_rotation_seed_000071),
        ("property_campaigns::tests::ch_rotation_seed_000072", ch_rotation_seed_000072),
        ("property_campaigns::tests::ch_rotation_seed_000073", ch_rotation_seed_000073),
        ("property_campaigns::tests::ch_rotation_seed_000074", ch_rotation_seed_000074),
        ("property_campaigns::tests::ch_rotation_seed_000075", ch_rotation_seed_000075),
        ("property_campaigns::tests::ch_rotation_seed_000076", ch_rotation_seed_000076),
        ("property_campaigns::tests::ch_rotation_seed_000077", ch_rotation_seed_000077),
        ("property_campaigns::tests::ch_rotation_seed_000078", ch_rotation_seed_000078),
        ("property_campaigns::tests::ch_rotation_seed_000079", ch_rotation_seed_000079),
        ("property_campaigns::tests::ch_rotation_seed_000080", ch_rotation_seed_000080),
        ("property_campaigns::tests::ch_rotation_seed_000081", ch_rotation_seed_000081),
        ("property_campaigns::tests::ch_rotation_seed_000082", ch_rotation_seed_000082),
        ("property_campaigns::tests::ch_rotation_seed_000083", ch_rotation_seed_000083),
        ("property_campaigns::tests::ch_rotation_seed_000084", ch_rotation_seed_000084),
        ("property_campaigns::tests::ch_rotation_seed_000085", ch_rotation_seed_000085),
        ("property_campaigns::tests::ch_rotation_seed_000086", ch_rotation_seed_000086),
        ("property_campaigns::tests::ch_rotation_seed_000087", ch_rotation_seed_000087),
        ("property_campaigns::tests::ch_rotation_seed_000088", ch_rotation_seed_000088),
        ("property_campaigns::tests::ch_rotation_seed_000089", ch_rotation_seed_000089),
        ("property_campaigns::tests::ch_rotation_seed_000090", ch_rotation_seed_000090),
        ("property_campaigns::tests::ch_rotation_seed_000091", ch_rotation_seed_000091),
        ("property_campaigns::tests::ch_rotation_seed_000092", ch_rotation_seed_000092),
        ("property_campaigns::tests::ch_rotation_seed_000093", ch_rotation_seed_000093),
        ("property_campaigns::tests::ch_rotation_seed_000094", ch_rotation_seed_000094),
        ("property_campaigns::tests::ch_rotation_seed_000095", ch_rotation_seed_000095),
        ("property_campaigns::tests::ch_rotation_seed_000096", ch_rotation_seed_000096),
        ("property_campaigns::tests::ch_rotation_seed_000097", ch_rotation_seed_000097),
        ("property_campaigns::tests::ch_rotation_seed_000098", ch_rotation_seed_000098),
        ("property_campaigns::tests::ch_rotation_seed_000099", ch_rotation_seed_000099),
        ("property_campaigns::tests::ch_rotation_seed_000100", ch_rotation_seed_000100),
        ("property_campaigns::tests::ch_rotation_seed_000101", ch_rotation_seed_000101),
        ("property_campaigns::tests::ch_rotation_seed_000102", ch_rotation_seed_000102),
        ("property_campaigns::tests::ch_rotation_seed_000103", ch_rotation_seed_000103),
        ("property_campaigns::tests::ch_rotation_seed_000104", ch_rotation_seed_000104),
        ("property_campaigns::tests::ch_rotation_seed_000105", ch_rotation_seed_000105),
        ("property_campaigns::tests::ch_rotation_seed_000106", ch_rotation_seed_000106),
        ("property_campaigns::tests::ch_rotation_seed_000107", ch_rotation_seed_000107),
        ("property_campaigns::tests::ch_rotation_seed_000108", ch_rotation_seed_000108),
        ("property_campaigns::tests::ch_rotation_seed_000109", ch_rotation_seed_000109),
        ("property_campaigns::tests::ch_rotation_seed_000110", ch_rotation_seed_000110),
        ("property_campaigns::tests::ch_rotation_seed_000111", ch_rotation_seed_000111),
        ("property_campaigns::tests::ch_rotation_seed_000112", ch_rotation_seed_000112),
        ("property_campaigns::tests::ch_rotation_seed_000113", ch_rotation_seed_000113),
        ("property_campaigns::tests::ch_rotation_seed_000114", ch_rotation_seed_000114),
        ("property_campaigns::tests::ch_rotation_seed_000115", ch_rotation_seed_000115),
        ("property_campaigns::tests::ch_rotation_seed_000116", ch_rotation_seed_000116),
        ("property_campaigns::tests::ch_rotation_seed_000117", ch_rotation_seed_000117),
        ("property_campaigns::tests::ch_rotation_seed_000118", ch_rotation_seed_000118),
        ("property_campaigns::tests::ch_rotation_seed_000119", ch_rotation_seed_000119),
        ("property_campaigns::tests::ch_scale_seed_000000", ch_scale_seed_000000),
        ("property_campaigns::tests::ch_scale_seed_000001", ch_scale_seed_000001),
        ("property_campaigns::tests::ch_scale_seed_000002", ch_scale_seed_000002),
        ("property_campaigns::tests::ch_scale_seed_000003", ch_scale_seed_000003),
        ("property_campaigns::tests::ch_scale_seed_000004", ch_scale_seed_000004),
        ("property_campaigns::tests::ch_scale_seed_000005", ch_scale_seed_000005),
        ("property_campaigns::tests::ch_scale_seed_000006", ch_scale_seed_000006),
        ("property_campaigns::tests::ch_scale_seed_000007", ch_scale_seed_000007),
        ("property_campaigns::tests::ch_scale_seed_000008", ch_scale_seed_000008),
        ("property_campaigns::tests::ch_scale_seed_000009", ch_scale_seed_000009),
        ("property_campaigns::tests::ch_scale_seed_000010", ch_scale_seed_000010),
        ("property_campaigns::tests::ch_scale_seed_000011", ch_scale_seed_000011),
        ("property_campaigns::tests::ch_scale_seed_000012", ch_scale_seed_000012),
        ("property_campaigns::tests::ch_scale_seed_000013", ch_scale_seed_000013),
        ("property_campaigns::tests::ch_scale_seed_000014", ch_scale_seed_000014),
        ("property_campaigns::tests::ch_scale_seed_000015", ch_scale_seed_000015),
        ("property_campaigns::tests::ch_scale_seed_000016", ch_scale_seed_000016),
        ("property_campaigns::tests::ch_scale_seed_000017", ch_scale_seed_000017),
        ("property_campaigns::tests::ch_scale_seed_000018", ch_scale_seed_000018),
        ("property_campaigns::tests::ch_scale_seed_000019", ch_scale_seed_000019),
        ("property_campaigns::tests::ch_scale_seed_000020", ch_scale_seed_000020),
        ("property_campaigns::tests::ch_scale_seed_000021", ch_scale_seed_000021),
        ("property_campaigns::tests::ch_scale_seed_000022", ch_scale_seed_000022),
        ("property_campaigns::tests::ch_scale_seed_000023", ch_scale_seed_000023),
        ("property_campaigns::tests::ch_scale_seed_000024", ch_scale_seed_000024),
        ("property_campaigns::tests::ch_scale_seed_000025", ch_scale_seed_000025),
        ("property_campaigns::tests::ch_scale_seed_000026", ch_scale_seed_000026),
        ("property_campaigns::tests::ch_scale_seed_000027", ch_scale_seed_000027),
        ("property_campaigns::tests::ch_scale_seed_000028", ch_scale_seed_000028),
        ("property_campaigns::tests::ch_scale_seed_000029", ch_scale_seed_000029),
        ("property_campaigns::tests::ch_scale_seed_000030", ch_scale_seed_000030),
        ("property_campaigns::tests::ch_scale_seed_000031", ch_scale_seed_000031),
        ("property_campaigns::tests::ch_scale_seed_000032", ch_scale_seed_000032),
        ("property_campaigns::tests::ch_scale_seed_000033", ch_scale_seed_000033),
        ("property_campaigns::tests::ch_scale_seed_000034", ch_scale_seed_000034),
        ("property_campaigns::tests::ch_scale_seed_000035", ch_scale_seed_000035),
        ("property_campaigns::tests::ch_scale_seed_000036", ch_scale_seed_000036),
        ("property_campaigns::tests::ch_scale_seed_000037", ch_scale_seed_000037),
        ("property_campaigns::tests::ch_scale_seed_000038", ch_scale_seed_000038),
        ("property_campaigns::tests::ch_scale_seed_000039", ch_scale_seed_000039),
        ("property_campaigns::tests::ch_scale_seed_000040", ch_scale_seed_000040),
        ("property_campaigns::tests::ch_scale_seed_000041", ch_scale_seed_000041),
        ("property_campaigns::tests::ch_scale_seed_000042", ch_scale_seed_000042),
        ("property_campaigns::tests::ch_scale_seed_000043", ch_scale_seed_000043),
        ("property_campaigns::tests::ch_scale_seed_000044", ch_scale_seed_000044),
        ("property_campaigns::tests::ch_scale_seed_000045", ch_scale_seed_000045),
        ("property_campaigns::tests::ch_scale_seed_000046", ch_scale_seed_000046),
        ("property_campaigns::tests::ch_scale_seed_000047", ch_scale_seed_000047),
        ("property_campaigns::tests::ch_scale_seed_000048", ch_scale_seed_000048),
        ("property_campaigns::tests::ch_scale_seed_000049", ch_scale_seed_000049),
        ("property_campaigns::tests::ch_scale_seed_000050", ch_scale_seed_000050),
        ("property_campaigns::tests::ch_scale_seed_000051", ch_scale_seed_000051),
        ("property_campaigns::tests::ch_scale_seed_000052", ch_scale_seed_000052),
        ("property_campaigns::tests::ch_scale_seed_000053", ch_scale_seed_000053),
        ("property_campaigns::tests::ch_scale_seed_000054", ch_scale_seed_000054),
        ("property_campaigns::tests::ch_scale_seed_000055", ch_scale_seed_000055),
        ("property_campaigns::tests::ch_scale_seed_000056", ch_scale_seed_000056),
        ("property_campaigns::tests::ch_scale_seed_000057", ch_scale_seed_000057),
        ("property_campaigns::tests::ch_scale_seed_000058", ch_scale_seed_000058),
        ("property_campaigns::tests::ch_scale_seed_000059", ch_scale_seed_000059),
        ("property_campaigns::tests::ch_scale_seed_000060", ch_scale_seed_000060),
        ("property_campaigns::tests::ch_scale_seed_000061", ch_scale_seed_000061),
        ("property_campaigns::tests::ch_scale_seed_000062", ch_scale_seed_000062),
        ("property_campaigns::tests::ch_scale_seed_000063", ch_scale_seed_000063),
        ("property_campaigns::tests::ch_scale_seed_000064", ch_scale_seed_000064),
        ("property_campaigns::tests::ch_scale_seed_000065", ch_scale_seed_000065),
        ("property_campaigns::tests::ch_scale_seed_000066", ch_scale_seed_000066),
        ("property_campaigns::tests::ch_scale_seed_000067", ch_scale_seed_000067),
        ("property_campaigns::tests::ch_scale_seed_000068", ch_scale_seed_000068),
        ("property_campaigns::tests::ch_scale_seed_000069", ch_scale_seed_000069),
        ("property_campaigns::tests::ch_scale_seed_000070", ch_scale_seed_000070),
        ("property_campaigns::tests::ch_scale_seed_000071", ch_scale_seed_000071),
        ("property_campaigns::tests::ch_scale_seed_000072", ch_scale_seed_000072),
        ("property_campaigns::tests::ch_scale_seed_000073", ch_scale_seed_000073),
        ("property_campaigns::tests::ch_scale_seed_000074", ch_scale_seed_000074),
        ("property_campaigns::tests::ch_scale_seed_000075", ch_scale_seed_000075),
        ("property_campaigns::tests::ch_scale_seed_000076", ch_scale_seed_000076),
        ("property_campaigns::tests::ch_scale_seed_000077", ch_scale_seed_000077),
        ("property_campaigns::tests::ch_scale_seed_000078", ch_scale_seed_000078),
        ("property_campaigns::tests::ch_scale_seed_000079", ch_scale_seed_000079),
        ("property_campaigns::tests::ch_scale_seed_000080", ch_scale_seed_000080),
        ("property_campaigns::tests::ch_scale_seed_000081", ch_scale_seed_000081),
        ("property_campaigns::tests::ch_scale_seed_000082", ch_scale_seed_000082),
        ("property_campaigns::tests::ch_scale_seed_000083", ch_scale_seed_000083),
        ("property_campaigns::tests::ch_scale_seed_000084", ch_scale_seed_000084),
        ("property_campaigns::tests::ch_scale_seed_000085", ch_scale_seed_000085),
        ("property_campaigns::tests::ch_scale_seed_000086", ch_scale_seed_000086),
        ("property_campaigns::tests::ch_scale_seed_000087", ch_scale_seed_000087),
        ("property_campaigns::tests::ch_scale_seed_000088", ch_scale_seed_000088),
        ("property_campaigns::tests::ch_scale_seed_000089", ch_scale_seed_000089),
        ("property_campaigns::tests::ch_scale_seed_000090", ch_scale_seed_000090),
        ("property_campaigns::tests::ch_scale_seed_000091", ch_scale_seed_000091),
        ("property_campaigns::tests::ch_scale_seed_000092", ch_scale_seed_000092),
        ("property_campaigns::tests::ch_scale_seed_000093", ch_scale_seed_000093),
        ("property_campaigns::tests::ch_scale_seed_000094", ch_scale_seed_000094),
        ("property_campaigns::tests::ch_scale_seed_000095", ch_scale_seed_000095),
        ("property_campaigns::tests::ch_scale_seed_000096", ch_scale_seed_000096),
        ("property_campaigns::tests::ch_scale_seed_000097", ch_scale_seed_000097),
        ("property_campaigns::tests::ch_scale_seed_000098", ch_scale_seed_000098),
        ("property_campaigns::tests::ch_scale_seed_000099", ch_scale_seed_000099),
        ("property_campaigns::tests::ch_scale_seed_000100", ch_scale_seed_000100),
        ("property_campaigns::tests::ch_scale_seed_000101", ch_scale_seed_000101),
        ("property_campaigns::tests::ch_scale_seed_000102", ch_scale_seed_000102),
        ("property_campaigns::tests::ch_scale_seed_000103", ch_scale_seed_000103),
        ("property_campaigns::tests::ch_scale_seed_000104", ch_scale_seed_000104),
        ("property_campaigns::tests::ch_scale_seed_000105", ch_scale_seed_000105),
        ("property_campaigns::tests::ch_scale_seed_000106", ch_scale_seed_000106),
        ("property_campaigns::tests::ch_scale_seed_000107", ch_scale_seed_000107),
        ("property_campaigns::tests::ch_scale_seed_000108", ch_scale_seed_000108),
        ("property_campaigns::tests::ch_scale_seed_000109", ch_scale_seed_000109),
        ("property_campaigns::tests::ch_scale_seed_000110", ch_scale_seed_000110),
        ("property_campaigns::tests::ch_scale_seed_000111", ch_scale_seed_000111),
        ("property_campaigns::tests::ch_scale_seed_000112", ch_scale_seed_000112),
        ("property_campaigns::tests::ch_scale_seed_000113", ch_scale_seed_000113),
        ("property_campaigns::tests::ch_scale_seed_000114", ch_scale_seed_000114),
        ("property_campaigns::tests::ch_scale_seed_000115", ch_scale_seed_000115),
        ("property_campaigns::tests::ch_scale_seed_000116", ch_scale_seed_000116),
        ("property_campaigns::tests::ch_scale_seed_000117", ch_scale_seed_000117),
        ("property_campaigns::tests::ch_scale_seed_000118", ch_scale_seed_000118),
        ("property_campaigns::tests::ch_scale_seed_000119", ch_scale_seed_000119),
        ("property_campaigns::tests::ch_superset_seed_000000", ch_superset_seed_000000),
        ("property_campaigns::tests::ch_superset_seed_000001", ch_superset_seed_000001),
        ("property_campaigns::tests::ch_superset_seed_000002", ch_superset_seed_000002),
        ("property_campaigns::tests::ch_superset_seed_000003", ch_superset_seed_000003),
        ("property_campaigns::tests::ch_superset_seed_000004", ch_superset_seed_000004),
        ("property_campaigns::tests::ch_superset_seed_000005", ch_superset_seed_000005),
        ("property_campaigns::tests::ch_superset_seed_000006", ch_superset_seed_000006),
        ("property_campaigns::tests::ch_superset_seed_000007", ch_superset_seed_000007),
        ("property_campaigns::tests::ch_superset_seed_000008", ch_superset_seed_000008),
        ("property_campaigns::tests::ch_superset_seed_000009", ch_superset_seed_000009),
        ("property_campaigns::tests::ch_superset_seed_000010", ch_superset_seed_000010),
        ("property_campaigns::tests::ch_superset_seed_000011", ch_superset_seed_000011),
        ("property_campaigns::tests::ch_superset_seed_000012", ch_superset_seed_000012),
        ("property_campaigns::tests::ch_superset_seed_000013", ch_superset_seed_000013),
        ("property_campaigns::tests::ch_superset_seed_000014", ch_superset_seed_000014),
        ("property_campaigns::tests::ch_superset_seed_000015", ch_superset_seed_000015),
        ("property_campaigns::tests::ch_superset_seed_000016", ch_superset_seed_000016),
        ("property_campaigns::tests::ch_superset_seed_000017", ch_superset_seed_000017),
        ("property_campaigns::tests::ch_superset_seed_000018", ch_superset_seed_000018),
        ("property_campaigns::tests::ch_superset_seed_000019", ch_superset_seed_000019),
        ("property_campaigns::tests::ch_superset_seed_000020", ch_superset_seed_000020),
        ("property_campaigns::tests::ch_superset_seed_000021", ch_superset_seed_000021),
        ("property_campaigns::tests::ch_superset_seed_000022", ch_superset_seed_000022),
        ("property_campaigns::tests::ch_superset_seed_000023", ch_superset_seed_000023),
        ("property_campaigns::tests::ch_superset_seed_000024", ch_superset_seed_000024),
        ("property_campaigns::tests::ch_superset_seed_000025", ch_superset_seed_000025),
        ("property_campaigns::tests::ch_superset_seed_000026", ch_superset_seed_000026),
        ("property_campaigns::tests::ch_superset_seed_000027", ch_superset_seed_000027),
        ("property_campaigns::tests::ch_superset_seed_000028", ch_superset_seed_000028),
        ("property_campaigns::tests::ch_superset_seed_000029", ch_superset_seed_000029),
        ("property_campaigns::tests::ch_superset_seed_000030", ch_superset_seed_000030),
        ("property_campaigns::tests::ch_superset_seed_000031", ch_superset_seed_000031),
        ("property_campaigns::tests::ch_superset_seed_000032", ch_superset_seed_000032),
        ("property_campaigns::tests::ch_superset_seed_000033", ch_superset_seed_000033),
        ("property_campaigns::tests::ch_superset_seed_000034", ch_superset_seed_000034),
        ("property_campaigns::tests::ch_superset_seed_000035", ch_superset_seed_000035),
        ("property_campaigns::tests::ch_superset_seed_000036", ch_superset_seed_000036),
        ("property_campaigns::tests::ch_superset_seed_000037", ch_superset_seed_000037),
        ("property_campaigns::tests::ch_superset_seed_000038", ch_superset_seed_000038),
        ("property_campaigns::tests::ch_superset_seed_000039", ch_superset_seed_000039),
        ("property_campaigns::tests::ch_superset_seed_000040", ch_superset_seed_000040),
        ("property_campaigns::tests::ch_superset_seed_000041", ch_superset_seed_000041),
        ("property_campaigns::tests::ch_superset_seed_000042", ch_superset_seed_000042),
        ("property_campaigns::tests::ch_superset_seed_000043", ch_superset_seed_000043),
        ("property_campaigns::tests::ch_superset_seed_000044", ch_superset_seed_000044),
        ("property_campaigns::tests::ch_superset_seed_000045", ch_superset_seed_000045),
        ("property_campaigns::tests::ch_superset_seed_000046", ch_superset_seed_000046),
        ("property_campaigns::tests::ch_superset_seed_000047", ch_superset_seed_000047),
        ("property_campaigns::tests::ch_superset_seed_000048", ch_superset_seed_000048),
        ("property_campaigns::tests::ch_superset_seed_000049", ch_superset_seed_000049),
        ("property_campaigns::tests::ch_superset_seed_000050", ch_superset_seed_000050),
        ("property_campaigns::tests::ch_superset_seed_000051", ch_superset_seed_000051),
        ("property_campaigns::tests::ch_superset_seed_000052", ch_superset_seed_000052),
        ("property_campaigns::tests::ch_superset_seed_000053", ch_superset_seed_000053),
        ("property_campaigns::tests::ch_superset_seed_000054", ch_superset_seed_000054),
        ("property_campaigns::tests::ch_superset_seed_000055", ch_superset_seed_000055),
        ("property_campaigns::tests::ch_superset_seed_000056", ch_superset_seed_000056),
        ("property_campaigns::tests::ch_superset_seed_000057", ch_superset_seed_000057),
        ("property_campaigns::tests::ch_superset_seed_000058", ch_superset_seed_000058),
        ("property_campaigns::tests::ch_superset_seed_000059", ch_superset_seed_000059),
        ("property_campaigns::tests::ch_superset_seed_000060", ch_superset_seed_000060),
        ("property_campaigns::tests::ch_superset_seed_000061", ch_superset_seed_000061),
        ("property_campaigns::tests::ch_superset_seed_000062", ch_superset_seed_000062),
        ("property_campaigns::tests::ch_superset_seed_000063", ch_superset_seed_000063),
        ("property_campaigns::tests::ch_superset_seed_000064", ch_superset_seed_000064),
        ("property_campaigns::tests::ch_superset_seed_000065", ch_superset_seed_000065),
        ("property_campaigns::tests::ch_superset_seed_000066", ch_superset_seed_000066),
        ("property_campaigns::tests::ch_superset_seed_000067", ch_superset_seed_000067),
        ("property_campaigns::tests::ch_superset_seed_000068", ch_superset_seed_000068),
        ("property_campaigns::tests::ch_superset_seed_000069", ch_superset_seed_000069),
        ("property_campaigns::tests::ch_superset_seed_000070", ch_superset_seed_000070),
        ("property_campaigns::tests::ch_superset_seed_000071", ch_superset_seed_000071),
        ("property_campaigns::tests::ch_superset_seed_000072", ch_superset_seed_000072),
        ("property_campaigns::tests::ch_superset_seed_000073", ch_superset_seed_000073),
        ("property_campaigns::tests::ch_superset_seed_000074", ch_superset_seed_000074),
        ("property_campaigns::tests::ch_superset_seed_000075", ch_superset_seed_000075),
        ("property_campaigns::tests::ch_superset_seed_000076", ch_superset_seed_000076),
        ("property_campaigns::tests::ch_superset_seed_000077", ch_superset_seed_000077),
        ("property_campaigns::tests::ch_superset_seed_000078", ch_superset_seed_000078),
        ("property_campaigns::tests::ch_superset_seed_000079", ch_superset_seed_000079),
        ("property_campaigns::tests::ch_superset_seed_000080", ch_superset_seed_000080),
        ("property_campaigns::tests::ch_superset_seed_000081", ch_superset_seed_000081),
        ("property_campaigns::tests::ch_superset_seed_000082", ch_superset_seed_000082),
        ("property_campaigns::tests::ch_superset_seed_000083", ch_superset_seed_000083),
        ("property_campaigns::tests::ch_superset_seed_000084", ch_superset_seed_000084),
        ("property_campaigns::tests::ch_superset_seed_000085", ch_superset_seed_000085),
        ("property_campaigns::tests::ch_superset_seed_000086", ch_superset_seed_000086),
        ("property_campaigns::tests::ch_superset_seed_000087", ch_superset_seed_000087),
        ("property_campaigns::tests::ch_superset_seed_000088", ch_superset_seed_000088),
        ("property_campaigns::tests::ch_superset_seed_000089", ch_superset_seed_000089),
        ("property_campaigns::tests::ch_superset_seed_000090", ch_superset_seed_000090),
        ("property_campaigns::tests::ch_superset_seed_000091", ch_superset_seed_000091),
        ("property_campaigns::tests::ch_superset_seed_000092", ch_superset_seed_000092),
        ("property_campaigns::tests::ch_superset_seed_000093", ch_superset_seed_000093),
        ("property_campaigns::tests::ch_superset_seed_000094", ch_superset_seed_000094),
        ("property_campaigns::tests::ch_superset_seed_000095", ch_superset_seed_000095),
        ("property_campaigns::tests::ch_superset_seed_000096", ch_superset_seed_000096),
        ("property_campaigns::tests::ch_superset_seed_000097", ch_superset_seed_000097),
        ("property_campaigns::tests::ch_superset_seed_000098", ch_superset_seed_000098),
        ("property_campaigns::tests::ch_superset_seed_000099", ch_superset_seed_000099),
        ("property_campaigns::tests::ch_superset_seed_000100", ch_superset_seed_000100),
        ("property_campaigns::tests::ch_superset_seed_000101", ch_superset_seed_000101),
        ("property_campaigns::tests::ch_superset_seed_000102", ch_superset_seed_000102),
        ("property_campaigns::tests::ch_superset_seed_000103", ch_superset_seed_000103),
        ("property_campaigns::tests::ch_superset_seed_000104", ch_superset_seed_000104),
        ("property_campaigns::tests::ch_superset_seed_000105", ch_superset_seed_000105),
        ("property_campaigns::tests::ch_superset_seed_000106", ch_superset_seed_000106),
        ("property_campaigns::tests::ch_superset_seed_000107", ch_superset_seed_000107),
        ("property_campaigns::tests::ch_superset_seed_000108", ch_superset_seed_000108),
        ("property_campaigns::tests::ch_superset_seed_000109", ch_superset_seed_000109),
        ("property_campaigns::tests::ch_superset_seed_000110", ch_superset_seed_000110),
        ("property_campaigns::tests::ch_superset_seed_000111", ch_superset_seed_000111),
        ("property_campaigns::tests::ch_superset_seed_000112", ch_superset_seed_000112),
        ("property_campaigns::tests::ch_superset_seed_000113", ch_superset_seed_000113),
        ("property_campaigns::tests::ch_superset_seed_000114", ch_superset_seed_000114),
        ("property_campaigns::tests::ch_superset_seed_000115", ch_superset_seed_000115),
        ("property_campaigns::tests::ch_superset_seed_000116", ch_superset_seed_000116),
        ("property_campaigns::tests::ch_superset_seed_000117", ch_superset_seed_000117),
        ("property_campaigns::tests::ch_superset_seed_000118", ch_superset_seed_000118),
        ("property_campaigns::tests::ch_superset_seed_000119", ch_superset_seed_000119),
        ("property_campaigns::tests::ch_interior_seed_000000", ch_interior_seed_000000),
        ("property_campaigns::tests::ch_interior_seed_000001", ch_interior_seed_000001),
        ("property_campaigns::tests::ch_interior_seed_000002", ch_interior_seed_000002),
        ("property_campaigns::tests::ch_interior_seed_000003", ch_interior_seed_000003),
        ("property_campaigns::tests::ch_interior_seed_000004", ch_interior_seed_000004),
        ("property_campaigns::tests::ch_interior_seed_000005", ch_interior_seed_000005),
        ("property_campaigns::tests::ch_interior_seed_000006", ch_interior_seed_000006),
        ("property_campaigns::tests::ch_interior_seed_000007", ch_interior_seed_000007),
        ("property_campaigns::tests::ch_interior_seed_000008", ch_interior_seed_000008),
        ("property_campaigns::tests::ch_interior_seed_000009", ch_interior_seed_000009),
        ("property_campaigns::tests::ch_interior_seed_000010", ch_interior_seed_000010),
        ("property_campaigns::tests::ch_interior_seed_000011", ch_interior_seed_000011),
        ("property_campaigns::tests::ch_interior_seed_000012", ch_interior_seed_000012),
        ("property_campaigns::tests::ch_interior_seed_000013", ch_interior_seed_000013),
        ("property_campaigns::tests::ch_interior_seed_000014", ch_interior_seed_000014),
        ("property_campaigns::tests::ch_interior_seed_000015", ch_interior_seed_000015),
        ("property_campaigns::tests::ch_interior_seed_000016", ch_interior_seed_000016),
        ("property_campaigns::tests::ch_interior_seed_000017", ch_interior_seed_000017),
        ("property_campaigns::tests::ch_interior_seed_000018", ch_interior_seed_000018),
        ("property_campaigns::tests::ch_interior_seed_000019", ch_interior_seed_000019),
        ("property_campaigns::tests::ch_interior_seed_000020", ch_interior_seed_000020),
        ("property_campaigns::tests::ch_interior_seed_000021", ch_interior_seed_000021),
        ("property_campaigns::tests::ch_interior_seed_000022", ch_interior_seed_000022),
        ("property_campaigns::tests::ch_interior_seed_000023", ch_interior_seed_000023),
        ("property_campaigns::tests::ch_interior_seed_000024", ch_interior_seed_000024),
        ("property_campaigns::tests::ch_interior_seed_000025", ch_interior_seed_000025),
        ("property_campaigns::tests::ch_interior_seed_000026", ch_interior_seed_000026),
        ("property_campaigns::tests::ch_interior_seed_000027", ch_interior_seed_000027),
        ("property_campaigns::tests::ch_interior_seed_000028", ch_interior_seed_000028),
        ("property_campaigns::tests::ch_interior_seed_000029", ch_interior_seed_000029),
        ("property_campaigns::tests::ch_interior_seed_000030", ch_interior_seed_000030),
        ("property_campaigns::tests::ch_interior_seed_000031", ch_interior_seed_000031),
        ("property_campaigns::tests::ch_interior_seed_000032", ch_interior_seed_000032),
        ("property_campaigns::tests::ch_interior_seed_000033", ch_interior_seed_000033),
        ("property_campaigns::tests::ch_interior_seed_000034", ch_interior_seed_000034),
        ("property_campaigns::tests::ch_interior_seed_000035", ch_interior_seed_000035),
        ("property_campaigns::tests::ch_interior_seed_000036", ch_interior_seed_000036),
        ("property_campaigns::tests::ch_interior_seed_000037", ch_interior_seed_000037),
        ("property_campaigns::tests::ch_interior_seed_000038", ch_interior_seed_000038),
        ("property_campaigns::tests::ch_interior_seed_000039", ch_interior_seed_000039),
        ("property_campaigns::tests::ch_interior_seed_000040", ch_interior_seed_000040),
        ("property_campaigns::tests::ch_interior_seed_000041", ch_interior_seed_000041),
        ("property_campaigns::tests::ch_interior_seed_000042", ch_interior_seed_000042),
        ("property_campaigns::tests::ch_interior_seed_000043", ch_interior_seed_000043),
        ("property_campaigns::tests::ch_interior_seed_000044", ch_interior_seed_000044),
        ("property_campaigns::tests::ch_interior_seed_000045", ch_interior_seed_000045),
        ("property_campaigns::tests::ch_interior_seed_000046", ch_interior_seed_000046),
        ("property_campaigns::tests::ch_interior_seed_000047", ch_interior_seed_000047),
        ("property_campaigns::tests::ch_interior_seed_000048", ch_interior_seed_000048),
        ("property_campaigns::tests::ch_interior_seed_000049", ch_interior_seed_000049),
        ("property_campaigns::tests::ch_interior_seed_000050", ch_interior_seed_000050),
        ("property_campaigns::tests::ch_interior_seed_000051", ch_interior_seed_000051),
        ("property_campaigns::tests::ch_interior_seed_000052", ch_interior_seed_000052),
        ("property_campaigns::tests::ch_interior_seed_000053", ch_interior_seed_000053),
        ("property_campaigns::tests::ch_interior_seed_000054", ch_interior_seed_000054),
        ("property_campaigns::tests::ch_interior_seed_000055", ch_interior_seed_000055),
        ("property_campaigns::tests::ch_interior_seed_000056", ch_interior_seed_000056),
        ("property_campaigns::tests::ch_interior_seed_000057", ch_interior_seed_000057),
        ("property_campaigns::tests::ch_interior_seed_000058", ch_interior_seed_000058),
        ("property_campaigns::tests::ch_interior_seed_000059", ch_interior_seed_000059),
        ("property_campaigns::tests::ch_interior_seed_000060", ch_interior_seed_000060),
        ("property_campaigns::tests::ch_interior_seed_000061", ch_interior_seed_000061),
        ("property_campaigns::tests::ch_interior_seed_000062", ch_interior_seed_000062),
        ("property_campaigns::tests::ch_interior_seed_000063", ch_interior_seed_000063),
        ("property_campaigns::tests::ch_interior_seed_000064", ch_interior_seed_000064),
        ("property_campaigns::tests::ch_interior_seed_000065", ch_interior_seed_000065),
        ("property_campaigns::tests::ch_interior_seed_000066", ch_interior_seed_000066),
        ("property_campaigns::tests::ch_interior_seed_000067", ch_interior_seed_000067),
        ("property_campaigns::tests::ch_interior_seed_000068", ch_interior_seed_000068),
        ("property_campaigns::tests::ch_interior_seed_000069", ch_interior_seed_000069),
        ("property_campaigns::tests::ch_interior_seed_000070", ch_interior_seed_000070),
        ("property_campaigns::tests::ch_interior_seed_000071", ch_interior_seed_000071),
        ("property_campaigns::tests::ch_interior_seed_000072", ch_interior_seed_000072),
        ("property_campaigns::tests::ch_interior_seed_000073", ch_interior_seed_000073),
        ("property_campaigns::tests::ch_interior_seed_000074", ch_interior_seed_000074),
        ("property_campaigns::tests::ch_interior_seed_000075", ch_interior_seed_000075),
        ("property_campaigns::tests::ch_interior_seed_000076", ch_interior_seed_000076),
        ("property_campaigns::tests::ch_interior_seed_000077", ch_interior_seed_000077),
        ("property_campaigns::tests::ch_interior_seed_000078", ch_interior_seed_000078),
        ("property_campaigns::tests::ch_interior_seed_000079", ch_interior_seed_000079),
        ("property_campaigns::tests::ch_interior_seed_000080", ch_interior_seed_000080),
        ("property_campaigns::tests::ch_interior_seed_000081", ch_interior_seed_000081),
        ("property_campaigns::tests::ch_interior_seed_000082", ch_interior_seed_000082),
        ("property_campaigns::tests::ch_interior_seed_000083", ch_interior_seed_000083),
        ("property_campaigns::tests::ch_interior_seed_000084", ch_interior_seed_000084),
        ("property_campaigns::tests::ch_interior_seed_000085", ch_interior_seed_000085),
        ("property_campaigns::tests::ch_interior_seed_000086", ch_interior_seed_000086),
        ("property_campaigns::tests::ch_interior_seed_000087", ch_interior_seed_000087),
        ("property_campaigns::tests::ch_interior_seed_000088", ch_interior_seed_000088),
        ("property_campaigns::tests::ch_interior_seed_000089", ch_interior_seed_000089),
        ("property_campaigns::tests::ch_interior_seed_000090", ch_interior_seed_000090),
        ("property_campaigns::tests::ch_interior_seed_000091", ch_interior_seed_000091),
        ("property_campaigns::tests::ch_interior_seed_000092", ch_interior_seed_000092),
        ("property_campaigns::tests::ch_interior_seed_000093", ch_interior_seed_000093),
        ("property_campaigns::tests::ch_interior_seed_000094", ch_interior_seed_000094),
        ("property_campaigns::tests::ch_interior_seed_000095", ch_interior_seed_000095),
        ("property_campaigns::tests::ch_interior_seed_000096", ch_interior_seed_000096),
        ("property_campaigns::tests::ch_interior_seed_000097", ch_interior_seed_000097),
        ("property_campaigns::tests::ch_interior_seed_000098", ch_interior_seed_000098),
        ("property_campaigns::tests::ch_interior_seed_000099", ch_interior_seed_000099),
        ("property_campaigns::tests::ch_interior_seed_000100", ch_interior_seed_000100),
        ("property_campaigns::tests::ch_interior_seed_000101", ch_interior_seed_000101),
        ("property_campaigns::tests::ch_interior_seed_000102", ch_interior_seed_000102),
        ("property_campaigns::tests::ch_interior_seed_000103", ch_interior_seed_000103),
        ("property_campaigns::tests::ch_interior_seed_000104", ch_interior_seed_000104),
        ("property_campaigns::tests::ch_interior_seed_000105", ch_interior_seed_000105),
        ("property_campaigns::tests::ch_interior_seed_000106", ch_interior_seed_000106),
        ("property_campaigns::tests::ch_interior_seed_000107", ch_interior_seed_000107),
        ("property_campaigns::tests::ch_interior_seed_000108", ch_interior_seed_000108),
        ("property_campaigns::tests::ch_interior_seed_000109", ch_interior_seed_000109),
        ("property_campaigns::tests::ch_interior_seed_000110", ch_interior_seed_000110),
        ("property_campaigns::tests::ch_interior_seed_000111", ch_interior_seed_000111),
        ("property_campaigns::tests::ch_interior_seed_000112", ch_interior_seed_000112),
        ("property_campaigns::tests::ch_interior_seed_000113", ch_interior_seed_000113),
        ("property_campaigns::tests::ch_interior_seed_000114", ch_interior_seed_000114),
        ("property_campaigns::tests::ch_interior_seed_000115", ch_interior_seed_000115),
        ("property_campaigns::tests::ch_interior_seed_000116", ch_interior_seed_000116),
        ("property_campaigns::tests::ch_interior_seed_000117", ch_interior_seed_000117),
        ("property_campaigns::tests::ch_interior_seed_000118", ch_interior_seed_000118),
        ("property_campaigns::tests::ch_interior_seed_000119", ch_interior_seed_000119),
        ("property_campaigns::tests::cc_dihedral_seed_000000", cc_dihedral_seed_000000),
        ("property_campaigns::tests::cc_dihedral_seed_000001", cc_dihedral_seed_000001),
        ("property_campaigns::tests::cc_dihedral_seed_000002", cc_dihedral_seed_000002),
        ("property_campaigns::tests::cc_dihedral_seed_000003", cc_dihedral_seed_000003),
        ("property_campaigns::tests::cc_dihedral_seed_000004", cc_dihedral_seed_000004),
        ("property_campaigns::tests::cc_dihedral_seed_000005", cc_dihedral_seed_000005),
        ("property_campaigns::tests::cc_dihedral_seed_000006", cc_dihedral_seed_000006),
        ("property_campaigns::tests::cc_dihedral_seed_000007", cc_dihedral_seed_000007),
        ("property_campaigns::tests::cc_dihedral_seed_000008", cc_dihedral_seed_000008),
        ("property_campaigns::tests::cc_dihedral_seed_000009", cc_dihedral_seed_000009),
        ("property_campaigns::tests::cc_dihedral_seed_000010", cc_dihedral_seed_000010),
        ("property_campaigns::tests::cc_dihedral_seed_000011", cc_dihedral_seed_000011),
        ("property_campaigns::tests::cc_dihedral_seed_000012", cc_dihedral_seed_000012),
        ("property_campaigns::tests::cc_dihedral_seed_000013", cc_dihedral_seed_000013),
        ("property_campaigns::tests::cc_dihedral_seed_000014", cc_dihedral_seed_000014),
        ("property_campaigns::tests::cc_dihedral_seed_000015", cc_dihedral_seed_000015),
        ("property_campaigns::tests::cc_dihedral_seed_000016", cc_dihedral_seed_000016),
        ("property_campaigns::tests::cc_dihedral_seed_000017", cc_dihedral_seed_000017),
        ("property_campaigns::tests::cc_dihedral_seed_000018", cc_dihedral_seed_000018),
        ("property_campaigns::tests::cc_dihedral_seed_000019", cc_dihedral_seed_000019),
        ("property_campaigns::tests::cc_dihedral_seed_000020", cc_dihedral_seed_000020),
        ("property_campaigns::tests::cc_dihedral_seed_000021", cc_dihedral_seed_000021),
        ("property_campaigns::tests::cc_dihedral_seed_000022", cc_dihedral_seed_000022),
        ("property_campaigns::tests::cc_dihedral_seed_000023", cc_dihedral_seed_000023),
        ("property_campaigns::tests::cc_dihedral_seed_000024", cc_dihedral_seed_000024),
        ("property_campaigns::tests::cc_dihedral_seed_000025", cc_dihedral_seed_000025),
        ("property_campaigns::tests::cc_dihedral_seed_000026", cc_dihedral_seed_000026),
        ("property_campaigns::tests::cc_dihedral_seed_000027", cc_dihedral_seed_000027),
        ("property_campaigns::tests::cc_dihedral_seed_000028", cc_dihedral_seed_000028),
        ("property_campaigns::tests::cc_dihedral_seed_000029", cc_dihedral_seed_000029),
        ("property_campaigns::tests::cc_dihedral_seed_000030", cc_dihedral_seed_000030),
        ("property_campaigns::tests::cc_dihedral_seed_000031", cc_dihedral_seed_000031),
        ("property_campaigns::tests::cc_dihedral_seed_000032", cc_dihedral_seed_000032),
        ("property_campaigns::tests::cc_dihedral_seed_000033", cc_dihedral_seed_000033),
        ("property_campaigns::tests::cc_dihedral_seed_000034", cc_dihedral_seed_000034),
        ("property_campaigns::tests::cc_dihedral_seed_000035", cc_dihedral_seed_000035),
        ("property_campaigns::tests::cc_dihedral_seed_000036", cc_dihedral_seed_000036),
        ("property_campaigns::tests::cc_dihedral_seed_000037", cc_dihedral_seed_000037),
        ("property_campaigns::tests::cc_dihedral_seed_000038", cc_dihedral_seed_000038),
        ("property_campaigns::tests::cc_dihedral_seed_000039", cc_dihedral_seed_000039),
        ("property_campaigns::tests::cc_dihedral_seed_000040", cc_dihedral_seed_000040),
        ("property_campaigns::tests::cc_dihedral_seed_000041", cc_dihedral_seed_000041),
        ("property_campaigns::tests::cc_dihedral_seed_000042", cc_dihedral_seed_000042),
        ("property_campaigns::tests::cc_dihedral_seed_000043", cc_dihedral_seed_000043),
        ("property_campaigns::tests::cc_dihedral_seed_000044", cc_dihedral_seed_000044),
        ("property_campaigns::tests::cc_dihedral_seed_000045", cc_dihedral_seed_000045),
        ("property_campaigns::tests::cc_dihedral_seed_000046", cc_dihedral_seed_000046),
        ("property_campaigns::tests::cc_dihedral_seed_000047", cc_dihedral_seed_000047),
        ("property_campaigns::tests::cc_dihedral_seed_000048", cc_dihedral_seed_000048),
        ("property_campaigns::tests::cc_dihedral_seed_000049", cc_dihedral_seed_000049),
        ("property_campaigns::tests::cc_dihedral_seed_000050", cc_dihedral_seed_000050),
        ("property_campaigns::tests::cc_dihedral_seed_000051", cc_dihedral_seed_000051),
        ("property_campaigns::tests::cc_dihedral_seed_000052", cc_dihedral_seed_000052),
        ("property_campaigns::tests::cc_dihedral_seed_000053", cc_dihedral_seed_000053),
        ("property_campaigns::tests::cc_dihedral_seed_000054", cc_dihedral_seed_000054),
        ("property_campaigns::tests::cc_dihedral_seed_000055", cc_dihedral_seed_000055),
        ("property_campaigns::tests::cc_dihedral_seed_000056", cc_dihedral_seed_000056),
        ("property_campaigns::tests::cc_dihedral_seed_000057", cc_dihedral_seed_000057),
        ("property_campaigns::tests::cc_dihedral_seed_000058", cc_dihedral_seed_000058),
        ("property_campaigns::tests::cc_dihedral_seed_000059", cc_dihedral_seed_000059),
        ("property_campaigns::tests::cc_dihedral_seed_000060", cc_dihedral_seed_000060),
        ("property_campaigns::tests::cc_dihedral_seed_000061", cc_dihedral_seed_000061),
        ("property_campaigns::tests::cc_dihedral_seed_000062", cc_dihedral_seed_000062),
        ("property_campaigns::tests::cc_dihedral_seed_000063", cc_dihedral_seed_000063),
        ("property_campaigns::tests::cc_dihedral_seed_000064", cc_dihedral_seed_000064),
        ("property_campaigns::tests::cc_dihedral_seed_000065", cc_dihedral_seed_000065),
        ("property_campaigns::tests::cc_dihedral_seed_000066", cc_dihedral_seed_000066),
        ("property_campaigns::tests::cc_dihedral_seed_000067", cc_dihedral_seed_000067),
        ("property_campaigns::tests::cc_dihedral_seed_000068", cc_dihedral_seed_000068),
        ("property_campaigns::tests::cc_dihedral_seed_000069", cc_dihedral_seed_000069),
        ("property_campaigns::tests::cc_dihedral_seed_000070", cc_dihedral_seed_000070),
        ("property_campaigns::tests::cc_dihedral_seed_000071", cc_dihedral_seed_000071),
        ("property_campaigns::tests::cc_dihedral_seed_000072", cc_dihedral_seed_000072),
        ("property_campaigns::tests::cc_dihedral_seed_000073", cc_dihedral_seed_000073),
        ("property_campaigns::tests::cc_dihedral_seed_000074", cc_dihedral_seed_000074),
        ("property_campaigns::tests::cc_dihedral_seed_000075", cc_dihedral_seed_000075),
        ("property_campaigns::tests::cc_dihedral_seed_000076", cc_dihedral_seed_000076),
        ("property_campaigns::tests::cc_dihedral_seed_000077", cc_dihedral_seed_000077),
        ("property_campaigns::tests::cc_dihedral_seed_000078", cc_dihedral_seed_000078),
        ("property_campaigns::tests::cc_dihedral_seed_000079", cc_dihedral_seed_000079),
        ("property_campaigns::tests::cc_dihedral_seed_000080", cc_dihedral_seed_000080),
        ("property_campaigns::tests::cc_dihedral_seed_000081", cc_dihedral_seed_000081),
        ("property_campaigns::tests::cc_dihedral_seed_000082", cc_dihedral_seed_000082),
        ("property_campaigns::tests::cc_dihedral_seed_000083", cc_dihedral_seed_000083),
        ("property_campaigns::tests::cc_dihedral_seed_000084", cc_dihedral_seed_000084),
        ("property_campaigns::tests::cc_dihedral_seed_000085", cc_dihedral_seed_000085),
        ("property_campaigns::tests::cc_dihedral_seed_000086", cc_dihedral_seed_000086),
        ("property_campaigns::tests::cc_dihedral_seed_000087", cc_dihedral_seed_000087),
        ("property_campaigns::tests::cc_dihedral_seed_000088", cc_dihedral_seed_000088),
        ("property_campaigns::tests::cc_dihedral_seed_000089", cc_dihedral_seed_000089),
        ("property_campaigns::tests::cc_dihedral_seed_000090", cc_dihedral_seed_000090),
        ("property_campaigns::tests::cc_dihedral_seed_000091", cc_dihedral_seed_000091),
        ("property_campaigns::tests::cc_dihedral_seed_000092", cc_dihedral_seed_000092),
        ("property_campaigns::tests::cc_dihedral_seed_000093", cc_dihedral_seed_000093),
        ("property_campaigns::tests::cc_dihedral_seed_000094", cc_dihedral_seed_000094),
        ("property_campaigns::tests::cc_dihedral_seed_000095", cc_dihedral_seed_000095),
        ("property_campaigns::tests::cc_dihedral_seed_000096", cc_dihedral_seed_000096),
        ("property_campaigns::tests::cc_dihedral_seed_000097", cc_dihedral_seed_000097),
        ("property_campaigns::tests::cc_dihedral_seed_000098", cc_dihedral_seed_000098),
        ("property_campaigns::tests::cc_dihedral_seed_000099", cc_dihedral_seed_000099),
        ("property_campaigns::tests::cc_union_monotone_seed_000000", cc_union_monotone_seed_000000),
        ("property_campaigns::tests::cc_union_monotone_seed_000001", cc_union_monotone_seed_000001),
        ("property_campaigns::tests::cc_union_monotone_seed_000002", cc_union_monotone_seed_000002),
        ("property_campaigns::tests::cc_union_monotone_seed_000003", cc_union_monotone_seed_000003),
        ("property_campaigns::tests::cc_union_monotone_seed_000004", cc_union_monotone_seed_000004),
        ("property_campaigns::tests::cc_union_monotone_seed_000005", cc_union_monotone_seed_000005),
        ("property_campaigns::tests::cc_union_monotone_seed_000006", cc_union_monotone_seed_000006),
        ("property_campaigns::tests::cc_union_monotone_seed_000007", cc_union_monotone_seed_000007),
        ("property_campaigns::tests::cc_union_monotone_seed_000008", cc_union_monotone_seed_000008),
        ("property_campaigns::tests::cc_union_monotone_seed_000009", cc_union_monotone_seed_000009),
        ("property_campaigns::tests::cc_union_monotone_seed_000010", cc_union_monotone_seed_000010),
        ("property_campaigns::tests::cc_union_monotone_seed_000011", cc_union_monotone_seed_000011),
        ("property_campaigns::tests::cc_union_monotone_seed_000012", cc_union_monotone_seed_000012),
        ("property_campaigns::tests::cc_union_monotone_seed_000013", cc_union_monotone_seed_000013),
        ("property_campaigns::tests::cc_union_monotone_seed_000014", cc_union_monotone_seed_000014),
        ("property_campaigns::tests::cc_union_monotone_seed_000015", cc_union_monotone_seed_000015),
        ("property_campaigns::tests::cc_union_monotone_seed_000016", cc_union_monotone_seed_000016),
        ("property_campaigns::tests::cc_union_monotone_seed_000017", cc_union_monotone_seed_000017),
        ("property_campaigns::tests::cc_union_monotone_seed_000018", cc_union_monotone_seed_000018),
        ("property_campaigns::tests::cc_union_monotone_seed_000019", cc_union_monotone_seed_000019),
        ("property_campaigns::tests::cc_union_monotone_seed_000020", cc_union_monotone_seed_000020),
        ("property_campaigns::tests::cc_union_monotone_seed_000021", cc_union_monotone_seed_000021),
        ("property_campaigns::tests::cc_union_monotone_seed_000022", cc_union_monotone_seed_000022),
        ("property_campaigns::tests::cc_union_monotone_seed_000023", cc_union_monotone_seed_000023),
        ("property_campaigns::tests::cc_union_monotone_seed_000024", cc_union_monotone_seed_000024),
        ("property_campaigns::tests::cc_union_monotone_seed_000025", cc_union_monotone_seed_000025),
        ("property_campaigns::tests::cc_union_monotone_seed_000026", cc_union_monotone_seed_000026),
        ("property_campaigns::tests::cc_union_monotone_seed_000027", cc_union_monotone_seed_000027),
        ("property_campaigns::tests::cc_union_monotone_seed_000028", cc_union_monotone_seed_000028),
        ("property_campaigns::tests::cc_union_monotone_seed_000029", cc_union_monotone_seed_000029),
        ("property_campaigns::tests::cc_union_monotone_seed_000030", cc_union_monotone_seed_000030),
        ("property_campaigns::tests::cc_union_monotone_seed_000031", cc_union_monotone_seed_000031),
        ("property_campaigns::tests::cc_union_monotone_seed_000032", cc_union_monotone_seed_000032),
        ("property_campaigns::tests::cc_union_monotone_seed_000033", cc_union_monotone_seed_000033),
        ("property_campaigns::tests::cc_union_monotone_seed_000034", cc_union_monotone_seed_000034),
        ("property_campaigns::tests::cc_union_monotone_seed_000035", cc_union_monotone_seed_000035),
        ("property_campaigns::tests::cc_union_monotone_seed_000036", cc_union_monotone_seed_000036),
        ("property_campaigns::tests::cc_union_monotone_seed_000037", cc_union_monotone_seed_000037),
        ("property_campaigns::tests::cc_union_monotone_seed_000038", cc_union_monotone_seed_000038),
        ("property_campaigns::tests::cc_union_monotone_seed_000039", cc_union_monotone_seed_000039),
        ("property_campaigns::tests::cc_union_monotone_seed_000040", cc_union_monotone_seed_000040),
        ("property_campaigns::tests::cc_union_monotone_seed_000041", cc_union_monotone_seed_000041),
        ("property_campaigns::tests::cc_union_monotone_seed_000042", cc_union_monotone_seed_000042),
        ("property_campaigns::tests::cc_union_monotone_seed_000043", cc_union_monotone_seed_000043),
        ("property_campaigns::tests::cc_union_monotone_seed_000044", cc_union_monotone_seed_000044),
        ("property_campaigns::tests::cc_union_monotone_seed_000045", cc_union_monotone_seed_000045),
        ("property_campaigns::tests::cc_union_monotone_seed_000046", cc_union_monotone_seed_000046),
        ("property_campaigns::tests::cc_union_monotone_seed_000047", cc_union_monotone_seed_000047),
        ("property_campaigns::tests::cc_union_monotone_seed_000048", cc_union_monotone_seed_000048),
        ("property_campaigns::tests::cc_union_monotone_seed_000049", cc_union_monotone_seed_000049),
        ("property_campaigns::tests::cc_union_monotone_seed_000050", cc_union_monotone_seed_000050),
        ("property_campaigns::tests::cc_union_monotone_seed_000051", cc_union_monotone_seed_000051),
        ("property_campaigns::tests::cc_union_monotone_seed_000052", cc_union_monotone_seed_000052),
        ("property_campaigns::tests::cc_union_monotone_seed_000053", cc_union_monotone_seed_000053),
        ("property_campaigns::tests::cc_union_monotone_seed_000054", cc_union_monotone_seed_000054),
        ("property_campaigns::tests::cc_union_monotone_seed_000055", cc_union_monotone_seed_000055),
        ("property_campaigns::tests::cc_union_monotone_seed_000056", cc_union_monotone_seed_000056),
        ("property_campaigns::tests::cc_union_monotone_seed_000057", cc_union_monotone_seed_000057),
        ("property_campaigns::tests::cc_union_monotone_seed_000058", cc_union_monotone_seed_000058),
        ("property_campaigns::tests::cc_union_monotone_seed_000059", cc_union_monotone_seed_000059),
        ("property_campaigns::tests::cc_union_monotone_seed_000060", cc_union_monotone_seed_000060),
        ("property_campaigns::tests::cc_union_monotone_seed_000061", cc_union_monotone_seed_000061),
        ("property_campaigns::tests::cc_union_monotone_seed_000062", cc_union_monotone_seed_000062),
        ("property_campaigns::tests::cc_union_monotone_seed_000063", cc_union_monotone_seed_000063),
        ("property_campaigns::tests::cc_union_monotone_seed_000064", cc_union_monotone_seed_000064),
        ("property_campaigns::tests::cc_union_monotone_seed_000065", cc_union_monotone_seed_000065),
        ("property_campaigns::tests::cc_union_monotone_seed_000066", cc_union_monotone_seed_000066),
        ("property_campaigns::tests::cc_union_monotone_seed_000067", cc_union_monotone_seed_000067),
        ("property_campaigns::tests::cc_union_monotone_seed_000068", cc_union_monotone_seed_000068),
        ("property_campaigns::tests::cc_union_monotone_seed_000069", cc_union_monotone_seed_000069),
        ("property_campaigns::tests::cc_union_monotone_seed_000070", cc_union_monotone_seed_000070),
        ("property_campaigns::tests::cc_union_monotone_seed_000071", cc_union_monotone_seed_000071),
        ("property_campaigns::tests::cc_union_monotone_seed_000072", cc_union_monotone_seed_000072),
        ("property_campaigns::tests::cc_union_monotone_seed_000073", cc_union_monotone_seed_000073),
        ("property_campaigns::tests::cc_union_monotone_seed_000074", cc_union_monotone_seed_000074),
        ("property_campaigns::tests::cc_union_monotone_seed_000075", cc_union_monotone_seed_000075),
        ("property_campaigns::tests::cc_union_monotone_seed_000076", cc_union_monotone_seed_000076),
        ("property_campaigns::tests::cc_union_monotone_seed_000077", cc_union_monotone_seed_000077),
        ("property_campaigns::tests::cc_union_monotone_seed_000078", cc_union_monotone_seed_000078),
        ("property_campaigns::tests::cc_union_monotone_seed_000079", cc_union_monotone_seed_000079),
        ("property_campaigns::tests::cc_union_monotone_seed_000080", cc_union_monotone_seed_000080),
        ("property_campaigns::tests::cc_union_monotone_seed_000081", cc_union_monotone_seed_000081),
        ("property_campaigns::tests::cc_union_monotone_seed_000082", cc_union_monotone_seed_000082),
        ("property_campaigns::tests::cc_union_monotone_seed_000083", cc_union_monotone_seed_000083),
        ("property_campaigns::tests::cc_union_monotone_seed_000084", cc_union_monotone_seed_000084),
        ("property_campaigns::tests::cc_union_monotone_seed_000085", cc_union_monotone_seed_000085),
        ("property_campaigns::tests::cc_union_monotone_seed_000086", cc_union_monotone_seed_000086),
        ("property_campaigns::tests::cc_union_monotone_seed_000087", cc_union_monotone_seed_000087),
        ("property_campaigns::tests::cc_union_monotone_seed_000088", cc_union_monotone_seed_000088),
        ("property_campaigns::tests::cc_union_monotone_seed_000089", cc_union_monotone_seed_000089),
        ("property_campaigns::tests::cc_union_monotone_seed_000090", cc_union_monotone_seed_000090),
        ("property_campaigns::tests::cc_union_monotone_seed_000091", cc_union_monotone_seed_000091),
        ("property_campaigns::tests::cc_union_monotone_seed_000092", cc_union_monotone_seed_000092),
        ("property_campaigns::tests::cc_union_monotone_seed_000093", cc_union_monotone_seed_000093),
        ("property_campaigns::tests::cc_union_monotone_seed_000094", cc_union_monotone_seed_000094),
        ("property_campaigns::tests::cc_union_monotone_seed_000095", cc_union_monotone_seed_000095),
        ("property_campaigns::tests::cc_union_monotone_seed_000096", cc_union_monotone_seed_000096),
        ("property_campaigns::tests::cc_union_monotone_seed_000097", cc_union_monotone_seed_000097),
        ("property_campaigns::tests::cc_union_monotone_seed_000098", cc_union_monotone_seed_000098),
        ("property_campaigns::tests::cc_union_monotone_seed_000099", cc_union_monotone_seed_000099),
        ("property_campaigns::tests::cc_padding_seed_000000", cc_padding_seed_000000),
        ("property_campaigns::tests::cc_padding_seed_000001", cc_padding_seed_000001),
        ("property_campaigns::tests::cc_padding_seed_000002", cc_padding_seed_000002),
        ("property_campaigns::tests::cc_padding_seed_000003", cc_padding_seed_000003),
        ("property_campaigns::tests::cc_padding_seed_000004", cc_padding_seed_000004),
        ("property_campaigns::tests::cc_padding_seed_000005", cc_padding_seed_000005),
        ("property_campaigns::tests::cc_padding_seed_000006", cc_padding_seed_000006),
        ("property_campaigns::tests::cc_padding_seed_000007", cc_padding_seed_000007),
        ("property_campaigns::tests::cc_padding_seed_000008", cc_padding_seed_000008),
        ("property_campaigns::tests::cc_padding_seed_000009", cc_padding_seed_000009),
        ("property_campaigns::tests::cc_padding_seed_000010", cc_padding_seed_000010),
        ("property_campaigns::tests::cc_padding_seed_000011", cc_padding_seed_000011),
        ("property_campaigns::tests::cc_padding_seed_000012", cc_padding_seed_000012),
        ("property_campaigns::tests::cc_padding_seed_000013", cc_padding_seed_000013),
        ("property_campaigns::tests::cc_padding_seed_000014", cc_padding_seed_000014),
        ("property_campaigns::tests::cc_padding_seed_000015", cc_padding_seed_000015),
        ("property_campaigns::tests::cc_padding_seed_000016", cc_padding_seed_000016),
        ("property_campaigns::tests::cc_padding_seed_000017", cc_padding_seed_000017),
        ("property_campaigns::tests::cc_padding_seed_000018", cc_padding_seed_000018),
        ("property_campaigns::tests::cc_padding_seed_000019", cc_padding_seed_000019),
        ("property_campaigns::tests::cc_padding_seed_000020", cc_padding_seed_000020),
        ("property_campaigns::tests::cc_padding_seed_000021", cc_padding_seed_000021),
        ("property_campaigns::tests::cc_padding_seed_000022", cc_padding_seed_000022),
        ("property_campaigns::tests::cc_padding_seed_000023", cc_padding_seed_000023),
        ("property_campaigns::tests::cc_padding_seed_000024", cc_padding_seed_000024),
        ("property_campaigns::tests::cc_padding_seed_000025", cc_padding_seed_000025),
        ("property_campaigns::tests::cc_padding_seed_000026", cc_padding_seed_000026),
        ("property_campaigns::tests::cc_padding_seed_000027", cc_padding_seed_000027),
        ("property_campaigns::tests::cc_padding_seed_000028", cc_padding_seed_000028),
        ("property_campaigns::tests::cc_padding_seed_000029", cc_padding_seed_000029),
        ("property_campaigns::tests::cc_padding_seed_000030", cc_padding_seed_000030),
        ("property_campaigns::tests::cc_padding_seed_000031", cc_padding_seed_000031),
        ("property_campaigns::tests::cc_padding_seed_000032", cc_padding_seed_000032),
        ("property_campaigns::tests::cc_padding_seed_000033", cc_padding_seed_000033),
        ("property_campaigns::tests::cc_padding_seed_000034", cc_padding_seed_000034),
        ("property_campaigns::tests::cc_padding_seed_000035", cc_padding_seed_000035),
        ("property_campaigns::tests::cc_padding_seed_000036", cc_padding_seed_000036),
        ("property_campaigns::tests::cc_padding_seed_000037", cc_padding_seed_000037),
        ("property_campaigns::tests::cc_padding_seed_000038", cc_padding_seed_000038),
        ("property_campaigns::tests::cc_padding_seed_000039", cc_padding_seed_000039),
        ("property_campaigns::tests::cc_padding_seed_000040", cc_padding_seed_000040),
        ("property_campaigns::tests::cc_padding_seed_000041", cc_padding_seed_000041),
        ("property_campaigns::tests::cc_padding_seed_000042", cc_padding_seed_000042),
        ("property_campaigns::tests::cc_padding_seed_000043", cc_padding_seed_000043),
        ("property_campaigns::tests::cc_padding_seed_000044", cc_padding_seed_000044),
        ("property_campaigns::tests::cc_padding_seed_000045", cc_padding_seed_000045),
        ("property_campaigns::tests::cc_padding_seed_000046", cc_padding_seed_000046),
        ("property_campaigns::tests::cc_padding_seed_000047", cc_padding_seed_000047),
        ("property_campaigns::tests::cc_padding_seed_000048", cc_padding_seed_000048),
        ("property_campaigns::tests::cc_padding_seed_000049", cc_padding_seed_000049),
        ("property_campaigns::tests::cc_padding_seed_000050", cc_padding_seed_000050),
        ("property_campaigns::tests::cc_padding_seed_000051", cc_padding_seed_000051),
        ("property_campaigns::tests::cc_padding_seed_000052", cc_padding_seed_000052),
        ("property_campaigns::tests::cc_padding_seed_000053", cc_padding_seed_000053),
        ("property_campaigns::tests::cc_padding_seed_000054", cc_padding_seed_000054),
        ("property_campaigns::tests::cc_padding_seed_000055", cc_padding_seed_000055),
        ("property_campaigns::tests::cc_padding_seed_000056", cc_padding_seed_000056),
        ("property_campaigns::tests::cc_padding_seed_000057", cc_padding_seed_000057),
        ("property_campaigns::tests::cc_padding_seed_000058", cc_padding_seed_000058),
        ("property_campaigns::tests::cc_padding_seed_000059", cc_padding_seed_000059),
        ("property_campaigns::tests::cc_padding_seed_000060", cc_padding_seed_000060),
        ("property_campaigns::tests::cc_padding_seed_000061", cc_padding_seed_000061),
        ("property_campaigns::tests::cc_padding_seed_000062", cc_padding_seed_000062),
        ("property_campaigns::tests::cc_padding_seed_000063", cc_padding_seed_000063),
        ("property_campaigns::tests::cc_padding_seed_000064", cc_padding_seed_000064),
        ("property_campaigns::tests::cc_padding_seed_000065", cc_padding_seed_000065),
        ("property_campaigns::tests::cc_padding_seed_000066", cc_padding_seed_000066),
        ("property_campaigns::tests::cc_padding_seed_000067", cc_padding_seed_000067),
        ("property_campaigns::tests::cc_padding_seed_000068", cc_padding_seed_000068),
        ("property_campaigns::tests::cc_padding_seed_000069", cc_padding_seed_000069),
        ("property_campaigns::tests::cc_padding_seed_000070", cc_padding_seed_000070),
        ("property_campaigns::tests::cc_padding_seed_000071", cc_padding_seed_000071),
        ("property_campaigns::tests::cc_padding_seed_000072", cc_padding_seed_000072),
        ("property_campaigns::tests::cc_padding_seed_000073", cc_padding_seed_000073),
        ("property_campaigns::tests::cc_padding_seed_000074", cc_padding_seed_000074),
        ("property_campaigns::tests::cc_padding_seed_000075", cc_padding_seed_000075),
        ("property_campaigns::tests::cc_padding_seed_000076", cc_padding_seed_000076),
        ("property_campaigns::tests::cc_padding_seed_000077", cc_padding_seed_000077),
        ("property_campaigns::tests::cc_padding_seed_000078", cc_padding_seed_000078),
        ("property_campaigns::tests::cc_padding_seed_000079", cc_padding_seed_000079),
        ("property_campaigns::tests::cc_padding_seed_000080", cc_padding_seed_000080),
        ("property_campaigns::tests::cc_padding_seed_000081", cc_padding_seed_000081),
        ("property_campaigns::tests::cc_padding_seed_000082", cc_padding_seed_000082),
        ("property_campaigns::tests::cc_padding_seed_000083", cc_padding_seed_000083),
        ("property_campaigns::tests::cc_padding_seed_000084", cc_padding_seed_000084),
        ("property_campaigns::tests::cc_padding_seed_000085", cc_padding_seed_000085),
        ("property_campaigns::tests::cc_padding_seed_000086", cc_padding_seed_000086),
        ("property_campaigns::tests::cc_padding_seed_000087", cc_padding_seed_000087),
        ("property_campaigns::tests::cc_padding_seed_000088", cc_padding_seed_000088),
        ("property_campaigns::tests::cc_padding_seed_000089", cc_padding_seed_000089),
        ("property_campaigns::tests::cc_padding_seed_000090", cc_padding_seed_000090),
        ("property_campaigns::tests::cc_padding_seed_000091", cc_padding_seed_000091),
        ("property_campaigns::tests::cc_padding_seed_000092", cc_padding_seed_000092),
        ("property_campaigns::tests::cc_padding_seed_000093", cc_padding_seed_000093),
        ("property_campaigns::tests::cc_padding_seed_000094", cc_padding_seed_000094),
        ("property_campaigns::tests::cc_padding_seed_000095", cc_padding_seed_000095),
        ("property_campaigns::tests::cc_padding_seed_000096", cc_padding_seed_000096),
        ("property_campaigns::tests::cc_padding_seed_000097", cc_padding_seed_000097),
        ("property_campaigns::tests::cc_padding_seed_000098", cc_padding_seed_000098),
        ("property_campaigns::tests::cc_padding_seed_000099", cc_padding_seed_000099),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
