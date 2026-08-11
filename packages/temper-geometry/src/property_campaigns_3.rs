// Third property campaign over temper-geometry: metamorphic and invariant
// properties over four independent, pure, deterministic kernels that the
// first two campaigns do not cover -- `edt.rs` (exact Euclidean distance
// transform), `pad_geometry.rs` (the shared pad-radius model: `py_hypot`,
// `bounding_radius`, `corner_radius`, `core_half_extents`), `copper_reach.rs`
// (`copper_reach_mm`, the per-component copper-extent kernel built on top of
// `pad_geometry`), and `obstacle_map_kernels.rs` (`circle_buffer_ring`, the
// GEOS-bit-exact `Point.buffer()` circle construction). The first campaign
// (`property_campaigns.rs`) covers `kicad_transform.rs`, `convex_hull.rs`,
// and `connected_components.rs`; the second (`property_campaigns_2.rs`)
// covers `sdf.rs`, `polygon.rs`, `overlap.rs`, and `projections.rs`. Nothing
// here repeats a property over any of those seven.
//
// Why a THIRD module instead of appending to either existing one
// -----------------------------------------------------------------------
// Same reasoning `property_campaigns_2.rs`'s own doc comment gives for being
// a second module rather than an addition to the first: multiple agents
// work in this repository concurrently, and appending thousands of lines to
// a file another agent may be mid-edit on is exactly the merge-collision
// risk `kicad_transform.rs`'s "declared at the tail so appends cannot
// rewrite a parallel agent's lines" comment in `lib.rs` warns about. A
// third, independently-registered module sidesteps that without touching
// either existing campaign file.
//
// Every property is a metamorphic or invariant relation over the real
// kernel -- a relationship that must hold between two *related* calls --
// never a restatement of the implementation (never "recompute X, and assert
// X equals X"). Each was checked against a deliberately broken kernel and
// shown to fail on exactly the cases it targets (and leave every other
// property green), then the kernel was reverted; see this crate's PR body
// for the full per-property mutation-testing evidence.
//
// No `proptest`, no RNG crate: `SplitMix64` below is the same small,
// self-contained, portable PRNG the first two campaigns use, duplicated
// here rather than imported -- it is a private, non-`pub` item in both of
// those modules (module-local by design), so nothing outside a campaign
// module can name it; re-deriving a few lines of PRNG code keeps this
// module readable and auditable on its own, the same tradeoff
// `property_campaigns_2.rs`'s own doc comment makes.
//
// Every item below (down to `mod tests`) is reachable ONLY from that
// module's `#[test]` functions -- the same reachability shape the first two
// campaigns document (a build with neither `test` nor `wasm-registry`
// active sees everything below as unused).
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
/// same base seed (same pattern as both earlier campaigns' `sub_rng`).
fn sub_rng(seed: u64, salt: u64) -> SplitMix64 {
    SplitMix64::new(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15).wrapping_add(salt))
}

// ===========================================================================
// Kernel 1: edt.rs -- the exact 2-D Euclidean distance transform
// (Felzenszwalb-Huttenlocher), `exact_edt` / `exact_edt_sampled`.
// ===========================================================================

use crate::edt::{exact_edt, exact_edt_sampled};

const EDT_SALT_SCALE: u64 = 0xE1;
const EDT_SALT_ADD_SOURCE: u64 = 0xE2;

/// A small random 0/1 mask, `4..=12` cells per side, with cell `0` FORCED
/// foreground. The forced cell exists so `edt_monotone_under_added_sources_impl`
/// always has a guaranteed foreground cell to flip to background -- without
/// it, an unlucky all-background density draw would make that property
/// compare a mask to itself (vacuously true) instead of actually adding a
/// source.
fn edt_gen_mask(seed: u64) -> (Vec<u8>, usize, usize) {
    let mut rng = SplitMix64::new(seed);
    let h = 4 + rng.index(9); // 4..=12
    let w = 4 + rng.index(9); // 4..=12
    let density = rng.range(0.15, 0.85);
    let mut mask: Vec<u8> = (0..h * w).map(|_| if rng.next_f64() < density { 1 } else { 0 }).collect();
    mask[0] = 1;
    (mask, h, w)
}

/// `exact_edt_sampled(mask, h, w, k, k)` must equal `k * exact_edt(mask, h, w)`
/// pointwise, for any uniform scale `k > 0`: scaling both axes' physical
/// spacing by `k` scales every reported distance by exactly `k` (a distance
/// is a length, and lengths scale linearly with the ruler). This is the same
/// relation `edt.rs`'s own hand-written
/// `test_anisotropic_sampling_matches_scaled_isotropic` checks at one fixed
/// mask and `k = 2.5`; this property exercises it across many random masks
/// and scale factors via the seeded harness.
///
/// Bug this would catch: `edt_squared_1d` computes `s2 = sampling * sampling`
/// and folds it into the parabola intersection/evaluation arithmetic -- a
/// refactor that applied `sampling` to only one of the two passes (rows vs
/// columns), or that used `sampling` instead of `sampling * sampling` in the
/// squared-distance accumulation, would break this scale law while leaving
/// the `k = 1` (isotropic) case, and thus every other property here, exactly
/// as green as before.
pub(crate) fn edt_scale_law_impl(seed: u64) {
    let (mask, h, w) = edt_gen_mask(seed);
    let mut k_rng = sub_rng(seed, EDT_SALT_SCALE);
    let k = k_rng.range(0.2, 8.0);
    let d_unit = exact_edt(&mask, h, w);
    let d_scaled = exact_edt_sampled(&mask, h, w, k, k);
    for i in 0..d_unit.len() {
        let (u, s) = (d_unit[i], d_scaled[i]);
        if u.is_infinite() && s.is_infinite() {
            continue;
        }
        let tol = 1e-7 * (k * u + 1.0);
        assert!(
            (s - k * u).abs() < tol,
            "exact_edt_sampled(k={k}) != k * exact_edt at cell {i}: seed={seed} h={h} w={w} unit={u} scaled={s} k*unit={}",
            k * u
        );
    }
}

/// Adding sources (flipping foreground cells to background) can only
/// DECREASE or leave unchanged the distance-to-nearest-source at every cell
/// -- more candidate sources never makes the nearest one farther away. This
/// is a genuine monotonicity law of the distance transform, independent of
/// the Felzenszwalb-Huttenlocher algorithm's internal machinery (the lower
/// envelope of parabolas), so it does not merely restate that construction.
///
/// Bug this would catch: any sign error or stale-state bug in the sweep
/// (`edt_squared_1d`'s `v`/`z` envelope bookkeeping, or the two-pass
/// row/column composition in `exact_edt_sampled`) that could make a cell's
/// reported distance INCREASE when a strictly closer source is added --
/// exactly the class of bug a single fixed-mask regression test cannot
/// surface, because it never compares two related masks.
pub(crate) fn edt_monotone_under_added_sources_impl(seed: u64) {
    let (mut mask, h, w) = edt_gen_mask(seed);
    let d_before = exact_edt(&mask, h, w);
    let mut rng = sub_rng(seed, EDT_SALT_ADD_SOURCE);
    // Cell 0 is guaranteed foreground by edt_gen_mask; flip it, plus 0..=2
    // more random cells (a flip on an already-background cell is a no-op,
    // still consistent with "adding sources").
    mask[0] = 0;
    let extra = rng.index(3);
    for _ in 0..extra {
        let idx = rng.index(h * w);
        mask[idx] = 0;
    }
    let d_after = exact_edt(&mask, h, w);
    for i in 0..d_before.len() {
        let (b, a) = (d_before[i], d_after[i]);
        if b.is_infinite() && a.is_infinite() {
            continue;
        }
        assert!(
            a <= b + 1e-9,
            "edt distance increased after adding sources at cell {i}: seed={seed} h={h} w={w} before={b} after={a}"
        );
    }
}

// ===========================================================================
// Kernel 2: pad_geometry.rs -- the shared shape-aware pad-radius model:
// `py_hypot` (CPython-exact hypot), `bounding_radius`, `corner_radius`,
// `core_half_extents`.
// ===========================================================================

use crate::pad_geometry::{
    bounding_radius, core_half_extents, corner_radius, py_hypot, SHAPE_CIRCLE, SHAPE_OVAL,
    SHAPE_RECT, SHAPE_ROUNDRECT, SHAPE_THRU_HOLE,
};

const PG_SALT_SCALE: u64 = 0xF1;
const PG_SALT_SHAPE: u64 = 0xF2;
const PG_SALT_WIDTH: u64 = 0xF3;

const PG_SHAPES: [i64; 5] = [SHAPE_CIRCLE, SHAPE_OVAL, SHAPE_RECT, SHAPE_ROUNDRECT, SHAPE_THRU_HOLE];

/// `py_hypot(x, y) == py_hypot(y, x)`: Euclidean distance from the origin
/// does not care which axis is which.
///
/// Bug this would catch: `vector_norm_2` folds `x` then `y` through an
/// asymmetric accumulation (`csum` seeded at `1.0`, then each coordinate's
/// squared contribution folded in via `dl_fast_sum`/`dl_mul` in sequence) --
/// a refactor that special-cased "the larger of the two goes first" (a
/// plausible-looking micro-optimization, since CPython's own `vector_norm`
/// does scale by `max` first) but broke it partway (e.g. applied the
/// component swap to only one of `dl_mul`'s two calls) would make this
/// property fail while leaving `hypot(x, 0)`-style edge tests untouched.
pub(crate) fn hypot_symmetric_impl(seed: u64) {
    let mut rng = SplitMix64::new(seed);
    let x = rng.range(-10_000.0, 10_000.0);
    let y = rng.range(-10_000.0, 10_000.0);
    let d_xy = py_hypot(x, y);
    let d_yx = py_hypot(y, x);
    let tol = 1e-9 * (d_xy.abs() + 1.0);
    assert!(
        (d_xy - d_yx).abs() < tol,
        "py_hypot not symmetric: seed={seed} x={x} y={y} hypot(x,y)={d_xy} hypot(y,x)={d_yx}"
    );
}

/// `py_hypot(k*x, k*y) == k * py_hypot(x, y)` for `k > 0`: Euclidean
/// distance is linear-homogeneous under uniform scaling of its input vector.
///
/// Bug this would catch: `vector_norm_2` computes a `scale = pow2(-max_e)`
/// factor from `frexp(max)` and un-scales (`h / scale`) at the end -- an
/// off-by-one in the exponent arithmetic (e.g. using `max_e` instead of
/// `-max_e`, or forgetting the final `/ scale`) would produce answers correct
/// only within a narrow magnitude band, passing small-input unit tests while
/// failing this property's wide swept range of `k`.
pub(crate) fn hypot_scale_invariant_impl(seed: u64) {
    let mut rng = SplitMix64::new(seed);
    let x = rng.range(-1000.0, 1000.0);
    let y = rng.range(-1000.0, 1000.0);
    let mut k_rng = sub_rng(seed, PG_SALT_SCALE);
    let k = k_rng.range(0.01, 100.0);
    let base = py_hypot(x, y);
    let scaled = py_hypot(k * x, k * y);
    let tol = 1e-7 * (k * base + 1.0);
    assert!(
        (scaled - k * base).abs() < tol,
        "py_hypot not scale-invariant: seed={seed} x={x} y={y} k={k} base={base} scaled={scaled} k*base={}",
        k * base
    );
}

/// `bounding_radius` is non-decreasing as `width` grows, holding `height`,
/// `shape`, and `ratio` (`<= 0.5`, the valid roundrect-ratio domain) fixed --
/// a physically obvious fact (a wider pad's bounding circle cannot shrink)
/// that is NOT obvious from the formula's syntax: `bounding_radius` composes
/// `core_half_extents` (itself a `max(width/2 - r, 0)` clamp) with a `corner_radius`
/// that, for `Oval`/`Roundrect`, itself depends on `width` through `min(width, height)`
/// -- so the two `width`-dependent terms interact instead of one simply
/// dominating.
///
/// Bug this would catch: `corner_radius`'s `Oval` arm uses `width.min(height)`;
/// swapping it to `width.max(height)` (a plausible typo given `Circle`'s arm
/// uses `.max`) would make the corner radius, and so `core_half_extents`,
/// disagree with the true pad geometry for `width > height`, breaking this
/// monotonicity for exactly that shape while `Rect`/`Circle` cases stayed
/// green.
pub(crate) fn bounding_radius_monotonic_in_width_impl(seed: u64) {
    let mut rng = SplitMix64::new(seed);
    let height = rng.range(0.05, 50.0);
    let w1 = rng.range(0.05, 50.0);
    let mut shape_rng = sub_rng(seed, PG_SALT_SHAPE);
    let shape = PG_SHAPES[shape_rng.index(PG_SHAPES.len())];
    let ratio = shape_rng.range(0.0, 0.5);
    let mut delta_rng = sub_rng(seed, PG_SALT_WIDTH);
    let delta = delta_rng.range(0.0001, 50.0);
    let w2 = w1 + delta;
    let b1 = bounding_radius(w1, height, shape, ratio);
    let b2 = bounding_radius(w2, height, shape, ratio);
    let tol = 1e-9 * (b1.abs() + b2.abs() + 1.0);
    assert!(
        b2 + tol >= b1,
        "bounding_radius decreased when width grew: seed={seed} shape={shape} ratio={ratio} height={height} w1={w1} w2={w2} b1={b1} b2={b2}"
    );
}

/// `core_half_extents(w, h, shape, ratio).0 + corner_radius(w, h, shape, ratio) == w / 2`,
/// and the same for `.1` and `h` -- the pad's half-width decomposes exactly
/// into a straight-edge half-length plus a corner radius, for any `ratio <= 0.5`
/// (the domain where the corner radius never exceeds the half-extent it is
/// carved from, so `core_half_extents`'s `max(..., 0)` clamp never fires).
/// This is a genuine cross-function relationship between two independently
/// implemented kernels (`corner_radius` and `core_half_extents`), not a
/// restatement of either one alone.
///
/// `Circle`/`ThruHole` are generated with `width == height`: `corner_radius`'s
/// `Circle` arm deliberately uses `width.max(height)` ("take the larger
/// defensively", its own doc comment) rather than the `min` every other
/// shape arm uses, precisely so a malformed circle with `width != height`
/// never UNDER-reports its radius -- but that defensive asymmetry means the
/// clean `hw + r == w/2` decomposition only holds at a circle's actual
/// domain (`width == height`); off that domain `r` can exceed `w/2`
/// (`core_half_extents` correctly clamps `hw` to `0`, and the identity is
/// not expected to hold). This property is about the decomposition
/// relationship, not about re-deriving `corner_radius`'s defensive fallback,
/// so it stays within `Circle`'s real domain.
///
/// Bug this would catch: a refactor of `core_half_extents` from
/// `(width / 2.0 - r).max(0.0)` to, say, `(width - r) / 2.0` (a subtle
/// distributivity slip) would still pass any test that only inspects
/// `core_half_extents` in isolation against a hand-picked expected value if
/// that value was computed with the same slipped formula, but fails this
/// property immediately because it checks the decomposition against
/// `corner_radius`'s independently-computed `r`.
pub(crate) fn core_half_extents_sum_identity_impl(seed: u64) {
    let mut rng = SplitMix64::new(seed);
    let width = rng.range(0.05, 50.0);
    let mut height = rng.range(0.05, 50.0);
    let mut shape_rng = sub_rng(seed, PG_SALT_SHAPE);
    let shape = PG_SHAPES[shape_rng.index(PG_SHAPES.len())];
    let ratio = shape_rng.range(0.0, 0.5);
    if shape == SHAPE_CIRCLE || shape == SHAPE_THRU_HOLE {
        height = width;
    }
    let (hw, hh) = core_half_extents(width, height, shape, ratio);
    let r = corner_radius(width, height, shape, ratio);
    let tol = 1e-9 * (width + height + 1.0);
    assert!(
        (hw + r - width / 2.0).abs() < tol,
        "core_half_extents.0 + corner_radius != width/2: seed={seed} shape={shape} ratio={ratio} width={width} height={height} hw={hw} r={r}"
    );
    assert!(
        (hh + r - height / 2.0).abs() < tol,
        "core_half_extents.1 + corner_radius != height/2: seed={seed} shape={shape} ratio={ratio} width={width} height={height} hh={hh} r={r}"
    );
}

// ===========================================================================
// Kernel 3: copper_reach.rs -- `copper_reach_mm`, the per-component copper
// extent kernel (`max over pads of |offset| + bounding_radius(...)`).
// ===========================================================================

use crate::copper_reach::{copper_reach_mm, PadRow};
use crate::kicad_transform::rotate_local_to_world;

const CR_SALT_SCALE: u64 = 0x71;
const CR_SALT_EXTRA: u64 = 0x72;
const CR_SALT_ROTATE: u64 = 0x73;

const CR_SHAPES: [i64; 4] = [SHAPE_CIRCLE, SHAPE_OVAL, SHAPE_RECT, SHAPE_ROUNDRECT];

fn cr_gen_pads(seed: u64) -> Vec<PadRow> {
    let mut rng = SplitMix64::new(seed);
    let n = 1 + rng.index(6); // 1..=6 pads
    (0..n)
        .map(|_| {
            let ox = rng.range(-50.0, 50.0);
            let oy = rng.range(-50.0, 50.0);
            let w = rng.range(0.2, 5.0);
            let h = rng.range(0.2, 5.0);
            let shape = CR_SHAPES[rng.index(CR_SHAPES.len())];
            let ratio = rng.range(0.0, 0.5);
            (ox, oy, w, h, shape, ratio)
        })
        .collect()
}

/// `copper_reach_mm` is linear-homogeneous under uniformly scaling every
/// pad's offset AND dimensions by `k > 0`: `copper_reach_mm(k * pads) ==
/// k * copper_reach_mm(pads)`. Both terms in the per-pad formula
/// (`py_hypot(offset)` and `bounding_radius(w, h, ...)`) are themselves
/// linear-homogeneous in their inputs (proven by `hypot_scale_invariant_impl`
/// and the linear-in-`width`/`height` structure `bounding_radius_monotonic_in_width_impl`
/// exercises), and `max` of scaled values scales the same way, so the whole
/// composition must too.
///
/// Bug this would catch: an accidental mix of scaled and unscaled terms --
/// e.g. scaling every pad's offset and width but not its height (a
/// copy-paste slip in a hypothetical batch-scaling call site this property
/// stands in for) -- breaks the exact scale law while leaving `k = 1`
/// (already covered by the existing hand-written unit tests) untouched.
pub(crate) fn copper_reach_scale_law_impl(seed: u64) {
    let pads = cr_gen_pads(seed);
    let mut k_rng = sub_rng(seed, CR_SALT_SCALE);
    let k = k_rng.range(0.1, 20.0);
    let scaled: Vec<PadRow> = pads
        .iter()
        .map(|&(ox, oy, w, h, shape, ratio)| (ox * k, oy * k, w * k, h * k, shape, ratio))
        .collect();
    let base = copper_reach_mm(&pads);
    let got = copper_reach_mm(&scaled);
    let tol = 1e-7 * (k * base + 1.0);
    assert!(
        (got - k * base).abs() < tol,
        "copper_reach_mm not scale-invariant: seed={seed} k={k} base={base} got={got} k*base={}",
        k * base
    );
}

/// Appending one more pad to a component's pad list cannot DECREASE
/// `copper_reach_mm`: it is a `max` over per-pad reach contributions, and
/// `max` over a superset is never smaller than `max` over the subset.
///
/// Bug this would catch: an accidental fold-with-`fold(0.0, f64::max)`-style
/// rewrite of the underlying `cpython_max` (which seeds its accumulator with
/// the FIRST element, not `0.0`) would silently clamp every all-negative or
/// unusual reach set to `0.0`, or an index-off-by-one in a hypothetical
/// "reach excluding the last pad" refactor would drop a pad's contribution
/// -- both violate this monotonicity while leaving a same-length-list
/// regression test unable to notice (it never compares two related lists).
pub(crate) fn copper_reach_monotone_under_added_pad_impl(seed: u64) {
    let pads = cr_gen_pads(seed);
    let mut extra_rng = sub_rng(seed, CR_SALT_EXTRA);
    let extra: PadRow = (
        extra_rng.range(-50.0, 50.0),
        extra_rng.range(-50.0, 50.0),
        extra_rng.range(0.2, 5.0),
        extra_rng.range(0.2, 5.0),
        CR_SHAPES[extra_rng.index(CR_SHAPES.len())],
        extra_rng.range(0.0, 0.5),
    );
    let base = copper_reach_mm(&pads);
    let mut extended = pads.clone();
    extended.push(extra);
    let got = copper_reach_mm(&extended);
    let tol = 1e-9 * (base + 1.0);
    assert!(
        got + tol >= base,
        "copper_reach_mm decreased after adding a pad: seed={seed} base={base} got={got}"
    );
}

/// Rotating every pad's offset about the component origin by the SAME angle
/// (KiCad's `rotate_local_to_world` convention) must not change
/// `copper_reach_mm`: `|offset|` is rotation-invariant (a rotation is an
/// isometry, proven directly by `property_campaigns.rs`'s
/// `kt_isometry_impl` over `rotate_local_to_world` itself) and
/// `bounding_radius` depends only on `width`/`height`/`shape`/`ratio`, none
/// of which the rotation touches.
///
/// Bug this would catch: a hypothetical caller-side helper that rotated pad
/// offsets before calling `copper_reach_mm` while forgetting to also rotate
/// (or correctly leave alone) the pad's `width`/`height` pairing -- e.g.
/// swapping `width` and `height` for pads rotated past a quadrant boundary --
/// would break this invariant for shapes where `width != height`
/// (`Oval`/`Rect`/`Roundrect`) while `Circle` pads (symmetric in
/// width/height) stayed accidentally green.
pub(crate) fn copper_reach_rotation_invariant_impl(seed: u64) {
    let pads = cr_gen_pads(seed);
    let mut theta_rng = sub_rng(seed, CR_SALT_ROTATE);
    let theta = theta_rng.range(-4.0 * std::f64::consts::PI, 4.0 * std::f64::consts::PI);
    let rotated: Vec<PadRow> = pads
        .iter()
        .map(|&(ox, oy, w, h, shape, ratio)| {
            let (rx, ry) = rotate_local_to_world(ox, oy, theta);
            (rx, ry, w, h, shape, ratio)
        })
        .collect();
    let base = copper_reach_mm(&pads);
    let got = copper_reach_mm(&rotated);
    let tol = 1e-7 * (base + 1.0);
    assert!(
        (got - base).abs() < tol,
        "copper_reach_mm not rotation-invariant: seed={seed} theta={theta} base={base} got={got}"
    );
}

// ===========================================================================
// Kernel 4: obstacle_map_kernels.rs -- `circle_buffer_ring`, the GEOS-exact
// `Point(cx, cy).buffer(radius, quad_segs)` circle-polygon construction.
// ===========================================================================

use crate::obstacle_map_kernels::circle_buffer_ring;

const OM_SALT_TRANSLATE: u64 = 0x91;
const OM_SALT_SCALE: u64 = 0x92;

fn om_gen_case(seed: u64) -> (f64, f64, f64, i64) {
    let mut rng = SplitMix64::new(seed);
    let cx = rng.range(-500.0, 500.0);
    let cy = rng.range(-500.0, 500.0);
    let radius = rng.range(0.01, 100.0);
    let quad_segs = 1 + rng.index(16) as i64; // 1..=16
    (cx, cy, radius, quad_segs)
}

/// Translating the circle's center by `(dx, dy)` translates every ring
/// vertex by exactly `(dx, dy)`: the ring's SHAPE (the sequence of angles
/// and which components snap to zero) depends only on `radius` and
/// `quad_segs`, never on `cx`/`cy`, which enter solely as an additive
/// offset applied identically to every vertex.
///
/// Bug this would catch: `geos_sin_cos_snap`'s zero-snap
/// (`if s.abs() < 5e-16 { s = 0.0 }`) is evaluated on the UNSCALED sin/cos
/// value before the `cx +`/`cy +` offset is added -- a refactor that instead
/// snapped the final offset coordinate (e.g. `if (cx + radius*c).abs() <
/// 5e-16`) would make cardinal-point snapping depend on `cx`/`cy`, breaking
/// translation equivariance at exactly the vertices whose un-translated
/// coordinate happens to be small, while the ring's un-translated shape
/// (this module's own `ring_shape_for_quad_segs_8` unit test, always run at
/// `cx = cy = 0`) stayed green.
pub(crate) fn circle_ring_translation_equivariant_impl(seed: u64) {
    let (cx, cy, radius, q) = om_gen_case(seed);
    let mut t_rng = sub_rng(seed, OM_SALT_TRANSLATE);
    let dx = t_rng.range(-1000.0, 1000.0);
    let dy = t_rng.range(-1000.0, 1000.0);
    let ring0 = circle_buffer_ring(cx, cy, radius, q);
    let ring1 = circle_buffer_ring(cx + dx, cy + dy, radius, q);
    assert_eq!(
        ring0.len(),
        ring1.len(),
        "translated ring has a different vertex count: seed={seed} cx={cx} cy={cy} dx={dx} dy={dy}"
    );
    let tol = 1e-7 * (dx.abs() + dy.abs() + 1.0);
    for i in 0..ring0.len() {
        assert!(
            (ring1[i].0 - ring0[i].0 - dx).abs() < tol,
            "vertex {i} x not translated by dx: seed={seed} dx={dx} dy={dy} v0={:?} v1={:?}",
            ring0[i],
            ring1[i]
        );
        assert!(
            (ring1[i].1 - ring0[i].1 - dy).abs() < tol,
            "vertex {i} y not translated by dy: seed={seed} dx={dx} dy={dy} v0={:?} v1={:?}",
            ring0[i],
            ring1[i]
        );
    }
}

/// Scaling `radius` by `k > 0` (holding `cx`, `cy`, `quad_segs` fixed) scales
/// every vertex's offset from the center by exactly `k`: the angle sequence
/// and which components snap to zero depend only on `quad_segs` (never on
/// `radius`), so `(vertex(k*r) - center) == k * (vertex(r) - center)` for
/// every vertex index.
///
/// Bug this would catch: `fillet`/`n_seg`/`ang_inc` are computed from
/// `quad_segs` alone in the real kernel -- a refactor that let `radius` leak
/// into that angle-quantization arithmetic (e.g. an adaptive segment count
/// keyed on `radius`, a real GEOS behavior for SOME geometry operations that
/// would be wrong to reproduce here) would change the vertex COUNT or angle
/// spacing as `radius` varies, breaking this property immediately -- a
/// single fixed-radius unit test cannot see it because it never compares two
/// different radii.
pub(crate) fn circle_ring_radius_scale_law_impl(seed: u64) {
    let (cx, cy, radius, q) = om_gen_case(seed);
    let mut k_rng = sub_rng(seed, OM_SALT_SCALE);
    let k = k_rng.range(0.05, 20.0);
    let ring0 = circle_buffer_ring(cx, cy, radius, q);
    let ring1 = circle_buffer_ring(cx, cy, radius * k, q);
    assert_eq!(
        ring0.len(),
        ring1.len(),
        "scaled-radius ring has a different vertex count: seed={seed} radius={radius} k={k}"
    );
    let tol = 1e-7 * (k * radius + 1.0);
    for i in 0..ring0.len() {
        let e0x = ring0[i].0 - cx;
        let e0y = ring0[i].1 - cy;
        let e1x = ring1[i].0 - cx;
        let e1y = ring1[i].1 - cy;
        assert!(
            (e1x - k * e0x).abs() < tol,
            "vertex {i} x offset not scaled by k: seed={seed} radius={radius} k={k} e0=({e0x},{e0y}) e1=({e1x},{e1y})"
        );
        assert!(
            (e1y - k * e0y).abs() < tol,
            "vertex {i} y offset not scaled by k: seed={seed} radius={radius} k={k} e0=({e0x},{e0y}) e1=({e1x},{e1y})"
        );
    }
}

/// Every vertex of `circle_buffer_ring(cx, cy, radius, q)` lies at Euclidean
/// distance `radius` from `(cx, cy)` -- the defining property of a circle
/// approximation, checked against a plain `sqrt((x-cx)^2+(y-cy)^2)` oracle
/// independent of the GEOS-replica trig the kernel itself uses.
///
/// Bug this would catch: `geos_sin_cos_snap`'s zero-snap threshold
/// (`5e-16`) applied to the WRONG operand (e.g. snapping `radius * c`
/// instead of `c`) would leave large-radius vertices measurably off the
/// circle (`radius * 5e-16` can exceed this property's tolerance once
/// `radius` is large, while a naive fixed-tolerance check at one small
/// radius, like this module's own `ring_shape_for_quad_segs_8` unit test at
/// `radius = 0.125`, would not detect the same relative bug at all).
pub(crate) fn circle_ring_vertices_at_radius_from_center_impl(seed: u64) {
    let (cx, cy, radius, q) = om_gen_case(seed);
    let ring = circle_buffer_ring(cx, cy, radius, q);
    let tol = 1e-9 * (radius + 1.0);
    for (i, &(x, y)) in ring.iter().enumerate() {
        let dist = ((x - cx) * (x - cx) + (y - cy) * (y - cy)).sqrt();
        assert!(
            (dist - radius).abs() < tol,
            "ring vertex {i} not at distance `radius` from center: seed={seed} cx={cx} cy={cy} radius={radius} vertex=({x},{y}) dist={dist}"
        );
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
        let mut a = SplitMix64::new(4242);
        let mut b = SplitMix64::new(4242);
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
    fn edt_gen_mask_dims_and_forced_cell_in_expected_range() {
        for seed in [0u64, 7, 999_999] {
            let (mask, h, w) = edt_gen_mask(seed);
            assert_eq!(mask.len(), h * w);
            assert!((4..=12).contains(&h), "seed={seed} h={h}");
            assert!((4..=12).contains(&w), "seed={seed} w={w}");
            assert_eq!(mask[0], 1, "seed={seed}: cell 0 must be forced foreground");
        }
    }

    #[cfg_attr(test, test)]
    fn cr_gen_pads_length_in_expected_range() {
        for seed in [0u64, 5, 777_777] {
            let pads = cr_gen_pads(seed);
            assert!(!pads.is_empty() && pads.len() <= 6, "seed={seed} n={}", pads.len());
        }
    }

    #[cfg_attr(test, test)]
    fn om_gen_case_is_deterministic() {
        assert_eq!(om_gen_case(42), om_gen_case(42));
    }

    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_hand_worked_roundrect() {
        // 4x2 roundrect, ratio 0.25: r = 0.25*min(4,2) = 0.5.
        // hw = 4/2 - 0.5 = 1.5, hh = 2/2 - 0.5 = 0.5.
        let (hw, hh) = core_half_extents(4.0, 2.0, SHAPE_ROUNDRECT, 0.25);
        let r = corner_radius(4.0, 2.0, SHAPE_ROUNDRECT, 0.25);
        assert!((hw - 1.5).abs() < 1e-12 && (hh - 0.5).abs() < 1e-12 && (r - 0.5).abs() < 1e-12);
        assert!((hw + r - 2.0).abs() < 1e-12);
        assert!((hh + r - 1.0).abs() < 1e-12);
    }

    #[cfg_attr(test, test)]
    fn circle_ring_translation_hand_worked_example() {
        let ring0 = circle_buffer_ring(0.0, 0.0, 1.0, 4);
        let ring1 = circle_buffer_ring(10.0, -5.0, 1.0, 4);
        assert_eq!(ring0.len(), ring1.len());
        for i in 0..ring0.len() {
            assert!((ring1[i].0 - ring0[i].0 - 10.0).abs() < 1e-9);
            assert!((ring1[i].1 - ring0[i].1 - (-5.0)).abs() < 1e-9);
        }
    }

    // --- 12 properties x seeded cases = 2000 distinct-input wasm tests. ---
    // --- edt_scale_law: 180 generated seeds ---
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000000() { edt_scale_law_impl(0); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000001() { edt_scale_law_impl(1); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000002() { edt_scale_law_impl(2); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000003() { edt_scale_law_impl(3); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000004() { edt_scale_law_impl(4); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000005() { edt_scale_law_impl(5); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000006() { edt_scale_law_impl(6); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000007() { edt_scale_law_impl(7); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000008() { edt_scale_law_impl(8); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000009() { edt_scale_law_impl(9); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000010() { edt_scale_law_impl(10); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000011() { edt_scale_law_impl(11); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000012() { edt_scale_law_impl(12); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000013() { edt_scale_law_impl(13); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000014() { edt_scale_law_impl(14); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000015() { edt_scale_law_impl(15); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000016() { edt_scale_law_impl(16); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000017() { edt_scale_law_impl(17); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000018() { edt_scale_law_impl(18); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000019() { edt_scale_law_impl(19); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000020() { edt_scale_law_impl(20); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000021() { edt_scale_law_impl(21); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000022() { edt_scale_law_impl(22); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000023() { edt_scale_law_impl(23); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000024() { edt_scale_law_impl(24); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000025() { edt_scale_law_impl(25); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000026() { edt_scale_law_impl(26); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000027() { edt_scale_law_impl(27); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000028() { edt_scale_law_impl(28); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000029() { edt_scale_law_impl(29); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000030() { edt_scale_law_impl(30); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000031() { edt_scale_law_impl(31); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000032() { edt_scale_law_impl(32); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000033() { edt_scale_law_impl(33); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000034() { edt_scale_law_impl(34); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000035() { edt_scale_law_impl(35); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000036() { edt_scale_law_impl(36); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000037() { edt_scale_law_impl(37); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000038() { edt_scale_law_impl(38); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000039() { edt_scale_law_impl(39); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000040() { edt_scale_law_impl(40); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000041() { edt_scale_law_impl(41); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000042() { edt_scale_law_impl(42); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000043() { edt_scale_law_impl(43); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000044() { edt_scale_law_impl(44); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000045() { edt_scale_law_impl(45); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000046() { edt_scale_law_impl(46); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000047() { edt_scale_law_impl(47); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000048() { edt_scale_law_impl(48); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000049() { edt_scale_law_impl(49); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000050() { edt_scale_law_impl(50); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000051() { edt_scale_law_impl(51); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000052() { edt_scale_law_impl(52); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000053() { edt_scale_law_impl(53); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000054() { edt_scale_law_impl(54); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000055() { edt_scale_law_impl(55); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000056() { edt_scale_law_impl(56); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000057() { edt_scale_law_impl(57); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000058() { edt_scale_law_impl(58); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000059() { edt_scale_law_impl(59); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000060() { edt_scale_law_impl(60); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000061() { edt_scale_law_impl(61); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000062() { edt_scale_law_impl(62); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000063() { edt_scale_law_impl(63); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000064() { edt_scale_law_impl(64); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000065() { edt_scale_law_impl(65); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000066() { edt_scale_law_impl(66); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000067() { edt_scale_law_impl(67); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000068() { edt_scale_law_impl(68); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000069() { edt_scale_law_impl(69); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000070() { edt_scale_law_impl(70); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000071() { edt_scale_law_impl(71); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000072() { edt_scale_law_impl(72); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000073() { edt_scale_law_impl(73); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000074() { edt_scale_law_impl(74); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000075() { edt_scale_law_impl(75); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000076() { edt_scale_law_impl(76); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000077() { edt_scale_law_impl(77); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000078() { edt_scale_law_impl(78); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000079() { edt_scale_law_impl(79); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000080() { edt_scale_law_impl(80); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000081() { edt_scale_law_impl(81); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000082() { edt_scale_law_impl(82); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000083() { edt_scale_law_impl(83); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000084() { edt_scale_law_impl(84); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000085() { edt_scale_law_impl(85); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000086() { edt_scale_law_impl(86); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000087() { edt_scale_law_impl(87); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000088() { edt_scale_law_impl(88); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000089() { edt_scale_law_impl(89); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000090() { edt_scale_law_impl(90); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000091() { edt_scale_law_impl(91); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000092() { edt_scale_law_impl(92); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000093() { edt_scale_law_impl(93); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000094() { edt_scale_law_impl(94); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000095() { edt_scale_law_impl(95); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000096() { edt_scale_law_impl(96); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000097() { edt_scale_law_impl(97); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000098() { edt_scale_law_impl(98); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000099() { edt_scale_law_impl(99); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000100() { edt_scale_law_impl(100); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000101() { edt_scale_law_impl(101); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000102() { edt_scale_law_impl(102); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000103() { edt_scale_law_impl(103); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000104() { edt_scale_law_impl(104); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000105() { edt_scale_law_impl(105); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000106() { edt_scale_law_impl(106); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000107() { edt_scale_law_impl(107); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000108() { edt_scale_law_impl(108); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000109() { edt_scale_law_impl(109); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000110() { edt_scale_law_impl(110); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000111() { edt_scale_law_impl(111); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000112() { edt_scale_law_impl(112); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000113() { edt_scale_law_impl(113); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000114() { edt_scale_law_impl(114); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000115() { edt_scale_law_impl(115); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000116() { edt_scale_law_impl(116); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000117() { edt_scale_law_impl(117); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000118() { edt_scale_law_impl(118); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000119() { edt_scale_law_impl(119); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000120() { edt_scale_law_impl(120); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000121() { edt_scale_law_impl(121); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000122() { edt_scale_law_impl(122); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000123() { edt_scale_law_impl(123); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000124() { edt_scale_law_impl(124); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000125() { edt_scale_law_impl(125); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000126() { edt_scale_law_impl(126); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000127() { edt_scale_law_impl(127); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000128() { edt_scale_law_impl(128); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000129() { edt_scale_law_impl(129); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000130() { edt_scale_law_impl(130); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000131() { edt_scale_law_impl(131); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000132() { edt_scale_law_impl(132); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000133() { edt_scale_law_impl(133); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000134() { edt_scale_law_impl(134); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000135() { edt_scale_law_impl(135); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000136() { edt_scale_law_impl(136); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000137() { edt_scale_law_impl(137); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000138() { edt_scale_law_impl(138); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000139() { edt_scale_law_impl(139); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000140() { edt_scale_law_impl(140); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000141() { edt_scale_law_impl(141); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000142() { edt_scale_law_impl(142); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000143() { edt_scale_law_impl(143); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000144() { edt_scale_law_impl(144); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000145() { edt_scale_law_impl(145); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000146() { edt_scale_law_impl(146); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000147() { edt_scale_law_impl(147); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000148() { edt_scale_law_impl(148); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000149() { edt_scale_law_impl(149); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000150() { edt_scale_law_impl(150); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000151() { edt_scale_law_impl(151); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000152() { edt_scale_law_impl(152); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000153() { edt_scale_law_impl(153); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000154() { edt_scale_law_impl(154); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000155() { edt_scale_law_impl(155); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000156() { edt_scale_law_impl(156); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000157() { edt_scale_law_impl(157); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000158() { edt_scale_law_impl(158); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000159() { edt_scale_law_impl(159); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000160() { edt_scale_law_impl(160); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000161() { edt_scale_law_impl(161); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000162() { edt_scale_law_impl(162); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000163() { edt_scale_law_impl(163); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000164() { edt_scale_law_impl(164); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000165() { edt_scale_law_impl(165); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000166() { edt_scale_law_impl(166); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000167() { edt_scale_law_impl(167); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000168() { edt_scale_law_impl(168); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000169() { edt_scale_law_impl(169); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000170() { edt_scale_law_impl(170); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000171() { edt_scale_law_impl(171); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000172() { edt_scale_law_impl(172); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000173() { edt_scale_law_impl(173); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000174() { edt_scale_law_impl(174); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000175() { edt_scale_law_impl(175); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000176() { edt_scale_law_impl(176); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000177() { edt_scale_law_impl(177); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000178() { edt_scale_law_impl(178); }
    #[cfg_attr(test, test)]
    fn edt_scale_law_seed_000179() { edt_scale_law_impl(179); }
    // --- edt_monotone_added_sources: 180 generated seeds ---
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000000() { edt_monotone_under_added_sources_impl(0); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000001() { edt_monotone_under_added_sources_impl(1); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000002() { edt_monotone_under_added_sources_impl(2); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000003() { edt_monotone_under_added_sources_impl(3); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000004() { edt_monotone_under_added_sources_impl(4); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000005() { edt_monotone_under_added_sources_impl(5); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000006() { edt_monotone_under_added_sources_impl(6); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000007() { edt_monotone_under_added_sources_impl(7); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000008() { edt_monotone_under_added_sources_impl(8); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000009() { edt_monotone_under_added_sources_impl(9); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000010() { edt_monotone_under_added_sources_impl(10); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000011() { edt_monotone_under_added_sources_impl(11); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000012() { edt_monotone_under_added_sources_impl(12); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000013() { edt_monotone_under_added_sources_impl(13); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000014() { edt_monotone_under_added_sources_impl(14); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000015() { edt_monotone_under_added_sources_impl(15); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000016() { edt_monotone_under_added_sources_impl(16); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000017() { edt_monotone_under_added_sources_impl(17); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000018() { edt_monotone_under_added_sources_impl(18); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000019() { edt_monotone_under_added_sources_impl(19); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000020() { edt_monotone_under_added_sources_impl(20); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000021() { edt_monotone_under_added_sources_impl(21); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000022() { edt_monotone_under_added_sources_impl(22); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000023() { edt_monotone_under_added_sources_impl(23); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000024() { edt_monotone_under_added_sources_impl(24); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000025() { edt_monotone_under_added_sources_impl(25); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000026() { edt_monotone_under_added_sources_impl(26); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000027() { edt_monotone_under_added_sources_impl(27); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000028() { edt_monotone_under_added_sources_impl(28); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000029() { edt_monotone_under_added_sources_impl(29); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000030() { edt_monotone_under_added_sources_impl(30); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000031() { edt_monotone_under_added_sources_impl(31); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000032() { edt_monotone_under_added_sources_impl(32); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000033() { edt_monotone_under_added_sources_impl(33); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000034() { edt_monotone_under_added_sources_impl(34); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000035() { edt_monotone_under_added_sources_impl(35); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000036() { edt_monotone_under_added_sources_impl(36); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000037() { edt_monotone_under_added_sources_impl(37); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000038() { edt_monotone_under_added_sources_impl(38); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000039() { edt_monotone_under_added_sources_impl(39); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000040() { edt_monotone_under_added_sources_impl(40); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000041() { edt_monotone_under_added_sources_impl(41); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000042() { edt_monotone_under_added_sources_impl(42); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000043() { edt_monotone_under_added_sources_impl(43); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000044() { edt_monotone_under_added_sources_impl(44); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000045() { edt_monotone_under_added_sources_impl(45); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000046() { edt_monotone_under_added_sources_impl(46); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000047() { edt_monotone_under_added_sources_impl(47); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000048() { edt_monotone_under_added_sources_impl(48); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000049() { edt_monotone_under_added_sources_impl(49); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000050() { edt_monotone_under_added_sources_impl(50); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000051() { edt_monotone_under_added_sources_impl(51); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000052() { edt_monotone_under_added_sources_impl(52); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000053() { edt_monotone_under_added_sources_impl(53); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000054() { edt_monotone_under_added_sources_impl(54); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000055() { edt_monotone_under_added_sources_impl(55); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000056() { edt_monotone_under_added_sources_impl(56); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000057() { edt_monotone_under_added_sources_impl(57); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000058() { edt_monotone_under_added_sources_impl(58); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000059() { edt_monotone_under_added_sources_impl(59); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000060() { edt_monotone_under_added_sources_impl(60); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000061() { edt_monotone_under_added_sources_impl(61); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000062() { edt_monotone_under_added_sources_impl(62); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000063() { edt_monotone_under_added_sources_impl(63); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000064() { edt_monotone_under_added_sources_impl(64); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000065() { edt_monotone_under_added_sources_impl(65); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000066() { edt_monotone_under_added_sources_impl(66); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000067() { edt_monotone_under_added_sources_impl(67); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000068() { edt_monotone_under_added_sources_impl(68); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000069() { edt_monotone_under_added_sources_impl(69); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000070() { edt_monotone_under_added_sources_impl(70); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000071() { edt_monotone_under_added_sources_impl(71); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000072() { edt_monotone_under_added_sources_impl(72); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000073() { edt_monotone_under_added_sources_impl(73); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000074() { edt_monotone_under_added_sources_impl(74); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000075() { edt_monotone_under_added_sources_impl(75); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000076() { edt_monotone_under_added_sources_impl(76); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000077() { edt_monotone_under_added_sources_impl(77); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000078() { edt_monotone_under_added_sources_impl(78); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000079() { edt_monotone_under_added_sources_impl(79); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000080() { edt_monotone_under_added_sources_impl(80); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000081() { edt_monotone_under_added_sources_impl(81); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000082() { edt_monotone_under_added_sources_impl(82); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000083() { edt_monotone_under_added_sources_impl(83); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000084() { edt_monotone_under_added_sources_impl(84); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000085() { edt_monotone_under_added_sources_impl(85); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000086() { edt_monotone_under_added_sources_impl(86); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000087() { edt_monotone_under_added_sources_impl(87); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000088() { edt_monotone_under_added_sources_impl(88); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000089() { edt_monotone_under_added_sources_impl(89); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000090() { edt_monotone_under_added_sources_impl(90); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000091() { edt_monotone_under_added_sources_impl(91); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000092() { edt_monotone_under_added_sources_impl(92); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000093() { edt_monotone_under_added_sources_impl(93); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000094() { edt_monotone_under_added_sources_impl(94); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000095() { edt_monotone_under_added_sources_impl(95); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000096() { edt_monotone_under_added_sources_impl(96); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000097() { edt_monotone_under_added_sources_impl(97); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000098() { edt_monotone_under_added_sources_impl(98); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000099() { edt_monotone_under_added_sources_impl(99); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000100() { edt_monotone_under_added_sources_impl(100); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000101() { edt_monotone_under_added_sources_impl(101); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000102() { edt_monotone_under_added_sources_impl(102); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000103() { edt_monotone_under_added_sources_impl(103); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000104() { edt_monotone_under_added_sources_impl(104); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000105() { edt_monotone_under_added_sources_impl(105); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000106() { edt_monotone_under_added_sources_impl(106); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000107() { edt_monotone_under_added_sources_impl(107); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000108() { edt_monotone_under_added_sources_impl(108); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000109() { edt_monotone_under_added_sources_impl(109); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000110() { edt_monotone_under_added_sources_impl(110); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000111() { edt_monotone_under_added_sources_impl(111); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000112() { edt_monotone_under_added_sources_impl(112); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000113() { edt_monotone_under_added_sources_impl(113); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000114() { edt_monotone_under_added_sources_impl(114); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000115() { edt_monotone_under_added_sources_impl(115); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000116() { edt_monotone_under_added_sources_impl(116); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000117() { edt_monotone_under_added_sources_impl(117); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000118() { edt_monotone_under_added_sources_impl(118); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000119() { edt_monotone_under_added_sources_impl(119); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000120() { edt_monotone_under_added_sources_impl(120); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000121() { edt_monotone_under_added_sources_impl(121); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000122() { edt_monotone_under_added_sources_impl(122); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000123() { edt_monotone_under_added_sources_impl(123); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000124() { edt_monotone_under_added_sources_impl(124); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000125() { edt_monotone_under_added_sources_impl(125); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000126() { edt_monotone_under_added_sources_impl(126); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000127() { edt_monotone_under_added_sources_impl(127); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000128() { edt_monotone_under_added_sources_impl(128); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000129() { edt_monotone_under_added_sources_impl(129); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000130() { edt_monotone_under_added_sources_impl(130); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000131() { edt_monotone_under_added_sources_impl(131); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000132() { edt_monotone_under_added_sources_impl(132); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000133() { edt_monotone_under_added_sources_impl(133); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000134() { edt_monotone_under_added_sources_impl(134); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000135() { edt_monotone_under_added_sources_impl(135); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000136() { edt_monotone_under_added_sources_impl(136); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000137() { edt_monotone_under_added_sources_impl(137); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000138() { edt_monotone_under_added_sources_impl(138); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000139() { edt_monotone_under_added_sources_impl(139); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000140() { edt_monotone_under_added_sources_impl(140); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000141() { edt_monotone_under_added_sources_impl(141); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000142() { edt_monotone_under_added_sources_impl(142); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000143() { edt_monotone_under_added_sources_impl(143); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000144() { edt_monotone_under_added_sources_impl(144); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000145() { edt_monotone_under_added_sources_impl(145); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000146() { edt_monotone_under_added_sources_impl(146); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000147() { edt_monotone_under_added_sources_impl(147); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000148() { edt_monotone_under_added_sources_impl(148); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000149() { edt_monotone_under_added_sources_impl(149); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000150() { edt_monotone_under_added_sources_impl(150); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000151() { edt_monotone_under_added_sources_impl(151); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000152() { edt_monotone_under_added_sources_impl(152); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000153() { edt_monotone_under_added_sources_impl(153); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000154() { edt_monotone_under_added_sources_impl(154); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000155() { edt_monotone_under_added_sources_impl(155); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000156() { edt_monotone_under_added_sources_impl(156); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000157() { edt_monotone_under_added_sources_impl(157); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000158() { edt_monotone_under_added_sources_impl(158); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000159() { edt_monotone_under_added_sources_impl(159); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000160() { edt_monotone_under_added_sources_impl(160); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000161() { edt_monotone_under_added_sources_impl(161); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000162() { edt_monotone_under_added_sources_impl(162); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000163() { edt_monotone_under_added_sources_impl(163); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000164() { edt_monotone_under_added_sources_impl(164); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000165() { edt_monotone_under_added_sources_impl(165); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000166() { edt_monotone_under_added_sources_impl(166); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000167() { edt_monotone_under_added_sources_impl(167); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000168() { edt_monotone_under_added_sources_impl(168); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000169() { edt_monotone_under_added_sources_impl(169); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000170() { edt_monotone_under_added_sources_impl(170); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000171() { edt_monotone_under_added_sources_impl(171); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000172() { edt_monotone_under_added_sources_impl(172); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000173() { edt_monotone_under_added_sources_impl(173); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000174() { edt_monotone_under_added_sources_impl(174); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000175() { edt_monotone_under_added_sources_impl(175); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000176() { edt_monotone_under_added_sources_impl(176); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000177() { edt_monotone_under_added_sources_impl(177); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000178() { edt_monotone_under_added_sources_impl(178); }
    #[cfg_attr(test, test)]
    fn edt_monotone_added_sources_seed_000179() { edt_monotone_under_added_sources_impl(179); }
    // --- hypot_symmetric: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000000() { hypot_symmetric_impl(0); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000001() { hypot_symmetric_impl(1); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000002() { hypot_symmetric_impl(2); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000003() { hypot_symmetric_impl(3); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000004() { hypot_symmetric_impl(4); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000005() { hypot_symmetric_impl(5); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000006() { hypot_symmetric_impl(6); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000007() { hypot_symmetric_impl(7); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000008() { hypot_symmetric_impl(8); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000009() { hypot_symmetric_impl(9); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000010() { hypot_symmetric_impl(10); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000011() { hypot_symmetric_impl(11); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000012() { hypot_symmetric_impl(12); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000013() { hypot_symmetric_impl(13); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000014() { hypot_symmetric_impl(14); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000015() { hypot_symmetric_impl(15); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000016() { hypot_symmetric_impl(16); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000017() { hypot_symmetric_impl(17); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000018() { hypot_symmetric_impl(18); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000019() { hypot_symmetric_impl(19); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000020() { hypot_symmetric_impl(20); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000021() { hypot_symmetric_impl(21); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000022() { hypot_symmetric_impl(22); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000023() { hypot_symmetric_impl(23); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000024() { hypot_symmetric_impl(24); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000025() { hypot_symmetric_impl(25); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000026() { hypot_symmetric_impl(26); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000027() { hypot_symmetric_impl(27); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000028() { hypot_symmetric_impl(28); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000029() { hypot_symmetric_impl(29); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000030() { hypot_symmetric_impl(30); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000031() { hypot_symmetric_impl(31); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000032() { hypot_symmetric_impl(32); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000033() { hypot_symmetric_impl(33); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000034() { hypot_symmetric_impl(34); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000035() { hypot_symmetric_impl(35); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000036() { hypot_symmetric_impl(36); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000037() { hypot_symmetric_impl(37); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000038() { hypot_symmetric_impl(38); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000039() { hypot_symmetric_impl(39); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000040() { hypot_symmetric_impl(40); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000041() { hypot_symmetric_impl(41); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000042() { hypot_symmetric_impl(42); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000043() { hypot_symmetric_impl(43); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000044() { hypot_symmetric_impl(44); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000045() { hypot_symmetric_impl(45); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000046() { hypot_symmetric_impl(46); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000047() { hypot_symmetric_impl(47); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000048() { hypot_symmetric_impl(48); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000049() { hypot_symmetric_impl(49); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000050() { hypot_symmetric_impl(50); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000051() { hypot_symmetric_impl(51); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000052() { hypot_symmetric_impl(52); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000053() { hypot_symmetric_impl(53); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000054() { hypot_symmetric_impl(54); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000055() { hypot_symmetric_impl(55); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000056() { hypot_symmetric_impl(56); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000057() { hypot_symmetric_impl(57); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000058() { hypot_symmetric_impl(58); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000059() { hypot_symmetric_impl(59); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000060() { hypot_symmetric_impl(60); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000061() { hypot_symmetric_impl(61); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000062() { hypot_symmetric_impl(62); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000063() { hypot_symmetric_impl(63); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000064() { hypot_symmetric_impl(64); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000065() { hypot_symmetric_impl(65); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000066() { hypot_symmetric_impl(66); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000067() { hypot_symmetric_impl(67); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000068() { hypot_symmetric_impl(68); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000069() { hypot_symmetric_impl(69); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000070() { hypot_symmetric_impl(70); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000071() { hypot_symmetric_impl(71); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000072() { hypot_symmetric_impl(72); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000073() { hypot_symmetric_impl(73); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000074() { hypot_symmetric_impl(74); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000075() { hypot_symmetric_impl(75); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000076() { hypot_symmetric_impl(76); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000077() { hypot_symmetric_impl(77); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000078() { hypot_symmetric_impl(78); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000079() { hypot_symmetric_impl(79); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000080() { hypot_symmetric_impl(80); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000081() { hypot_symmetric_impl(81); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000082() { hypot_symmetric_impl(82); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000083() { hypot_symmetric_impl(83); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000084() { hypot_symmetric_impl(84); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000085() { hypot_symmetric_impl(85); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000086() { hypot_symmetric_impl(86); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000087() { hypot_symmetric_impl(87); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000088() { hypot_symmetric_impl(88); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000089() { hypot_symmetric_impl(89); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000090() { hypot_symmetric_impl(90); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000091() { hypot_symmetric_impl(91); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000092() { hypot_symmetric_impl(92); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000093() { hypot_symmetric_impl(93); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000094() { hypot_symmetric_impl(94); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000095() { hypot_symmetric_impl(95); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000096() { hypot_symmetric_impl(96); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000097() { hypot_symmetric_impl(97); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000098() { hypot_symmetric_impl(98); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000099() { hypot_symmetric_impl(99); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000100() { hypot_symmetric_impl(100); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000101() { hypot_symmetric_impl(101); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000102() { hypot_symmetric_impl(102); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000103() { hypot_symmetric_impl(103); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000104() { hypot_symmetric_impl(104); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000105() { hypot_symmetric_impl(105); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000106() { hypot_symmetric_impl(106); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000107() { hypot_symmetric_impl(107); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000108() { hypot_symmetric_impl(108); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000109() { hypot_symmetric_impl(109); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000110() { hypot_symmetric_impl(110); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000111() { hypot_symmetric_impl(111); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000112() { hypot_symmetric_impl(112); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000113() { hypot_symmetric_impl(113); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000114() { hypot_symmetric_impl(114); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000115() { hypot_symmetric_impl(115); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000116() { hypot_symmetric_impl(116); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000117() { hypot_symmetric_impl(117); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000118() { hypot_symmetric_impl(118); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000119() { hypot_symmetric_impl(119); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000120() { hypot_symmetric_impl(120); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000121() { hypot_symmetric_impl(121); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000122() { hypot_symmetric_impl(122); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000123() { hypot_symmetric_impl(123); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000124() { hypot_symmetric_impl(124); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000125() { hypot_symmetric_impl(125); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000126() { hypot_symmetric_impl(126); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000127() { hypot_symmetric_impl(127); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000128() { hypot_symmetric_impl(128); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000129() { hypot_symmetric_impl(129); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000130() { hypot_symmetric_impl(130); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000131() { hypot_symmetric_impl(131); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000132() { hypot_symmetric_impl(132); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000133() { hypot_symmetric_impl(133); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000134() { hypot_symmetric_impl(134); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000135() { hypot_symmetric_impl(135); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000136() { hypot_symmetric_impl(136); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000137() { hypot_symmetric_impl(137); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000138() { hypot_symmetric_impl(138); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000139() { hypot_symmetric_impl(139); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000140() { hypot_symmetric_impl(140); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000141() { hypot_symmetric_impl(141); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000142() { hypot_symmetric_impl(142); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000143() { hypot_symmetric_impl(143); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000144() { hypot_symmetric_impl(144); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000145() { hypot_symmetric_impl(145); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000146() { hypot_symmetric_impl(146); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000147() { hypot_symmetric_impl(147); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000148() { hypot_symmetric_impl(148); }
    #[cfg_attr(test, test)]
    fn hypot_symmetric_seed_000149() { hypot_symmetric_impl(149); }
    // --- hypot_scale_invariant: 170 generated seeds ---
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000000() { hypot_scale_invariant_impl(0); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000001() { hypot_scale_invariant_impl(1); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000002() { hypot_scale_invariant_impl(2); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000003() { hypot_scale_invariant_impl(3); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000004() { hypot_scale_invariant_impl(4); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000005() { hypot_scale_invariant_impl(5); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000006() { hypot_scale_invariant_impl(6); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000007() { hypot_scale_invariant_impl(7); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000008() { hypot_scale_invariant_impl(8); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000009() { hypot_scale_invariant_impl(9); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000010() { hypot_scale_invariant_impl(10); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000011() { hypot_scale_invariant_impl(11); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000012() { hypot_scale_invariant_impl(12); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000013() { hypot_scale_invariant_impl(13); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000014() { hypot_scale_invariant_impl(14); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000015() { hypot_scale_invariant_impl(15); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000016() { hypot_scale_invariant_impl(16); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000017() { hypot_scale_invariant_impl(17); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000018() { hypot_scale_invariant_impl(18); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000019() { hypot_scale_invariant_impl(19); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000020() { hypot_scale_invariant_impl(20); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000021() { hypot_scale_invariant_impl(21); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000022() { hypot_scale_invariant_impl(22); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000023() { hypot_scale_invariant_impl(23); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000024() { hypot_scale_invariant_impl(24); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000025() { hypot_scale_invariant_impl(25); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000026() { hypot_scale_invariant_impl(26); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000027() { hypot_scale_invariant_impl(27); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000028() { hypot_scale_invariant_impl(28); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000029() { hypot_scale_invariant_impl(29); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000030() { hypot_scale_invariant_impl(30); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000031() { hypot_scale_invariant_impl(31); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000032() { hypot_scale_invariant_impl(32); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000033() { hypot_scale_invariant_impl(33); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000034() { hypot_scale_invariant_impl(34); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000035() { hypot_scale_invariant_impl(35); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000036() { hypot_scale_invariant_impl(36); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000037() { hypot_scale_invariant_impl(37); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000038() { hypot_scale_invariant_impl(38); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000039() { hypot_scale_invariant_impl(39); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000040() { hypot_scale_invariant_impl(40); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000041() { hypot_scale_invariant_impl(41); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000042() { hypot_scale_invariant_impl(42); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000043() { hypot_scale_invariant_impl(43); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000044() { hypot_scale_invariant_impl(44); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000045() { hypot_scale_invariant_impl(45); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000046() { hypot_scale_invariant_impl(46); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000047() { hypot_scale_invariant_impl(47); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000048() { hypot_scale_invariant_impl(48); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000049() { hypot_scale_invariant_impl(49); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000050() { hypot_scale_invariant_impl(50); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000051() { hypot_scale_invariant_impl(51); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000052() { hypot_scale_invariant_impl(52); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000053() { hypot_scale_invariant_impl(53); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000054() { hypot_scale_invariant_impl(54); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000055() { hypot_scale_invariant_impl(55); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000056() { hypot_scale_invariant_impl(56); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000057() { hypot_scale_invariant_impl(57); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000058() { hypot_scale_invariant_impl(58); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000059() { hypot_scale_invariant_impl(59); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000060() { hypot_scale_invariant_impl(60); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000061() { hypot_scale_invariant_impl(61); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000062() { hypot_scale_invariant_impl(62); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000063() { hypot_scale_invariant_impl(63); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000064() { hypot_scale_invariant_impl(64); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000065() { hypot_scale_invariant_impl(65); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000066() { hypot_scale_invariant_impl(66); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000067() { hypot_scale_invariant_impl(67); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000068() { hypot_scale_invariant_impl(68); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000069() { hypot_scale_invariant_impl(69); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000070() { hypot_scale_invariant_impl(70); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000071() { hypot_scale_invariant_impl(71); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000072() { hypot_scale_invariant_impl(72); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000073() { hypot_scale_invariant_impl(73); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000074() { hypot_scale_invariant_impl(74); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000075() { hypot_scale_invariant_impl(75); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000076() { hypot_scale_invariant_impl(76); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000077() { hypot_scale_invariant_impl(77); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000078() { hypot_scale_invariant_impl(78); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000079() { hypot_scale_invariant_impl(79); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000080() { hypot_scale_invariant_impl(80); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000081() { hypot_scale_invariant_impl(81); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000082() { hypot_scale_invariant_impl(82); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000083() { hypot_scale_invariant_impl(83); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000084() { hypot_scale_invariant_impl(84); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000085() { hypot_scale_invariant_impl(85); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000086() { hypot_scale_invariant_impl(86); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000087() { hypot_scale_invariant_impl(87); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000088() { hypot_scale_invariant_impl(88); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000089() { hypot_scale_invariant_impl(89); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000090() { hypot_scale_invariant_impl(90); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000091() { hypot_scale_invariant_impl(91); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000092() { hypot_scale_invariant_impl(92); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000093() { hypot_scale_invariant_impl(93); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000094() { hypot_scale_invariant_impl(94); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000095() { hypot_scale_invariant_impl(95); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000096() { hypot_scale_invariant_impl(96); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000097() { hypot_scale_invariant_impl(97); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000098() { hypot_scale_invariant_impl(98); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000099() { hypot_scale_invariant_impl(99); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000100() { hypot_scale_invariant_impl(100); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000101() { hypot_scale_invariant_impl(101); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000102() { hypot_scale_invariant_impl(102); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000103() { hypot_scale_invariant_impl(103); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000104() { hypot_scale_invariant_impl(104); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000105() { hypot_scale_invariant_impl(105); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000106() { hypot_scale_invariant_impl(106); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000107() { hypot_scale_invariant_impl(107); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000108() { hypot_scale_invariant_impl(108); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000109() { hypot_scale_invariant_impl(109); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000110() { hypot_scale_invariant_impl(110); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000111() { hypot_scale_invariant_impl(111); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000112() { hypot_scale_invariant_impl(112); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000113() { hypot_scale_invariant_impl(113); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000114() { hypot_scale_invariant_impl(114); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000115() { hypot_scale_invariant_impl(115); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000116() { hypot_scale_invariant_impl(116); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000117() { hypot_scale_invariant_impl(117); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000118() { hypot_scale_invariant_impl(118); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000119() { hypot_scale_invariant_impl(119); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000120() { hypot_scale_invariant_impl(120); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000121() { hypot_scale_invariant_impl(121); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000122() { hypot_scale_invariant_impl(122); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000123() { hypot_scale_invariant_impl(123); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000124() { hypot_scale_invariant_impl(124); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000125() { hypot_scale_invariant_impl(125); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000126() { hypot_scale_invariant_impl(126); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000127() { hypot_scale_invariant_impl(127); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000128() { hypot_scale_invariant_impl(128); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000129() { hypot_scale_invariant_impl(129); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000130() { hypot_scale_invariant_impl(130); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000131() { hypot_scale_invariant_impl(131); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000132() { hypot_scale_invariant_impl(132); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000133() { hypot_scale_invariant_impl(133); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000134() { hypot_scale_invariant_impl(134); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000135() { hypot_scale_invariant_impl(135); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000136() { hypot_scale_invariant_impl(136); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000137() { hypot_scale_invariant_impl(137); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000138() { hypot_scale_invariant_impl(138); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000139() { hypot_scale_invariant_impl(139); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000140() { hypot_scale_invariant_impl(140); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000141() { hypot_scale_invariant_impl(141); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000142() { hypot_scale_invariant_impl(142); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000143() { hypot_scale_invariant_impl(143); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000144() { hypot_scale_invariant_impl(144); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000145() { hypot_scale_invariant_impl(145); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000146() { hypot_scale_invariant_impl(146); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000147() { hypot_scale_invariant_impl(147); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000148() { hypot_scale_invariant_impl(148); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000149() { hypot_scale_invariant_impl(149); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000150() { hypot_scale_invariant_impl(150); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000151() { hypot_scale_invariant_impl(151); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000152() { hypot_scale_invariant_impl(152); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000153() { hypot_scale_invariant_impl(153); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000154() { hypot_scale_invariant_impl(154); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000155() { hypot_scale_invariant_impl(155); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000156() { hypot_scale_invariant_impl(156); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000157() { hypot_scale_invariant_impl(157); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000158() { hypot_scale_invariant_impl(158); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000159() { hypot_scale_invariant_impl(159); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000160() { hypot_scale_invariant_impl(160); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000161() { hypot_scale_invariant_impl(161); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000162() { hypot_scale_invariant_impl(162); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000163() { hypot_scale_invariant_impl(163); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000164() { hypot_scale_invariant_impl(164); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000165() { hypot_scale_invariant_impl(165); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000166() { hypot_scale_invariant_impl(166); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000167() { hypot_scale_invariant_impl(167); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000168() { hypot_scale_invariant_impl(168); }
    #[cfg_attr(test, test)]
    fn hypot_scale_invariant_seed_000169() { hypot_scale_invariant_impl(169); }
    // --- bounding_radius_monotonic_width: 200 generated seeds ---
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000000() { bounding_radius_monotonic_in_width_impl(0); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000001() { bounding_radius_monotonic_in_width_impl(1); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000002() { bounding_radius_monotonic_in_width_impl(2); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000003() { bounding_radius_monotonic_in_width_impl(3); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000004() { bounding_radius_monotonic_in_width_impl(4); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000005() { bounding_radius_monotonic_in_width_impl(5); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000006() { bounding_radius_monotonic_in_width_impl(6); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000007() { bounding_radius_monotonic_in_width_impl(7); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000008() { bounding_radius_monotonic_in_width_impl(8); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000009() { bounding_radius_monotonic_in_width_impl(9); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000010() { bounding_radius_monotonic_in_width_impl(10); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000011() { bounding_radius_monotonic_in_width_impl(11); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000012() { bounding_radius_monotonic_in_width_impl(12); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000013() { bounding_radius_monotonic_in_width_impl(13); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000014() { bounding_radius_monotonic_in_width_impl(14); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000015() { bounding_radius_monotonic_in_width_impl(15); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000016() { bounding_radius_monotonic_in_width_impl(16); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000017() { bounding_radius_monotonic_in_width_impl(17); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000018() { bounding_radius_monotonic_in_width_impl(18); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000019() { bounding_radius_monotonic_in_width_impl(19); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000020() { bounding_radius_monotonic_in_width_impl(20); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000021() { bounding_radius_monotonic_in_width_impl(21); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000022() { bounding_radius_monotonic_in_width_impl(22); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000023() { bounding_radius_monotonic_in_width_impl(23); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000024() { bounding_radius_monotonic_in_width_impl(24); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000025() { bounding_radius_monotonic_in_width_impl(25); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000026() { bounding_radius_monotonic_in_width_impl(26); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000027() { bounding_radius_monotonic_in_width_impl(27); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000028() { bounding_radius_monotonic_in_width_impl(28); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000029() { bounding_radius_monotonic_in_width_impl(29); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000030() { bounding_radius_monotonic_in_width_impl(30); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000031() { bounding_radius_monotonic_in_width_impl(31); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000032() { bounding_radius_monotonic_in_width_impl(32); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000033() { bounding_radius_monotonic_in_width_impl(33); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000034() { bounding_radius_monotonic_in_width_impl(34); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000035() { bounding_radius_monotonic_in_width_impl(35); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000036() { bounding_radius_monotonic_in_width_impl(36); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000037() { bounding_radius_monotonic_in_width_impl(37); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000038() { bounding_radius_monotonic_in_width_impl(38); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000039() { bounding_radius_monotonic_in_width_impl(39); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000040() { bounding_radius_monotonic_in_width_impl(40); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000041() { bounding_radius_monotonic_in_width_impl(41); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000042() { bounding_radius_monotonic_in_width_impl(42); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000043() { bounding_radius_monotonic_in_width_impl(43); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000044() { bounding_radius_monotonic_in_width_impl(44); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000045() { bounding_radius_monotonic_in_width_impl(45); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000046() { bounding_radius_monotonic_in_width_impl(46); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000047() { bounding_radius_monotonic_in_width_impl(47); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000048() { bounding_radius_monotonic_in_width_impl(48); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000049() { bounding_radius_monotonic_in_width_impl(49); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000050() { bounding_radius_monotonic_in_width_impl(50); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000051() { bounding_radius_monotonic_in_width_impl(51); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000052() { bounding_radius_monotonic_in_width_impl(52); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000053() { bounding_radius_monotonic_in_width_impl(53); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000054() { bounding_radius_monotonic_in_width_impl(54); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000055() { bounding_radius_monotonic_in_width_impl(55); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000056() { bounding_radius_monotonic_in_width_impl(56); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000057() { bounding_radius_monotonic_in_width_impl(57); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000058() { bounding_radius_monotonic_in_width_impl(58); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000059() { bounding_radius_monotonic_in_width_impl(59); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000060() { bounding_radius_monotonic_in_width_impl(60); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000061() { bounding_radius_monotonic_in_width_impl(61); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000062() { bounding_radius_monotonic_in_width_impl(62); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000063() { bounding_radius_monotonic_in_width_impl(63); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000064() { bounding_radius_monotonic_in_width_impl(64); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000065() { bounding_radius_monotonic_in_width_impl(65); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000066() { bounding_radius_monotonic_in_width_impl(66); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000067() { bounding_radius_monotonic_in_width_impl(67); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000068() { bounding_radius_monotonic_in_width_impl(68); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000069() { bounding_radius_monotonic_in_width_impl(69); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000070() { bounding_radius_monotonic_in_width_impl(70); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000071() { bounding_radius_monotonic_in_width_impl(71); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000072() { bounding_radius_monotonic_in_width_impl(72); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000073() { bounding_radius_monotonic_in_width_impl(73); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000074() { bounding_radius_monotonic_in_width_impl(74); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000075() { bounding_radius_monotonic_in_width_impl(75); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000076() { bounding_radius_monotonic_in_width_impl(76); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000077() { bounding_radius_monotonic_in_width_impl(77); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000078() { bounding_radius_monotonic_in_width_impl(78); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000079() { bounding_radius_monotonic_in_width_impl(79); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000080() { bounding_radius_monotonic_in_width_impl(80); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000081() { bounding_radius_monotonic_in_width_impl(81); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000082() { bounding_radius_monotonic_in_width_impl(82); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000083() { bounding_radius_monotonic_in_width_impl(83); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000084() { bounding_radius_monotonic_in_width_impl(84); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000085() { bounding_radius_monotonic_in_width_impl(85); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000086() { bounding_radius_monotonic_in_width_impl(86); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000087() { bounding_radius_monotonic_in_width_impl(87); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000088() { bounding_radius_monotonic_in_width_impl(88); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000089() { bounding_radius_monotonic_in_width_impl(89); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000090() { bounding_radius_monotonic_in_width_impl(90); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000091() { bounding_radius_monotonic_in_width_impl(91); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000092() { bounding_radius_monotonic_in_width_impl(92); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000093() { bounding_radius_monotonic_in_width_impl(93); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000094() { bounding_radius_monotonic_in_width_impl(94); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000095() { bounding_radius_monotonic_in_width_impl(95); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000096() { bounding_radius_monotonic_in_width_impl(96); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000097() { bounding_radius_monotonic_in_width_impl(97); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000098() { bounding_radius_monotonic_in_width_impl(98); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000099() { bounding_radius_monotonic_in_width_impl(99); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000100() { bounding_radius_monotonic_in_width_impl(100); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000101() { bounding_radius_monotonic_in_width_impl(101); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000102() { bounding_radius_monotonic_in_width_impl(102); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000103() { bounding_radius_monotonic_in_width_impl(103); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000104() { bounding_radius_monotonic_in_width_impl(104); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000105() { bounding_radius_monotonic_in_width_impl(105); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000106() { bounding_radius_monotonic_in_width_impl(106); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000107() { bounding_radius_monotonic_in_width_impl(107); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000108() { bounding_radius_monotonic_in_width_impl(108); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000109() { bounding_radius_monotonic_in_width_impl(109); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000110() { bounding_radius_monotonic_in_width_impl(110); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000111() { bounding_radius_monotonic_in_width_impl(111); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000112() { bounding_radius_monotonic_in_width_impl(112); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000113() { bounding_radius_monotonic_in_width_impl(113); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000114() { bounding_radius_monotonic_in_width_impl(114); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000115() { bounding_radius_monotonic_in_width_impl(115); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000116() { bounding_radius_monotonic_in_width_impl(116); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000117() { bounding_radius_monotonic_in_width_impl(117); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000118() { bounding_radius_monotonic_in_width_impl(118); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000119() { bounding_radius_monotonic_in_width_impl(119); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000120() { bounding_radius_monotonic_in_width_impl(120); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000121() { bounding_radius_monotonic_in_width_impl(121); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000122() { bounding_radius_monotonic_in_width_impl(122); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000123() { bounding_radius_monotonic_in_width_impl(123); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000124() { bounding_radius_monotonic_in_width_impl(124); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000125() { bounding_radius_monotonic_in_width_impl(125); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000126() { bounding_radius_monotonic_in_width_impl(126); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000127() { bounding_radius_monotonic_in_width_impl(127); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000128() { bounding_radius_monotonic_in_width_impl(128); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000129() { bounding_radius_monotonic_in_width_impl(129); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000130() { bounding_radius_monotonic_in_width_impl(130); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000131() { bounding_radius_monotonic_in_width_impl(131); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000132() { bounding_radius_monotonic_in_width_impl(132); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000133() { bounding_radius_monotonic_in_width_impl(133); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000134() { bounding_radius_monotonic_in_width_impl(134); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000135() { bounding_radius_monotonic_in_width_impl(135); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000136() { bounding_radius_monotonic_in_width_impl(136); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000137() { bounding_radius_monotonic_in_width_impl(137); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000138() { bounding_radius_monotonic_in_width_impl(138); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000139() { bounding_radius_monotonic_in_width_impl(139); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000140() { bounding_radius_monotonic_in_width_impl(140); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000141() { bounding_radius_monotonic_in_width_impl(141); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000142() { bounding_radius_monotonic_in_width_impl(142); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000143() { bounding_radius_monotonic_in_width_impl(143); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000144() { bounding_radius_monotonic_in_width_impl(144); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000145() { bounding_radius_monotonic_in_width_impl(145); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000146() { bounding_radius_monotonic_in_width_impl(146); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000147() { bounding_radius_monotonic_in_width_impl(147); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000148() { bounding_radius_monotonic_in_width_impl(148); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000149() { bounding_radius_monotonic_in_width_impl(149); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000150() { bounding_radius_monotonic_in_width_impl(150); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000151() { bounding_radius_monotonic_in_width_impl(151); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000152() { bounding_radius_monotonic_in_width_impl(152); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000153() { bounding_radius_monotonic_in_width_impl(153); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000154() { bounding_radius_monotonic_in_width_impl(154); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000155() { bounding_radius_monotonic_in_width_impl(155); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000156() { bounding_radius_monotonic_in_width_impl(156); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000157() { bounding_radius_monotonic_in_width_impl(157); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000158() { bounding_radius_monotonic_in_width_impl(158); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000159() { bounding_radius_monotonic_in_width_impl(159); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000160() { bounding_radius_monotonic_in_width_impl(160); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000161() { bounding_radius_monotonic_in_width_impl(161); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000162() { bounding_radius_monotonic_in_width_impl(162); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000163() { bounding_radius_monotonic_in_width_impl(163); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000164() { bounding_radius_monotonic_in_width_impl(164); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000165() { bounding_radius_monotonic_in_width_impl(165); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000166() { bounding_radius_monotonic_in_width_impl(166); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000167() { bounding_radius_monotonic_in_width_impl(167); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000168() { bounding_radius_monotonic_in_width_impl(168); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000169() { bounding_radius_monotonic_in_width_impl(169); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000170() { bounding_radius_monotonic_in_width_impl(170); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000171() { bounding_radius_monotonic_in_width_impl(171); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000172() { bounding_radius_monotonic_in_width_impl(172); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000173() { bounding_radius_monotonic_in_width_impl(173); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000174() { bounding_radius_monotonic_in_width_impl(174); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000175() { bounding_radius_monotonic_in_width_impl(175); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000176() { bounding_radius_monotonic_in_width_impl(176); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000177() { bounding_radius_monotonic_in_width_impl(177); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000178() { bounding_radius_monotonic_in_width_impl(178); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000179() { bounding_radius_monotonic_in_width_impl(179); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000180() { bounding_radius_monotonic_in_width_impl(180); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000181() { bounding_radius_monotonic_in_width_impl(181); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000182() { bounding_radius_monotonic_in_width_impl(182); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000183() { bounding_radius_monotonic_in_width_impl(183); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000184() { bounding_radius_monotonic_in_width_impl(184); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000185() { bounding_radius_monotonic_in_width_impl(185); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000186() { bounding_radius_monotonic_in_width_impl(186); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000187() { bounding_radius_monotonic_in_width_impl(187); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000188() { bounding_radius_monotonic_in_width_impl(188); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000189() { bounding_radius_monotonic_in_width_impl(189); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000190() { bounding_radius_monotonic_in_width_impl(190); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000191() { bounding_radius_monotonic_in_width_impl(191); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000192() { bounding_radius_monotonic_in_width_impl(192); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000193() { bounding_radius_monotonic_in_width_impl(193); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000194() { bounding_radius_monotonic_in_width_impl(194); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000195() { bounding_radius_monotonic_in_width_impl(195); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000196() { bounding_radius_monotonic_in_width_impl(196); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000197() { bounding_radius_monotonic_in_width_impl(197); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000198() { bounding_radius_monotonic_in_width_impl(198); }
    #[cfg_attr(test, test)]
    fn bounding_radius_monotonic_width_seed_000199() { bounding_radius_monotonic_in_width_impl(199); }
    // --- core_half_extents_sum_identity: 160 generated seeds ---
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000000() { core_half_extents_sum_identity_impl(0); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000001() { core_half_extents_sum_identity_impl(1); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000002() { core_half_extents_sum_identity_impl(2); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000003() { core_half_extents_sum_identity_impl(3); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000004() { core_half_extents_sum_identity_impl(4); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000005() { core_half_extents_sum_identity_impl(5); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000006() { core_half_extents_sum_identity_impl(6); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000007() { core_half_extents_sum_identity_impl(7); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000008() { core_half_extents_sum_identity_impl(8); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000009() { core_half_extents_sum_identity_impl(9); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000010() { core_half_extents_sum_identity_impl(10); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000011() { core_half_extents_sum_identity_impl(11); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000012() { core_half_extents_sum_identity_impl(12); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000013() { core_half_extents_sum_identity_impl(13); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000014() { core_half_extents_sum_identity_impl(14); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000015() { core_half_extents_sum_identity_impl(15); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000016() { core_half_extents_sum_identity_impl(16); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000017() { core_half_extents_sum_identity_impl(17); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000018() { core_half_extents_sum_identity_impl(18); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000019() { core_half_extents_sum_identity_impl(19); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000020() { core_half_extents_sum_identity_impl(20); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000021() { core_half_extents_sum_identity_impl(21); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000022() { core_half_extents_sum_identity_impl(22); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000023() { core_half_extents_sum_identity_impl(23); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000024() { core_half_extents_sum_identity_impl(24); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000025() { core_half_extents_sum_identity_impl(25); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000026() { core_half_extents_sum_identity_impl(26); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000027() { core_half_extents_sum_identity_impl(27); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000028() { core_half_extents_sum_identity_impl(28); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000029() { core_half_extents_sum_identity_impl(29); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000030() { core_half_extents_sum_identity_impl(30); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000031() { core_half_extents_sum_identity_impl(31); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000032() { core_half_extents_sum_identity_impl(32); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000033() { core_half_extents_sum_identity_impl(33); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000034() { core_half_extents_sum_identity_impl(34); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000035() { core_half_extents_sum_identity_impl(35); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000036() { core_half_extents_sum_identity_impl(36); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000037() { core_half_extents_sum_identity_impl(37); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000038() { core_half_extents_sum_identity_impl(38); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000039() { core_half_extents_sum_identity_impl(39); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000040() { core_half_extents_sum_identity_impl(40); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000041() { core_half_extents_sum_identity_impl(41); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000042() { core_half_extents_sum_identity_impl(42); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000043() { core_half_extents_sum_identity_impl(43); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000044() { core_half_extents_sum_identity_impl(44); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000045() { core_half_extents_sum_identity_impl(45); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000046() { core_half_extents_sum_identity_impl(46); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000047() { core_half_extents_sum_identity_impl(47); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000048() { core_half_extents_sum_identity_impl(48); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000049() { core_half_extents_sum_identity_impl(49); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000050() { core_half_extents_sum_identity_impl(50); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000051() { core_half_extents_sum_identity_impl(51); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000052() { core_half_extents_sum_identity_impl(52); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000053() { core_half_extents_sum_identity_impl(53); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000054() { core_half_extents_sum_identity_impl(54); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000055() { core_half_extents_sum_identity_impl(55); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000056() { core_half_extents_sum_identity_impl(56); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000057() { core_half_extents_sum_identity_impl(57); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000058() { core_half_extents_sum_identity_impl(58); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000059() { core_half_extents_sum_identity_impl(59); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000060() { core_half_extents_sum_identity_impl(60); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000061() { core_half_extents_sum_identity_impl(61); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000062() { core_half_extents_sum_identity_impl(62); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000063() { core_half_extents_sum_identity_impl(63); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000064() { core_half_extents_sum_identity_impl(64); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000065() { core_half_extents_sum_identity_impl(65); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000066() { core_half_extents_sum_identity_impl(66); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000067() { core_half_extents_sum_identity_impl(67); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000068() { core_half_extents_sum_identity_impl(68); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000069() { core_half_extents_sum_identity_impl(69); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000070() { core_half_extents_sum_identity_impl(70); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000071() { core_half_extents_sum_identity_impl(71); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000072() { core_half_extents_sum_identity_impl(72); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000073() { core_half_extents_sum_identity_impl(73); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000074() { core_half_extents_sum_identity_impl(74); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000075() { core_half_extents_sum_identity_impl(75); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000076() { core_half_extents_sum_identity_impl(76); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000077() { core_half_extents_sum_identity_impl(77); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000078() { core_half_extents_sum_identity_impl(78); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000079() { core_half_extents_sum_identity_impl(79); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000080() { core_half_extents_sum_identity_impl(80); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000081() { core_half_extents_sum_identity_impl(81); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000082() { core_half_extents_sum_identity_impl(82); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000083() { core_half_extents_sum_identity_impl(83); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000084() { core_half_extents_sum_identity_impl(84); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000085() { core_half_extents_sum_identity_impl(85); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000086() { core_half_extents_sum_identity_impl(86); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000087() { core_half_extents_sum_identity_impl(87); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000088() { core_half_extents_sum_identity_impl(88); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000089() { core_half_extents_sum_identity_impl(89); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000090() { core_half_extents_sum_identity_impl(90); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000091() { core_half_extents_sum_identity_impl(91); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000092() { core_half_extents_sum_identity_impl(92); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000093() { core_half_extents_sum_identity_impl(93); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000094() { core_half_extents_sum_identity_impl(94); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000095() { core_half_extents_sum_identity_impl(95); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000096() { core_half_extents_sum_identity_impl(96); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000097() { core_half_extents_sum_identity_impl(97); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000098() { core_half_extents_sum_identity_impl(98); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000099() { core_half_extents_sum_identity_impl(99); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000100() { core_half_extents_sum_identity_impl(100); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000101() { core_half_extents_sum_identity_impl(101); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000102() { core_half_extents_sum_identity_impl(102); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000103() { core_half_extents_sum_identity_impl(103); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000104() { core_half_extents_sum_identity_impl(104); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000105() { core_half_extents_sum_identity_impl(105); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000106() { core_half_extents_sum_identity_impl(106); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000107() { core_half_extents_sum_identity_impl(107); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000108() { core_half_extents_sum_identity_impl(108); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000109() { core_half_extents_sum_identity_impl(109); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000110() { core_half_extents_sum_identity_impl(110); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000111() { core_half_extents_sum_identity_impl(111); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000112() { core_half_extents_sum_identity_impl(112); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000113() { core_half_extents_sum_identity_impl(113); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000114() { core_half_extents_sum_identity_impl(114); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000115() { core_half_extents_sum_identity_impl(115); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000116() { core_half_extents_sum_identity_impl(116); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000117() { core_half_extents_sum_identity_impl(117); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000118() { core_half_extents_sum_identity_impl(118); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000119() { core_half_extents_sum_identity_impl(119); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000120() { core_half_extents_sum_identity_impl(120); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000121() { core_half_extents_sum_identity_impl(121); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000122() { core_half_extents_sum_identity_impl(122); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000123() { core_half_extents_sum_identity_impl(123); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000124() { core_half_extents_sum_identity_impl(124); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000125() { core_half_extents_sum_identity_impl(125); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000126() { core_half_extents_sum_identity_impl(126); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000127() { core_half_extents_sum_identity_impl(127); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000128() { core_half_extents_sum_identity_impl(128); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000129() { core_half_extents_sum_identity_impl(129); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000130() { core_half_extents_sum_identity_impl(130); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000131() { core_half_extents_sum_identity_impl(131); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000132() { core_half_extents_sum_identity_impl(132); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000133() { core_half_extents_sum_identity_impl(133); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000134() { core_half_extents_sum_identity_impl(134); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000135() { core_half_extents_sum_identity_impl(135); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000136() { core_half_extents_sum_identity_impl(136); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000137() { core_half_extents_sum_identity_impl(137); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000138() { core_half_extents_sum_identity_impl(138); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000139() { core_half_extents_sum_identity_impl(139); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000140() { core_half_extents_sum_identity_impl(140); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000141() { core_half_extents_sum_identity_impl(141); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000142() { core_half_extents_sum_identity_impl(142); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000143() { core_half_extents_sum_identity_impl(143); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000144() { core_half_extents_sum_identity_impl(144); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000145() { core_half_extents_sum_identity_impl(145); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000146() { core_half_extents_sum_identity_impl(146); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000147() { core_half_extents_sum_identity_impl(147); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000148() { core_half_extents_sum_identity_impl(148); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000149() { core_half_extents_sum_identity_impl(149); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000150() { core_half_extents_sum_identity_impl(150); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000151() { core_half_extents_sum_identity_impl(151); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000152() { core_half_extents_sum_identity_impl(152); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000153() { core_half_extents_sum_identity_impl(153); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000154() { core_half_extents_sum_identity_impl(154); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000155() { core_half_extents_sum_identity_impl(155); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000156() { core_half_extents_sum_identity_impl(156); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000157() { core_half_extents_sum_identity_impl(157); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000158() { core_half_extents_sum_identity_impl(158); }
    #[cfg_attr(test, test)]
    fn core_half_extents_sum_identity_seed_000159() { core_half_extents_sum_identity_impl(159); }
    // --- copper_reach_scale_law: 180 generated seeds ---
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000000() { copper_reach_scale_law_impl(0); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000001() { copper_reach_scale_law_impl(1); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000002() { copper_reach_scale_law_impl(2); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000003() { copper_reach_scale_law_impl(3); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000004() { copper_reach_scale_law_impl(4); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000005() { copper_reach_scale_law_impl(5); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000006() { copper_reach_scale_law_impl(6); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000007() { copper_reach_scale_law_impl(7); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000008() { copper_reach_scale_law_impl(8); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000009() { copper_reach_scale_law_impl(9); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000010() { copper_reach_scale_law_impl(10); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000011() { copper_reach_scale_law_impl(11); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000012() { copper_reach_scale_law_impl(12); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000013() { copper_reach_scale_law_impl(13); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000014() { copper_reach_scale_law_impl(14); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000015() { copper_reach_scale_law_impl(15); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000016() { copper_reach_scale_law_impl(16); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000017() { copper_reach_scale_law_impl(17); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000018() { copper_reach_scale_law_impl(18); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000019() { copper_reach_scale_law_impl(19); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000020() { copper_reach_scale_law_impl(20); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000021() { copper_reach_scale_law_impl(21); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000022() { copper_reach_scale_law_impl(22); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000023() { copper_reach_scale_law_impl(23); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000024() { copper_reach_scale_law_impl(24); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000025() { copper_reach_scale_law_impl(25); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000026() { copper_reach_scale_law_impl(26); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000027() { copper_reach_scale_law_impl(27); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000028() { copper_reach_scale_law_impl(28); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000029() { copper_reach_scale_law_impl(29); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000030() { copper_reach_scale_law_impl(30); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000031() { copper_reach_scale_law_impl(31); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000032() { copper_reach_scale_law_impl(32); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000033() { copper_reach_scale_law_impl(33); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000034() { copper_reach_scale_law_impl(34); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000035() { copper_reach_scale_law_impl(35); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000036() { copper_reach_scale_law_impl(36); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000037() { copper_reach_scale_law_impl(37); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000038() { copper_reach_scale_law_impl(38); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000039() { copper_reach_scale_law_impl(39); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000040() { copper_reach_scale_law_impl(40); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000041() { copper_reach_scale_law_impl(41); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000042() { copper_reach_scale_law_impl(42); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000043() { copper_reach_scale_law_impl(43); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000044() { copper_reach_scale_law_impl(44); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000045() { copper_reach_scale_law_impl(45); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000046() { copper_reach_scale_law_impl(46); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000047() { copper_reach_scale_law_impl(47); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000048() { copper_reach_scale_law_impl(48); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000049() { copper_reach_scale_law_impl(49); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000050() { copper_reach_scale_law_impl(50); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000051() { copper_reach_scale_law_impl(51); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000052() { copper_reach_scale_law_impl(52); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000053() { copper_reach_scale_law_impl(53); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000054() { copper_reach_scale_law_impl(54); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000055() { copper_reach_scale_law_impl(55); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000056() { copper_reach_scale_law_impl(56); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000057() { copper_reach_scale_law_impl(57); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000058() { copper_reach_scale_law_impl(58); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000059() { copper_reach_scale_law_impl(59); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000060() { copper_reach_scale_law_impl(60); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000061() { copper_reach_scale_law_impl(61); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000062() { copper_reach_scale_law_impl(62); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000063() { copper_reach_scale_law_impl(63); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000064() { copper_reach_scale_law_impl(64); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000065() { copper_reach_scale_law_impl(65); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000066() { copper_reach_scale_law_impl(66); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000067() { copper_reach_scale_law_impl(67); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000068() { copper_reach_scale_law_impl(68); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000069() { copper_reach_scale_law_impl(69); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000070() { copper_reach_scale_law_impl(70); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000071() { copper_reach_scale_law_impl(71); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000072() { copper_reach_scale_law_impl(72); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000073() { copper_reach_scale_law_impl(73); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000074() { copper_reach_scale_law_impl(74); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000075() { copper_reach_scale_law_impl(75); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000076() { copper_reach_scale_law_impl(76); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000077() { copper_reach_scale_law_impl(77); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000078() { copper_reach_scale_law_impl(78); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000079() { copper_reach_scale_law_impl(79); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000080() { copper_reach_scale_law_impl(80); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000081() { copper_reach_scale_law_impl(81); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000082() { copper_reach_scale_law_impl(82); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000083() { copper_reach_scale_law_impl(83); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000084() { copper_reach_scale_law_impl(84); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000085() { copper_reach_scale_law_impl(85); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000086() { copper_reach_scale_law_impl(86); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000087() { copper_reach_scale_law_impl(87); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000088() { copper_reach_scale_law_impl(88); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000089() { copper_reach_scale_law_impl(89); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000090() { copper_reach_scale_law_impl(90); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000091() { copper_reach_scale_law_impl(91); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000092() { copper_reach_scale_law_impl(92); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000093() { copper_reach_scale_law_impl(93); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000094() { copper_reach_scale_law_impl(94); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000095() { copper_reach_scale_law_impl(95); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000096() { copper_reach_scale_law_impl(96); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000097() { copper_reach_scale_law_impl(97); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000098() { copper_reach_scale_law_impl(98); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000099() { copper_reach_scale_law_impl(99); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000100() { copper_reach_scale_law_impl(100); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000101() { copper_reach_scale_law_impl(101); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000102() { copper_reach_scale_law_impl(102); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000103() { copper_reach_scale_law_impl(103); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000104() { copper_reach_scale_law_impl(104); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000105() { copper_reach_scale_law_impl(105); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000106() { copper_reach_scale_law_impl(106); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000107() { copper_reach_scale_law_impl(107); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000108() { copper_reach_scale_law_impl(108); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000109() { copper_reach_scale_law_impl(109); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000110() { copper_reach_scale_law_impl(110); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000111() { copper_reach_scale_law_impl(111); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000112() { copper_reach_scale_law_impl(112); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000113() { copper_reach_scale_law_impl(113); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000114() { copper_reach_scale_law_impl(114); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000115() { copper_reach_scale_law_impl(115); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000116() { copper_reach_scale_law_impl(116); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000117() { copper_reach_scale_law_impl(117); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000118() { copper_reach_scale_law_impl(118); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000119() { copper_reach_scale_law_impl(119); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000120() { copper_reach_scale_law_impl(120); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000121() { copper_reach_scale_law_impl(121); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000122() { copper_reach_scale_law_impl(122); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000123() { copper_reach_scale_law_impl(123); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000124() { copper_reach_scale_law_impl(124); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000125() { copper_reach_scale_law_impl(125); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000126() { copper_reach_scale_law_impl(126); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000127() { copper_reach_scale_law_impl(127); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000128() { copper_reach_scale_law_impl(128); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000129() { copper_reach_scale_law_impl(129); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000130() { copper_reach_scale_law_impl(130); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000131() { copper_reach_scale_law_impl(131); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000132() { copper_reach_scale_law_impl(132); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000133() { copper_reach_scale_law_impl(133); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000134() { copper_reach_scale_law_impl(134); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000135() { copper_reach_scale_law_impl(135); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000136() { copper_reach_scale_law_impl(136); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000137() { copper_reach_scale_law_impl(137); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000138() { copper_reach_scale_law_impl(138); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000139() { copper_reach_scale_law_impl(139); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000140() { copper_reach_scale_law_impl(140); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000141() { copper_reach_scale_law_impl(141); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000142() { copper_reach_scale_law_impl(142); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000143() { copper_reach_scale_law_impl(143); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000144() { copper_reach_scale_law_impl(144); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000145() { copper_reach_scale_law_impl(145); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000146() { copper_reach_scale_law_impl(146); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000147() { copper_reach_scale_law_impl(147); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000148() { copper_reach_scale_law_impl(148); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000149() { copper_reach_scale_law_impl(149); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000150() { copper_reach_scale_law_impl(150); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000151() { copper_reach_scale_law_impl(151); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000152() { copper_reach_scale_law_impl(152); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000153() { copper_reach_scale_law_impl(153); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000154() { copper_reach_scale_law_impl(154); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000155() { copper_reach_scale_law_impl(155); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000156() { copper_reach_scale_law_impl(156); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000157() { copper_reach_scale_law_impl(157); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000158() { copper_reach_scale_law_impl(158); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000159() { copper_reach_scale_law_impl(159); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000160() { copper_reach_scale_law_impl(160); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000161() { copper_reach_scale_law_impl(161); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000162() { copper_reach_scale_law_impl(162); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000163() { copper_reach_scale_law_impl(163); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000164() { copper_reach_scale_law_impl(164); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000165() { copper_reach_scale_law_impl(165); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000166() { copper_reach_scale_law_impl(166); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000167() { copper_reach_scale_law_impl(167); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000168() { copper_reach_scale_law_impl(168); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000169() { copper_reach_scale_law_impl(169); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000170() { copper_reach_scale_law_impl(170); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000171() { copper_reach_scale_law_impl(171); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000172() { copper_reach_scale_law_impl(172); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000173() { copper_reach_scale_law_impl(173); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000174() { copper_reach_scale_law_impl(174); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000175() { copper_reach_scale_law_impl(175); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000176() { copper_reach_scale_law_impl(176); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000177() { copper_reach_scale_law_impl(177); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000178() { copper_reach_scale_law_impl(178); }
    #[cfg_attr(test, test)]
    fn copper_reach_scale_law_seed_000179() { copper_reach_scale_law_impl(179); }
    // --- copper_reach_monotone_added_pad: 180 generated seeds ---
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000000() { copper_reach_monotone_under_added_pad_impl(0); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000001() { copper_reach_monotone_under_added_pad_impl(1); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000002() { copper_reach_monotone_under_added_pad_impl(2); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000003() { copper_reach_monotone_under_added_pad_impl(3); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000004() { copper_reach_monotone_under_added_pad_impl(4); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000005() { copper_reach_monotone_under_added_pad_impl(5); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000006() { copper_reach_monotone_under_added_pad_impl(6); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000007() { copper_reach_monotone_under_added_pad_impl(7); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000008() { copper_reach_monotone_under_added_pad_impl(8); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000009() { copper_reach_monotone_under_added_pad_impl(9); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000010() { copper_reach_monotone_under_added_pad_impl(10); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000011() { copper_reach_monotone_under_added_pad_impl(11); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000012() { copper_reach_monotone_under_added_pad_impl(12); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000013() { copper_reach_monotone_under_added_pad_impl(13); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000014() { copper_reach_monotone_under_added_pad_impl(14); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000015() { copper_reach_monotone_under_added_pad_impl(15); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000016() { copper_reach_monotone_under_added_pad_impl(16); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000017() { copper_reach_monotone_under_added_pad_impl(17); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000018() { copper_reach_monotone_under_added_pad_impl(18); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000019() { copper_reach_monotone_under_added_pad_impl(19); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000020() { copper_reach_monotone_under_added_pad_impl(20); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000021() { copper_reach_monotone_under_added_pad_impl(21); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000022() { copper_reach_monotone_under_added_pad_impl(22); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000023() { copper_reach_monotone_under_added_pad_impl(23); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000024() { copper_reach_monotone_under_added_pad_impl(24); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000025() { copper_reach_monotone_under_added_pad_impl(25); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000026() { copper_reach_monotone_under_added_pad_impl(26); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000027() { copper_reach_monotone_under_added_pad_impl(27); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000028() { copper_reach_monotone_under_added_pad_impl(28); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000029() { copper_reach_monotone_under_added_pad_impl(29); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000030() { copper_reach_monotone_under_added_pad_impl(30); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000031() { copper_reach_monotone_under_added_pad_impl(31); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000032() { copper_reach_monotone_under_added_pad_impl(32); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000033() { copper_reach_monotone_under_added_pad_impl(33); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000034() { copper_reach_monotone_under_added_pad_impl(34); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000035() { copper_reach_monotone_under_added_pad_impl(35); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000036() { copper_reach_monotone_under_added_pad_impl(36); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000037() { copper_reach_monotone_under_added_pad_impl(37); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000038() { copper_reach_monotone_under_added_pad_impl(38); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000039() { copper_reach_monotone_under_added_pad_impl(39); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000040() { copper_reach_monotone_under_added_pad_impl(40); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000041() { copper_reach_monotone_under_added_pad_impl(41); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000042() { copper_reach_monotone_under_added_pad_impl(42); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000043() { copper_reach_monotone_under_added_pad_impl(43); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000044() { copper_reach_monotone_under_added_pad_impl(44); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000045() { copper_reach_monotone_under_added_pad_impl(45); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000046() { copper_reach_monotone_under_added_pad_impl(46); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000047() { copper_reach_monotone_under_added_pad_impl(47); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000048() { copper_reach_monotone_under_added_pad_impl(48); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000049() { copper_reach_monotone_under_added_pad_impl(49); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000050() { copper_reach_monotone_under_added_pad_impl(50); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000051() { copper_reach_monotone_under_added_pad_impl(51); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000052() { copper_reach_monotone_under_added_pad_impl(52); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000053() { copper_reach_monotone_under_added_pad_impl(53); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000054() { copper_reach_monotone_under_added_pad_impl(54); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000055() { copper_reach_monotone_under_added_pad_impl(55); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000056() { copper_reach_monotone_under_added_pad_impl(56); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000057() { copper_reach_monotone_under_added_pad_impl(57); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000058() { copper_reach_monotone_under_added_pad_impl(58); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000059() { copper_reach_monotone_under_added_pad_impl(59); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000060() { copper_reach_monotone_under_added_pad_impl(60); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000061() { copper_reach_monotone_under_added_pad_impl(61); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000062() { copper_reach_monotone_under_added_pad_impl(62); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000063() { copper_reach_monotone_under_added_pad_impl(63); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000064() { copper_reach_monotone_under_added_pad_impl(64); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000065() { copper_reach_monotone_under_added_pad_impl(65); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000066() { copper_reach_monotone_under_added_pad_impl(66); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000067() { copper_reach_monotone_under_added_pad_impl(67); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000068() { copper_reach_monotone_under_added_pad_impl(68); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000069() { copper_reach_monotone_under_added_pad_impl(69); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000070() { copper_reach_monotone_under_added_pad_impl(70); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000071() { copper_reach_monotone_under_added_pad_impl(71); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000072() { copper_reach_monotone_under_added_pad_impl(72); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000073() { copper_reach_monotone_under_added_pad_impl(73); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000074() { copper_reach_monotone_under_added_pad_impl(74); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000075() { copper_reach_monotone_under_added_pad_impl(75); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000076() { copper_reach_monotone_under_added_pad_impl(76); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000077() { copper_reach_monotone_under_added_pad_impl(77); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000078() { copper_reach_monotone_under_added_pad_impl(78); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000079() { copper_reach_monotone_under_added_pad_impl(79); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000080() { copper_reach_monotone_under_added_pad_impl(80); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000081() { copper_reach_monotone_under_added_pad_impl(81); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000082() { copper_reach_monotone_under_added_pad_impl(82); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000083() { copper_reach_monotone_under_added_pad_impl(83); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000084() { copper_reach_monotone_under_added_pad_impl(84); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000085() { copper_reach_monotone_under_added_pad_impl(85); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000086() { copper_reach_monotone_under_added_pad_impl(86); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000087() { copper_reach_monotone_under_added_pad_impl(87); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000088() { copper_reach_monotone_under_added_pad_impl(88); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000089() { copper_reach_monotone_under_added_pad_impl(89); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000090() { copper_reach_monotone_under_added_pad_impl(90); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000091() { copper_reach_monotone_under_added_pad_impl(91); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000092() { copper_reach_monotone_under_added_pad_impl(92); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000093() { copper_reach_monotone_under_added_pad_impl(93); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000094() { copper_reach_monotone_under_added_pad_impl(94); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000095() { copper_reach_monotone_under_added_pad_impl(95); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000096() { copper_reach_monotone_under_added_pad_impl(96); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000097() { copper_reach_monotone_under_added_pad_impl(97); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000098() { copper_reach_monotone_under_added_pad_impl(98); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000099() { copper_reach_monotone_under_added_pad_impl(99); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000100() { copper_reach_monotone_under_added_pad_impl(100); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000101() { copper_reach_monotone_under_added_pad_impl(101); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000102() { copper_reach_monotone_under_added_pad_impl(102); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000103() { copper_reach_monotone_under_added_pad_impl(103); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000104() { copper_reach_monotone_under_added_pad_impl(104); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000105() { copper_reach_monotone_under_added_pad_impl(105); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000106() { copper_reach_monotone_under_added_pad_impl(106); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000107() { copper_reach_monotone_under_added_pad_impl(107); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000108() { copper_reach_monotone_under_added_pad_impl(108); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000109() { copper_reach_monotone_under_added_pad_impl(109); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000110() { copper_reach_monotone_under_added_pad_impl(110); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000111() { copper_reach_monotone_under_added_pad_impl(111); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000112() { copper_reach_monotone_under_added_pad_impl(112); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000113() { copper_reach_monotone_under_added_pad_impl(113); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000114() { copper_reach_monotone_under_added_pad_impl(114); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000115() { copper_reach_monotone_under_added_pad_impl(115); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000116() { copper_reach_monotone_under_added_pad_impl(116); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000117() { copper_reach_monotone_under_added_pad_impl(117); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000118() { copper_reach_monotone_under_added_pad_impl(118); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000119() { copper_reach_monotone_under_added_pad_impl(119); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000120() { copper_reach_monotone_under_added_pad_impl(120); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000121() { copper_reach_monotone_under_added_pad_impl(121); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000122() { copper_reach_monotone_under_added_pad_impl(122); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000123() { copper_reach_monotone_under_added_pad_impl(123); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000124() { copper_reach_monotone_under_added_pad_impl(124); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000125() { copper_reach_monotone_under_added_pad_impl(125); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000126() { copper_reach_monotone_under_added_pad_impl(126); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000127() { copper_reach_monotone_under_added_pad_impl(127); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000128() { copper_reach_monotone_under_added_pad_impl(128); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000129() { copper_reach_monotone_under_added_pad_impl(129); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000130() { copper_reach_monotone_under_added_pad_impl(130); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000131() { copper_reach_monotone_under_added_pad_impl(131); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000132() { copper_reach_monotone_under_added_pad_impl(132); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000133() { copper_reach_monotone_under_added_pad_impl(133); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000134() { copper_reach_monotone_under_added_pad_impl(134); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000135() { copper_reach_monotone_under_added_pad_impl(135); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000136() { copper_reach_monotone_under_added_pad_impl(136); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000137() { copper_reach_monotone_under_added_pad_impl(137); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000138() { copper_reach_monotone_under_added_pad_impl(138); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000139() { copper_reach_monotone_under_added_pad_impl(139); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000140() { copper_reach_monotone_under_added_pad_impl(140); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000141() { copper_reach_monotone_under_added_pad_impl(141); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000142() { copper_reach_monotone_under_added_pad_impl(142); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000143() { copper_reach_monotone_under_added_pad_impl(143); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000144() { copper_reach_monotone_under_added_pad_impl(144); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000145() { copper_reach_monotone_under_added_pad_impl(145); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000146() { copper_reach_monotone_under_added_pad_impl(146); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000147() { copper_reach_monotone_under_added_pad_impl(147); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000148() { copper_reach_monotone_under_added_pad_impl(148); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000149() { copper_reach_monotone_under_added_pad_impl(149); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000150() { copper_reach_monotone_under_added_pad_impl(150); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000151() { copper_reach_monotone_under_added_pad_impl(151); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000152() { copper_reach_monotone_under_added_pad_impl(152); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000153() { copper_reach_monotone_under_added_pad_impl(153); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000154() { copper_reach_monotone_under_added_pad_impl(154); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000155() { copper_reach_monotone_under_added_pad_impl(155); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000156() { copper_reach_monotone_under_added_pad_impl(156); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000157() { copper_reach_monotone_under_added_pad_impl(157); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000158() { copper_reach_monotone_under_added_pad_impl(158); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000159() { copper_reach_monotone_under_added_pad_impl(159); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000160() { copper_reach_monotone_under_added_pad_impl(160); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000161() { copper_reach_monotone_under_added_pad_impl(161); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000162() { copper_reach_monotone_under_added_pad_impl(162); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000163() { copper_reach_monotone_under_added_pad_impl(163); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000164() { copper_reach_monotone_under_added_pad_impl(164); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000165() { copper_reach_monotone_under_added_pad_impl(165); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000166() { copper_reach_monotone_under_added_pad_impl(166); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000167() { copper_reach_monotone_under_added_pad_impl(167); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000168() { copper_reach_monotone_under_added_pad_impl(168); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000169() { copper_reach_monotone_under_added_pad_impl(169); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000170() { copper_reach_monotone_under_added_pad_impl(170); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000171() { copper_reach_monotone_under_added_pad_impl(171); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000172() { copper_reach_monotone_under_added_pad_impl(172); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000173() { copper_reach_monotone_under_added_pad_impl(173); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000174() { copper_reach_monotone_under_added_pad_impl(174); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000175() { copper_reach_monotone_under_added_pad_impl(175); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000176() { copper_reach_monotone_under_added_pad_impl(176); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000177() { copper_reach_monotone_under_added_pad_impl(177); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000178() { copper_reach_monotone_under_added_pad_impl(178); }
    #[cfg_attr(test, test)]
    fn copper_reach_monotone_added_pad_seed_000179() { copper_reach_monotone_under_added_pad_impl(179); }
    // --- copper_reach_rotation_invariant: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000000() { copper_reach_rotation_invariant_impl(0); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000001() { copper_reach_rotation_invariant_impl(1); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000002() { copper_reach_rotation_invariant_impl(2); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000003() { copper_reach_rotation_invariant_impl(3); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000004() { copper_reach_rotation_invariant_impl(4); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000005() { copper_reach_rotation_invariant_impl(5); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000006() { copper_reach_rotation_invariant_impl(6); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000007() { copper_reach_rotation_invariant_impl(7); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000008() { copper_reach_rotation_invariant_impl(8); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000009() { copper_reach_rotation_invariant_impl(9); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000010() { copper_reach_rotation_invariant_impl(10); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000011() { copper_reach_rotation_invariant_impl(11); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000012() { copper_reach_rotation_invariant_impl(12); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000013() { copper_reach_rotation_invariant_impl(13); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000014() { copper_reach_rotation_invariant_impl(14); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000015() { copper_reach_rotation_invariant_impl(15); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000016() { copper_reach_rotation_invariant_impl(16); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000017() { copper_reach_rotation_invariant_impl(17); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000018() { copper_reach_rotation_invariant_impl(18); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000019() { copper_reach_rotation_invariant_impl(19); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000020() { copper_reach_rotation_invariant_impl(20); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000021() { copper_reach_rotation_invariant_impl(21); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000022() { copper_reach_rotation_invariant_impl(22); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000023() { copper_reach_rotation_invariant_impl(23); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000024() { copper_reach_rotation_invariant_impl(24); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000025() { copper_reach_rotation_invariant_impl(25); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000026() { copper_reach_rotation_invariant_impl(26); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000027() { copper_reach_rotation_invariant_impl(27); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000028() { copper_reach_rotation_invariant_impl(28); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000029() { copper_reach_rotation_invariant_impl(29); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000030() { copper_reach_rotation_invariant_impl(30); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000031() { copper_reach_rotation_invariant_impl(31); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000032() { copper_reach_rotation_invariant_impl(32); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000033() { copper_reach_rotation_invariant_impl(33); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000034() { copper_reach_rotation_invariant_impl(34); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000035() { copper_reach_rotation_invariant_impl(35); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000036() { copper_reach_rotation_invariant_impl(36); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000037() { copper_reach_rotation_invariant_impl(37); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000038() { copper_reach_rotation_invariant_impl(38); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000039() { copper_reach_rotation_invariant_impl(39); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000040() { copper_reach_rotation_invariant_impl(40); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000041() { copper_reach_rotation_invariant_impl(41); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000042() { copper_reach_rotation_invariant_impl(42); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000043() { copper_reach_rotation_invariant_impl(43); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000044() { copper_reach_rotation_invariant_impl(44); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000045() { copper_reach_rotation_invariant_impl(45); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000046() { copper_reach_rotation_invariant_impl(46); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000047() { copper_reach_rotation_invariant_impl(47); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000048() { copper_reach_rotation_invariant_impl(48); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000049() { copper_reach_rotation_invariant_impl(49); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000050() { copper_reach_rotation_invariant_impl(50); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000051() { copper_reach_rotation_invariant_impl(51); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000052() { copper_reach_rotation_invariant_impl(52); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000053() { copper_reach_rotation_invariant_impl(53); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000054() { copper_reach_rotation_invariant_impl(54); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000055() { copper_reach_rotation_invariant_impl(55); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000056() { copper_reach_rotation_invariant_impl(56); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000057() { copper_reach_rotation_invariant_impl(57); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000058() { copper_reach_rotation_invariant_impl(58); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000059() { copper_reach_rotation_invariant_impl(59); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000060() { copper_reach_rotation_invariant_impl(60); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000061() { copper_reach_rotation_invariant_impl(61); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000062() { copper_reach_rotation_invariant_impl(62); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000063() { copper_reach_rotation_invariant_impl(63); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000064() { copper_reach_rotation_invariant_impl(64); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000065() { copper_reach_rotation_invariant_impl(65); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000066() { copper_reach_rotation_invariant_impl(66); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000067() { copper_reach_rotation_invariant_impl(67); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000068() { copper_reach_rotation_invariant_impl(68); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000069() { copper_reach_rotation_invariant_impl(69); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000070() { copper_reach_rotation_invariant_impl(70); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000071() { copper_reach_rotation_invariant_impl(71); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000072() { copper_reach_rotation_invariant_impl(72); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000073() { copper_reach_rotation_invariant_impl(73); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000074() { copper_reach_rotation_invariant_impl(74); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000075() { copper_reach_rotation_invariant_impl(75); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000076() { copper_reach_rotation_invariant_impl(76); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000077() { copper_reach_rotation_invariant_impl(77); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000078() { copper_reach_rotation_invariant_impl(78); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000079() { copper_reach_rotation_invariant_impl(79); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000080() { copper_reach_rotation_invariant_impl(80); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000081() { copper_reach_rotation_invariant_impl(81); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000082() { copper_reach_rotation_invariant_impl(82); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000083() { copper_reach_rotation_invariant_impl(83); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000084() { copper_reach_rotation_invariant_impl(84); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000085() { copper_reach_rotation_invariant_impl(85); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000086() { copper_reach_rotation_invariant_impl(86); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000087() { copper_reach_rotation_invariant_impl(87); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000088() { copper_reach_rotation_invariant_impl(88); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000089() { copper_reach_rotation_invariant_impl(89); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000090() { copper_reach_rotation_invariant_impl(90); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000091() { copper_reach_rotation_invariant_impl(91); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000092() { copper_reach_rotation_invariant_impl(92); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000093() { copper_reach_rotation_invariant_impl(93); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000094() { copper_reach_rotation_invariant_impl(94); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000095() { copper_reach_rotation_invariant_impl(95); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000096() { copper_reach_rotation_invariant_impl(96); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000097() { copper_reach_rotation_invariant_impl(97); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000098() { copper_reach_rotation_invariant_impl(98); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000099() { copper_reach_rotation_invariant_impl(99); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000100() { copper_reach_rotation_invariant_impl(100); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000101() { copper_reach_rotation_invariant_impl(101); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000102() { copper_reach_rotation_invariant_impl(102); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000103() { copper_reach_rotation_invariant_impl(103); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000104() { copper_reach_rotation_invariant_impl(104); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000105() { copper_reach_rotation_invariant_impl(105); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000106() { copper_reach_rotation_invariant_impl(106); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000107() { copper_reach_rotation_invariant_impl(107); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000108() { copper_reach_rotation_invariant_impl(108); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000109() { copper_reach_rotation_invariant_impl(109); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000110() { copper_reach_rotation_invariant_impl(110); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000111() { copper_reach_rotation_invariant_impl(111); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000112() { copper_reach_rotation_invariant_impl(112); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000113() { copper_reach_rotation_invariant_impl(113); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000114() { copper_reach_rotation_invariant_impl(114); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000115() { copper_reach_rotation_invariant_impl(115); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000116() { copper_reach_rotation_invariant_impl(116); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000117() { copper_reach_rotation_invariant_impl(117); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000118() { copper_reach_rotation_invariant_impl(118); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000119() { copper_reach_rotation_invariant_impl(119); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000120() { copper_reach_rotation_invariant_impl(120); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000121() { copper_reach_rotation_invariant_impl(121); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000122() { copper_reach_rotation_invariant_impl(122); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000123() { copper_reach_rotation_invariant_impl(123); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000124() { copper_reach_rotation_invariant_impl(124); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000125() { copper_reach_rotation_invariant_impl(125); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000126() { copper_reach_rotation_invariant_impl(126); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000127() { copper_reach_rotation_invariant_impl(127); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000128() { copper_reach_rotation_invariant_impl(128); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000129() { copper_reach_rotation_invariant_impl(129); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000130() { copper_reach_rotation_invariant_impl(130); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000131() { copper_reach_rotation_invariant_impl(131); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000132() { copper_reach_rotation_invariant_impl(132); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000133() { copper_reach_rotation_invariant_impl(133); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000134() { copper_reach_rotation_invariant_impl(134); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000135() { copper_reach_rotation_invariant_impl(135); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000136() { copper_reach_rotation_invariant_impl(136); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000137() { copper_reach_rotation_invariant_impl(137); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000138() { copper_reach_rotation_invariant_impl(138); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000139() { copper_reach_rotation_invariant_impl(139); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000140() { copper_reach_rotation_invariant_impl(140); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000141() { copper_reach_rotation_invariant_impl(141); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000142() { copper_reach_rotation_invariant_impl(142); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000143() { copper_reach_rotation_invariant_impl(143); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000144() { copper_reach_rotation_invariant_impl(144); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000145() { copper_reach_rotation_invariant_impl(145); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000146() { copper_reach_rotation_invariant_impl(146); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000147() { copper_reach_rotation_invariant_impl(147); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000148() { copper_reach_rotation_invariant_impl(148); }
    #[cfg_attr(test, test)]
    fn copper_reach_rotation_invariant_seed_000149() { copper_reach_rotation_invariant_impl(149); }
    // --- circle_ring_translation_equivariant: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000000() { circle_ring_translation_equivariant_impl(0); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000001() { circle_ring_translation_equivariant_impl(1); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000002() { circle_ring_translation_equivariant_impl(2); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000003() { circle_ring_translation_equivariant_impl(3); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000004() { circle_ring_translation_equivariant_impl(4); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000005() { circle_ring_translation_equivariant_impl(5); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000006() { circle_ring_translation_equivariant_impl(6); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000007() { circle_ring_translation_equivariant_impl(7); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000008() { circle_ring_translation_equivariant_impl(8); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000009() { circle_ring_translation_equivariant_impl(9); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000010() { circle_ring_translation_equivariant_impl(10); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000011() { circle_ring_translation_equivariant_impl(11); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000012() { circle_ring_translation_equivariant_impl(12); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000013() { circle_ring_translation_equivariant_impl(13); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000014() { circle_ring_translation_equivariant_impl(14); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000015() { circle_ring_translation_equivariant_impl(15); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000016() { circle_ring_translation_equivariant_impl(16); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000017() { circle_ring_translation_equivariant_impl(17); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000018() { circle_ring_translation_equivariant_impl(18); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000019() { circle_ring_translation_equivariant_impl(19); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000020() { circle_ring_translation_equivariant_impl(20); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000021() { circle_ring_translation_equivariant_impl(21); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000022() { circle_ring_translation_equivariant_impl(22); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000023() { circle_ring_translation_equivariant_impl(23); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000024() { circle_ring_translation_equivariant_impl(24); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000025() { circle_ring_translation_equivariant_impl(25); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000026() { circle_ring_translation_equivariant_impl(26); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000027() { circle_ring_translation_equivariant_impl(27); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000028() { circle_ring_translation_equivariant_impl(28); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000029() { circle_ring_translation_equivariant_impl(29); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000030() { circle_ring_translation_equivariant_impl(30); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000031() { circle_ring_translation_equivariant_impl(31); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000032() { circle_ring_translation_equivariant_impl(32); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000033() { circle_ring_translation_equivariant_impl(33); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000034() { circle_ring_translation_equivariant_impl(34); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000035() { circle_ring_translation_equivariant_impl(35); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000036() { circle_ring_translation_equivariant_impl(36); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000037() { circle_ring_translation_equivariant_impl(37); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000038() { circle_ring_translation_equivariant_impl(38); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000039() { circle_ring_translation_equivariant_impl(39); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000040() { circle_ring_translation_equivariant_impl(40); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000041() { circle_ring_translation_equivariant_impl(41); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000042() { circle_ring_translation_equivariant_impl(42); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000043() { circle_ring_translation_equivariant_impl(43); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000044() { circle_ring_translation_equivariant_impl(44); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000045() { circle_ring_translation_equivariant_impl(45); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000046() { circle_ring_translation_equivariant_impl(46); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000047() { circle_ring_translation_equivariant_impl(47); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000048() { circle_ring_translation_equivariant_impl(48); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000049() { circle_ring_translation_equivariant_impl(49); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000050() { circle_ring_translation_equivariant_impl(50); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000051() { circle_ring_translation_equivariant_impl(51); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000052() { circle_ring_translation_equivariant_impl(52); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000053() { circle_ring_translation_equivariant_impl(53); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000054() { circle_ring_translation_equivariant_impl(54); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000055() { circle_ring_translation_equivariant_impl(55); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000056() { circle_ring_translation_equivariant_impl(56); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000057() { circle_ring_translation_equivariant_impl(57); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000058() { circle_ring_translation_equivariant_impl(58); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000059() { circle_ring_translation_equivariant_impl(59); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000060() { circle_ring_translation_equivariant_impl(60); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000061() { circle_ring_translation_equivariant_impl(61); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000062() { circle_ring_translation_equivariant_impl(62); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000063() { circle_ring_translation_equivariant_impl(63); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000064() { circle_ring_translation_equivariant_impl(64); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000065() { circle_ring_translation_equivariant_impl(65); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000066() { circle_ring_translation_equivariant_impl(66); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000067() { circle_ring_translation_equivariant_impl(67); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000068() { circle_ring_translation_equivariant_impl(68); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000069() { circle_ring_translation_equivariant_impl(69); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000070() { circle_ring_translation_equivariant_impl(70); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000071() { circle_ring_translation_equivariant_impl(71); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000072() { circle_ring_translation_equivariant_impl(72); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000073() { circle_ring_translation_equivariant_impl(73); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000074() { circle_ring_translation_equivariant_impl(74); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000075() { circle_ring_translation_equivariant_impl(75); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000076() { circle_ring_translation_equivariant_impl(76); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000077() { circle_ring_translation_equivariant_impl(77); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000078() { circle_ring_translation_equivariant_impl(78); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000079() { circle_ring_translation_equivariant_impl(79); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000080() { circle_ring_translation_equivariant_impl(80); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000081() { circle_ring_translation_equivariant_impl(81); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000082() { circle_ring_translation_equivariant_impl(82); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000083() { circle_ring_translation_equivariant_impl(83); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000084() { circle_ring_translation_equivariant_impl(84); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000085() { circle_ring_translation_equivariant_impl(85); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000086() { circle_ring_translation_equivariant_impl(86); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000087() { circle_ring_translation_equivariant_impl(87); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000088() { circle_ring_translation_equivariant_impl(88); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000089() { circle_ring_translation_equivariant_impl(89); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000090() { circle_ring_translation_equivariant_impl(90); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000091() { circle_ring_translation_equivariant_impl(91); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000092() { circle_ring_translation_equivariant_impl(92); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000093() { circle_ring_translation_equivariant_impl(93); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000094() { circle_ring_translation_equivariant_impl(94); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000095() { circle_ring_translation_equivariant_impl(95); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000096() { circle_ring_translation_equivariant_impl(96); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000097() { circle_ring_translation_equivariant_impl(97); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000098() { circle_ring_translation_equivariant_impl(98); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000099() { circle_ring_translation_equivariant_impl(99); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000100() { circle_ring_translation_equivariant_impl(100); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000101() { circle_ring_translation_equivariant_impl(101); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000102() { circle_ring_translation_equivariant_impl(102); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000103() { circle_ring_translation_equivariant_impl(103); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000104() { circle_ring_translation_equivariant_impl(104); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000105() { circle_ring_translation_equivariant_impl(105); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000106() { circle_ring_translation_equivariant_impl(106); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000107() { circle_ring_translation_equivariant_impl(107); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000108() { circle_ring_translation_equivariant_impl(108); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000109() { circle_ring_translation_equivariant_impl(109); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000110() { circle_ring_translation_equivariant_impl(110); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000111() { circle_ring_translation_equivariant_impl(111); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000112() { circle_ring_translation_equivariant_impl(112); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000113() { circle_ring_translation_equivariant_impl(113); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000114() { circle_ring_translation_equivariant_impl(114); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000115() { circle_ring_translation_equivariant_impl(115); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000116() { circle_ring_translation_equivariant_impl(116); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000117() { circle_ring_translation_equivariant_impl(117); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000118() { circle_ring_translation_equivariant_impl(118); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000119() { circle_ring_translation_equivariant_impl(119); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000120() { circle_ring_translation_equivariant_impl(120); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000121() { circle_ring_translation_equivariant_impl(121); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000122() { circle_ring_translation_equivariant_impl(122); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000123() { circle_ring_translation_equivariant_impl(123); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000124() { circle_ring_translation_equivariant_impl(124); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000125() { circle_ring_translation_equivariant_impl(125); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000126() { circle_ring_translation_equivariant_impl(126); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000127() { circle_ring_translation_equivariant_impl(127); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000128() { circle_ring_translation_equivariant_impl(128); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000129() { circle_ring_translation_equivariant_impl(129); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000130() { circle_ring_translation_equivariant_impl(130); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000131() { circle_ring_translation_equivariant_impl(131); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000132() { circle_ring_translation_equivariant_impl(132); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000133() { circle_ring_translation_equivariant_impl(133); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000134() { circle_ring_translation_equivariant_impl(134); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000135() { circle_ring_translation_equivariant_impl(135); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000136() { circle_ring_translation_equivariant_impl(136); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000137() { circle_ring_translation_equivariant_impl(137); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000138() { circle_ring_translation_equivariant_impl(138); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000139() { circle_ring_translation_equivariant_impl(139); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000140() { circle_ring_translation_equivariant_impl(140); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000141() { circle_ring_translation_equivariant_impl(141); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000142() { circle_ring_translation_equivariant_impl(142); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000143() { circle_ring_translation_equivariant_impl(143); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000144() { circle_ring_translation_equivariant_impl(144); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000145() { circle_ring_translation_equivariant_impl(145); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000146() { circle_ring_translation_equivariant_impl(146); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000147() { circle_ring_translation_equivariant_impl(147); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000148() { circle_ring_translation_equivariant_impl(148); }
    #[cfg_attr(test, test)]
    fn circle_ring_translation_equivariant_seed_000149() { circle_ring_translation_equivariant_impl(149); }
    // --- circle_ring_radius_scale_law: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000000() { circle_ring_radius_scale_law_impl(0); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000001() { circle_ring_radius_scale_law_impl(1); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000002() { circle_ring_radius_scale_law_impl(2); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000003() { circle_ring_radius_scale_law_impl(3); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000004() { circle_ring_radius_scale_law_impl(4); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000005() { circle_ring_radius_scale_law_impl(5); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000006() { circle_ring_radius_scale_law_impl(6); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000007() { circle_ring_radius_scale_law_impl(7); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000008() { circle_ring_radius_scale_law_impl(8); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000009() { circle_ring_radius_scale_law_impl(9); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000010() { circle_ring_radius_scale_law_impl(10); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000011() { circle_ring_radius_scale_law_impl(11); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000012() { circle_ring_radius_scale_law_impl(12); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000013() { circle_ring_radius_scale_law_impl(13); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000014() { circle_ring_radius_scale_law_impl(14); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000015() { circle_ring_radius_scale_law_impl(15); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000016() { circle_ring_radius_scale_law_impl(16); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000017() { circle_ring_radius_scale_law_impl(17); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000018() { circle_ring_radius_scale_law_impl(18); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000019() { circle_ring_radius_scale_law_impl(19); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000020() { circle_ring_radius_scale_law_impl(20); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000021() { circle_ring_radius_scale_law_impl(21); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000022() { circle_ring_radius_scale_law_impl(22); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000023() { circle_ring_radius_scale_law_impl(23); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000024() { circle_ring_radius_scale_law_impl(24); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000025() { circle_ring_radius_scale_law_impl(25); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000026() { circle_ring_radius_scale_law_impl(26); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000027() { circle_ring_radius_scale_law_impl(27); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000028() { circle_ring_radius_scale_law_impl(28); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000029() { circle_ring_radius_scale_law_impl(29); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000030() { circle_ring_radius_scale_law_impl(30); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000031() { circle_ring_radius_scale_law_impl(31); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000032() { circle_ring_radius_scale_law_impl(32); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000033() { circle_ring_radius_scale_law_impl(33); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000034() { circle_ring_radius_scale_law_impl(34); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000035() { circle_ring_radius_scale_law_impl(35); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000036() { circle_ring_radius_scale_law_impl(36); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000037() { circle_ring_radius_scale_law_impl(37); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000038() { circle_ring_radius_scale_law_impl(38); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000039() { circle_ring_radius_scale_law_impl(39); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000040() { circle_ring_radius_scale_law_impl(40); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000041() { circle_ring_radius_scale_law_impl(41); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000042() { circle_ring_radius_scale_law_impl(42); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000043() { circle_ring_radius_scale_law_impl(43); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000044() { circle_ring_radius_scale_law_impl(44); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000045() { circle_ring_radius_scale_law_impl(45); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000046() { circle_ring_radius_scale_law_impl(46); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000047() { circle_ring_radius_scale_law_impl(47); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000048() { circle_ring_radius_scale_law_impl(48); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000049() { circle_ring_radius_scale_law_impl(49); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000050() { circle_ring_radius_scale_law_impl(50); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000051() { circle_ring_radius_scale_law_impl(51); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000052() { circle_ring_radius_scale_law_impl(52); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000053() { circle_ring_radius_scale_law_impl(53); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000054() { circle_ring_radius_scale_law_impl(54); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000055() { circle_ring_radius_scale_law_impl(55); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000056() { circle_ring_radius_scale_law_impl(56); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000057() { circle_ring_radius_scale_law_impl(57); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000058() { circle_ring_radius_scale_law_impl(58); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000059() { circle_ring_radius_scale_law_impl(59); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000060() { circle_ring_radius_scale_law_impl(60); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000061() { circle_ring_radius_scale_law_impl(61); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000062() { circle_ring_radius_scale_law_impl(62); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000063() { circle_ring_radius_scale_law_impl(63); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000064() { circle_ring_radius_scale_law_impl(64); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000065() { circle_ring_radius_scale_law_impl(65); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000066() { circle_ring_radius_scale_law_impl(66); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000067() { circle_ring_radius_scale_law_impl(67); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000068() { circle_ring_radius_scale_law_impl(68); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000069() { circle_ring_radius_scale_law_impl(69); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000070() { circle_ring_radius_scale_law_impl(70); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000071() { circle_ring_radius_scale_law_impl(71); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000072() { circle_ring_radius_scale_law_impl(72); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000073() { circle_ring_radius_scale_law_impl(73); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000074() { circle_ring_radius_scale_law_impl(74); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000075() { circle_ring_radius_scale_law_impl(75); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000076() { circle_ring_radius_scale_law_impl(76); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000077() { circle_ring_radius_scale_law_impl(77); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000078() { circle_ring_radius_scale_law_impl(78); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000079() { circle_ring_radius_scale_law_impl(79); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000080() { circle_ring_radius_scale_law_impl(80); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000081() { circle_ring_radius_scale_law_impl(81); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000082() { circle_ring_radius_scale_law_impl(82); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000083() { circle_ring_radius_scale_law_impl(83); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000084() { circle_ring_radius_scale_law_impl(84); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000085() { circle_ring_radius_scale_law_impl(85); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000086() { circle_ring_radius_scale_law_impl(86); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000087() { circle_ring_radius_scale_law_impl(87); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000088() { circle_ring_radius_scale_law_impl(88); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000089() { circle_ring_radius_scale_law_impl(89); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000090() { circle_ring_radius_scale_law_impl(90); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000091() { circle_ring_radius_scale_law_impl(91); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000092() { circle_ring_radius_scale_law_impl(92); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000093() { circle_ring_radius_scale_law_impl(93); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000094() { circle_ring_radius_scale_law_impl(94); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000095() { circle_ring_radius_scale_law_impl(95); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000096() { circle_ring_radius_scale_law_impl(96); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000097() { circle_ring_radius_scale_law_impl(97); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000098() { circle_ring_radius_scale_law_impl(98); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000099() { circle_ring_radius_scale_law_impl(99); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000100() { circle_ring_radius_scale_law_impl(100); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000101() { circle_ring_radius_scale_law_impl(101); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000102() { circle_ring_radius_scale_law_impl(102); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000103() { circle_ring_radius_scale_law_impl(103); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000104() { circle_ring_radius_scale_law_impl(104); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000105() { circle_ring_radius_scale_law_impl(105); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000106() { circle_ring_radius_scale_law_impl(106); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000107() { circle_ring_radius_scale_law_impl(107); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000108() { circle_ring_radius_scale_law_impl(108); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000109() { circle_ring_radius_scale_law_impl(109); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000110() { circle_ring_radius_scale_law_impl(110); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000111() { circle_ring_radius_scale_law_impl(111); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000112() { circle_ring_radius_scale_law_impl(112); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000113() { circle_ring_radius_scale_law_impl(113); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000114() { circle_ring_radius_scale_law_impl(114); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000115() { circle_ring_radius_scale_law_impl(115); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000116() { circle_ring_radius_scale_law_impl(116); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000117() { circle_ring_radius_scale_law_impl(117); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000118() { circle_ring_radius_scale_law_impl(118); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000119() { circle_ring_radius_scale_law_impl(119); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000120() { circle_ring_radius_scale_law_impl(120); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000121() { circle_ring_radius_scale_law_impl(121); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000122() { circle_ring_radius_scale_law_impl(122); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000123() { circle_ring_radius_scale_law_impl(123); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000124() { circle_ring_radius_scale_law_impl(124); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000125() { circle_ring_radius_scale_law_impl(125); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000126() { circle_ring_radius_scale_law_impl(126); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000127() { circle_ring_radius_scale_law_impl(127); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000128() { circle_ring_radius_scale_law_impl(128); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000129() { circle_ring_radius_scale_law_impl(129); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000130() { circle_ring_radius_scale_law_impl(130); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000131() { circle_ring_radius_scale_law_impl(131); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000132() { circle_ring_radius_scale_law_impl(132); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000133() { circle_ring_radius_scale_law_impl(133); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000134() { circle_ring_radius_scale_law_impl(134); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000135() { circle_ring_radius_scale_law_impl(135); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000136() { circle_ring_radius_scale_law_impl(136); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000137() { circle_ring_radius_scale_law_impl(137); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000138() { circle_ring_radius_scale_law_impl(138); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000139() { circle_ring_radius_scale_law_impl(139); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000140() { circle_ring_radius_scale_law_impl(140); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000141() { circle_ring_radius_scale_law_impl(141); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000142() { circle_ring_radius_scale_law_impl(142); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000143() { circle_ring_radius_scale_law_impl(143); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000144() { circle_ring_radius_scale_law_impl(144); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000145() { circle_ring_radius_scale_law_impl(145); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000146() { circle_ring_radius_scale_law_impl(146); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000147() { circle_ring_radius_scale_law_impl(147); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000148() { circle_ring_radius_scale_law_impl(148); }
    #[cfg_attr(test, test)]
    fn circle_ring_radius_scale_law_seed_000149() { circle_ring_radius_scale_law_impl(149); }
    // --- circle_ring_vertices_at_radius: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000000() { circle_ring_vertices_at_radius_from_center_impl(0); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000001() { circle_ring_vertices_at_radius_from_center_impl(1); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000002() { circle_ring_vertices_at_radius_from_center_impl(2); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000003() { circle_ring_vertices_at_radius_from_center_impl(3); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000004() { circle_ring_vertices_at_radius_from_center_impl(4); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000005() { circle_ring_vertices_at_radius_from_center_impl(5); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000006() { circle_ring_vertices_at_radius_from_center_impl(6); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000007() { circle_ring_vertices_at_radius_from_center_impl(7); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000008() { circle_ring_vertices_at_radius_from_center_impl(8); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000009() { circle_ring_vertices_at_radius_from_center_impl(9); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000010() { circle_ring_vertices_at_radius_from_center_impl(10); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000011() { circle_ring_vertices_at_radius_from_center_impl(11); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000012() { circle_ring_vertices_at_radius_from_center_impl(12); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000013() { circle_ring_vertices_at_radius_from_center_impl(13); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000014() { circle_ring_vertices_at_radius_from_center_impl(14); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000015() { circle_ring_vertices_at_radius_from_center_impl(15); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000016() { circle_ring_vertices_at_radius_from_center_impl(16); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000017() { circle_ring_vertices_at_radius_from_center_impl(17); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000018() { circle_ring_vertices_at_radius_from_center_impl(18); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000019() { circle_ring_vertices_at_radius_from_center_impl(19); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000020() { circle_ring_vertices_at_radius_from_center_impl(20); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000021() { circle_ring_vertices_at_radius_from_center_impl(21); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000022() { circle_ring_vertices_at_radius_from_center_impl(22); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000023() { circle_ring_vertices_at_radius_from_center_impl(23); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000024() { circle_ring_vertices_at_radius_from_center_impl(24); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000025() { circle_ring_vertices_at_radius_from_center_impl(25); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000026() { circle_ring_vertices_at_radius_from_center_impl(26); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000027() { circle_ring_vertices_at_radius_from_center_impl(27); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000028() { circle_ring_vertices_at_radius_from_center_impl(28); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000029() { circle_ring_vertices_at_radius_from_center_impl(29); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000030() { circle_ring_vertices_at_radius_from_center_impl(30); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000031() { circle_ring_vertices_at_radius_from_center_impl(31); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000032() { circle_ring_vertices_at_radius_from_center_impl(32); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000033() { circle_ring_vertices_at_radius_from_center_impl(33); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000034() { circle_ring_vertices_at_radius_from_center_impl(34); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000035() { circle_ring_vertices_at_radius_from_center_impl(35); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000036() { circle_ring_vertices_at_radius_from_center_impl(36); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000037() { circle_ring_vertices_at_radius_from_center_impl(37); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000038() { circle_ring_vertices_at_radius_from_center_impl(38); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000039() { circle_ring_vertices_at_radius_from_center_impl(39); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000040() { circle_ring_vertices_at_radius_from_center_impl(40); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000041() { circle_ring_vertices_at_radius_from_center_impl(41); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000042() { circle_ring_vertices_at_radius_from_center_impl(42); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000043() { circle_ring_vertices_at_radius_from_center_impl(43); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000044() { circle_ring_vertices_at_radius_from_center_impl(44); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000045() { circle_ring_vertices_at_radius_from_center_impl(45); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000046() { circle_ring_vertices_at_radius_from_center_impl(46); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000047() { circle_ring_vertices_at_radius_from_center_impl(47); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000048() { circle_ring_vertices_at_radius_from_center_impl(48); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000049() { circle_ring_vertices_at_radius_from_center_impl(49); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000050() { circle_ring_vertices_at_radius_from_center_impl(50); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000051() { circle_ring_vertices_at_radius_from_center_impl(51); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000052() { circle_ring_vertices_at_radius_from_center_impl(52); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000053() { circle_ring_vertices_at_radius_from_center_impl(53); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000054() { circle_ring_vertices_at_radius_from_center_impl(54); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000055() { circle_ring_vertices_at_radius_from_center_impl(55); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000056() { circle_ring_vertices_at_radius_from_center_impl(56); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000057() { circle_ring_vertices_at_radius_from_center_impl(57); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000058() { circle_ring_vertices_at_radius_from_center_impl(58); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000059() { circle_ring_vertices_at_radius_from_center_impl(59); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000060() { circle_ring_vertices_at_radius_from_center_impl(60); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000061() { circle_ring_vertices_at_radius_from_center_impl(61); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000062() { circle_ring_vertices_at_radius_from_center_impl(62); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000063() { circle_ring_vertices_at_radius_from_center_impl(63); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000064() { circle_ring_vertices_at_radius_from_center_impl(64); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000065() { circle_ring_vertices_at_radius_from_center_impl(65); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000066() { circle_ring_vertices_at_radius_from_center_impl(66); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000067() { circle_ring_vertices_at_radius_from_center_impl(67); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000068() { circle_ring_vertices_at_radius_from_center_impl(68); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000069() { circle_ring_vertices_at_radius_from_center_impl(69); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000070() { circle_ring_vertices_at_radius_from_center_impl(70); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000071() { circle_ring_vertices_at_radius_from_center_impl(71); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000072() { circle_ring_vertices_at_radius_from_center_impl(72); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000073() { circle_ring_vertices_at_radius_from_center_impl(73); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000074() { circle_ring_vertices_at_radius_from_center_impl(74); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000075() { circle_ring_vertices_at_radius_from_center_impl(75); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000076() { circle_ring_vertices_at_radius_from_center_impl(76); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000077() { circle_ring_vertices_at_radius_from_center_impl(77); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000078() { circle_ring_vertices_at_radius_from_center_impl(78); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000079() { circle_ring_vertices_at_radius_from_center_impl(79); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000080() { circle_ring_vertices_at_radius_from_center_impl(80); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000081() { circle_ring_vertices_at_radius_from_center_impl(81); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000082() { circle_ring_vertices_at_radius_from_center_impl(82); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000083() { circle_ring_vertices_at_radius_from_center_impl(83); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000084() { circle_ring_vertices_at_radius_from_center_impl(84); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000085() { circle_ring_vertices_at_radius_from_center_impl(85); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000086() { circle_ring_vertices_at_radius_from_center_impl(86); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000087() { circle_ring_vertices_at_radius_from_center_impl(87); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000088() { circle_ring_vertices_at_radius_from_center_impl(88); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000089() { circle_ring_vertices_at_radius_from_center_impl(89); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000090() { circle_ring_vertices_at_radius_from_center_impl(90); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000091() { circle_ring_vertices_at_radius_from_center_impl(91); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000092() { circle_ring_vertices_at_radius_from_center_impl(92); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000093() { circle_ring_vertices_at_radius_from_center_impl(93); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000094() { circle_ring_vertices_at_radius_from_center_impl(94); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000095() { circle_ring_vertices_at_radius_from_center_impl(95); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000096() { circle_ring_vertices_at_radius_from_center_impl(96); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000097() { circle_ring_vertices_at_radius_from_center_impl(97); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000098() { circle_ring_vertices_at_radius_from_center_impl(98); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000099() { circle_ring_vertices_at_radius_from_center_impl(99); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000100() { circle_ring_vertices_at_radius_from_center_impl(100); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000101() { circle_ring_vertices_at_radius_from_center_impl(101); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000102() { circle_ring_vertices_at_radius_from_center_impl(102); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000103() { circle_ring_vertices_at_radius_from_center_impl(103); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000104() { circle_ring_vertices_at_radius_from_center_impl(104); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000105() { circle_ring_vertices_at_radius_from_center_impl(105); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000106() { circle_ring_vertices_at_radius_from_center_impl(106); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000107() { circle_ring_vertices_at_radius_from_center_impl(107); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000108() { circle_ring_vertices_at_radius_from_center_impl(108); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000109() { circle_ring_vertices_at_radius_from_center_impl(109); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000110() { circle_ring_vertices_at_radius_from_center_impl(110); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000111() { circle_ring_vertices_at_radius_from_center_impl(111); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000112() { circle_ring_vertices_at_radius_from_center_impl(112); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000113() { circle_ring_vertices_at_radius_from_center_impl(113); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000114() { circle_ring_vertices_at_radius_from_center_impl(114); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000115() { circle_ring_vertices_at_radius_from_center_impl(115); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000116() { circle_ring_vertices_at_radius_from_center_impl(116); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000117() { circle_ring_vertices_at_radius_from_center_impl(117); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000118() { circle_ring_vertices_at_radius_from_center_impl(118); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000119() { circle_ring_vertices_at_radius_from_center_impl(119); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000120() { circle_ring_vertices_at_radius_from_center_impl(120); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000121() { circle_ring_vertices_at_radius_from_center_impl(121); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000122() { circle_ring_vertices_at_radius_from_center_impl(122); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000123() { circle_ring_vertices_at_radius_from_center_impl(123); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000124() { circle_ring_vertices_at_radius_from_center_impl(124); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000125() { circle_ring_vertices_at_radius_from_center_impl(125); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000126() { circle_ring_vertices_at_radius_from_center_impl(126); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000127() { circle_ring_vertices_at_radius_from_center_impl(127); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000128() { circle_ring_vertices_at_radius_from_center_impl(128); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000129() { circle_ring_vertices_at_radius_from_center_impl(129); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000130() { circle_ring_vertices_at_radius_from_center_impl(130); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000131() { circle_ring_vertices_at_radius_from_center_impl(131); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000132() { circle_ring_vertices_at_radius_from_center_impl(132); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000133() { circle_ring_vertices_at_radius_from_center_impl(133); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000134() { circle_ring_vertices_at_radius_from_center_impl(134); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000135() { circle_ring_vertices_at_radius_from_center_impl(135); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000136() { circle_ring_vertices_at_radius_from_center_impl(136); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000137() { circle_ring_vertices_at_radius_from_center_impl(137); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000138() { circle_ring_vertices_at_radius_from_center_impl(138); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000139() { circle_ring_vertices_at_radius_from_center_impl(139); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000140() { circle_ring_vertices_at_radius_from_center_impl(140); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000141() { circle_ring_vertices_at_radius_from_center_impl(141); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000142() { circle_ring_vertices_at_radius_from_center_impl(142); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000143() { circle_ring_vertices_at_radius_from_center_impl(143); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000144() { circle_ring_vertices_at_radius_from_center_impl(144); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000145() { circle_ring_vertices_at_radius_from_center_impl(145); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000146() { circle_ring_vertices_at_radius_from_center_impl(146); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000147() { circle_ring_vertices_at_radius_from_center_impl(147); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000148() { circle_ring_vertices_at_radius_from_center_impl(148); }
    #[cfg_attr(test, test)]
    fn circle_ring_vertices_at_radius_seed_000149() { circle_ring_vertices_at_radius_from_center_impl(149); }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("property_campaigns_3::tests::splitmix64_is_deterministic_in_seed", splitmix64_is_deterministic_in_seed),
        ("property_campaigns_3::tests::splitmix64_varies_with_seed", splitmix64_varies_with_seed),
        ("property_campaigns_3::tests::edt_gen_mask_dims_and_forced_cell_in_expected_range", edt_gen_mask_dims_and_forced_cell_in_expected_range),
        ("property_campaigns_3::tests::cr_gen_pads_length_in_expected_range", cr_gen_pads_length_in_expected_range),
        ("property_campaigns_3::tests::om_gen_case_is_deterministic", om_gen_case_is_deterministic),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_hand_worked_roundrect", core_half_extents_sum_identity_hand_worked_roundrect),
        ("property_campaigns_3::tests::circle_ring_translation_hand_worked_example", circle_ring_translation_hand_worked_example),
        ("property_campaigns_3::tests::edt_scale_law_seed_000000", edt_scale_law_seed_000000),
        ("property_campaigns_3::tests::edt_scale_law_seed_000001", edt_scale_law_seed_000001),
        ("property_campaigns_3::tests::edt_scale_law_seed_000002", edt_scale_law_seed_000002),
        ("property_campaigns_3::tests::edt_scale_law_seed_000003", edt_scale_law_seed_000003),
        ("property_campaigns_3::tests::edt_scale_law_seed_000004", edt_scale_law_seed_000004),
        ("property_campaigns_3::tests::edt_scale_law_seed_000005", edt_scale_law_seed_000005),
        ("property_campaigns_3::tests::edt_scale_law_seed_000006", edt_scale_law_seed_000006),
        ("property_campaigns_3::tests::edt_scale_law_seed_000007", edt_scale_law_seed_000007),
        ("property_campaigns_3::tests::edt_scale_law_seed_000008", edt_scale_law_seed_000008),
        ("property_campaigns_3::tests::edt_scale_law_seed_000009", edt_scale_law_seed_000009),
        ("property_campaigns_3::tests::edt_scale_law_seed_000010", edt_scale_law_seed_000010),
        ("property_campaigns_3::tests::edt_scale_law_seed_000011", edt_scale_law_seed_000011),
        ("property_campaigns_3::tests::edt_scale_law_seed_000012", edt_scale_law_seed_000012),
        ("property_campaigns_3::tests::edt_scale_law_seed_000013", edt_scale_law_seed_000013),
        ("property_campaigns_3::tests::edt_scale_law_seed_000014", edt_scale_law_seed_000014),
        ("property_campaigns_3::tests::edt_scale_law_seed_000015", edt_scale_law_seed_000015),
        ("property_campaigns_3::tests::edt_scale_law_seed_000016", edt_scale_law_seed_000016),
        ("property_campaigns_3::tests::edt_scale_law_seed_000017", edt_scale_law_seed_000017),
        ("property_campaigns_3::tests::edt_scale_law_seed_000018", edt_scale_law_seed_000018),
        ("property_campaigns_3::tests::edt_scale_law_seed_000019", edt_scale_law_seed_000019),
        ("property_campaigns_3::tests::edt_scale_law_seed_000020", edt_scale_law_seed_000020),
        ("property_campaigns_3::tests::edt_scale_law_seed_000021", edt_scale_law_seed_000021),
        ("property_campaigns_3::tests::edt_scale_law_seed_000022", edt_scale_law_seed_000022),
        ("property_campaigns_3::tests::edt_scale_law_seed_000023", edt_scale_law_seed_000023),
        ("property_campaigns_3::tests::edt_scale_law_seed_000024", edt_scale_law_seed_000024),
        ("property_campaigns_3::tests::edt_scale_law_seed_000025", edt_scale_law_seed_000025),
        ("property_campaigns_3::tests::edt_scale_law_seed_000026", edt_scale_law_seed_000026),
        ("property_campaigns_3::tests::edt_scale_law_seed_000027", edt_scale_law_seed_000027),
        ("property_campaigns_3::tests::edt_scale_law_seed_000028", edt_scale_law_seed_000028),
        ("property_campaigns_3::tests::edt_scale_law_seed_000029", edt_scale_law_seed_000029),
        ("property_campaigns_3::tests::edt_scale_law_seed_000030", edt_scale_law_seed_000030),
        ("property_campaigns_3::tests::edt_scale_law_seed_000031", edt_scale_law_seed_000031),
        ("property_campaigns_3::tests::edt_scale_law_seed_000032", edt_scale_law_seed_000032),
        ("property_campaigns_3::tests::edt_scale_law_seed_000033", edt_scale_law_seed_000033),
        ("property_campaigns_3::tests::edt_scale_law_seed_000034", edt_scale_law_seed_000034),
        ("property_campaigns_3::tests::edt_scale_law_seed_000035", edt_scale_law_seed_000035),
        ("property_campaigns_3::tests::edt_scale_law_seed_000036", edt_scale_law_seed_000036),
        ("property_campaigns_3::tests::edt_scale_law_seed_000037", edt_scale_law_seed_000037),
        ("property_campaigns_3::tests::edt_scale_law_seed_000038", edt_scale_law_seed_000038),
        ("property_campaigns_3::tests::edt_scale_law_seed_000039", edt_scale_law_seed_000039),
        ("property_campaigns_3::tests::edt_scale_law_seed_000040", edt_scale_law_seed_000040),
        ("property_campaigns_3::tests::edt_scale_law_seed_000041", edt_scale_law_seed_000041),
        ("property_campaigns_3::tests::edt_scale_law_seed_000042", edt_scale_law_seed_000042),
        ("property_campaigns_3::tests::edt_scale_law_seed_000043", edt_scale_law_seed_000043),
        ("property_campaigns_3::tests::edt_scale_law_seed_000044", edt_scale_law_seed_000044),
        ("property_campaigns_3::tests::edt_scale_law_seed_000045", edt_scale_law_seed_000045),
        ("property_campaigns_3::tests::edt_scale_law_seed_000046", edt_scale_law_seed_000046),
        ("property_campaigns_3::tests::edt_scale_law_seed_000047", edt_scale_law_seed_000047),
        ("property_campaigns_3::tests::edt_scale_law_seed_000048", edt_scale_law_seed_000048),
        ("property_campaigns_3::tests::edt_scale_law_seed_000049", edt_scale_law_seed_000049),
        ("property_campaigns_3::tests::edt_scale_law_seed_000050", edt_scale_law_seed_000050),
        ("property_campaigns_3::tests::edt_scale_law_seed_000051", edt_scale_law_seed_000051),
        ("property_campaigns_3::tests::edt_scale_law_seed_000052", edt_scale_law_seed_000052),
        ("property_campaigns_3::tests::edt_scale_law_seed_000053", edt_scale_law_seed_000053),
        ("property_campaigns_3::tests::edt_scale_law_seed_000054", edt_scale_law_seed_000054),
        ("property_campaigns_3::tests::edt_scale_law_seed_000055", edt_scale_law_seed_000055),
        ("property_campaigns_3::tests::edt_scale_law_seed_000056", edt_scale_law_seed_000056),
        ("property_campaigns_3::tests::edt_scale_law_seed_000057", edt_scale_law_seed_000057),
        ("property_campaigns_3::tests::edt_scale_law_seed_000058", edt_scale_law_seed_000058),
        ("property_campaigns_3::tests::edt_scale_law_seed_000059", edt_scale_law_seed_000059),
        ("property_campaigns_3::tests::edt_scale_law_seed_000060", edt_scale_law_seed_000060),
        ("property_campaigns_3::tests::edt_scale_law_seed_000061", edt_scale_law_seed_000061),
        ("property_campaigns_3::tests::edt_scale_law_seed_000062", edt_scale_law_seed_000062),
        ("property_campaigns_3::tests::edt_scale_law_seed_000063", edt_scale_law_seed_000063),
        ("property_campaigns_3::tests::edt_scale_law_seed_000064", edt_scale_law_seed_000064),
        ("property_campaigns_3::tests::edt_scale_law_seed_000065", edt_scale_law_seed_000065),
        ("property_campaigns_3::tests::edt_scale_law_seed_000066", edt_scale_law_seed_000066),
        ("property_campaigns_3::tests::edt_scale_law_seed_000067", edt_scale_law_seed_000067),
        ("property_campaigns_3::tests::edt_scale_law_seed_000068", edt_scale_law_seed_000068),
        ("property_campaigns_3::tests::edt_scale_law_seed_000069", edt_scale_law_seed_000069),
        ("property_campaigns_3::tests::edt_scale_law_seed_000070", edt_scale_law_seed_000070),
        ("property_campaigns_3::tests::edt_scale_law_seed_000071", edt_scale_law_seed_000071),
        ("property_campaigns_3::tests::edt_scale_law_seed_000072", edt_scale_law_seed_000072),
        ("property_campaigns_3::tests::edt_scale_law_seed_000073", edt_scale_law_seed_000073),
        ("property_campaigns_3::tests::edt_scale_law_seed_000074", edt_scale_law_seed_000074),
        ("property_campaigns_3::tests::edt_scale_law_seed_000075", edt_scale_law_seed_000075),
        ("property_campaigns_3::tests::edt_scale_law_seed_000076", edt_scale_law_seed_000076),
        ("property_campaigns_3::tests::edt_scale_law_seed_000077", edt_scale_law_seed_000077),
        ("property_campaigns_3::tests::edt_scale_law_seed_000078", edt_scale_law_seed_000078),
        ("property_campaigns_3::tests::edt_scale_law_seed_000079", edt_scale_law_seed_000079),
        ("property_campaigns_3::tests::edt_scale_law_seed_000080", edt_scale_law_seed_000080),
        ("property_campaigns_3::tests::edt_scale_law_seed_000081", edt_scale_law_seed_000081),
        ("property_campaigns_3::tests::edt_scale_law_seed_000082", edt_scale_law_seed_000082),
        ("property_campaigns_3::tests::edt_scale_law_seed_000083", edt_scale_law_seed_000083),
        ("property_campaigns_3::tests::edt_scale_law_seed_000084", edt_scale_law_seed_000084),
        ("property_campaigns_3::tests::edt_scale_law_seed_000085", edt_scale_law_seed_000085),
        ("property_campaigns_3::tests::edt_scale_law_seed_000086", edt_scale_law_seed_000086),
        ("property_campaigns_3::tests::edt_scale_law_seed_000087", edt_scale_law_seed_000087),
        ("property_campaigns_3::tests::edt_scale_law_seed_000088", edt_scale_law_seed_000088),
        ("property_campaigns_3::tests::edt_scale_law_seed_000089", edt_scale_law_seed_000089),
        ("property_campaigns_3::tests::edt_scale_law_seed_000090", edt_scale_law_seed_000090),
        ("property_campaigns_3::tests::edt_scale_law_seed_000091", edt_scale_law_seed_000091),
        ("property_campaigns_3::tests::edt_scale_law_seed_000092", edt_scale_law_seed_000092),
        ("property_campaigns_3::tests::edt_scale_law_seed_000093", edt_scale_law_seed_000093),
        ("property_campaigns_3::tests::edt_scale_law_seed_000094", edt_scale_law_seed_000094),
        ("property_campaigns_3::tests::edt_scale_law_seed_000095", edt_scale_law_seed_000095),
        ("property_campaigns_3::tests::edt_scale_law_seed_000096", edt_scale_law_seed_000096),
        ("property_campaigns_3::tests::edt_scale_law_seed_000097", edt_scale_law_seed_000097),
        ("property_campaigns_3::tests::edt_scale_law_seed_000098", edt_scale_law_seed_000098),
        ("property_campaigns_3::tests::edt_scale_law_seed_000099", edt_scale_law_seed_000099),
        ("property_campaigns_3::tests::edt_scale_law_seed_000100", edt_scale_law_seed_000100),
        ("property_campaigns_3::tests::edt_scale_law_seed_000101", edt_scale_law_seed_000101),
        ("property_campaigns_3::tests::edt_scale_law_seed_000102", edt_scale_law_seed_000102),
        ("property_campaigns_3::tests::edt_scale_law_seed_000103", edt_scale_law_seed_000103),
        ("property_campaigns_3::tests::edt_scale_law_seed_000104", edt_scale_law_seed_000104),
        ("property_campaigns_3::tests::edt_scale_law_seed_000105", edt_scale_law_seed_000105),
        ("property_campaigns_3::tests::edt_scale_law_seed_000106", edt_scale_law_seed_000106),
        ("property_campaigns_3::tests::edt_scale_law_seed_000107", edt_scale_law_seed_000107),
        ("property_campaigns_3::tests::edt_scale_law_seed_000108", edt_scale_law_seed_000108),
        ("property_campaigns_3::tests::edt_scale_law_seed_000109", edt_scale_law_seed_000109),
        ("property_campaigns_3::tests::edt_scale_law_seed_000110", edt_scale_law_seed_000110),
        ("property_campaigns_3::tests::edt_scale_law_seed_000111", edt_scale_law_seed_000111),
        ("property_campaigns_3::tests::edt_scale_law_seed_000112", edt_scale_law_seed_000112),
        ("property_campaigns_3::tests::edt_scale_law_seed_000113", edt_scale_law_seed_000113),
        ("property_campaigns_3::tests::edt_scale_law_seed_000114", edt_scale_law_seed_000114),
        ("property_campaigns_3::tests::edt_scale_law_seed_000115", edt_scale_law_seed_000115),
        ("property_campaigns_3::tests::edt_scale_law_seed_000116", edt_scale_law_seed_000116),
        ("property_campaigns_3::tests::edt_scale_law_seed_000117", edt_scale_law_seed_000117),
        ("property_campaigns_3::tests::edt_scale_law_seed_000118", edt_scale_law_seed_000118),
        ("property_campaigns_3::tests::edt_scale_law_seed_000119", edt_scale_law_seed_000119),
        ("property_campaigns_3::tests::edt_scale_law_seed_000120", edt_scale_law_seed_000120),
        ("property_campaigns_3::tests::edt_scale_law_seed_000121", edt_scale_law_seed_000121),
        ("property_campaigns_3::tests::edt_scale_law_seed_000122", edt_scale_law_seed_000122),
        ("property_campaigns_3::tests::edt_scale_law_seed_000123", edt_scale_law_seed_000123),
        ("property_campaigns_3::tests::edt_scale_law_seed_000124", edt_scale_law_seed_000124),
        ("property_campaigns_3::tests::edt_scale_law_seed_000125", edt_scale_law_seed_000125),
        ("property_campaigns_3::tests::edt_scale_law_seed_000126", edt_scale_law_seed_000126),
        ("property_campaigns_3::tests::edt_scale_law_seed_000127", edt_scale_law_seed_000127),
        ("property_campaigns_3::tests::edt_scale_law_seed_000128", edt_scale_law_seed_000128),
        ("property_campaigns_3::tests::edt_scale_law_seed_000129", edt_scale_law_seed_000129),
        ("property_campaigns_3::tests::edt_scale_law_seed_000130", edt_scale_law_seed_000130),
        ("property_campaigns_3::tests::edt_scale_law_seed_000131", edt_scale_law_seed_000131),
        ("property_campaigns_3::tests::edt_scale_law_seed_000132", edt_scale_law_seed_000132),
        ("property_campaigns_3::tests::edt_scale_law_seed_000133", edt_scale_law_seed_000133),
        ("property_campaigns_3::tests::edt_scale_law_seed_000134", edt_scale_law_seed_000134),
        ("property_campaigns_3::tests::edt_scale_law_seed_000135", edt_scale_law_seed_000135),
        ("property_campaigns_3::tests::edt_scale_law_seed_000136", edt_scale_law_seed_000136),
        ("property_campaigns_3::tests::edt_scale_law_seed_000137", edt_scale_law_seed_000137),
        ("property_campaigns_3::tests::edt_scale_law_seed_000138", edt_scale_law_seed_000138),
        ("property_campaigns_3::tests::edt_scale_law_seed_000139", edt_scale_law_seed_000139),
        ("property_campaigns_3::tests::edt_scale_law_seed_000140", edt_scale_law_seed_000140),
        ("property_campaigns_3::tests::edt_scale_law_seed_000141", edt_scale_law_seed_000141),
        ("property_campaigns_3::tests::edt_scale_law_seed_000142", edt_scale_law_seed_000142),
        ("property_campaigns_3::tests::edt_scale_law_seed_000143", edt_scale_law_seed_000143),
        ("property_campaigns_3::tests::edt_scale_law_seed_000144", edt_scale_law_seed_000144),
        ("property_campaigns_3::tests::edt_scale_law_seed_000145", edt_scale_law_seed_000145),
        ("property_campaigns_3::tests::edt_scale_law_seed_000146", edt_scale_law_seed_000146),
        ("property_campaigns_3::tests::edt_scale_law_seed_000147", edt_scale_law_seed_000147),
        ("property_campaigns_3::tests::edt_scale_law_seed_000148", edt_scale_law_seed_000148),
        ("property_campaigns_3::tests::edt_scale_law_seed_000149", edt_scale_law_seed_000149),
        ("property_campaigns_3::tests::edt_scale_law_seed_000150", edt_scale_law_seed_000150),
        ("property_campaigns_3::tests::edt_scale_law_seed_000151", edt_scale_law_seed_000151),
        ("property_campaigns_3::tests::edt_scale_law_seed_000152", edt_scale_law_seed_000152),
        ("property_campaigns_3::tests::edt_scale_law_seed_000153", edt_scale_law_seed_000153),
        ("property_campaigns_3::tests::edt_scale_law_seed_000154", edt_scale_law_seed_000154),
        ("property_campaigns_3::tests::edt_scale_law_seed_000155", edt_scale_law_seed_000155),
        ("property_campaigns_3::tests::edt_scale_law_seed_000156", edt_scale_law_seed_000156),
        ("property_campaigns_3::tests::edt_scale_law_seed_000157", edt_scale_law_seed_000157),
        ("property_campaigns_3::tests::edt_scale_law_seed_000158", edt_scale_law_seed_000158),
        ("property_campaigns_3::tests::edt_scale_law_seed_000159", edt_scale_law_seed_000159),
        ("property_campaigns_3::tests::edt_scale_law_seed_000160", edt_scale_law_seed_000160),
        ("property_campaigns_3::tests::edt_scale_law_seed_000161", edt_scale_law_seed_000161),
        ("property_campaigns_3::tests::edt_scale_law_seed_000162", edt_scale_law_seed_000162),
        ("property_campaigns_3::tests::edt_scale_law_seed_000163", edt_scale_law_seed_000163),
        ("property_campaigns_3::tests::edt_scale_law_seed_000164", edt_scale_law_seed_000164),
        ("property_campaigns_3::tests::edt_scale_law_seed_000165", edt_scale_law_seed_000165),
        ("property_campaigns_3::tests::edt_scale_law_seed_000166", edt_scale_law_seed_000166),
        ("property_campaigns_3::tests::edt_scale_law_seed_000167", edt_scale_law_seed_000167),
        ("property_campaigns_3::tests::edt_scale_law_seed_000168", edt_scale_law_seed_000168),
        ("property_campaigns_3::tests::edt_scale_law_seed_000169", edt_scale_law_seed_000169),
        ("property_campaigns_3::tests::edt_scale_law_seed_000170", edt_scale_law_seed_000170),
        ("property_campaigns_3::tests::edt_scale_law_seed_000171", edt_scale_law_seed_000171),
        ("property_campaigns_3::tests::edt_scale_law_seed_000172", edt_scale_law_seed_000172),
        ("property_campaigns_3::tests::edt_scale_law_seed_000173", edt_scale_law_seed_000173),
        ("property_campaigns_3::tests::edt_scale_law_seed_000174", edt_scale_law_seed_000174),
        ("property_campaigns_3::tests::edt_scale_law_seed_000175", edt_scale_law_seed_000175),
        ("property_campaigns_3::tests::edt_scale_law_seed_000176", edt_scale_law_seed_000176),
        ("property_campaigns_3::tests::edt_scale_law_seed_000177", edt_scale_law_seed_000177),
        ("property_campaigns_3::tests::edt_scale_law_seed_000178", edt_scale_law_seed_000178),
        ("property_campaigns_3::tests::edt_scale_law_seed_000179", edt_scale_law_seed_000179),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000000", edt_monotone_added_sources_seed_000000),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000001", edt_monotone_added_sources_seed_000001),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000002", edt_monotone_added_sources_seed_000002),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000003", edt_monotone_added_sources_seed_000003),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000004", edt_monotone_added_sources_seed_000004),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000005", edt_monotone_added_sources_seed_000005),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000006", edt_monotone_added_sources_seed_000006),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000007", edt_monotone_added_sources_seed_000007),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000008", edt_monotone_added_sources_seed_000008),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000009", edt_monotone_added_sources_seed_000009),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000010", edt_monotone_added_sources_seed_000010),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000011", edt_monotone_added_sources_seed_000011),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000012", edt_monotone_added_sources_seed_000012),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000013", edt_monotone_added_sources_seed_000013),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000014", edt_monotone_added_sources_seed_000014),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000015", edt_monotone_added_sources_seed_000015),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000016", edt_monotone_added_sources_seed_000016),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000017", edt_monotone_added_sources_seed_000017),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000018", edt_monotone_added_sources_seed_000018),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000019", edt_monotone_added_sources_seed_000019),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000020", edt_monotone_added_sources_seed_000020),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000021", edt_monotone_added_sources_seed_000021),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000022", edt_monotone_added_sources_seed_000022),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000023", edt_monotone_added_sources_seed_000023),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000024", edt_monotone_added_sources_seed_000024),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000025", edt_monotone_added_sources_seed_000025),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000026", edt_monotone_added_sources_seed_000026),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000027", edt_monotone_added_sources_seed_000027),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000028", edt_monotone_added_sources_seed_000028),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000029", edt_monotone_added_sources_seed_000029),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000030", edt_monotone_added_sources_seed_000030),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000031", edt_monotone_added_sources_seed_000031),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000032", edt_monotone_added_sources_seed_000032),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000033", edt_monotone_added_sources_seed_000033),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000034", edt_monotone_added_sources_seed_000034),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000035", edt_monotone_added_sources_seed_000035),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000036", edt_monotone_added_sources_seed_000036),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000037", edt_monotone_added_sources_seed_000037),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000038", edt_monotone_added_sources_seed_000038),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000039", edt_monotone_added_sources_seed_000039),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000040", edt_monotone_added_sources_seed_000040),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000041", edt_monotone_added_sources_seed_000041),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000042", edt_monotone_added_sources_seed_000042),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000043", edt_monotone_added_sources_seed_000043),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000044", edt_monotone_added_sources_seed_000044),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000045", edt_monotone_added_sources_seed_000045),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000046", edt_monotone_added_sources_seed_000046),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000047", edt_monotone_added_sources_seed_000047),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000048", edt_monotone_added_sources_seed_000048),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000049", edt_monotone_added_sources_seed_000049),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000050", edt_monotone_added_sources_seed_000050),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000051", edt_monotone_added_sources_seed_000051),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000052", edt_monotone_added_sources_seed_000052),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000053", edt_monotone_added_sources_seed_000053),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000054", edt_monotone_added_sources_seed_000054),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000055", edt_monotone_added_sources_seed_000055),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000056", edt_monotone_added_sources_seed_000056),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000057", edt_monotone_added_sources_seed_000057),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000058", edt_monotone_added_sources_seed_000058),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000059", edt_monotone_added_sources_seed_000059),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000060", edt_monotone_added_sources_seed_000060),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000061", edt_monotone_added_sources_seed_000061),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000062", edt_monotone_added_sources_seed_000062),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000063", edt_monotone_added_sources_seed_000063),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000064", edt_monotone_added_sources_seed_000064),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000065", edt_monotone_added_sources_seed_000065),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000066", edt_monotone_added_sources_seed_000066),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000067", edt_monotone_added_sources_seed_000067),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000068", edt_monotone_added_sources_seed_000068),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000069", edt_monotone_added_sources_seed_000069),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000070", edt_monotone_added_sources_seed_000070),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000071", edt_monotone_added_sources_seed_000071),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000072", edt_monotone_added_sources_seed_000072),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000073", edt_monotone_added_sources_seed_000073),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000074", edt_monotone_added_sources_seed_000074),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000075", edt_monotone_added_sources_seed_000075),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000076", edt_monotone_added_sources_seed_000076),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000077", edt_monotone_added_sources_seed_000077),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000078", edt_monotone_added_sources_seed_000078),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000079", edt_monotone_added_sources_seed_000079),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000080", edt_monotone_added_sources_seed_000080),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000081", edt_monotone_added_sources_seed_000081),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000082", edt_monotone_added_sources_seed_000082),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000083", edt_monotone_added_sources_seed_000083),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000084", edt_monotone_added_sources_seed_000084),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000085", edt_monotone_added_sources_seed_000085),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000086", edt_monotone_added_sources_seed_000086),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000087", edt_monotone_added_sources_seed_000087),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000088", edt_monotone_added_sources_seed_000088),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000089", edt_monotone_added_sources_seed_000089),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000090", edt_monotone_added_sources_seed_000090),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000091", edt_monotone_added_sources_seed_000091),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000092", edt_monotone_added_sources_seed_000092),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000093", edt_monotone_added_sources_seed_000093),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000094", edt_monotone_added_sources_seed_000094),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000095", edt_monotone_added_sources_seed_000095),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000096", edt_monotone_added_sources_seed_000096),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000097", edt_monotone_added_sources_seed_000097),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000098", edt_monotone_added_sources_seed_000098),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000099", edt_monotone_added_sources_seed_000099),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000100", edt_monotone_added_sources_seed_000100),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000101", edt_monotone_added_sources_seed_000101),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000102", edt_monotone_added_sources_seed_000102),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000103", edt_monotone_added_sources_seed_000103),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000104", edt_monotone_added_sources_seed_000104),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000105", edt_monotone_added_sources_seed_000105),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000106", edt_monotone_added_sources_seed_000106),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000107", edt_monotone_added_sources_seed_000107),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000108", edt_monotone_added_sources_seed_000108),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000109", edt_monotone_added_sources_seed_000109),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000110", edt_monotone_added_sources_seed_000110),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000111", edt_monotone_added_sources_seed_000111),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000112", edt_monotone_added_sources_seed_000112),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000113", edt_monotone_added_sources_seed_000113),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000114", edt_monotone_added_sources_seed_000114),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000115", edt_monotone_added_sources_seed_000115),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000116", edt_monotone_added_sources_seed_000116),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000117", edt_monotone_added_sources_seed_000117),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000118", edt_monotone_added_sources_seed_000118),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000119", edt_monotone_added_sources_seed_000119),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000120", edt_monotone_added_sources_seed_000120),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000121", edt_monotone_added_sources_seed_000121),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000122", edt_monotone_added_sources_seed_000122),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000123", edt_monotone_added_sources_seed_000123),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000124", edt_monotone_added_sources_seed_000124),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000125", edt_monotone_added_sources_seed_000125),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000126", edt_monotone_added_sources_seed_000126),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000127", edt_monotone_added_sources_seed_000127),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000128", edt_monotone_added_sources_seed_000128),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000129", edt_monotone_added_sources_seed_000129),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000130", edt_monotone_added_sources_seed_000130),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000131", edt_monotone_added_sources_seed_000131),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000132", edt_monotone_added_sources_seed_000132),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000133", edt_monotone_added_sources_seed_000133),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000134", edt_monotone_added_sources_seed_000134),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000135", edt_monotone_added_sources_seed_000135),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000136", edt_monotone_added_sources_seed_000136),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000137", edt_monotone_added_sources_seed_000137),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000138", edt_monotone_added_sources_seed_000138),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000139", edt_monotone_added_sources_seed_000139),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000140", edt_monotone_added_sources_seed_000140),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000141", edt_monotone_added_sources_seed_000141),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000142", edt_monotone_added_sources_seed_000142),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000143", edt_monotone_added_sources_seed_000143),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000144", edt_monotone_added_sources_seed_000144),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000145", edt_monotone_added_sources_seed_000145),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000146", edt_monotone_added_sources_seed_000146),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000147", edt_monotone_added_sources_seed_000147),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000148", edt_monotone_added_sources_seed_000148),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000149", edt_monotone_added_sources_seed_000149),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000150", edt_monotone_added_sources_seed_000150),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000151", edt_monotone_added_sources_seed_000151),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000152", edt_monotone_added_sources_seed_000152),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000153", edt_monotone_added_sources_seed_000153),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000154", edt_monotone_added_sources_seed_000154),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000155", edt_monotone_added_sources_seed_000155),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000156", edt_monotone_added_sources_seed_000156),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000157", edt_monotone_added_sources_seed_000157),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000158", edt_monotone_added_sources_seed_000158),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000159", edt_monotone_added_sources_seed_000159),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000160", edt_monotone_added_sources_seed_000160),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000161", edt_monotone_added_sources_seed_000161),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000162", edt_monotone_added_sources_seed_000162),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000163", edt_monotone_added_sources_seed_000163),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000164", edt_monotone_added_sources_seed_000164),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000165", edt_monotone_added_sources_seed_000165),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000166", edt_monotone_added_sources_seed_000166),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000167", edt_monotone_added_sources_seed_000167),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000168", edt_monotone_added_sources_seed_000168),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000169", edt_monotone_added_sources_seed_000169),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000170", edt_monotone_added_sources_seed_000170),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000171", edt_monotone_added_sources_seed_000171),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000172", edt_monotone_added_sources_seed_000172),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000173", edt_monotone_added_sources_seed_000173),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000174", edt_monotone_added_sources_seed_000174),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000175", edt_monotone_added_sources_seed_000175),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000176", edt_monotone_added_sources_seed_000176),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000177", edt_monotone_added_sources_seed_000177),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000178", edt_monotone_added_sources_seed_000178),
        ("property_campaigns_3::tests::edt_monotone_added_sources_seed_000179", edt_monotone_added_sources_seed_000179),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000000", hypot_symmetric_seed_000000),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000001", hypot_symmetric_seed_000001),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000002", hypot_symmetric_seed_000002),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000003", hypot_symmetric_seed_000003),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000004", hypot_symmetric_seed_000004),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000005", hypot_symmetric_seed_000005),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000006", hypot_symmetric_seed_000006),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000007", hypot_symmetric_seed_000007),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000008", hypot_symmetric_seed_000008),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000009", hypot_symmetric_seed_000009),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000010", hypot_symmetric_seed_000010),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000011", hypot_symmetric_seed_000011),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000012", hypot_symmetric_seed_000012),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000013", hypot_symmetric_seed_000013),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000014", hypot_symmetric_seed_000014),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000015", hypot_symmetric_seed_000015),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000016", hypot_symmetric_seed_000016),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000017", hypot_symmetric_seed_000017),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000018", hypot_symmetric_seed_000018),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000019", hypot_symmetric_seed_000019),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000020", hypot_symmetric_seed_000020),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000021", hypot_symmetric_seed_000021),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000022", hypot_symmetric_seed_000022),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000023", hypot_symmetric_seed_000023),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000024", hypot_symmetric_seed_000024),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000025", hypot_symmetric_seed_000025),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000026", hypot_symmetric_seed_000026),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000027", hypot_symmetric_seed_000027),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000028", hypot_symmetric_seed_000028),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000029", hypot_symmetric_seed_000029),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000030", hypot_symmetric_seed_000030),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000031", hypot_symmetric_seed_000031),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000032", hypot_symmetric_seed_000032),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000033", hypot_symmetric_seed_000033),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000034", hypot_symmetric_seed_000034),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000035", hypot_symmetric_seed_000035),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000036", hypot_symmetric_seed_000036),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000037", hypot_symmetric_seed_000037),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000038", hypot_symmetric_seed_000038),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000039", hypot_symmetric_seed_000039),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000040", hypot_symmetric_seed_000040),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000041", hypot_symmetric_seed_000041),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000042", hypot_symmetric_seed_000042),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000043", hypot_symmetric_seed_000043),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000044", hypot_symmetric_seed_000044),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000045", hypot_symmetric_seed_000045),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000046", hypot_symmetric_seed_000046),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000047", hypot_symmetric_seed_000047),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000048", hypot_symmetric_seed_000048),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000049", hypot_symmetric_seed_000049),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000050", hypot_symmetric_seed_000050),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000051", hypot_symmetric_seed_000051),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000052", hypot_symmetric_seed_000052),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000053", hypot_symmetric_seed_000053),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000054", hypot_symmetric_seed_000054),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000055", hypot_symmetric_seed_000055),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000056", hypot_symmetric_seed_000056),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000057", hypot_symmetric_seed_000057),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000058", hypot_symmetric_seed_000058),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000059", hypot_symmetric_seed_000059),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000060", hypot_symmetric_seed_000060),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000061", hypot_symmetric_seed_000061),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000062", hypot_symmetric_seed_000062),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000063", hypot_symmetric_seed_000063),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000064", hypot_symmetric_seed_000064),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000065", hypot_symmetric_seed_000065),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000066", hypot_symmetric_seed_000066),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000067", hypot_symmetric_seed_000067),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000068", hypot_symmetric_seed_000068),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000069", hypot_symmetric_seed_000069),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000070", hypot_symmetric_seed_000070),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000071", hypot_symmetric_seed_000071),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000072", hypot_symmetric_seed_000072),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000073", hypot_symmetric_seed_000073),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000074", hypot_symmetric_seed_000074),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000075", hypot_symmetric_seed_000075),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000076", hypot_symmetric_seed_000076),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000077", hypot_symmetric_seed_000077),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000078", hypot_symmetric_seed_000078),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000079", hypot_symmetric_seed_000079),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000080", hypot_symmetric_seed_000080),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000081", hypot_symmetric_seed_000081),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000082", hypot_symmetric_seed_000082),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000083", hypot_symmetric_seed_000083),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000084", hypot_symmetric_seed_000084),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000085", hypot_symmetric_seed_000085),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000086", hypot_symmetric_seed_000086),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000087", hypot_symmetric_seed_000087),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000088", hypot_symmetric_seed_000088),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000089", hypot_symmetric_seed_000089),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000090", hypot_symmetric_seed_000090),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000091", hypot_symmetric_seed_000091),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000092", hypot_symmetric_seed_000092),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000093", hypot_symmetric_seed_000093),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000094", hypot_symmetric_seed_000094),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000095", hypot_symmetric_seed_000095),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000096", hypot_symmetric_seed_000096),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000097", hypot_symmetric_seed_000097),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000098", hypot_symmetric_seed_000098),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000099", hypot_symmetric_seed_000099),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000100", hypot_symmetric_seed_000100),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000101", hypot_symmetric_seed_000101),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000102", hypot_symmetric_seed_000102),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000103", hypot_symmetric_seed_000103),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000104", hypot_symmetric_seed_000104),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000105", hypot_symmetric_seed_000105),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000106", hypot_symmetric_seed_000106),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000107", hypot_symmetric_seed_000107),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000108", hypot_symmetric_seed_000108),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000109", hypot_symmetric_seed_000109),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000110", hypot_symmetric_seed_000110),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000111", hypot_symmetric_seed_000111),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000112", hypot_symmetric_seed_000112),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000113", hypot_symmetric_seed_000113),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000114", hypot_symmetric_seed_000114),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000115", hypot_symmetric_seed_000115),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000116", hypot_symmetric_seed_000116),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000117", hypot_symmetric_seed_000117),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000118", hypot_symmetric_seed_000118),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000119", hypot_symmetric_seed_000119),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000120", hypot_symmetric_seed_000120),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000121", hypot_symmetric_seed_000121),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000122", hypot_symmetric_seed_000122),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000123", hypot_symmetric_seed_000123),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000124", hypot_symmetric_seed_000124),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000125", hypot_symmetric_seed_000125),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000126", hypot_symmetric_seed_000126),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000127", hypot_symmetric_seed_000127),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000128", hypot_symmetric_seed_000128),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000129", hypot_symmetric_seed_000129),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000130", hypot_symmetric_seed_000130),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000131", hypot_symmetric_seed_000131),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000132", hypot_symmetric_seed_000132),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000133", hypot_symmetric_seed_000133),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000134", hypot_symmetric_seed_000134),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000135", hypot_symmetric_seed_000135),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000136", hypot_symmetric_seed_000136),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000137", hypot_symmetric_seed_000137),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000138", hypot_symmetric_seed_000138),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000139", hypot_symmetric_seed_000139),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000140", hypot_symmetric_seed_000140),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000141", hypot_symmetric_seed_000141),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000142", hypot_symmetric_seed_000142),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000143", hypot_symmetric_seed_000143),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000144", hypot_symmetric_seed_000144),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000145", hypot_symmetric_seed_000145),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000146", hypot_symmetric_seed_000146),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000147", hypot_symmetric_seed_000147),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000148", hypot_symmetric_seed_000148),
        ("property_campaigns_3::tests::hypot_symmetric_seed_000149", hypot_symmetric_seed_000149),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000000", hypot_scale_invariant_seed_000000),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000001", hypot_scale_invariant_seed_000001),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000002", hypot_scale_invariant_seed_000002),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000003", hypot_scale_invariant_seed_000003),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000004", hypot_scale_invariant_seed_000004),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000005", hypot_scale_invariant_seed_000005),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000006", hypot_scale_invariant_seed_000006),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000007", hypot_scale_invariant_seed_000007),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000008", hypot_scale_invariant_seed_000008),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000009", hypot_scale_invariant_seed_000009),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000010", hypot_scale_invariant_seed_000010),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000011", hypot_scale_invariant_seed_000011),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000012", hypot_scale_invariant_seed_000012),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000013", hypot_scale_invariant_seed_000013),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000014", hypot_scale_invariant_seed_000014),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000015", hypot_scale_invariant_seed_000015),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000016", hypot_scale_invariant_seed_000016),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000017", hypot_scale_invariant_seed_000017),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000018", hypot_scale_invariant_seed_000018),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000019", hypot_scale_invariant_seed_000019),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000020", hypot_scale_invariant_seed_000020),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000021", hypot_scale_invariant_seed_000021),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000022", hypot_scale_invariant_seed_000022),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000023", hypot_scale_invariant_seed_000023),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000024", hypot_scale_invariant_seed_000024),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000025", hypot_scale_invariant_seed_000025),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000026", hypot_scale_invariant_seed_000026),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000027", hypot_scale_invariant_seed_000027),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000028", hypot_scale_invariant_seed_000028),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000029", hypot_scale_invariant_seed_000029),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000030", hypot_scale_invariant_seed_000030),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000031", hypot_scale_invariant_seed_000031),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000032", hypot_scale_invariant_seed_000032),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000033", hypot_scale_invariant_seed_000033),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000034", hypot_scale_invariant_seed_000034),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000035", hypot_scale_invariant_seed_000035),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000036", hypot_scale_invariant_seed_000036),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000037", hypot_scale_invariant_seed_000037),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000038", hypot_scale_invariant_seed_000038),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000039", hypot_scale_invariant_seed_000039),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000040", hypot_scale_invariant_seed_000040),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000041", hypot_scale_invariant_seed_000041),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000042", hypot_scale_invariant_seed_000042),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000043", hypot_scale_invariant_seed_000043),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000044", hypot_scale_invariant_seed_000044),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000045", hypot_scale_invariant_seed_000045),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000046", hypot_scale_invariant_seed_000046),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000047", hypot_scale_invariant_seed_000047),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000048", hypot_scale_invariant_seed_000048),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000049", hypot_scale_invariant_seed_000049),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000050", hypot_scale_invariant_seed_000050),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000051", hypot_scale_invariant_seed_000051),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000052", hypot_scale_invariant_seed_000052),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000053", hypot_scale_invariant_seed_000053),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000054", hypot_scale_invariant_seed_000054),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000055", hypot_scale_invariant_seed_000055),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000056", hypot_scale_invariant_seed_000056),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000057", hypot_scale_invariant_seed_000057),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000058", hypot_scale_invariant_seed_000058),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000059", hypot_scale_invariant_seed_000059),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000060", hypot_scale_invariant_seed_000060),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000061", hypot_scale_invariant_seed_000061),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000062", hypot_scale_invariant_seed_000062),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000063", hypot_scale_invariant_seed_000063),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000064", hypot_scale_invariant_seed_000064),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000065", hypot_scale_invariant_seed_000065),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000066", hypot_scale_invariant_seed_000066),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000067", hypot_scale_invariant_seed_000067),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000068", hypot_scale_invariant_seed_000068),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000069", hypot_scale_invariant_seed_000069),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000070", hypot_scale_invariant_seed_000070),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000071", hypot_scale_invariant_seed_000071),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000072", hypot_scale_invariant_seed_000072),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000073", hypot_scale_invariant_seed_000073),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000074", hypot_scale_invariant_seed_000074),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000075", hypot_scale_invariant_seed_000075),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000076", hypot_scale_invariant_seed_000076),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000077", hypot_scale_invariant_seed_000077),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000078", hypot_scale_invariant_seed_000078),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000079", hypot_scale_invariant_seed_000079),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000080", hypot_scale_invariant_seed_000080),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000081", hypot_scale_invariant_seed_000081),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000082", hypot_scale_invariant_seed_000082),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000083", hypot_scale_invariant_seed_000083),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000084", hypot_scale_invariant_seed_000084),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000085", hypot_scale_invariant_seed_000085),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000086", hypot_scale_invariant_seed_000086),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000087", hypot_scale_invariant_seed_000087),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000088", hypot_scale_invariant_seed_000088),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000089", hypot_scale_invariant_seed_000089),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000090", hypot_scale_invariant_seed_000090),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000091", hypot_scale_invariant_seed_000091),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000092", hypot_scale_invariant_seed_000092),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000093", hypot_scale_invariant_seed_000093),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000094", hypot_scale_invariant_seed_000094),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000095", hypot_scale_invariant_seed_000095),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000096", hypot_scale_invariant_seed_000096),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000097", hypot_scale_invariant_seed_000097),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000098", hypot_scale_invariant_seed_000098),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000099", hypot_scale_invariant_seed_000099),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000100", hypot_scale_invariant_seed_000100),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000101", hypot_scale_invariant_seed_000101),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000102", hypot_scale_invariant_seed_000102),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000103", hypot_scale_invariant_seed_000103),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000104", hypot_scale_invariant_seed_000104),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000105", hypot_scale_invariant_seed_000105),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000106", hypot_scale_invariant_seed_000106),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000107", hypot_scale_invariant_seed_000107),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000108", hypot_scale_invariant_seed_000108),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000109", hypot_scale_invariant_seed_000109),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000110", hypot_scale_invariant_seed_000110),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000111", hypot_scale_invariant_seed_000111),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000112", hypot_scale_invariant_seed_000112),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000113", hypot_scale_invariant_seed_000113),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000114", hypot_scale_invariant_seed_000114),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000115", hypot_scale_invariant_seed_000115),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000116", hypot_scale_invariant_seed_000116),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000117", hypot_scale_invariant_seed_000117),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000118", hypot_scale_invariant_seed_000118),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000119", hypot_scale_invariant_seed_000119),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000120", hypot_scale_invariant_seed_000120),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000121", hypot_scale_invariant_seed_000121),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000122", hypot_scale_invariant_seed_000122),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000123", hypot_scale_invariant_seed_000123),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000124", hypot_scale_invariant_seed_000124),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000125", hypot_scale_invariant_seed_000125),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000126", hypot_scale_invariant_seed_000126),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000127", hypot_scale_invariant_seed_000127),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000128", hypot_scale_invariant_seed_000128),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000129", hypot_scale_invariant_seed_000129),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000130", hypot_scale_invariant_seed_000130),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000131", hypot_scale_invariant_seed_000131),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000132", hypot_scale_invariant_seed_000132),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000133", hypot_scale_invariant_seed_000133),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000134", hypot_scale_invariant_seed_000134),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000135", hypot_scale_invariant_seed_000135),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000136", hypot_scale_invariant_seed_000136),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000137", hypot_scale_invariant_seed_000137),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000138", hypot_scale_invariant_seed_000138),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000139", hypot_scale_invariant_seed_000139),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000140", hypot_scale_invariant_seed_000140),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000141", hypot_scale_invariant_seed_000141),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000142", hypot_scale_invariant_seed_000142),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000143", hypot_scale_invariant_seed_000143),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000144", hypot_scale_invariant_seed_000144),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000145", hypot_scale_invariant_seed_000145),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000146", hypot_scale_invariant_seed_000146),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000147", hypot_scale_invariant_seed_000147),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000148", hypot_scale_invariant_seed_000148),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000149", hypot_scale_invariant_seed_000149),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000150", hypot_scale_invariant_seed_000150),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000151", hypot_scale_invariant_seed_000151),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000152", hypot_scale_invariant_seed_000152),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000153", hypot_scale_invariant_seed_000153),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000154", hypot_scale_invariant_seed_000154),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000155", hypot_scale_invariant_seed_000155),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000156", hypot_scale_invariant_seed_000156),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000157", hypot_scale_invariant_seed_000157),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000158", hypot_scale_invariant_seed_000158),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000159", hypot_scale_invariant_seed_000159),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000160", hypot_scale_invariant_seed_000160),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000161", hypot_scale_invariant_seed_000161),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000162", hypot_scale_invariant_seed_000162),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000163", hypot_scale_invariant_seed_000163),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000164", hypot_scale_invariant_seed_000164),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000165", hypot_scale_invariant_seed_000165),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000166", hypot_scale_invariant_seed_000166),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000167", hypot_scale_invariant_seed_000167),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000168", hypot_scale_invariant_seed_000168),
        ("property_campaigns_3::tests::hypot_scale_invariant_seed_000169", hypot_scale_invariant_seed_000169),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000000", bounding_radius_monotonic_width_seed_000000),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000001", bounding_radius_monotonic_width_seed_000001),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000002", bounding_radius_monotonic_width_seed_000002),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000003", bounding_radius_monotonic_width_seed_000003),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000004", bounding_radius_monotonic_width_seed_000004),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000005", bounding_radius_monotonic_width_seed_000005),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000006", bounding_radius_monotonic_width_seed_000006),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000007", bounding_radius_monotonic_width_seed_000007),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000008", bounding_radius_monotonic_width_seed_000008),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000009", bounding_radius_monotonic_width_seed_000009),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000010", bounding_radius_monotonic_width_seed_000010),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000011", bounding_radius_monotonic_width_seed_000011),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000012", bounding_radius_monotonic_width_seed_000012),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000013", bounding_radius_monotonic_width_seed_000013),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000014", bounding_radius_monotonic_width_seed_000014),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000015", bounding_radius_monotonic_width_seed_000015),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000016", bounding_radius_monotonic_width_seed_000016),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000017", bounding_radius_monotonic_width_seed_000017),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000018", bounding_radius_monotonic_width_seed_000018),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000019", bounding_radius_monotonic_width_seed_000019),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000020", bounding_radius_monotonic_width_seed_000020),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000021", bounding_radius_monotonic_width_seed_000021),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000022", bounding_radius_monotonic_width_seed_000022),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000023", bounding_radius_monotonic_width_seed_000023),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000024", bounding_radius_monotonic_width_seed_000024),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000025", bounding_radius_monotonic_width_seed_000025),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000026", bounding_radius_monotonic_width_seed_000026),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000027", bounding_radius_monotonic_width_seed_000027),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000028", bounding_radius_monotonic_width_seed_000028),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000029", bounding_radius_monotonic_width_seed_000029),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000030", bounding_radius_monotonic_width_seed_000030),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000031", bounding_radius_monotonic_width_seed_000031),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000032", bounding_radius_monotonic_width_seed_000032),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000033", bounding_radius_monotonic_width_seed_000033),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000034", bounding_radius_monotonic_width_seed_000034),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000035", bounding_radius_monotonic_width_seed_000035),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000036", bounding_radius_monotonic_width_seed_000036),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000037", bounding_radius_monotonic_width_seed_000037),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000038", bounding_radius_monotonic_width_seed_000038),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000039", bounding_radius_monotonic_width_seed_000039),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000040", bounding_radius_monotonic_width_seed_000040),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000041", bounding_radius_monotonic_width_seed_000041),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000042", bounding_radius_monotonic_width_seed_000042),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000043", bounding_radius_monotonic_width_seed_000043),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000044", bounding_radius_monotonic_width_seed_000044),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000045", bounding_radius_monotonic_width_seed_000045),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000046", bounding_radius_monotonic_width_seed_000046),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000047", bounding_radius_monotonic_width_seed_000047),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000048", bounding_radius_monotonic_width_seed_000048),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000049", bounding_radius_monotonic_width_seed_000049),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000050", bounding_radius_monotonic_width_seed_000050),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000051", bounding_radius_monotonic_width_seed_000051),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000052", bounding_radius_monotonic_width_seed_000052),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000053", bounding_radius_monotonic_width_seed_000053),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000054", bounding_radius_monotonic_width_seed_000054),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000055", bounding_radius_monotonic_width_seed_000055),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000056", bounding_radius_monotonic_width_seed_000056),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000057", bounding_radius_monotonic_width_seed_000057),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000058", bounding_radius_monotonic_width_seed_000058),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000059", bounding_radius_monotonic_width_seed_000059),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000060", bounding_radius_monotonic_width_seed_000060),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000061", bounding_radius_monotonic_width_seed_000061),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000062", bounding_radius_monotonic_width_seed_000062),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000063", bounding_radius_monotonic_width_seed_000063),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000064", bounding_radius_monotonic_width_seed_000064),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000065", bounding_radius_monotonic_width_seed_000065),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000066", bounding_radius_monotonic_width_seed_000066),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000067", bounding_radius_monotonic_width_seed_000067),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000068", bounding_radius_monotonic_width_seed_000068),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000069", bounding_radius_monotonic_width_seed_000069),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000070", bounding_radius_monotonic_width_seed_000070),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000071", bounding_radius_monotonic_width_seed_000071),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000072", bounding_radius_monotonic_width_seed_000072),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000073", bounding_radius_monotonic_width_seed_000073),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000074", bounding_radius_monotonic_width_seed_000074),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000075", bounding_radius_monotonic_width_seed_000075),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000076", bounding_radius_monotonic_width_seed_000076),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000077", bounding_radius_monotonic_width_seed_000077),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000078", bounding_radius_monotonic_width_seed_000078),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000079", bounding_radius_monotonic_width_seed_000079),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000080", bounding_radius_monotonic_width_seed_000080),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000081", bounding_radius_monotonic_width_seed_000081),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000082", bounding_radius_monotonic_width_seed_000082),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000083", bounding_radius_monotonic_width_seed_000083),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000084", bounding_radius_monotonic_width_seed_000084),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000085", bounding_radius_monotonic_width_seed_000085),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000086", bounding_radius_monotonic_width_seed_000086),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000087", bounding_radius_monotonic_width_seed_000087),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000088", bounding_radius_monotonic_width_seed_000088),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000089", bounding_radius_monotonic_width_seed_000089),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000090", bounding_radius_monotonic_width_seed_000090),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000091", bounding_radius_monotonic_width_seed_000091),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000092", bounding_radius_monotonic_width_seed_000092),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000093", bounding_radius_monotonic_width_seed_000093),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000094", bounding_radius_monotonic_width_seed_000094),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000095", bounding_radius_monotonic_width_seed_000095),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000096", bounding_radius_monotonic_width_seed_000096),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000097", bounding_radius_monotonic_width_seed_000097),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000098", bounding_radius_monotonic_width_seed_000098),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000099", bounding_radius_monotonic_width_seed_000099),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000100", bounding_radius_monotonic_width_seed_000100),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000101", bounding_radius_monotonic_width_seed_000101),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000102", bounding_radius_monotonic_width_seed_000102),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000103", bounding_radius_monotonic_width_seed_000103),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000104", bounding_radius_monotonic_width_seed_000104),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000105", bounding_radius_monotonic_width_seed_000105),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000106", bounding_radius_monotonic_width_seed_000106),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000107", bounding_radius_monotonic_width_seed_000107),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000108", bounding_radius_monotonic_width_seed_000108),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000109", bounding_radius_monotonic_width_seed_000109),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000110", bounding_radius_monotonic_width_seed_000110),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000111", bounding_radius_monotonic_width_seed_000111),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000112", bounding_radius_monotonic_width_seed_000112),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000113", bounding_radius_monotonic_width_seed_000113),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000114", bounding_radius_monotonic_width_seed_000114),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000115", bounding_radius_monotonic_width_seed_000115),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000116", bounding_radius_monotonic_width_seed_000116),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000117", bounding_radius_monotonic_width_seed_000117),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000118", bounding_radius_monotonic_width_seed_000118),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000119", bounding_radius_monotonic_width_seed_000119),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000120", bounding_radius_monotonic_width_seed_000120),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000121", bounding_radius_monotonic_width_seed_000121),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000122", bounding_radius_monotonic_width_seed_000122),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000123", bounding_radius_monotonic_width_seed_000123),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000124", bounding_radius_monotonic_width_seed_000124),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000125", bounding_radius_monotonic_width_seed_000125),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000126", bounding_radius_monotonic_width_seed_000126),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000127", bounding_radius_monotonic_width_seed_000127),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000128", bounding_radius_monotonic_width_seed_000128),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000129", bounding_radius_monotonic_width_seed_000129),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000130", bounding_radius_monotonic_width_seed_000130),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000131", bounding_radius_monotonic_width_seed_000131),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000132", bounding_radius_monotonic_width_seed_000132),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000133", bounding_radius_monotonic_width_seed_000133),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000134", bounding_radius_monotonic_width_seed_000134),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000135", bounding_radius_monotonic_width_seed_000135),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000136", bounding_radius_monotonic_width_seed_000136),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000137", bounding_radius_monotonic_width_seed_000137),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000138", bounding_radius_monotonic_width_seed_000138),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000139", bounding_radius_monotonic_width_seed_000139),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000140", bounding_radius_monotonic_width_seed_000140),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000141", bounding_radius_monotonic_width_seed_000141),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000142", bounding_radius_monotonic_width_seed_000142),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000143", bounding_radius_monotonic_width_seed_000143),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000144", bounding_radius_monotonic_width_seed_000144),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000145", bounding_radius_monotonic_width_seed_000145),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000146", bounding_radius_monotonic_width_seed_000146),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000147", bounding_radius_monotonic_width_seed_000147),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000148", bounding_radius_monotonic_width_seed_000148),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000149", bounding_radius_monotonic_width_seed_000149),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000150", bounding_radius_monotonic_width_seed_000150),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000151", bounding_radius_monotonic_width_seed_000151),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000152", bounding_radius_monotonic_width_seed_000152),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000153", bounding_radius_monotonic_width_seed_000153),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000154", bounding_radius_monotonic_width_seed_000154),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000155", bounding_radius_monotonic_width_seed_000155),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000156", bounding_radius_monotonic_width_seed_000156),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000157", bounding_radius_monotonic_width_seed_000157),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000158", bounding_radius_monotonic_width_seed_000158),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000159", bounding_radius_monotonic_width_seed_000159),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000160", bounding_radius_monotonic_width_seed_000160),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000161", bounding_radius_monotonic_width_seed_000161),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000162", bounding_radius_monotonic_width_seed_000162),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000163", bounding_radius_monotonic_width_seed_000163),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000164", bounding_radius_monotonic_width_seed_000164),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000165", bounding_radius_monotonic_width_seed_000165),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000166", bounding_radius_monotonic_width_seed_000166),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000167", bounding_radius_monotonic_width_seed_000167),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000168", bounding_radius_monotonic_width_seed_000168),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000169", bounding_radius_monotonic_width_seed_000169),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000170", bounding_radius_monotonic_width_seed_000170),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000171", bounding_radius_monotonic_width_seed_000171),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000172", bounding_radius_monotonic_width_seed_000172),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000173", bounding_radius_monotonic_width_seed_000173),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000174", bounding_radius_monotonic_width_seed_000174),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000175", bounding_radius_monotonic_width_seed_000175),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000176", bounding_radius_monotonic_width_seed_000176),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000177", bounding_radius_monotonic_width_seed_000177),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000178", bounding_radius_monotonic_width_seed_000178),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000179", bounding_radius_monotonic_width_seed_000179),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000180", bounding_radius_monotonic_width_seed_000180),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000181", bounding_radius_monotonic_width_seed_000181),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000182", bounding_radius_monotonic_width_seed_000182),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000183", bounding_radius_monotonic_width_seed_000183),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000184", bounding_radius_monotonic_width_seed_000184),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000185", bounding_radius_monotonic_width_seed_000185),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000186", bounding_radius_monotonic_width_seed_000186),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000187", bounding_radius_monotonic_width_seed_000187),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000188", bounding_radius_monotonic_width_seed_000188),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000189", bounding_radius_monotonic_width_seed_000189),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000190", bounding_radius_monotonic_width_seed_000190),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000191", bounding_radius_monotonic_width_seed_000191),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000192", bounding_radius_monotonic_width_seed_000192),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000193", bounding_radius_monotonic_width_seed_000193),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000194", bounding_radius_monotonic_width_seed_000194),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000195", bounding_radius_monotonic_width_seed_000195),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000196", bounding_radius_monotonic_width_seed_000196),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000197", bounding_radius_monotonic_width_seed_000197),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000198", bounding_radius_monotonic_width_seed_000198),
        ("property_campaigns_3::tests::bounding_radius_monotonic_width_seed_000199", bounding_radius_monotonic_width_seed_000199),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000000", core_half_extents_sum_identity_seed_000000),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000001", core_half_extents_sum_identity_seed_000001),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000002", core_half_extents_sum_identity_seed_000002),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000003", core_half_extents_sum_identity_seed_000003),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000004", core_half_extents_sum_identity_seed_000004),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000005", core_half_extents_sum_identity_seed_000005),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000006", core_half_extents_sum_identity_seed_000006),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000007", core_half_extents_sum_identity_seed_000007),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000008", core_half_extents_sum_identity_seed_000008),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000009", core_half_extents_sum_identity_seed_000009),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000010", core_half_extents_sum_identity_seed_000010),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000011", core_half_extents_sum_identity_seed_000011),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000012", core_half_extents_sum_identity_seed_000012),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000013", core_half_extents_sum_identity_seed_000013),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000014", core_half_extents_sum_identity_seed_000014),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000015", core_half_extents_sum_identity_seed_000015),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000016", core_half_extents_sum_identity_seed_000016),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000017", core_half_extents_sum_identity_seed_000017),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000018", core_half_extents_sum_identity_seed_000018),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000019", core_half_extents_sum_identity_seed_000019),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000020", core_half_extents_sum_identity_seed_000020),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000021", core_half_extents_sum_identity_seed_000021),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000022", core_half_extents_sum_identity_seed_000022),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000023", core_half_extents_sum_identity_seed_000023),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000024", core_half_extents_sum_identity_seed_000024),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000025", core_half_extents_sum_identity_seed_000025),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000026", core_half_extents_sum_identity_seed_000026),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000027", core_half_extents_sum_identity_seed_000027),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000028", core_half_extents_sum_identity_seed_000028),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000029", core_half_extents_sum_identity_seed_000029),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000030", core_half_extents_sum_identity_seed_000030),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000031", core_half_extents_sum_identity_seed_000031),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000032", core_half_extents_sum_identity_seed_000032),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000033", core_half_extents_sum_identity_seed_000033),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000034", core_half_extents_sum_identity_seed_000034),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000035", core_half_extents_sum_identity_seed_000035),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000036", core_half_extents_sum_identity_seed_000036),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000037", core_half_extents_sum_identity_seed_000037),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000038", core_half_extents_sum_identity_seed_000038),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000039", core_half_extents_sum_identity_seed_000039),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000040", core_half_extents_sum_identity_seed_000040),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000041", core_half_extents_sum_identity_seed_000041),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000042", core_half_extents_sum_identity_seed_000042),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000043", core_half_extents_sum_identity_seed_000043),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000044", core_half_extents_sum_identity_seed_000044),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000045", core_half_extents_sum_identity_seed_000045),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000046", core_half_extents_sum_identity_seed_000046),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000047", core_half_extents_sum_identity_seed_000047),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000048", core_half_extents_sum_identity_seed_000048),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000049", core_half_extents_sum_identity_seed_000049),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000050", core_half_extents_sum_identity_seed_000050),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000051", core_half_extents_sum_identity_seed_000051),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000052", core_half_extents_sum_identity_seed_000052),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000053", core_half_extents_sum_identity_seed_000053),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000054", core_half_extents_sum_identity_seed_000054),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000055", core_half_extents_sum_identity_seed_000055),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000056", core_half_extents_sum_identity_seed_000056),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000057", core_half_extents_sum_identity_seed_000057),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000058", core_half_extents_sum_identity_seed_000058),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000059", core_half_extents_sum_identity_seed_000059),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000060", core_half_extents_sum_identity_seed_000060),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000061", core_half_extents_sum_identity_seed_000061),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000062", core_half_extents_sum_identity_seed_000062),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000063", core_half_extents_sum_identity_seed_000063),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000064", core_half_extents_sum_identity_seed_000064),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000065", core_half_extents_sum_identity_seed_000065),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000066", core_half_extents_sum_identity_seed_000066),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000067", core_half_extents_sum_identity_seed_000067),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000068", core_half_extents_sum_identity_seed_000068),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000069", core_half_extents_sum_identity_seed_000069),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000070", core_half_extents_sum_identity_seed_000070),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000071", core_half_extents_sum_identity_seed_000071),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000072", core_half_extents_sum_identity_seed_000072),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000073", core_half_extents_sum_identity_seed_000073),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000074", core_half_extents_sum_identity_seed_000074),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000075", core_half_extents_sum_identity_seed_000075),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000076", core_half_extents_sum_identity_seed_000076),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000077", core_half_extents_sum_identity_seed_000077),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000078", core_half_extents_sum_identity_seed_000078),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000079", core_half_extents_sum_identity_seed_000079),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000080", core_half_extents_sum_identity_seed_000080),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000081", core_half_extents_sum_identity_seed_000081),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000082", core_half_extents_sum_identity_seed_000082),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000083", core_half_extents_sum_identity_seed_000083),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000084", core_half_extents_sum_identity_seed_000084),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000085", core_half_extents_sum_identity_seed_000085),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000086", core_half_extents_sum_identity_seed_000086),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000087", core_half_extents_sum_identity_seed_000087),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000088", core_half_extents_sum_identity_seed_000088),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000089", core_half_extents_sum_identity_seed_000089),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000090", core_half_extents_sum_identity_seed_000090),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000091", core_half_extents_sum_identity_seed_000091),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000092", core_half_extents_sum_identity_seed_000092),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000093", core_half_extents_sum_identity_seed_000093),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000094", core_half_extents_sum_identity_seed_000094),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000095", core_half_extents_sum_identity_seed_000095),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000096", core_half_extents_sum_identity_seed_000096),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000097", core_half_extents_sum_identity_seed_000097),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000098", core_half_extents_sum_identity_seed_000098),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000099", core_half_extents_sum_identity_seed_000099),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000100", core_half_extents_sum_identity_seed_000100),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000101", core_half_extents_sum_identity_seed_000101),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000102", core_half_extents_sum_identity_seed_000102),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000103", core_half_extents_sum_identity_seed_000103),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000104", core_half_extents_sum_identity_seed_000104),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000105", core_half_extents_sum_identity_seed_000105),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000106", core_half_extents_sum_identity_seed_000106),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000107", core_half_extents_sum_identity_seed_000107),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000108", core_half_extents_sum_identity_seed_000108),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000109", core_half_extents_sum_identity_seed_000109),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000110", core_half_extents_sum_identity_seed_000110),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000111", core_half_extents_sum_identity_seed_000111),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000112", core_half_extents_sum_identity_seed_000112),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000113", core_half_extents_sum_identity_seed_000113),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000114", core_half_extents_sum_identity_seed_000114),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000115", core_half_extents_sum_identity_seed_000115),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000116", core_half_extents_sum_identity_seed_000116),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000117", core_half_extents_sum_identity_seed_000117),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000118", core_half_extents_sum_identity_seed_000118),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000119", core_half_extents_sum_identity_seed_000119),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000120", core_half_extents_sum_identity_seed_000120),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000121", core_half_extents_sum_identity_seed_000121),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000122", core_half_extents_sum_identity_seed_000122),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000123", core_half_extents_sum_identity_seed_000123),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000124", core_half_extents_sum_identity_seed_000124),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000125", core_half_extents_sum_identity_seed_000125),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000126", core_half_extents_sum_identity_seed_000126),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000127", core_half_extents_sum_identity_seed_000127),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000128", core_half_extents_sum_identity_seed_000128),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000129", core_half_extents_sum_identity_seed_000129),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000130", core_half_extents_sum_identity_seed_000130),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000131", core_half_extents_sum_identity_seed_000131),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000132", core_half_extents_sum_identity_seed_000132),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000133", core_half_extents_sum_identity_seed_000133),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000134", core_half_extents_sum_identity_seed_000134),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000135", core_half_extents_sum_identity_seed_000135),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000136", core_half_extents_sum_identity_seed_000136),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000137", core_half_extents_sum_identity_seed_000137),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000138", core_half_extents_sum_identity_seed_000138),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000139", core_half_extents_sum_identity_seed_000139),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000140", core_half_extents_sum_identity_seed_000140),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000141", core_half_extents_sum_identity_seed_000141),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000142", core_half_extents_sum_identity_seed_000142),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000143", core_half_extents_sum_identity_seed_000143),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000144", core_half_extents_sum_identity_seed_000144),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000145", core_half_extents_sum_identity_seed_000145),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000146", core_half_extents_sum_identity_seed_000146),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000147", core_half_extents_sum_identity_seed_000147),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000148", core_half_extents_sum_identity_seed_000148),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000149", core_half_extents_sum_identity_seed_000149),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000150", core_half_extents_sum_identity_seed_000150),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000151", core_half_extents_sum_identity_seed_000151),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000152", core_half_extents_sum_identity_seed_000152),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000153", core_half_extents_sum_identity_seed_000153),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000154", core_half_extents_sum_identity_seed_000154),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000155", core_half_extents_sum_identity_seed_000155),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000156", core_half_extents_sum_identity_seed_000156),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000157", core_half_extents_sum_identity_seed_000157),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000158", core_half_extents_sum_identity_seed_000158),
        ("property_campaigns_3::tests::core_half_extents_sum_identity_seed_000159", core_half_extents_sum_identity_seed_000159),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000000", copper_reach_scale_law_seed_000000),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000001", copper_reach_scale_law_seed_000001),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000002", copper_reach_scale_law_seed_000002),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000003", copper_reach_scale_law_seed_000003),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000004", copper_reach_scale_law_seed_000004),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000005", copper_reach_scale_law_seed_000005),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000006", copper_reach_scale_law_seed_000006),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000007", copper_reach_scale_law_seed_000007),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000008", copper_reach_scale_law_seed_000008),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000009", copper_reach_scale_law_seed_000009),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000010", copper_reach_scale_law_seed_000010),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000011", copper_reach_scale_law_seed_000011),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000012", copper_reach_scale_law_seed_000012),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000013", copper_reach_scale_law_seed_000013),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000014", copper_reach_scale_law_seed_000014),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000015", copper_reach_scale_law_seed_000015),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000016", copper_reach_scale_law_seed_000016),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000017", copper_reach_scale_law_seed_000017),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000018", copper_reach_scale_law_seed_000018),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000019", copper_reach_scale_law_seed_000019),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000020", copper_reach_scale_law_seed_000020),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000021", copper_reach_scale_law_seed_000021),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000022", copper_reach_scale_law_seed_000022),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000023", copper_reach_scale_law_seed_000023),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000024", copper_reach_scale_law_seed_000024),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000025", copper_reach_scale_law_seed_000025),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000026", copper_reach_scale_law_seed_000026),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000027", copper_reach_scale_law_seed_000027),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000028", copper_reach_scale_law_seed_000028),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000029", copper_reach_scale_law_seed_000029),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000030", copper_reach_scale_law_seed_000030),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000031", copper_reach_scale_law_seed_000031),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000032", copper_reach_scale_law_seed_000032),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000033", copper_reach_scale_law_seed_000033),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000034", copper_reach_scale_law_seed_000034),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000035", copper_reach_scale_law_seed_000035),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000036", copper_reach_scale_law_seed_000036),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000037", copper_reach_scale_law_seed_000037),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000038", copper_reach_scale_law_seed_000038),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000039", copper_reach_scale_law_seed_000039),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000040", copper_reach_scale_law_seed_000040),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000041", copper_reach_scale_law_seed_000041),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000042", copper_reach_scale_law_seed_000042),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000043", copper_reach_scale_law_seed_000043),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000044", copper_reach_scale_law_seed_000044),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000045", copper_reach_scale_law_seed_000045),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000046", copper_reach_scale_law_seed_000046),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000047", copper_reach_scale_law_seed_000047),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000048", copper_reach_scale_law_seed_000048),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000049", copper_reach_scale_law_seed_000049),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000050", copper_reach_scale_law_seed_000050),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000051", copper_reach_scale_law_seed_000051),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000052", copper_reach_scale_law_seed_000052),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000053", copper_reach_scale_law_seed_000053),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000054", copper_reach_scale_law_seed_000054),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000055", copper_reach_scale_law_seed_000055),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000056", copper_reach_scale_law_seed_000056),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000057", copper_reach_scale_law_seed_000057),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000058", copper_reach_scale_law_seed_000058),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000059", copper_reach_scale_law_seed_000059),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000060", copper_reach_scale_law_seed_000060),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000061", copper_reach_scale_law_seed_000061),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000062", copper_reach_scale_law_seed_000062),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000063", copper_reach_scale_law_seed_000063),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000064", copper_reach_scale_law_seed_000064),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000065", copper_reach_scale_law_seed_000065),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000066", copper_reach_scale_law_seed_000066),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000067", copper_reach_scale_law_seed_000067),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000068", copper_reach_scale_law_seed_000068),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000069", copper_reach_scale_law_seed_000069),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000070", copper_reach_scale_law_seed_000070),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000071", copper_reach_scale_law_seed_000071),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000072", copper_reach_scale_law_seed_000072),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000073", copper_reach_scale_law_seed_000073),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000074", copper_reach_scale_law_seed_000074),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000075", copper_reach_scale_law_seed_000075),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000076", copper_reach_scale_law_seed_000076),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000077", copper_reach_scale_law_seed_000077),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000078", copper_reach_scale_law_seed_000078),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000079", copper_reach_scale_law_seed_000079),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000080", copper_reach_scale_law_seed_000080),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000081", copper_reach_scale_law_seed_000081),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000082", copper_reach_scale_law_seed_000082),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000083", copper_reach_scale_law_seed_000083),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000084", copper_reach_scale_law_seed_000084),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000085", copper_reach_scale_law_seed_000085),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000086", copper_reach_scale_law_seed_000086),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000087", copper_reach_scale_law_seed_000087),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000088", copper_reach_scale_law_seed_000088),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000089", copper_reach_scale_law_seed_000089),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000090", copper_reach_scale_law_seed_000090),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000091", copper_reach_scale_law_seed_000091),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000092", copper_reach_scale_law_seed_000092),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000093", copper_reach_scale_law_seed_000093),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000094", copper_reach_scale_law_seed_000094),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000095", copper_reach_scale_law_seed_000095),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000096", copper_reach_scale_law_seed_000096),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000097", copper_reach_scale_law_seed_000097),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000098", copper_reach_scale_law_seed_000098),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000099", copper_reach_scale_law_seed_000099),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000100", copper_reach_scale_law_seed_000100),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000101", copper_reach_scale_law_seed_000101),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000102", copper_reach_scale_law_seed_000102),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000103", copper_reach_scale_law_seed_000103),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000104", copper_reach_scale_law_seed_000104),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000105", copper_reach_scale_law_seed_000105),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000106", copper_reach_scale_law_seed_000106),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000107", copper_reach_scale_law_seed_000107),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000108", copper_reach_scale_law_seed_000108),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000109", copper_reach_scale_law_seed_000109),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000110", copper_reach_scale_law_seed_000110),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000111", copper_reach_scale_law_seed_000111),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000112", copper_reach_scale_law_seed_000112),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000113", copper_reach_scale_law_seed_000113),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000114", copper_reach_scale_law_seed_000114),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000115", copper_reach_scale_law_seed_000115),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000116", copper_reach_scale_law_seed_000116),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000117", copper_reach_scale_law_seed_000117),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000118", copper_reach_scale_law_seed_000118),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000119", copper_reach_scale_law_seed_000119),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000120", copper_reach_scale_law_seed_000120),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000121", copper_reach_scale_law_seed_000121),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000122", copper_reach_scale_law_seed_000122),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000123", copper_reach_scale_law_seed_000123),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000124", copper_reach_scale_law_seed_000124),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000125", copper_reach_scale_law_seed_000125),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000126", copper_reach_scale_law_seed_000126),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000127", copper_reach_scale_law_seed_000127),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000128", copper_reach_scale_law_seed_000128),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000129", copper_reach_scale_law_seed_000129),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000130", copper_reach_scale_law_seed_000130),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000131", copper_reach_scale_law_seed_000131),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000132", copper_reach_scale_law_seed_000132),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000133", copper_reach_scale_law_seed_000133),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000134", copper_reach_scale_law_seed_000134),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000135", copper_reach_scale_law_seed_000135),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000136", copper_reach_scale_law_seed_000136),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000137", copper_reach_scale_law_seed_000137),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000138", copper_reach_scale_law_seed_000138),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000139", copper_reach_scale_law_seed_000139),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000140", copper_reach_scale_law_seed_000140),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000141", copper_reach_scale_law_seed_000141),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000142", copper_reach_scale_law_seed_000142),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000143", copper_reach_scale_law_seed_000143),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000144", copper_reach_scale_law_seed_000144),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000145", copper_reach_scale_law_seed_000145),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000146", copper_reach_scale_law_seed_000146),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000147", copper_reach_scale_law_seed_000147),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000148", copper_reach_scale_law_seed_000148),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000149", copper_reach_scale_law_seed_000149),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000150", copper_reach_scale_law_seed_000150),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000151", copper_reach_scale_law_seed_000151),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000152", copper_reach_scale_law_seed_000152),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000153", copper_reach_scale_law_seed_000153),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000154", copper_reach_scale_law_seed_000154),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000155", copper_reach_scale_law_seed_000155),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000156", copper_reach_scale_law_seed_000156),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000157", copper_reach_scale_law_seed_000157),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000158", copper_reach_scale_law_seed_000158),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000159", copper_reach_scale_law_seed_000159),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000160", copper_reach_scale_law_seed_000160),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000161", copper_reach_scale_law_seed_000161),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000162", copper_reach_scale_law_seed_000162),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000163", copper_reach_scale_law_seed_000163),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000164", copper_reach_scale_law_seed_000164),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000165", copper_reach_scale_law_seed_000165),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000166", copper_reach_scale_law_seed_000166),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000167", copper_reach_scale_law_seed_000167),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000168", copper_reach_scale_law_seed_000168),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000169", copper_reach_scale_law_seed_000169),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000170", copper_reach_scale_law_seed_000170),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000171", copper_reach_scale_law_seed_000171),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000172", copper_reach_scale_law_seed_000172),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000173", copper_reach_scale_law_seed_000173),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000174", copper_reach_scale_law_seed_000174),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000175", copper_reach_scale_law_seed_000175),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000176", copper_reach_scale_law_seed_000176),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000177", copper_reach_scale_law_seed_000177),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000178", copper_reach_scale_law_seed_000178),
        ("property_campaigns_3::tests::copper_reach_scale_law_seed_000179", copper_reach_scale_law_seed_000179),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000000", copper_reach_monotone_added_pad_seed_000000),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000001", copper_reach_monotone_added_pad_seed_000001),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000002", copper_reach_monotone_added_pad_seed_000002),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000003", copper_reach_monotone_added_pad_seed_000003),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000004", copper_reach_monotone_added_pad_seed_000004),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000005", copper_reach_monotone_added_pad_seed_000005),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000006", copper_reach_monotone_added_pad_seed_000006),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000007", copper_reach_monotone_added_pad_seed_000007),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000008", copper_reach_monotone_added_pad_seed_000008),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000009", copper_reach_monotone_added_pad_seed_000009),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000010", copper_reach_monotone_added_pad_seed_000010),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000011", copper_reach_monotone_added_pad_seed_000011),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000012", copper_reach_monotone_added_pad_seed_000012),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000013", copper_reach_monotone_added_pad_seed_000013),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000014", copper_reach_monotone_added_pad_seed_000014),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000015", copper_reach_monotone_added_pad_seed_000015),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000016", copper_reach_monotone_added_pad_seed_000016),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000017", copper_reach_monotone_added_pad_seed_000017),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000018", copper_reach_monotone_added_pad_seed_000018),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000019", copper_reach_monotone_added_pad_seed_000019),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000020", copper_reach_monotone_added_pad_seed_000020),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000021", copper_reach_monotone_added_pad_seed_000021),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000022", copper_reach_monotone_added_pad_seed_000022),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000023", copper_reach_monotone_added_pad_seed_000023),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000024", copper_reach_monotone_added_pad_seed_000024),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000025", copper_reach_monotone_added_pad_seed_000025),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000026", copper_reach_monotone_added_pad_seed_000026),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000027", copper_reach_monotone_added_pad_seed_000027),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000028", copper_reach_monotone_added_pad_seed_000028),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000029", copper_reach_monotone_added_pad_seed_000029),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000030", copper_reach_monotone_added_pad_seed_000030),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000031", copper_reach_monotone_added_pad_seed_000031),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000032", copper_reach_monotone_added_pad_seed_000032),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000033", copper_reach_monotone_added_pad_seed_000033),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000034", copper_reach_monotone_added_pad_seed_000034),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000035", copper_reach_monotone_added_pad_seed_000035),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000036", copper_reach_monotone_added_pad_seed_000036),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000037", copper_reach_monotone_added_pad_seed_000037),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000038", copper_reach_monotone_added_pad_seed_000038),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000039", copper_reach_monotone_added_pad_seed_000039),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000040", copper_reach_monotone_added_pad_seed_000040),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000041", copper_reach_monotone_added_pad_seed_000041),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000042", copper_reach_monotone_added_pad_seed_000042),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000043", copper_reach_monotone_added_pad_seed_000043),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000044", copper_reach_monotone_added_pad_seed_000044),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000045", copper_reach_monotone_added_pad_seed_000045),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000046", copper_reach_monotone_added_pad_seed_000046),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000047", copper_reach_monotone_added_pad_seed_000047),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000048", copper_reach_monotone_added_pad_seed_000048),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000049", copper_reach_monotone_added_pad_seed_000049),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000050", copper_reach_monotone_added_pad_seed_000050),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000051", copper_reach_monotone_added_pad_seed_000051),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000052", copper_reach_monotone_added_pad_seed_000052),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000053", copper_reach_monotone_added_pad_seed_000053),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000054", copper_reach_monotone_added_pad_seed_000054),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000055", copper_reach_monotone_added_pad_seed_000055),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000056", copper_reach_monotone_added_pad_seed_000056),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000057", copper_reach_monotone_added_pad_seed_000057),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000058", copper_reach_monotone_added_pad_seed_000058),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000059", copper_reach_monotone_added_pad_seed_000059),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000060", copper_reach_monotone_added_pad_seed_000060),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000061", copper_reach_monotone_added_pad_seed_000061),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000062", copper_reach_monotone_added_pad_seed_000062),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000063", copper_reach_monotone_added_pad_seed_000063),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000064", copper_reach_monotone_added_pad_seed_000064),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000065", copper_reach_monotone_added_pad_seed_000065),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000066", copper_reach_monotone_added_pad_seed_000066),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000067", copper_reach_monotone_added_pad_seed_000067),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000068", copper_reach_monotone_added_pad_seed_000068),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000069", copper_reach_monotone_added_pad_seed_000069),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000070", copper_reach_monotone_added_pad_seed_000070),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000071", copper_reach_monotone_added_pad_seed_000071),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000072", copper_reach_monotone_added_pad_seed_000072),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000073", copper_reach_monotone_added_pad_seed_000073),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000074", copper_reach_monotone_added_pad_seed_000074),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000075", copper_reach_monotone_added_pad_seed_000075),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000076", copper_reach_monotone_added_pad_seed_000076),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000077", copper_reach_monotone_added_pad_seed_000077),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000078", copper_reach_monotone_added_pad_seed_000078),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000079", copper_reach_monotone_added_pad_seed_000079),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000080", copper_reach_monotone_added_pad_seed_000080),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000081", copper_reach_monotone_added_pad_seed_000081),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000082", copper_reach_monotone_added_pad_seed_000082),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000083", copper_reach_monotone_added_pad_seed_000083),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000084", copper_reach_monotone_added_pad_seed_000084),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000085", copper_reach_monotone_added_pad_seed_000085),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000086", copper_reach_monotone_added_pad_seed_000086),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000087", copper_reach_monotone_added_pad_seed_000087),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000088", copper_reach_monotone_added_pad_seed_000088),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000089", copper_reach_monotone_added_pad_seed_000089),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000090", copper_reach_monotone_added_pad_seed_000090),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000091", copper_reach_monotone_added_pad_seed_000091),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000092", copper_reach_monotone_added_pad_seed_000092),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000093", copper_reach_monotone_added_pad_seed_000093),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000094", copper_reach_monotone_added_pad_seed_000094),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000095", copper_reach_monotone_added_pad_seed_000095),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000096", copper_reach_monotone_added_pad_seed_000096),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000097", copper_reach_monotone_added_pad_seed_000097),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000098", copper_reach_monotone_added_pad_seed_000098),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000099", copper_reach_monotone_added_pad_seed_000099),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000100", copper_reach_monotone_added_pad_seed_000100),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000101", copper_reach_monotone_added_pad_seed_000101),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000102", copper_reach_monotone_added_pad_seed_000102),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000103", copper_reach_monotone_added_pad_seed_000103),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000104", copper_reach_monotone_added_pad_seed_000104),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000105", copper_reach_monotone_added_pad_seed_000105),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000106", copper_reach_monotone_added_pad_seed_000106),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000107", copper_reach_monotone_added_pad_seed_000107),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000108", copper_reach_monotone_added_pad_seed_000108),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000109", copper_reach_monotone_added_pad_seed_000109),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000110", copper_reach_monotone_added_pad_seed_000110),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000111", copper_reach_monotone_added_pad_seed_000111),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000112", copper_reach_monotone_added_pad_seed_000112),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000113", copper_reach_monotone_added_pad_seed_000113),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000114", copper_reach_monotone_added_pad_seed_000114),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000115", copper_reach_monotone_added_pad_seed_000115),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000116", copper_reach_monotone_added_pad_seed_000116),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000117", copper_reach_monotone_added_pad_seed_000117),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000118", copper_reach_monotone_added_pad_seed_000118),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000119", copper_reach_monotone_added_pad_seed_000119),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000120", copper_reach_monotone_added_pad_seed_000120),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000121", copper_reach_monotone_added_pad_seed_000121),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000122", copper_reach_monotone_added_pad_seed_000122),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000123", copper_reach_monotone_added_pad_seed_000123),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000124", copper_reach_monotone_added_pad_seed_000124),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000125", copper_reach_monotone_added_pad_seed_000125),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000126", copper_reach_monotone_added_pad_seed_000126),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000127", copper_reach_monotone_added_pad_seed_000127),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000128", copper_reach_monotone_added_pad_seed_000128),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000129", copper_reach_monotone_added_pad_seed_000129),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000130", copper_reach_monotone_added_pad_seed_000130),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000131", copper_reach_monotone_added_pad_seed_000131),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000132", copper_reach_monotone_added_pad_seed_000132),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000133", copper_reach_monotone_added_pad_seed_000133),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000134", copper_reach_monotone_added_pad_seed_000134),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000135", copper_reach_monotone_added_pad_seed_000135),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000136", copper_reach_monotone_added_pad_seed_000136),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000137", copper_reach_monotone_added_pad_seed_000137),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000138", copper_reach_monotone_added_pad_seed_000138),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000139", copper_reach_monotone_added_pad_seed_000139),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000140", copper_reach_monotone_added_pad_seed_000140),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000141", copper_reach_monotone_added_pad_seed_000141),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000142", copper_reach_monotone_added_pad_seed_000142),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000143", copper_reach_monotone_added_pad_seed_000143),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000144", copper_reach_monotone_added_pad_seed_000144),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000145", copper_reach_monotone_added_pad_seed_000145),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000146", copper_reach_monotone_added_pad_seed_000146),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000147", copper_reach_monotone_added_pad_seed_000147),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000148", copper_reach_monotone_added_pad_seed_000148),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000149", copper_reach_monotone_added_pad_seed_000149),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000150", copper_reach_monotone_added_pad_seed_000150),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000151", copper_reach_monotone_added_pad_seed_000151),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000152", copper_reach_monotone_added_pad_seed_000152),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000153", copper_reach_monotone_added_pad_seed_000153),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000154", copper_reach_monotone_added_pad_seed_000154),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000155", copper_reach_monotone_added_pad_seed_000155),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000156", copper_reach_monotone_added_pad_seed_000156),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000157", copper_reach_monotone_added_pad_seed_000157),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000158", copper_reach_monotone_added_pad_seed_000158),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000159", copper_reach_monotone_added_pad_seed_000159),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000160", copper_reach_monotone_added_pad_seed_000160),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000161", copper_reach_monotone_added_pad_seed_000161),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000162", copper_reach_monotone_added_pad_seed_000162),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000163", copper_reach_monotone_added_pad_seed_000163),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000164", copper_reach_monotone_added_pad_seed_000164),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000165", copper_reach_monotone_added_pad_seed_000165),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000166", copper_reach_monotone_added_pad_seed_000166),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000167", copper_reach_monotone_added_pad_seed_000167),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000168", copper_reach_monotone_added_pad_seed_000168),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000169", copper_reach_monotone_added_pad_seed_000169),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000170", copper_reach_monotone_added_pad_seed_000170),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000171", copper_reach_monotone_added_pad_seed_000171),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000172", copper_reach_monotone_added_pad_seed_000172),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000173", copper_reach_monotone_added_pad_seed_000173),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000174", copper_reach_monotone_added_pad_seed_000174),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000175", copper_reach_monotone_added_pad_seed_000175),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000176", copper_reach_monotone_added_pad_seed_000176),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000177", copper_reach_monotone_added_pad_seed_000177),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000178", copper_reach_monotone_added_pad_seed_000178),
        ("property_campaigns_3::tests::copper_reach_monotone_added_pad_seed_000179", copper_reach_monotone_added_pad_seed_000179),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000000", copper_reach_rotation_invariant_seed_000000),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000001", copper_reach_rotation_invariant_seed_000001),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000002", copper_reach_rotation_invariant_seed_000002),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000003", copper_reach_rotation_invariant_seed_000003),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000004", copper_reach_rotation_invariant_seed_000004),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000005", copper_reach_rotation_invariant_seed_000005),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000006", copper_reach_rotation_invariant_seed_000006),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000007", copper_reach_rotation_invariant_seed_000007),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000008", copper_reach_rotation_invariant_seed_000008),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000009", copper_reach_rotation_invariant_seed_000009),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000010", copper_reach_rotation_invariant_seed_000010),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000011", copper_reach_rotation_invariant_seed_000011),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000012", copper_reach_rotation_invariant_seed_000012),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000013", copper_reach_rotation_invariant_seed_000013),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000014", copper_reach_rotation_invariant_seed_000014),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000015", copper_reach_rotation_invariant_seed_000015),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000016", copper_reach_rotation_invariant_seed_000016),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000017", copper_reach_rotation_invariant_seed_000017),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000018", copper_reach_rotation_invariant_seed_000018),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000019", copper_reach_rotation_invariant_seed_000019),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000020", copper_reach_rotation_invariant_seed_000020),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000021", copper_reach_rotation_invariant_seed_000021),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000022", copper_reach_rotation_invariant_seed_000022),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000023", copper_reach_rotation_invariant_seed_000023),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000024", copper_reach_rotation_invariant_seed_000024),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000025", copper_reach_rotation_invariant_seed_000025),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000026", copper_reach_rotation_invariant_seed_000026),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000027", copper_reach_rotation_invariant_seed_000027),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000028", copper_reach_rotation_invariant_seed_000028),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000029", copper_reach_rotation_invariant_seed_000029),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000030", copper_reach_rotation_invariant_seed_000030),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000031", copper_reach_rotation_invariant_seed_000031),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000032", copper_reach_rotation_invariant_seed_000032),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000033", copper_reach_rotation_invariant_seed_000033),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000034", copper_reach_rotation_invariant_seed_000034),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000035", copper_reach_rotation_invariant_seed_000035),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000036", copper_reach_rotation_invariant_seed_000036),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000037", copper_reach_rotation_invariant_seed_000037),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000038", copper_reach_rotation_invariant_seed_000038),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000039", copper_reach_rotation_invariant_seed_000039),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000040", copper_reach_rotation_invariant_seed_000040),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000041", copper_reach_rotation_invariant_seed_000041),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000042", copper_reach_rotation_invariant_seed_000042),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000043", copper_reach_rotation_invariant_seed_000043),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000044", copper_reach_rotation_invariant_seed_000044),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000045", copper_reach_rotation_invariant_seed_000045),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000046", copper_reach_rotation_invariant_seed_000046),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000047", copper_reach_rotation_invariant_seed_000047),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000048", copper_reach_rotation_invariant_seed_000048),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000049", copper_reach_rotation_invariant_seed_000049),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000050", copper_reach_rotation_invariant_seed_000050),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000051", copper_reach_rotation_invariant_seed_000051),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000052", copper_reach_rotation_invariant_seed_000052),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000053", copper_reach_rotation_invariant_seed_000053),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000054", copper_reach_rotation_invariant_seed_000054),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000055", copper_reach_rotation_invariant_seed_000055),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000056", copper_reach_rotation_invariant_seed_000056),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000057", copper_reach_rotation_invariant_seed_000057),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000058", copper_reach_rotation_invariant_seed_000058),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000059", copper_reach_rotation_invariant_seed_000059),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000060", copper_reach_rotation_invariant_seed_000060),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000061", copper_reach_rotation_invariant_seed_000061),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000062", copper_reach_rotation_invariant_seed_000062),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000063", copper_reach_rotation_invariant_seed_000063),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000064", copper_reach_rotation_invariant_seed_000064),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000065", copper_reach_rotation_invariant_seed_000065),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000066", copper_reach_rotation_invariant_seed_000066),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000067", copper_reach_rotation_invariant_seed_000067),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000068", copper_reach_rotation_invariant_seed_000068),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000069", copper_reach_rotation_invariant_seed_000069),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000070", copper_reach_rotation_invariant_seed_000070),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000071", copper_reach_rotation_invariant_seed_000071),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000072", copper_reach_rotation_invariant_seed_000072),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000073", copper_reach_rotation_invariant_seed_000073),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000074", copper_reach_rotation_invariant_seed_000074),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000075", copper_reach_rotation_invariant_seed_000075),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000076", copper_reach_rotation_invariant_seed_000076),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000077", copper_reach_rotation_invariant_seed_000077),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000078", copper_reach_rotation_invariant_seed_000078),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000079", copper_reach_rotation_invariant_seed_000079),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000080", copper_reach_rotation_invariant_seed_000080),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000081", copper_reach_rotation_invariant_seed_000081),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000082", copper_reach_rotation_invariant_seed_000082),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000083", copper_reach_rotation_invariant_seed_000083),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000084", copper_reach_rotation_invariant_seed_000084),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000085", copper_reach_rotation_invariant_seed_000085),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000086", copper_reach_rotation_invariant_seed_000086),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000087", copper_reach_rotation_invariant_seed_000087),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000088", copper_reach_rotation_invariant_seed_000088),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000089", copper_reach_rotation_invariant_seed_000089),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000090", copper_reach_rotation_invariant_seed_000090),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000091", copper_reach_rotation_invariant_seed_000091),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000092", copper_reach_rotation_invariant_seed_000092),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000093", copper_reach_rotation_invariant_seed_000093),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000094", copper_reach_rotation_invariant_seed_000094),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000095", copper_reach_rotation_invariant_seed_000095),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000096", copper_reach_rotation_invariant_seed_000096),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000097", copper_reach_rotation_invariant_seed_000097),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000098", copper_reach_rotation_invariant_seed_000098),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000099", copper_reach_rotation_invariant_seed_000099),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000100", copper_reach_rotation_invariant_seed_000100),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000101", copper_reach_rotation_invariant_seed_000101),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000102", copper_reach_rotation_invariant_seed_000102),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000103", copper_reach_rotation_invariant_seed_000103),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000104", copper_reach_rotation_invariant_seed_000104),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000105", copper_reach_rotation_invariant_seed_000105),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000106", copper_reach_rotation_invariant_seed_000106),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000107", copper_reach_rotation_invariant_seed_000107),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000108", copper_reach_rotation_invariant_seed_000108),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000109", copper_reach_rotation_invariant_seed_000109),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000110", copper_reach_rotation_invariant_seed_000110),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000111", copper_reach_rotation_invariant_seed_000111),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000112", copper_reach_rotation_invariant_seed_000112),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000113", copper_reach_rotation_invariant_seed_000113),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000114", copper_reach_rotation_invariant_seed_000114),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000115", copper_reach_rotation_invariant_seed_000115),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000116", copper_reach_rotation_invariant_seed_000116),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000117", copper_reach_rotation_invariant_seed_000117),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000118", copper_reach_rotation_invariant_seed_000118),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000119", copper_reach_rotation_invariant_seed_000119),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000120", copper_reach_rotation_invariant_seed_000120),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000121", copper_reach_rotation_invariant_seed_000121),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000122", copper_reach_rotation_invariant_seed_000122),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000123", copper_reach_rotation_invariant_seed_000123),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000124", copper_reach_rotation_invariant_seed_000124),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000125", copper_reach_rotation_invariant_seed_000125),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000126", copper_reach_rotation_invariant_seed_000126),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000127", copper_reach_rotation_invariant_seed_000127),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000128", copper_reach_rotation_invariant_seed_000128),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000129", copper_reach_rotation_invariant_seed_000129),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000130", copper_reach_rotation_invariant_seed_000130),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000131", copper_reach_rotation_invariant_seed_000131),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000132", copper_reach_rotation_invariant_seed_000132),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000133", copper_reach_rotation_invariant_seed_000133),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000134", copper_reach_rotation_invariant_seed_000134),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000135", copper_reach_rotation_invariant_seed_000135),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000136", copper_reach_rotation_invariant_seed_000136),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000137", copper_reach_rotation_invariant_seed_000137),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000138", copper_reach_rotation_invariant_seed_000138),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000139", copper_reach_rotation_invariant_seed_000139),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000140", copper_reach_rotation_invariant_seed_000140),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000141", copper_reach_rotation_invariant_seed_000141),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000142", copper_reach_rotation_invariant_seed_000142),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000143", copper_reach_rotation_invariant_seed_000143),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000144", copper_reach_rotation_invariant_seed_000144),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000145", copper_reach_rotation_invariant_seed_000145),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000146", copper_reach_rotation_invariant_seed_000146),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000147", copper_reach_rotation_invariant_seed_000147),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000148", copper_reach_rotation_invariant_seed_000148),
        ("property_campaigns_3::tests::copper_reach_rotation_invariant_seed_000149", copper_reach_rotation_invariant_seed_000149),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000000", circle_ring_translation_equivariant_seed_000000),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000001", circle_ring_translation_equivariant_seed_000001),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000002", circle_ring_translation_equivariant_seed_000002),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000003", circle_ring_translation_equivariant_seed_000003),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000004", circle_ring_translation_equivariant_seed_000004),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000005", circle_ring_translation_equivariant_seed_000005),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000006", circle_ring_translation_equivariant_seed_000006),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000007", circle_ring_translation_equivariant_seed_000007),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000008", circle_ring_translation_equivariant_seed_000008),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000009", circle_ring_translation_equivariant_seed_000009),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000010", circle_ring_translation_equivariant_seed_000010),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000011", circle_ring_translation_equivariant_seed_000011),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000012", circle_ring_translation_equivariant_seed_000012),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000013", circle_ring_translation_equivariant_seed_000013),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000014", circle_ring_translation_equivariant_seed_000014),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000015", circle_ring_translation_equivariant_seed_000015),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000016", circle_ring_translation_equivariant_seed_000016),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000017", circle_ring_translation_equivariant_seed_000017),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000018", circle_ring_translation_equivariant_seed_000018),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000019", circle_ring_translation_equivariant_seed_000019),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000020", circle_ring_translation_equivariant_seed_000020),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000021", circle_ring_translation_equivariant_seed_000021),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000022", circle_ring_translation_equivariant_seed_000022),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000023", circle_ring_translation_equivariant_seed_000023),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000024", circle_ring_translation_equivariant_seed_000024),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000025", circle_ring_translation_equivariant_seed_000025),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000026", circle_ring_translation_equivariant_seed_000026),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000027", circle_ring_translation_equivariant_seed_000027),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000028", circle_ring_translation_equivariant_seed_000028),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000029", circle_ring_translation_equivariant_seed_000029),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000030", circle_ring_translation_equivariant_seed_000030),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000031", circle_ring_translation_equivariant_seed_000031),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000032", circle_ring_translation_equivariant_seed_000032),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000033", circle_ring_translation_equivariant_seed_000033),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000034", circle_ring_translation_equivariant_seed_000034),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000035", circle_ring_translation_equivariant_seed_000035),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000036", circle_ring_translation_equivariant_seed_000036),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000037", circle_ring_translation_equivariant_seed_000037),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000038", circle_ring_translation_equivariant_seed_000038),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000039", circle_ring_translation_equivariant_seed_000039),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000040", circle_ring_translation_equivariant_seed_000040),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000041", circle_ring_translation_equivariant_seed_000041),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000042", circle_ring_translation_equivariant_seed_000042),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000043", circle_ring_translation_equivariant_seed_000043),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000044", circle_ring_translation_equivariant_seed_000044),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000045", circle_ring_translation_equivariant_seed_000045),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000046", circle_ring_translation_equivariant_seed_000046),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000047", circle_ring_translation_equivariant_seed_000047),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000048", circle_ring_translation_equivariant_seed_000048),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000049", circle_ring_translation_equivariant_seed_000049),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000050", circle_ring_translation_equivariant_seed_000050),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000051", circle_ring_translation_equivariant_seed_000051),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000052", circle_ring_translation_equivariant_seed_000052),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000053", circle_ring_translation_equivariant_seed_000053),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000054", circle_ring_translation_equivariant_seed_000054),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000055", circle_ring_translation_equivariant_seed_000055),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000056", circle_ring_translation_equivariant_seed_000056),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000057", circle_ring_translation_equivariant_seed_000057),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000058", circle_ring_translation_equivariant_seed_000058),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000059", circle_ring_translation_equivariant_seed_000059),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000060", circle_ring_translation_equivariant_seed_000060),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000061", circle_ring_translation_equivariant_seed_000061),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000062", circle_ring_translation_equivariant_seed_000062),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000063", circle_ring_translation_equivariant_seed_000063),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000064", circle_ring_translation_equivariant_seed_000064),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000065", circle_ring_translation_equivariant_seed_000065),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000066", circle_ring_translation_equivariant_seed_000066),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000067", circle_ring_translation_equivariant_seed_000067),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000068", circle_ring_translation_equivariant_seed_000068),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000069", circle_ring_translation_equivariant_seed_000069),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000070", circle_ring_translation_equivariant_seed_000070),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000071", circle_ring_translation_equivariant_seed_000071),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000072", circle_ring_translation_equivariant_seed_000072),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000073", circle_ring_translation_equivariant_seed_000073),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000074", circle_ring_translation_equivariant_seed_000074),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000075", circle_ring_translation_equivariant_seed_000075),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000076", circle_ring_translation_equivariant_seed_000076),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000077", circle_ring_translation_equivariant_seed_000077),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000078", circle_ring_translation_equivariant_seed_000078),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000079", circle_ring_translation_equivariant_seed_000079),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000080", circle_ring_translation_equivariant_seed_000080),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000081", circle_ring_translation_equivariant_seed_000081),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000082", circle_ring_translation_equivariant_seed_000082),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000083", circle_ring_translation_equivariant_seed_000083),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000084", circle_ring_translation_equivariant_seed_000084),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000085", circle_ring_translation_equivariant_seed_000085),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000086", circle_ring_translation_equivariant_seed_000086),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000087", circle_ring_translation_equivariant_seed_000087),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000088", circle_ring_translation_equivariant_seed_000088),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000089", circle_ring_translation_equivariant_seed_000089),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000090", circle_ring_translation_equivariant_seed_000090),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000091", circle_ring_translation_equivariant_seed_000091),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000092", circle_ring_translation_equivariant_seed_000092),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000093", circle_ring_translation_equivariant_seed_000093),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000094", circle_ring_translation_equivariant_seed_000094),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000095", circle_ring_translation_equivariant_seed_000095),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000096", circle_ring_translation_equivariant_seed_000096),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000097", circle_ring_translation_equivariant_seed_000097),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000098", circle_ring_translation_equivariant_seed_000098),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000099", circle_ring_translation_equivariant_seed_000099),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000100", circle_ring_translation_equivariant_seed_000100),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000101", circle_ring_translation_equivariant_seed_000101),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000102", circle_ring_translation_equivariant_seed_000102),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000103", circle_ring_translation_equivariant_seed_000103),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000104", circle_ring_translation_equivariant_seed_000104),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000105", circle_ring_translation_equivariant_seed_000105),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000106", circle_ring_translation_equivariant_seed_000106),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000107", circle_ring_translation_equivariant_seed_000107),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000108", circle_ring_translation_equivariant_seed_000108),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000109", circle_ring_translation_equivariant_seed_000109),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000110", circle_ring_translation_equivariant_seed_000110),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000111", circle_ring_translation_equivariant_seed_000111),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000112", circle_ring_translation_equivariant_seed_000112),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000113", circle_ring_translation_equivariant_seed_000113),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000114", circle_ring_translation_equivariant_seed_000114),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000115", circle_ring_translation_equivariant_seed_000115),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000116", circle_ring_translation_equivariant_seed_000116),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000117", circle_ring_translation_equivariant_seed_000117),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000118", circle_ring_translation_equivariant_seed_000118),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000119", circle_ring_translation_equivariant_seed_000119),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000120", circle_ring_translation_equivariant_seed_000120),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000121", circle_ring_translation_equivariant_seed_000121),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000122", circle_ring_translation_equivariant_seed_000122),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000123", circle_ring_translation_equivariant_seed_000123),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000124", circle_ring_translation_equivariant_seed_000124),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000125", circle_ring_translation_equivariant_seed_000125),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000126", circle_ring_translation_equivariant_seed_000126),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000127", circle_ring_translation_equivariant_seed_000127),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000128", circle_ring_translation_equivariant_seed_000128),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000129", circle_ring_translation_equivariant_seed_000129),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000130", circle_ring_translation_equivariant_seed_000130),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000131", circle_ring_translation_equivariant_seed_000131),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000132", circle_ring_translation_equivariant_seed_000132),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000133", circle_ring_translation_equivariant_seed_000133),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000134", circle_ring_translation_equivariant_seed_000134),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000135", circle_ring_translation_equivariant_seed_000135),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000136", circle_ring_translation_equivariant_seed_000136),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000137", circle_ring_translation_equivariant_seed_000137),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000138", circle_ring_translation_equivariant_seed_000138),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000139", circle_ring_translation_equivariant_seed_000139),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000140", circle_ring_translation_equivariant_seed_000140),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000141", circle_ring_translation_equivariant_seed_000141),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000142", circle_ring_translation_equivariant_seed_000142),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000143", circle_ring_translation_equivariant_seed_000143),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000144", circle_ring_translation_equivariant_seed_000144),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000145", circle_ring_translation_equivariant_seed_000145),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000146", circle_ring_translation_equivariant_seed_000146),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000147", circle_ring_translation_equivariant_seed_000147),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000148", circle_ring_translation_equivariant_seed_000148),
        ("property_campaigns_3::tests::circle_ring_translation_equivariant_seed_000149", circle_ring_translation_equivariant_seed_000149),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000000", circle_ring_radius_scale_law_seed_000000),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000001", circle_ring_radius_scale_law_seed_000001),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000002", circle_ring_radius_scale_law_seed_000002),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000003", circle_ring_radius_scale_law_seed_000003),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000004", circle_ring_radius_scale_law_seed_000004),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000005", circle_ring_radius_scale_law_seed_000005),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000006", circle_ring_radius_scale_law_seed_000006),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000007", circle_ring_radius_scale_law_seed_000007),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000008", circle_ring_radius_scale_law_seed_000008),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000009", circle_ring_radius_scale_law_seed_000009),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000010", circle_ring_radius_scale_law_seed_000010),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000011", circle_ring_radius_scale_law_seed_000011),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000012", circle_ring_radius_scale_law_seed_000012),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000013", circle_ring_radius_scale_law_seed_000013),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000014", circle_ring_radius_scale_law_seed_000014),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000015", circle_ring_radius_scale_law_seed_000015),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000016", circle_ring_radius_scale_law_seed_000016),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000017", circle_ring_radius_scale_law_seed_000017),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000018", circle_ring_radius_scale_law_seed_000018),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000019", circle_ring_radius_scale_law_seed_000019),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000020", circle_ring_radius_scale_law_seed_000020),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000021", circle_ring_radius_scale_law_seed_000021),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000022", circle_ring_radius_scale_law_seed_000022),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000023", circle_ring_radius_scale_law_seed_000023),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000024", circle_ring_radius_scale_law_seed_000024),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000025", circle_ring_radius_scale_law_seed_000025),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000026", circle_ring_radius_scale_law_seed_000026),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000027", circle_ring_radius_scale_law_seed_000027),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000028", circle_ring_radius_scale_law_seed_000028),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000029", circle_ring_radius_scale_law_seed_000029),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000030", circle_ring_radius_scale_law_seed_000030),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000031", circle_ring_radius_scale_law_seed_000031),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000032", circle_ring_radius_scale_law_seed_000032),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000033", circle_ring_radius_scale_law_seed_000033),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000034", circle_ring_radius_scale_law_seed_000034),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000035", circle_ring_radius_scale_law_seed_000035),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000036", circle_ring_radius_scale_law_seed_000036),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000037", circle_ring_radius_scale_law_seed_000037),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000038", circle_ring_radius_scale_law_seed_000038),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000039", circle_ring_radius_scale_law_seed_000039),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000040", circle_ring_radius_scale_law_seed_000040),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000041", circle_ring_radius_scale_law_seed_000041),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000042", circle_ring_radius_scale_law_seed_000042),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000043", circle_ring_radius_scale_law_seed_000043),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000044", circle_ring_radius_scale_law_seed_000044),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000045", circle_ring_radius_scale_law_seed_000045),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000046", circle_ring_radius_scale_law_seed_000046),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000047", circle_ring_radius_scale_law_seed_000047),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000048", circle_ring_radius_scale_law_seed_000048),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000049", circle_ring_radius_scale_law_seed_000049),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000050", circle_ring_radius_scale_law_seed_000050),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000051", circle_ring_radius_scale_law_seed_000051),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000052", circle_ring_radius_scale_law_seed_000052),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000053", circle_ring_radius_scale_law_seed_000053),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000054", circle_ring_radius_scale_law_seed_000054),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000055", circle_ring_radius_scale_law_seed_000055),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000056", circle_ring_radius_scale_law_seed_000056),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000057", circle_ring_radius_scale_law_seed_000057),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000058", circle_ring_radius_scale_law_seed_000058),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000059", circle_ring_radius_scale_law_seed_000059),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000060", circle_ring_radius_scale_law_seed_000060),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000061", circle_ring_radius_scale_law_seed_000061),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000062", circle_ring_radius_scale_law_seed_000062),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000063", circle_ring_radius_scale_law_seed_000063),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000064", circle_ring_radius_scale_law_seed_000064),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000065", circle_ring_radius_scale_law_seed_000065),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000066", circle_ring_radius_scale_law_seed_000066),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000067", circle_ring_radius_scale_law_seed_000067),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000068", circle_ring_radius_scale_law_seed_000068),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000069", circle_ring_radius_scale_law_seed_000069),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000070", circle_ring_radius_scale_law_seed_000070),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000071", circle_ring_radius_scale_law_seed_000071),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000072", circle_ring_radius_scale_law_seed_000072),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000073", circle_ring_radius_scale_law_seed_000073),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000074", circle_ring_radius_scale_law_seed_000074),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000075", circle_ring_radius_scale_law_seed_000075),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000076", circle_ring_radius_scale_law_seed_000076),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000077", circle_ring_radius_scale_law_seed_000077),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000078", circle_ring_radius_scale_law_seed_000078),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000079", circle_ring_radius_scale_law_seed_000079),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000080", circle_ring_radius_scale_law_seed_000080),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000081", circle_ring_radius_scale_law_seed_000081),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000082", circle_ring_radius_scale_law_seed_000082),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000083", circle_ring_radius_scale_law_seed_000083),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000084", circle_ring_radius_scale_law_seed_000084),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000085", circle_ring_radius_scale_law_seed_000085),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000086", circle_ring_radius_scale_law_seed_000086),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000087", circle_ring_radius_scale_law_seed_000087),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000088", circle_ring_radius_scale_law_seed_000088),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000089", circle_ring_radius_scale_law_seed_000089),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000090", circle_ring_radius_scale_law_seed_000090),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000091", circle_ring_radius_scale_law_seed_000091),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000092", circle_ring_radius_scale_law_seed_000092),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000093", circle_ring_radius_scale_law_seed_000093),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000094", circle_ring_radius_scale_law_seed_000094),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000095", circle_ring_radius_scale_law_seed_000095),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000096", circle_ring_radius_scale_law_seed_000096),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000097", circle_ring_radius_scale_law_seed_000097),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000098", circle_ring_radius_scale_law_seed_000098),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000099", circle_ring_radius_scale_law_seed_000099),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000100", circle_ring_radius_scale_law_seed_000100),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000101", circle_ring_radius_scale_law_seed_000101),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000102", circle_ring_radius_scale_law_seed_000102),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000103", circle_ring_radius_scale_law_seed_000103),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000104", circle_ring_radius_scale_law_seed_000104),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000105", circle_ring_radius_scale_law_seed_000105),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000106", circle_ring_radius_scale_law_seed_000106),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000107", circle_ring_radius_scale_law_seed_000107),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000108", circle_ring_radius_scale_law_seed_000108),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000109", circle_ring_radius_scale_law_seed_000109),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000110", circle_ring_radius_scale_law_seed_000110),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000111", circle_ring_radius_scale_law_seed_000111),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000112", circle_ring_radius_scale_law_seed_000112),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000113", circle_ring_radius_scale_law_seed_000113),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000114", circle_ring_radius_scale_law_seed_000114),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000115", circle_ring_radius_scale_law_seed_000115),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000116", circle_ring_radius_scale_law_seed_000116),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000117", circle_ring_radius_scale_law_seed_000117),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000118", circle_ring_radius_scale_law_seed_000118),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000119", circle_ring_radius_scale_law_seed_000119),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000120", circle_ring_radius_scale_law_seed_000120),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000121", circle_ring_radius_scale_law_seed_000121),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000122", circle_ring_radius_scale_law_seed_000122),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000123", circle_ring_radius_scale_law_seed_000123),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000124", circle_ring_radius_scale_law_seed_000124),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000125", circle_ring_radius_scale_law_seed_000125),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000126", circle_ring_radius_scale_law_seed_000126),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000127", circle_ring_radius_scale_law_seed_000127),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000128", circle_ring_radius_scale_law_seed_000128),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000129", circle_ring_radius_scale_law_seed_000129),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000130", circle_ring_radius_scale_law_seed_000130),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000131", circle_ring_radius_scale_law_seed_000131),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000132", circle_ring_radius_scale_law_seed_000132),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000133", circle_ring_radius_scale_law_seed_000133),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000134", circle_ring_radius_scale_law_seed_000134),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000135", circle_ring_radius_scale_law_seed_000135),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000136", circle_ring_radius_scale_law_seed_000136),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000137", circle_ring_radius_scale_law_seed_000137),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000138", circle_ring_radius_scale_law_seed_000138),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000139", circle_ring_radius_scale_law_seed_000139),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000140", circle_ring_radius_scale_law_seed_000140),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000141", circle_ring_radius_scale_law_seed_000141),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000142", circle_ring_radius_scale_law_seed_000142),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000143", circle_ring_radius_scale_law_seed_000143),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000144", circle_ring_radius_scale_law_seed_000144),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000145", circle_ring_radius_scale_law_seed_000145),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000146", circle_ring_radius_scale_law_seed_000146),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000147", circle_ring_radius_scale_law_seed_000147),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000148", circle_ring_radius_scale_law_seed_000148),
        ("property_campaigns_3::tests::circle_ring_radius_scale_law_seed_000149", circle_ring_radius_scale_law_seed_000149),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000000", circle_ring_vertices_at_radius_seed_000000),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000001", circle_ring_vertices_at_radius_seed_000001),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000002", circle_ring_vertices_at_radius_seed_000002),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000003", circle_ring_vertices_at_radius_seed_000003),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000004", circle_ring_vertices_at_radius_seed_000004),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000005", circle_ring_vertices_at_radius_seed_000005),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000006", circle_ring_vertices_at_radius_seed_000006),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000007", circle_ring_vertices_at_radius_seed_000007),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000008", circle_ring_vertices_at_radius_seed_000008),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000009", circle_ring_vertices_at_radius_seed_000009),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000010", circle_ring_vertices_at_radius_seed_000010),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000011", circle_ring_vertices_at_radius_seed_000011),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000012", circle_ring_vertices_at_radius_seed_000012),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000013", circle_ring_vertices_at_radius_seed_000013),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000014", circle_ring_vertices_at_radius_seed_000014),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000015", circle_ring_vertices_at_radius_seed_000015),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000016", circle_ring_vertices_at_radius_seed_000016),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000017", circle_ring_vertices_at_radius_seed_000017),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000018", circle_ring_vertices_at_radius_seed_000018),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000019", circle_ring_vertices_at_radius_seed_000019),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000020", circle_ring_vertices_at_radius_seed_000020),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000021", circle_ring_vertices_at_radius_seed_000021),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000022", circle_ring_vertices_at_radius_seed_000022),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000023", circle_ring_vertices_at_radius_seed_000023),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000024", circle_ring_vertices_at_radius_seed_000024),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000025", circle_ring_vertices_at_radius_seed_000025),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000026", circle_ring_vertices_at_radius_seed_000026),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000027", circle_ring_vertices_at_radius_seed_000027),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000028", circle_ring_vertices_at_radius_seed_000028),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000029", circle_ring_vertices_at_radius_seed_000029),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000030", circle_ring_vertices_at_radius_seed_000030),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000031", circle_ring_vertices_at_radius_seed_000031),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000032", circle_ring_vertices_at_radius_seed_000032),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000033", circle_ring_vertices_at_radius_seed_000033),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000034", circle_ring_vertices_at_radius_seed_000034),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000035", circle_ring_vertices_at_radius_seed_000035),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000036", circle_ring_vertices_at_radius_seed_000036),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000037", circle_ring_vertices_at_radius_seed_000037),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000038", circle_ring_vertices_at_radius_seed_000038),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000039", circle_ring_vertices_at_radius_seed_000039),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000040", circle_ring_vertices_at_radius_seed_000040),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000041", circle_ring_vertices_at_radius_seed_000041),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000042", circle_ring_vertices_at_radius_seed_000042),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000043", circle_ring_vertices_at_radius_seed_000043),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000044", circle_ring_vertices_at_radius_seed_000044),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000045", circle_ring_vertices_at_radius_seed_000045),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000046", circle_ring_vertices_at_radius_seed_000046),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000047", circle_ring_vertices_at_radius_seed_000047),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000048", circle_ring_vertices_at_radius_seed_000048),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000049", circle_ring_vertices_at_radius_seed_000049),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000050", circle_ring_vertices_at_radius_seed_000050),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000051", circle_ring_vertices_at_radius_seed_000051),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000052", circle_ring_vertices_at_radius_seed_000052),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000053", circle_ring_vertices_at_radius_seed_000053),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000054", circle_ring_vertices_at_radius_seed_000054),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000055", circle_ring_vertices_at_radius_seed_000055),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000056", circle_ring_vertices_at_radius_seed_000056),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000057", circle_ring_vertices_at_radius_seed_000057),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000058", circle_ring_vertices_at_radius_seed_000058),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000059", circle_ring_vertices_at_radius_seed_000059),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000060", circle_ring_vertices_at_radius_seed_000060),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000061", circle_ring_vertices_at_radius_seed_000061),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000062", circle_ring_vertices_at_radius_seed_000062),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000063", circle_ring_vertices_at_radius_seed_000063),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000064", circle_ring_vertices_at_radius_seed_000064),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000065", circle_ring_vertices_at_radius_seed_000065),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000066", circle_ring_vertices_at_radius_seed_000066),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000067", circle_ring_vertices_at_radius_seed_000067),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000068", circle_ring_vertices_at_radius_seed_000068),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000069", circle_ring_vertices_at_radius_seed_000069),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000070", circle_ring_vertices_at_radius_seed_000070),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000071", circle_ring_vertices_at_radius_seed_000071),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000072", circle_ring_vertices_at_radius_seed_000072),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000073", circle_ring_vertices_at_radius_seed_000073),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000074", circle_ring_vertices_at_radius_seed_000074),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000075", circle_ring_vertices_at_radius_seed_000075),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000076", circle_ring_vertices_at_radius_seed_000076),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000077", circle_ring_vertices_at_radius_seed_000077),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000078", circle_ring_vertices_at_radius_seed_000078),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000079", circle_ring_vertices_at_radius_seed_000079),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000080", circle_ring_vertices_at_radius_seed_000080),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000081", circle_ring_vertices_at_radius_seed_000081),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000082", circle_ring_vertices_at_radius_seed_000082),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000083", circle_ring_vertices_at_radius_seed_000083),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000084", circle_ring_vertices_at_radius_seed_000084),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000085", circle_ring_vertices_at_radius_seed_000085),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000086", circle_ring_vertices_at_radius_seed_000086),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000087", circle_ring_vertices_at_radius_seed_000087),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000088", circle_ring_vertices_at_radius_seed_000088),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000089", circle_ring_vertices_at_radius_seed_000089),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000090", circle_ring_vertices_at_radius_seed_000090),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000091", circle_ring_vertices_at_radius_seed_000091),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000092", circle_ring_vertices_at_radius_seed_000092),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000093", circle_ring_vertices_at_radius_seed_000093),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000094", circle_ring_vertices_at_radius_seed_000094),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000095", circle_ring_vertices_at_radius_seed_000095),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000096", circle_ring_vertices_at_radius_seed_000096),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000097", circle_ring_vertices_at_radius_seed_000097),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000098", circle_ring_vertices_at_radius_seed_000098),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000099", circle_ring_vertices_at_radius_seed_000099),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000100", circle_ring_vertices_at_radius_seed_000100),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000101", circle_ring_vertices_at_radius_seed_000101),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000102", circle_ring_vertices_at_radius_seed_000102),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000103", circle_ring_vertices_at_radius_seed_000103),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000104", circle_ring_vertices_at_radius_seed_000104),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000105", circle_ring_vertices_at_radius_seed_000105),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000106", circle_ring_vertices_at_radius_seed_000106),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000107", circle_ring_vertices_at_radius_seed_000107),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000108", circle_ring_vertices_at_radius_seed_000108),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000109", circle_ring_vertices_at_radius_seed_000109),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000110", circle_ring_vertices_at_radius_seed_000110),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000111", circle_ring_vertices_at_radius_seed_000111),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000112", circle_ring_vertices_at_radius_seed_000112),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000113", circle_ring_vertices_at_radius_seed_000113),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000114", circle_ring_vertices_at_radius_seed_000114),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000115", circle_ring_vertices_at_radius_seed_000115),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000116", circle_ring_vertices_at_radius_seed_000116),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000117", circle_ring_vertices_at_radius_seed_000117),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000118", circle_ring_vertices_at_radius_seed_000118),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000119", circle_ring_vertices_at_radius_seed_000119),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000120", circle_ring_vertices_at_radius_seed_000120),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000121", circle_ring_vertices_at_radius_seed_000121),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000122", circle_ring_vertices_at_radius_seed_000122),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000123", circle_ring_vertices_at_radius_seed_000123),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000124", circle_ring_vertices_at_radius_seed_000124),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000125", circle_ring_vertices_at_radius_seed_000125),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000126", circle_ring_vertices_at_radius_seed_000126),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000127", circle_ring_vertices_at_radius_seed_000127),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000128", circle_ring_vertices_at_radius_seed_000128),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000129", circle_ring_vertices_at_radius_seed_000129),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000130", circle_ring_vertices_at_radius_seed_000130),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000131", circle_ring_vertices_at_radius_seed_000131),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000132", circle_ring_vertices_at_radius_seed_000132),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000133", circle_ring_vertices_at_radius_seed_000133),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000134", circle_ring_vertices_at_radius_seed_000134),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000135", circle_ring_vertices_at_radius_seed_000135),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000136", circle_ring_vertices_at_radius_seed_000136),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000137", circle_ring_vertices_at_radius_seed_000137),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000138", circle_ring_vertices_at_radius_seed_000138),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000139", circle_ring_vertices_at_radius_seed_000139),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000140", circle_ring_vertices_at_radius_seed_000140),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000141", circle_ring_vertices_at_radius_seed_000141),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000142", circle_ring_vertices_at_radius_seed_000142),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000143", circle_ring_vertices_at_radius_seed_000143),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000144", circle_ring_vertices_at_radius_seed_000144),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000145", circle_ring_vertices_at_radius_seed_000145),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000146", circle_ring_vertices_at_radius_seed_000146),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000147", circle_ring_vertices_at_radius_seed_000147),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000148", circle_ring_vertices_at_radius_seed_000148),
        ("property_campaigns_3::tests::circle_ring_vertices_at_radius_seed_000149", circle_ring_vertices_at_radius_seed_000149),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
