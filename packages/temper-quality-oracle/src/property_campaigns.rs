// Property-based campaigns over three independent, pure, deterministic
// temper-quality-oracle kernels: CPython `max`/`min` semantics
// (`py_max2`/`py_min2`), numpy's pairwise summation (`numpy_pairwise_sum`),
// and two placement-quality metrics that are supposed to behave like real
// geometric/physical quantities (`compactness_score`,
// `connectivity_clustering_score`).
//
// Why this exists (R7 / the WASM-tier volume payload)
// -----------------------------------------------------------------------
// A fixed, hand-written unit-test fixture explores the same handful of
// inputs every time it runs. This module gives the wasm32 tier a payload
// where each registered test explores a *distinct* generated input: every
// property below is a pure function of a `u64` seed through the
// `SplitMix64` generator below, so e.g. `mm_nan_second_arg_returns_first_seed_000042`
// and `..._seed_000043` exercise different operands, and a failure is
// reproducible from its seed alone.
//
// Each property is a metamorphic or invariant relation over the real
// kernel -- a relationship that must hold between two *related* calls --
// never a restatement of the implementation (i.e. never "recompute X, and
// assert X equals X"). Every one is picked so that a plausible bug in the
// kernel it covers flips it from green to red; see this crate's PR body
// (or `docs/evidence/` if this lands with one) for the mutation-testing
// evidence: each property was checked against a deliberately broken kernel
// and shown to fail on exactly (or mostly) the cases it should, with
// sibling properties in the same group staying green, then the kernel was
// reverted.
//
// No `proptest`: it is a dev-dependency, absent from the ordinary
// (non-test) build this crate's `wasm-registry` feature compiles into (see
// `scripts/gen_wasm_test_registry.py`'s `PROPTEST_USE` exclusion and
// `packages/temper-geometry/src/property_campaigns.rs`, the module this one
// copies the shape of -- itself copied from
// `packages/temper-drc-rs/src/rules/drc/property_campaigns.rs`). No RNG
// crate either: `SplitMix64` below is a small, self-contained, portable
// PRNG -- wasm32-unknown-unknown has no OS entropy source, and fixed seeds
// are what make a wasm32 trap reproducible from its seed by a human reading
// the failing test's name.
//
// Every item below (down to `mod tests`) is reachable ONLY from that
// module's `#[test]` functions -- which `scripts/gen_wasm_test_registry.py`
// turns into `pub(crate)` and reaches indirectly through
// `tests::WASM_TESTS` once this module is registered. A build with neither
// `test` nor `wasm-registry` active (e.g. `--features python` alone) sees
// every item below as unused -- same reason this crate's own `lib.rs`
// applies `#![allow(dead_code)]` under `not(feature = "python")`, and the
// two sibling `property_campaigns.rs` modules apply the same blanket allow
// to their own equivalent items.
#![allow(dead_code)]

// ---------------------------------------------------------------------------
// Deterministic PRNG (SplitMix64) -- pure, no external dependency, portable
// to wasm32-unknown-unknown without an entropy source. Shared by every
// property below; each draws its own generated case from `seed` directly,
// and any extra randomized parameter (a translation, a scale exponent, a
// shrink factor, ...) from an independent `sub_rng(seed, salt)` stream so a
// property's own parameters never correlate with which base case `seed`
// produced.
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
/// same base seed (same pattern as `temper-geometry`'s `sub_rng`).
fn sub_rng(seed: u64, salt: u64) -> SplitMix64 {
    SplitMix64::new(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15).wrapping_add(salt))
}

// ===========================================================================
// Kernel group A: `py_max2` / `py_min2` -- CPython `max(a, b)` / `min(a, b)`
// semantics (catalog class B5 in `placement_metrics.rs`'s module doc):
// `max(a, b)` is literally `b if b > a else a`, keeping the *first* argument
// on ties and NaN. `f64::max`/`f64::min` follow IEEE `maxNum`/`minNum`
// instead, which ignores NaN entirely and does not commit to a first-vs-
// second rule for signed zero. The properties below pin exactly where the
// two semantics agree and where they provably diverge.
// ===========================================================================

use crate::placement_metrics::{py_max2, py_min2};

const MM_SALT_PAIR_B: u64 = 0xA1;

/// A single finite f64 spanning several orders of magnitude.
fn mm_gen_finite(seed: u64) -> f64 {
    let mut rng = SplitMix64::new(seed);
    rng.range(-1.0e6, 1.0e6)
}

/// A pair of finite f64s guaranteed at least `0.01` apart in absolute terms.
///
/// "Well-separated" is deliberate: `py_max2`/`py_min2`'s only order
/// dependence is at a value *tie* -- NaN (comparisons with NaN are always
/// false) or the signed-zero pair `(0.0, -0.0)` (equal by `==`, distinct by
/// bit pattern). Away from both, whichever operand is numerically larger is
/// selected regardless of which argument position it sits in, so this
/// generator deliberately stays clear of that boundary -- the tie cases get
/// their own dedicated generator (`mm_gen_zero_pair`) and property below.
fn mm_gen_pair(seed: u64) -> (f64, f64) {
    let mut rng = SplitMix64::new(seed);
    let a = rng.range(-1.0e4, 1.0e4);
    let mut b_rng = sub_rng(seed, MM_SALT_PAIR_B);
    let sign = if b_rng.next_u64() & 1 == 0 { 1.0 } else { -1.0 };
    let mag = b_rng.range(0.01, 2.0e4);
    (a, a + sign * mag)
}

/// Two floats that are `==` (both `0.0`) but bit-distinct: `+0.0` derived
/// from `a * 0.0` (exact, `+0.0`, for any finite positive `a`) and `-0.0`
/// from negating it. The seed varies `a`, which does not change the outcome
/// -- the point is that the tie-breaking property below holds *regardless*
/// of how the zero was produced, not that the specific bits differ per
/// seed. (Not `a - a`: clippy's `eq_op` lint rightly flags identical
/// operands to `-` as almost always a mistake, so this uses a differently-
/// shaped exact-zero identity instead.)
fn mm_gen_zero_pair(seed: u64) -> (f64, f64) {
    let mut rng = SplitMix64::new(seed);
    let a = rng.range(0.5, 1.0e6);
    let pos_zero = a * 0.0;
    (pos_zero, -pos_zero)
}

/// Property MM-agree: away from NaN and the +/-0.0 tie, `py_max2`/`py_min2`
/// select exactly the value `f64::max`/`f64::min` would -- an independently
/// implemented oracle (IEEE `maxNum`/`minNum`, not CPython's rule) for "is
/// this actually the larger/smaller of the two". This is what pins
/// `py_max2`/`py_min2` to genuine max/min selection rather than some other
/// rule that happens to satisfy the NaN/zero properties below (e.g. a
/// min/max swap: see the PR body's mutation evidence -- that mutant is
/// caught here and only here among this group's four properties).
pub(crate) fn mm_agrees_with_ieee_away_from_nan_impl(seed: u64) {
    let (a, b) = mm_gen_pair(seed);
    let py_max_r = py_max2(a, b);
    let py_min_r = py_min2(a, b);
    let ieee_max_r = f64::max(a, b);
    let ieee_min_r = f64::min(a, b);
    assert_eq!(
        py_max_r.to_bits(),
        ieee_max_r.to_bits(),
        "py_max2 should select the same value as f64::max away from NaN/zero-ties: \
         seed={seed} a={a} b={b} py_max2={py_max_r} f64::max={ieee_max_r}"
    );
    assert_eq!(
        py_min_r.to_bits(),
        ieee_min_r.to_bits(),
        "py_min2 should select the same value as f64::min away from NaN/zero-ties: \
         seed={seed} a={a} b={b} py_min2={py_min_r} f64::min={ieee_min_r}"
    );
}

/// Property MM-nan2: CPython's `max(x, nan)`/`min(x, nan)` keep the first
/// (non-NaN) argument -- `b > a` (or `b < a`) is always false when `b` is
/// NaN, so the `else` branch fires and returns `a` untouched.
pub(crate) fn mm_nan_second_arg_returns_first_impl(seed: u64) {
    let x = mm_gen_finite(seed);
    let max_r = py_max2(x, f64::NAN);
    let min_r = py_min2(x, f64::NAN);
    assert_eq!(
        max_r.to_bits(),
        x.to_bits(),
        "py_max2(x, NaN) must return x unchanged: seed={seed} x={x} got={max_r}"
    );
    assert_eq!(
        min_r.to_bits(),
        x.to_bits(),
        "py_min2(x, NaN) must return x unchanged: seed={seed} x={x} got={min_r}"
    );
}

/// Property MM-nan1: CPython's `max(nan, x)`/`min(nan, x)` keep the first
/// argument too -- which is NaN this time, so the result stays NaN. This is
/// the exact asymmetry the crate's own module docs call out: NaN in the
/// *first* position poisons the result; NaN in the second does not (compare
/// `mm_nan_second_arg_returns_first_impl`). It is also where `py_max2`/
/// `py_min2` provably diverge from `f64::max`/`f64::min`, which are
/// documented to ignore NaN in *either* position and return the other
/// operand -- pinned directly below rather than assumed.
pub(crate) fn mm_nan_first_arg_propagates_impl(seed: u64) {
    let x = mm_gen_finite(seed);
    let max_r = py_max2(f64::NAN, x);
    let min_r = py_min2(f64::NAN, x);
    assert!(
        max_r.is_nan(),
        "py_max2(NaN, x) must stay NaN (first-arg-wins): seed={seed} x={x} got={max_r}"
    );
    assert!(
        min_r.is_nan(),
        "py_min2(NaN, x) must stay NaN (first-arg-wins): seed={seed} x={x} got={min_r}"
    );
    let ieee_max_r = f64::max(f64::NAN, x);
    let ieee_min_r = f64::min(f64::NAN, x);
    assert_eq!(
        ieee_max_r.to_bits(),
        x.to_bits(),
        "sanity: f64::max ignores a leading NaN and returns the other operand: seed={seed} x={x}"
    );
    assert_eq!(
        ieee_min_r.to_bits(),
        x.to_bits(),
        "sanity: f64::min ignores a leading NaN and returns the other operand: seed={seed} x={x}"
    );
}

/// Property MM-zero: `py_max2(+0.0, -0.0) == +0.0` and
/// `py_max2(-0.0, +0.0) == -0.0` (and the same for `py_min2`) --
/// deterministic, first-argument-wins tie-breaking on the one pair of
/// distinct-bit-pattern-but-`==`-equal finite floats. `f64::max`/`f64::min`
/// make no such guarantee for a signed-zero tie.
pub(crate) fn mm_signed_zero_first_arg_wins_impl(seed: u64) {
    let (pos_zero, neg_zero) = mm_gen_zero_pair(seed);
    assert!(
        pos_zero.is_sign_positive() && pos_zero == 0.0,
        "sanity: a * 0.0 must be +0.0 for finite positive a: seed={seed}"
    );
    assert!(
        neg_zero.is_sign_negative() && neg_zero == 0.0,
        "sanity: -(a * 0.0) must be -0.0: seed={seed}"
    );

    assert!(
        py_max2(pos_zero, neg_zero).is_sign_positive(),
        "py_max2(+0.0, -0.0) must keep the first (+0.0) argument: seed={seed}"
    );
    assert!(
        py_max2(neg_zero, pos_zero).is_sign_negative(),
        "py_max2(-0.0, +0.0) must keep the first (-0.0) argument: seed={seed}"
    );
    assert!(
        py_min2(pos_zero, neg_zero).is_sign_positive(),
        "py_min2(+0.0, -0.0) must keep the first (+0.0) argument: seed={seed}"
    );
    assert!(
        py_min2(neg_zero, pos_zero).is_sign_negative(),
        "py_min2(-0.0, +0.0) must keep the first (-0.0) argument: seed={seed}"
    );
}

// ===========================================================================
// Kernel group B: `numpy_pairwise_sum` / `naive_sum` -- catalog class B11.
// `np.sum` is not naive left-to-right addition (naive below 8 elements, an
// 8-way unrolled accumulation up to 128, recursive halving above); the
// properties below check the algebraic laws that hold for ANY sequence of
// IEEE-754 additions regardless of how they are grouped (scaling by an
// exact power of two, and negation, both commute exactly with `+`), a
// bounded-agreement law against naive summation that must hold everywhere,
// and the one case (n <= 2, always the naive branch) where reversing the
// input is provably a no-op.
// ===========================================================================

use crate::placement_metrics::{naive_sum, numpy_pairwise_sum};

const SM_SALT_SCALE: u64 = 0xB1;

/// An array of 1..=150 values in [-1e3, 1e3) -- spans all three of
/// `numpy_pairwise_sum`'s branches (naive below 8, 8-lane unrolled 8..=128,
/// recursive above).
fn sm_gen_array(seed: u64) -> Vec<f64> {
    let mut rng = SplitMix64::new(seed);
    let n = 1 + rng.index(150);
    (0..n).map(|_| rng.range(-1.0e3, 1.0e3)).collect()
}

/// Property SM-scale: scaling every element by an exact power of two scales
/// the sum by exactly the same factor, bit-for-bit. This holds for ANY
/// sequence of IEEE-754 additions (not just this specific algorithm):
/// multiplying by `2^k` only shifts an operand's exponent (exact, no
/// rounding, within the safe range this generator stays in), and `fl(x*2^k +
/// y*2^k) == fl(x + y) * 2^k` exactly because the rounding decision depends
/// only on the relative alignment of the significands, which a uniform
/// exponent shift does not change. `k` is bounded to +/-8 and the base
/// magnitude to 1e3 so no partial sum gets near overflow/underflow, where
/// the exactness argument breaks down.
pub(crate) fn sm_scale_invariance_pow2_impl(seed: u64) {
    let a = sm_gen_array(seed);
    let mut k_rng = sub_rng(seed, SM_SALT_SCALE);
    let k = k_rng.index(17) as i32 - 8; // -8..=8
    let factor = 2f64.powi(k);
    let scaled: Vec<f64> = a.iter().map(|&v| v * factor).collect();
    let base = numpy_pairwise_sum(&a);
    let expected = base * factor;
    let actual = numpy_pairwise_sum(&scaled);
    assert_eq!(
        actual.to_bits(),
        expected.to_bits(),
        "numpy_pairwise_sum did not scale exactly under a power-of-two factor: \
         seed={seed} n={} k={k} base={base:e} expected={expected:e} actual={actual:e}",
        a.len()
    );
}

/// Property SM-negate: negating every element negates the sum, bit-for-bit.
/// Negation flips only the sign bit (exact, no rounding), and IEEE-754
/// round-to-nearest-even addition is symmetric under negation:
/// `fl(-x + -y) == -fl(x + y)` always, exactly, regardless of grouping.
pub(crate) fn sm_negation_invariance_impl(seed: u64) {
    let a = sm_gen_array(seed);
    let negated: Vec<f64> = a.iter().map(|&v| -v).collect();
    let base = numpy_pairwise_sum(&a);
    let actual = numpy_pairwise_sum(&negated);
    assert_eq!(
        actual.to_bits(),
        (-base).to_bits(),
        "numpy_pairwise_sum did not negate exactly under elementwise negation: \
         seed={seed} n={} base={base:e} negated_sum={actual:e}",
        a.len()
    );
}

/// Property SM-bound: `numpy_pairwise_sum` and `naive_sum` agree within a
/// stated rounding-error bound, everywhere -- not just below 8 elements
/// (where they are bit-identical; that narrower fact is pinned by this
/// crate's existing hand-written and proptest coverage). The classical bound
/// for a sum of `n` terms accumulated through IEEE-754 addition, however the
/// additions are grouped, is `O(n * eps * sum(|a_i|))`; 16x is a deliberately
/// generous constant (the true worst case is close to `n * eps`, and numpy's
/// pairwise scheme has a *tighter* `O(log n * eps)` bound than naive's `O(n *
/// eps)`, so 16x leaves ample headroom without weakening the check into a
/// tautology).
pub(crate) fn sm_bounded_agreement_with_naive_impl(seed: u64) {
    let a = sm_gen_array(seed);
    let p = numpy_pairwise_sum(&a);
    let n = naive_sum(&a);
    let abs_vals: Vec<f64> = a.iter().map(|v| v.abs()).collect();
    let abs_sum = naive_sum(&abs_vals);
    let count = a.len() as f64;
    let tol = 16.0 * count * f64::EPSILON * abs_sum + 1e-300;
    let diff = (p - n).abs();
    assert!(
        diff <= tol,
        "numpy_pairwise_sum and naive_sum diverged beyond the stated rounding-error bound: \
         seed={seed} n={} diff={diff:e} tol={tol:e} pairwise={p:e} naive={n:e}",
        a.len()
    );
}

/// An array of 0..=2 values -- always short enough that
/// `numpy_pairwise_sum` takes its naive branch (n < 8) and reduces to at
/// most one `+`.
fn sm_gen_small_array(seed: u64) -> Vec<f64> {
    let mut rng = SplitMix64::new(seed);
    let n = rng.index(3); // 0, 1, or 2
    (0..n).map(|_| rng.range(-1.0e6, 1.0e6)).collect()
}

/// Property SM-reverse: for n <= 2, reversing the input does not change
/// `numpy_pairwise_sum`'s result, bit-for-bit. This is deliberately narrow
/// -- "invariant under reversal only where the algorithm says it is": a
/// single IEEE-754 addition is exactly commutative (`fl(a + b) == fl(b +
/// a)`, no rounding-order dependence with only one operation), so n <= 1 is
/// trivial and n == 2 is the smallest genuine case. This does NOT generalise
/// to n >= 3: reassociating three or more additions in a different order is
/// not guaranteed bit-identical even though every individual `+` is
/// commutative, which is exactly why numpy's own pairwise/8-lane/recursive
/// scheme produces a *different* result from naive summation above n == 7 in
/// the first place (see this crate's existing
/// `pairwise_sum_diverges_from_naive_at_eight`).
pub(crate) fn sm_reversal_invariant_small_n_impl(seed: u64) {
    let a = sm_gen_small_array(seed);
    let mut rev = a.clone();
    rev.reverse();
    let fwd = numpy_pairwise_sum(&a);
    let bwd = numpy_pairwise_sum(&rev);
    assert_eq!(
        fwd.to_bits(),
        bwd.to_bits(),
        "numpy_pairwise_sum(n<=2) must be exactly reversal-invariant: seed={seed} a={a:?} fwd={fwd:e} bwd={bwd:e}"
    );
}

// ===========================================================================
// Kernel group C: `compactness_score` / `connectivity_clustering_score` --
// placement-quality metrics that are supposed to behave like real
// dimensionless geometric ratios: invariant under sliding the whole
// placement around (translation), invariant under uniformly rescaling it
// (a dimensionless ratio has no absolute length scale to leak), and
// monotone under moving a net's components closer together (a tighter
// bounding box can only make "how tightly packed is this net" look better
// or the same, never worse).
// ===========================================================================

use crate::placement_metrics::{compactness_score, connectivity_clustering_score, NetCluster};

const PM_SALT_TRANSLATE: u64 = 0xC1;
const PM_SALT_SCALE: u64 = 0xC2;
const PM_SALT_SHRINK: u64 = 0xC3;

/// A `compactness_score` case: 2..=7 components with a position, a positive
/// half-width/half-height, and an area generated as a fraction (20%-100%)
/// of the component's own bbox -- keeping the utilization ratio away from
/// the trivial "always saturates at 1.0" regime so translation/scale bugs
/// have somewhere to show up.
///
/// A named struct rather than a 4-tuple: clippy's `type_complexity` lint
/// (correctly) flags a `(Vec<(f64, f64)>, Vec<f64>, Vec<f64>, Vec<f64>)`
/// return type as hard to read at the call site.
struct CompactnessCase {
    positions: Vec<(f64, f64)>,
    half_widths: Vec<f64>,
    half_heights: Vec<f64>,
    areas: Vec<f64>,
}

fn pm_gen_compactness_case(seed: u64) -> CompactnessCase {
    let mut rng = SplitMix64::new(seed);
    let n = 2 + rng.index(6); // 2..=7
    let mut positions = Vec::with_capacity(n);
    let mut half_widths = Vec::with_capacity(n);
    let mut half_heights = Vec::with_capacity(n);
    let mut areas = Vec::with_capacity(n);
    for _ in 0..n {
        positions.push((rng.range(-500.0, 500.0), rng.range(-500.0, 500.0)));
        let hw = rng.range(1.0, 20.0);
        let hh = rng.range(1.0, 20.0);
        let frac = rng.range(0.2, 1.0);
        half_widths.push(hw);
        half_heights.push(hh);
        areas.push(4.0 * hw * hh * frac);
    }
    CompactnessCase {
        positions,
        half_widths,
        half_heights,
        areas,
    }
}

/// Property PM-translate: `compactness_score` is invariant, within a tight
/// numerical tolerance, under translating every component's position by the
/// same `(dx, dy)` -- the score is built entirely from `(x_max - x_min)`,
/// `(y_max - y_min)` and per-component areas, none of which depend on the
/// placement's absolute position. The tolerance (not bit-exactness) is
/// because `(x_max + dx) - (x_min + dx)` is not guaranteed bit-identical to
/// `x_max - x_min` for arbitrary `dx` (each addition rounds independently
/// before the subtraction) -- unlike the power-of-two scale law below, an
/// arbitrary real-valued translation has no exactness argument, only a
/// rounding-error one, so this property states a bound instead of equality.
pub(crate) fn pm_compactness_translation_invariance_impl(seed: u64) {
    let case = pm_gen_compactness_case(seed);
    let mut t_rng = sub_rng(seed, PM_SALT_TRANSLATE);
    let dx = t_rng.range(-1.0e4, 1.0e4);
    let dy = t_rng.range(-1.0e4, 1.0e4);
    let shifted: Vec<(f64, f64)> = case
        .positions
        .iter()
        .map(|&(x, y)| (x + dx, y + dy))
        .collect();
    let before = compactness_score(
        &case.positions,
        &case.half_widths,
        &case.half_heights,
        &case.areas,
    );
    let after = compactness_score(&shifted, &case.half_widths, &case.half_heights, &case.areas);
    let tol = 1e-6;
    assert!(
        (before - after).abs() <= tol,
        "compactness_score is not translation-invariant within tolerance: \
         seed={seed} dx={dx} dy={dy} before={before} after={after}"
    );
}

/// Property PM-scale: `compactness_score` is EXACTLY invariant, bit-for-bit,
/// under uniformly rescaling the whole case by a power of two -- positions
/// and half-extents by `s = 2^k`, areas by `s^2` (areas are a width*height
/// product, so they scale quadratically under a linear rescale). Utilization
/// is `total_area / placement_area`; both numerator and denominator scale by
/// exactly `s^2` (every intermediate `+`/`-`/`*`/`/` in the kernel commutes
/// exactly with a power-of-two factor, the same exactness argument as
/// `sm_scale_invariance_pow2_impl`), so the ratio -- and therefore the
/// score -- comes out bit-identical. This is "scale behaviour follows a
/// stated law": a dimensionless ratio metric has no absolute length scale to
/// leak, and unlike the translation property above, power-of-two scaling
/// keeps the whole computation exact enough to assert equality rather than a
/// tolerance.
pub(crate) fn pm_compactness_scale_law_pow2_impl(seed: u64) {
    let case = pm_gen_compactness_case(seed);
    let mut k_rng = sub_rng(seed, PM_SALT_SCALE);
    let k = k_rng.index(9) as i32 - 4; // -4..=4
    let s = 2f64.powi(k);
    let s2 = s * s;
    let scaled_positions: Vec<(f64, f64)> = case
        .positions
        .iter()
        .map(|&(x, y)| (x * s, y * s))
        .collect();
    let scaled_hw: Vec<f64> = case.half_widths.iter().map(|&v| v * s).collect();
    let scaled_hh: Vec<f64> = case.half_heights.iter().map(|&v| v * s).collect();
    let scaled_areas: Vec<f64> = case.areas.iter().map(|&v| v * s2).collect();
    let before = compactness_score(
        &case.positions,
        &case.half_widths,
        &case.half_heights,
        &case.areas,
    );
    let after = compactness_score(&scaled_positions, &scaled_hw, &scaled_hh, &scaled_areas);
    assert_eq!(
        before.to_bits(),
        after.to_bits(),
        "compactness_score did not obey the power-of-two scale law: seed={seed} k={k} before={before} after={after}"
    );
}

/// A `NetCluster` of 2..=6 components with a position, positive
/// half-width/half-height (>= 0.5, so `actual_area` in
/// `connectivity_clustering_score` can never be zeroed out by the shrink
/// below), and an area generated as a fraction of the component's own bbox.
fn pm_gen_net(seed: u64) -> NetCluster {
    let mut rng = SplitMix64::new(seed);
    let n = 2 + rng.index(5); // 2..=6
    let mut positions = Vec::with_capacity(n);
    let mut half_widths = Vec::with_capacity(n);
    let mut half_heights = Vec::with_capacity(n);
    let mut areas = Vec::with_capacity(n);
    for _ in 0..n {
        positions.push((rng.range(-300.0, 300.0), rng.range(-300.0, 300.0)));
        let hw = rng.range(0.5, 10.0);
        let hh = rng.range(0.5, 10.0);
        let frac = rng.range(0.1, 1.0);
        half_widths.push(hw);
        half_heights.push(hh);
        areas.push(4.0 * hw * hh * frac);
    }
    NetCluster {
        positions,
        half_widths,
        half_heights,
        areas,
    }
}

/// Property PM-monotone: shrinking a net's components toward their centroid
/// by a factor `t` in `(0, 1)` -- moving them strictly closer together --
/// never *decreases* `connectivity_clustering_score` (within a tiny
/// tolerance for floating rounding at the ratio's saturation boundary).
///
/// Why this must hold: the net's bounding-box span scales by exactly `t` in
/// each axis while the half-extent padding (`2 * max_hw`, `2 * max_hh`) does
/// not shrink, so `actual_area` is non-increasing; `min_possible_area` (the
/// sum of component areas) is untouched by the shrink. The score is
/// `min_possible_area / max(actual_area, min_possible_area)`, whose
/// denominator is therefore non-increasing while the numerator is constant
/// -- a ratio that can only grow or stay the same. This is the "moving
/// components closer never worsens a wirelength-style metric" monotonicity
/// class named in the campaign brief, applied to the one metric in this
/// crate shaped like it.
pub(crate) fn pm_connectivity_monotone_under_shrink_impl(seed: u64) {
    let net = pm_gen_net(seed);
    let n = net.positions.len() as f64;
    let cx = net.positions.iter().map(|p| p.0).sum::<f64>() / n;
    let cy = net.positions.iter().map(|p| p.1).sum::<f64>() / n;
    let mut s_rng = sub_rng(seed, PM_SALT_SHRINK);
    let t = s_rng.range(0.1, 0.9);
    let shrunk_positions: Vec<(f64, f64)> = net
        .positions
        .iter()
        .map(|&(x, y)| (cx + t * (x - cx), cy + t * (y - cy)))
        .collect();
    let before = connectivity_clustering_score(std::slice::from_ref(&net), false);
    let shrunk_net = NetCluster {
        positions: shrunk_positions,
        half_widths: net.half_widths.clone(),
        half_heights: net.half_heights.clone(),
        areas: net.areas.clone(),
    };
    let after = connectivity_clustering_score(std::slice::from_ref(&shrunk_net), false);
    let tol = 1e-9;
    assert!(
        after >= before - tol,
        "connectivity_clustering_score worsened when the net's components moved closer together: \
         seed={seed} t={t} before={before} after={after}"
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
    fn mm_gen_pair_is_well_separated() {
        for seed in [0u64, 1, 500, 999_999] {
            let (a, b) = mm_gen_pair(seed);
            assert!((b - a).abs() >= 0.01, "seed={seed} a={a} b={b}");
        }
    }

    #[cfg_attr(test, test)]
    fn mm_gen_zero_pair_produces_true_signed_zeros() {
        for seed in [0u64, 42, 12345] {
            let (pos, neg) = mm_gen_zero_pair(seed);
            assert_eq!(pos, 0.0);
            assert_eq!(neg, 0.0);
            assert!(pos.is_sign_positive());
            assert!(neg.is_sign_negative());
        }
    }

    #[cfg_attr(test, test)]
    fn mm_signed_zero_first_arg_wins_on_a_hand_worked_example() {
        // Explicit non-random cross-check of the same relation
        // `mm_signed_zero_first_arg_wins_impl` exercises at volume.
        assert!(py_max2(0.0, -0.0).is_sign_positive());
        assert!(py_max2(-0.0, 0.0).is_sign_negative());
        assert!(py_min2(0.0, -0.0).is_sign_positive());
        assert!(py_min2(-0.0, 0.0).is_sign_negative());
    }

    #[cfg_attr(test, test)]
    fn sm_gen_array_length_in_expected_range() {
        for seed in [0u64, 1, 500, 999_999] {
            let a = sm_gen_array(seed);
            assert!(!a.is_empty() && a.len() <= 150, "seed={seed} n={}", a.len());
        }
    }

    #[cfg_attr(test, test)]
    fn sm_gen_small_array_length_in_expected_range() {
        for seed in [0u64, 1, 500, 999_999] {
            let a = sm_gen_small_array(seed);
            assert!(a.len() <= 2, "seed={seed} n={}", a.len());
        }
    }

    #[cfg_attr(test, test)]
    fn sm_scale_invariance_on_a_hand_built_array() {
        // Explicit non-random cross-check: [1.0, 2.0, 3.0] scaled by 2^3 == 8.
        let a = [1.0_f64, 2.0, 3.0];
        let scaled: Vec<f64> = a.iter().map(|v| v * 8.0).collect();
        let base = numpy_pairwise_sum(&a);
        assert_eq!(base, 6.0);
        assert_eq!(numpy_pairwise_sum(&scaled), 48.0);
    }

    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_on_a_hand_built_pair() {
        let a = [3.5_f64, -1.25];
        let b = [-1.25_f64, 3.5];
        assert_eq!(
            numpy_pairwise_sum(&a).to_bits(),
            numpy_pairwise_sum(&b).to_bits()
        );
    }

    #[cfg_attr(test, test)]
    fn pm_gen_compactness_case_dims_in_expected_range() {
        for seed in [0u64, 3, 12345] {
            let case = pm_gen_compactness_case(seed);
            let n = case.positions.len();
            assert!((2..=7).contains(&n), "seed={seed} n={n}");
            assert_eq!(case.half_widths.len(), n);
            assert_eq!(case.half_heights.len(), n);
            assert_eq!(case.areas.len(), n);
        }
    }

    #[cfg_attr(test, test)]
    fn pm_gen_net_dims_in_expected_range() {
        for seed in [0u64, 3, 12345] {
            let net = pm_gen_net(seed);
            let n = net.positions.len();
            assert!((2..=6).contains(&n), "seed={seed} n={n}");
            assert_eq!(net.half_widths.len(), n);
            assert_eq!(net.half_heights.len(), n);
            assert_eq!(net.areas.len(), n);
        }
    }

    #[cfg_attr(test, test)]
    fn pm_compactness_translation_invariance_on_a_hand_built_case() {
        // A single component whose area exactly fills its own bbox: score is
        // exactly 1.0 regardless of where it sits on the board.
        let positions = [(10.0, 20.0)];
        let hw = [5.0];
        let hh = [3.0];
        let areas = [4.0 * 5.0 * 3.0];
        let before = compactness_score(&positions, &hw, &hh, &areas);
        let shifted = [(10.0 + 1000.0, 20.0 - 500.0)];
        let after = compactness_score(&shifted, &hw, &hh, &areas);
        assert_eq!(before, 1.0);
        assert_eq!(after, 1.0);
    }

    // --- mm_agrees_with_ieee: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000000() {
        mm_agrees_with_ieee_away_from_nan_impl(0);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000001() {
        mm_agrees_with_ieee_away_from_nan_impl(1);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000002() {
        mm_agrees_with_ieee_away_from_nan_impl(2);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000003() {
        mm_agrees_with_ieee_away_from_nan_impl(3);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000004() {
        mm_agrees_with_ieee_away_from_nan_impl(4);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000005() {
        mm_agrees_with_ieee_away_from_nan_impl(5);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000006() {
        mm_agrees_with_ieee_away_from_nan_impl(6);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000007() {
        mm_agrees_with_ieee_away_from_nan_impl(7);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000008() {
        mm_agrees_with_ieee_away_from_nan_impl(8);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000009() {
        mm_agrees_with_ieee_away_from_nan_impl(9);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000010() {
        mm_agrees_with_ieee_away_from_nan_impl(10);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000011() {
        mm_agrees_with_ieee_away_from_nan_impl(11);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000012() {
        mm_agrees_with_ieee_away_from_nan_impl(12);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000013() {
        mm_agrees_with_ieee_away_from_nan_impl(13);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000014() {
        mm_agrees_with_ieee_away_from_nan_impl(14);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000015() {
        mm_agrees_with_ieee_away_from_nan_impl(15);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000016() {
        mm_agrees_with_ieee_away_from_nan_impl(16);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000017() {
        mm_agrees_with_ieee_away_from_nan_impl(17);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000018() {
        mm_agrees_with_ieee_away_from_nan_impl(18);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000019() {
        mm_agrees_with_ieee_away_from_nan_impl(19);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000020() {
        mm_agrees_with_ieee_away_from_nan_impl(20);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000021() {
        mm_agrees_with_ieee_away_from_nan_impl(21);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000022() {
        mm_agrees_with_ieee_away_from_nan_impl(22);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000023() {
        mm_agrees_with_ieee_away_from_nan_impl(23);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000024() {
        mm_agrees_with_ieee_away_from_nan_impl(24);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000025() {
        mm_agrees_with_ieee_away_from_nan_impl(25);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000026() {
        mm_agrees_with_ieee_away_from_nan_impl(26);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000027() {
        mm_agrees_with_ieee_away_from_nan_impl(27);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000028() {
        mm_agrees_with_ieee_away_from_nan_impl(28);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000029() {
        mm_agrees_with_ieee_away_from_nan_impl(29);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000030() {
        mm_agrees_with_ieee_away_from_nan_impl(30);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000031() {
        mm_agrees_with_ieee_away_from_nan_impl(31);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000032() {
        mm_agrees_with_ieee_away_from_nan_impl(32);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000033() {
        mm_agrees_with_ieee_away_from_nan_impl(33);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000034() {
        mm_agrees_with_ieee_away_from_nan_impl(34);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000035() {
        mm_agrees_with_ieee_away_from_nan_impl(35);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000036() {
        mm_agrees_with_ieee_away_from_nan_impl(36);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000037() {
        mm_agrees_with_ieee_away_from_nan_impl(37);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000038() {
        mm_agrees_with_ieee_away_from_nan_impl(38);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000039() {
        mm_agrees_with_ieee_away_from_nan_impl(39);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000040() {
        mm_agrees_with_ieee_away_from_nan_impl(40);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000041() {
        mm_agrees_with_ieee_away_from_nan_impl(41);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000042() {
        mm_agrees_with_ieee_away_from_nan_impl(42);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000043() {
        mm_agrees_with_ieee_away_from_nan_impl(43);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000044() {
        mm_agrees_with_ieee_away_from_nan_impl(44);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000045() {
        mm_agrees_with_ieee_away_from_nan_impl(45);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000046() {
        mm_agrees_with_ieee_away_from_nan_impl(46);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000047() {
        mm_agrees_with_ieee_away_from_nan_impl(47);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000048() {
        mm_agrees_with_ieee_away_from_nan_impl(48);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000049() {
        mm_agrees_with_ieee_away_from_nan_impl(49);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000050() {
        mm_agrees_with_ieee_away_from_nan_impl(50);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000051() {
        mm_agrees_with_ieee_away_from_nan_impl(51);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000052() {
        mm_agrees_with_ieee_away_from_nan_impl(52);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000053() {
        mm_agrees_with_ieee_away_from_nan_impl(53);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000054() {
        mm_agrees_with_ieee_away_from_nan_impl(54);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000055() {
        mm_agrees_with_ieee_away_from_nan_impl(55);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000056() {
        mm_agrees_with_ieee_away_from_nan_impl(56);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000057() {
        mm_agrees_with_ieee_away_from_nan_impl(57);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000058() {
        mm_agrees_with_ieee_away_from_nan_impl(58);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000059() {
        mm_agrees_with_ieee_away_from_nan_impl(59);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000060() {
        mm_agrees_with_ieee_away_from_nan_impl(60);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000061() {
        mm_agrees_with_ieee_away_from_nan_impl(61);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000062() {
        mm_agrees_with_ieee_away_from_nan_impl(62);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000063() {
        mm_agrees_with_ieee_away_from_nan_impl(63);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000064() {
        mm_agrees_with_ieee_away_from_nan_impl(64);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000065() {
        mm_agrees_with_ieee_away_from_nan_impl(65);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000066() {
        mm_agrees_with_ieee_away_from_nan_impl(66);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000067() {
        mm_agrees_with_ieee_away_from_nan_impl(67);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000068() {
        mm_agrees_with_ieee_away_from_nan_impl(68);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000069() {
        mm_agrees_with_ieee_away_from_nan_impl(69);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000070() {
        mm_agrees_with_ieee_away_from_nan_impl(70);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000071() {
        mm_agrees_with_ieee_away_from_nan_impl(71);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000072() {
        mm_agrees_with_ieee_away_from_nan_impl(72);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000073() {
        mm_agrees_with_ieee_away_from_nan_impl(73);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000074() {
        mm_agrees_with_ieee_away_from_nan_impl(74);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000075() {
        mm_agrees_with_ieee_away_from_nan_impl(75);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000076() {
        mm_agrees_with_ieee_away_from_nan_impl(76);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000077() {
        mm_agrees_with_ieee_away_from_nan_impl(77);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000078() {
        mm_agrees_with_ieee_away_from_nan_impl(78);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000079() {
        mm_agrees_with_ieee_away_from_nan_impl(79);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000080() {
        mm_agrees_with_ieee_away_from_nan_impl(80);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000081() {
        mm_agrees_with_ieee_away_from_nan_impl(81);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000082() {
        mm_agrees_with_ieee_away_from_nan_impl(82);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000083() {
        mm_agrees_with_ieee_away_from_nan_impl(83);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000084() {
        mm_agrees_with_ieee_away_from_nan_impl(84);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000085() {
        mm_agrees_with_ieee_away_from_nan_impl(85);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000086() {
        mm_agrees_with_ieee_away_from_nan_impl(86);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000087() {
        mm_agrees_with_ieee_away_from_nan_impl(87);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000088() {
        mm_agrees_with_ieee_away_from_nan_impl(88);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000089() {
        mm_agrees_with_ieee_away_from_nan_impl(89);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000090() {
        mm_agrees_with_ieee_away_from_nan_impl(90);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000091() {
        mm_agrees_with_ieee_away_from_nan_impl(91);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000092() {
        mm_agrees_with_ieee_away_from_nan_impl(92);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000093() {
        mm_agrees_with_ieee_away_from_nan_impl(93);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000094() {
        mm_agrees_with_ieee_away_from_nan_impl(94);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000095() {
        mm_agrees_with_ieee_away_from_nan_impl(95);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000096() {
        mm_agrees_with_ieee_away_from_nan_impl(96);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000097() {
        mm_agrees_with_ieee_away_from_nan_impl(97);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000098() {
        mm_agrees_with_ieee_away_from_nan_impl(98);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000099() {
        mm_agrees_with_ieee_away_from_nan_impl(99);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000100() {
        mm_agrees_with_ieee_away_from_nan_impl(100);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000101() {
        mm_agrees_with_ieee_away_from_nan_impl(101);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000102() {
        mm_agrees_with_ieee_away_from_nan_impl(102);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000103() {
        mm_agrees_with_ieee_away_from_nan_impl(103);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000104() {
        mm_agrees_with_ieee_away_from_nan_impl(104);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000105() {
        mm_agrees_with_ieee_away_from_nan_impl(105);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000106() {
        mm_agrees_with_ieee_away_from_nan_impl(106);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000107() {
        mm_agrees_with_ieee_away_from_nan_impl(107);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000108() {
        mm_agrees_with_ieee_away_from_nan_impl(108);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000109() {
        mm_agrees_with_ieee_away_from_nan_impl(109);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000110() {
        mm_agrees_with_ieee_away_from_nan_impl(110);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000111() {
        mm_agrees_with_ieee_away_from_nan_impl(111);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000112() {
        mm_agrees_with_ieee_away_from_nan_impl(112);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000113() {
        mm_agrees_with_ieee_away_from_nan_impl(113);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000114() {
        mm_agrees_with_ieee_away_from_nan_impl(114);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000115() {
        mm_agrees_with_ieee_away_from_nan_impl(115);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000116() {
        mm_agrees_with_ieee_away_from_nan_impl(116);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000117() {
        mm_agrees_with_ieee_away_from_nan_impl(117);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000118() {
        mm_agrees_with_ieee_away_from_nan_impl(118);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000119() {
        mm_agrees_with_ieee_away_from_nan_impl(119);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000120() {
        mm_agrees_with_ieee_away_from_nan_impl(120);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000121() {
        mm_agrees_with_ieee_away_from_nan_impl(121);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000122() {
        mm_agrees_with_ieee_away_from_nan_impl(122);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000123() {
        mm_agrees_with_ieee_away_from_nan_impl(123);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000124() {
        mm_agrees_with_ieee_away_from_nan_impl(124);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000125() {
        mm_agrees_with_ieee_away_from_nan_impl(125);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000126() {
        mm_agrees_with_ieee_away_from_nan_impl(126);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000127() {
        mm_agrees_with_ieee_away_from_nan_impl(127);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000128() {
        mm_agrees_with_ieee_away_from_nan_impl(128);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000129() {
        mm_agrees_with_ieee_away_from_nan_impl(129);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000130() {
        mm_agrees_with_ieee_away_from_nan_impl(130);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000131() {
        mm_agrees_with_ieee_away_from_nan_impl(131);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000132() {
        mm_agrees_with_ieee_away_from_nan_impl(132);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000133() {
        mm_agrees_with_ieee_away_from_nan_impl(133);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000134() {
        mm_agrees_with_ieee_away_from_nan_impl(134);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000135() {
        mm_agrees_with_ieee_away_from_nan_impl(135);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000136() {
        mm_agrees_with_ieee_away_from_nan_impl(136);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000137() {
        mm_agrees_with_ieee_away_from_nan_impl(137);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000138() {
        mm_agrees_with_ieee_away_from_nan_impl(138);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000139() {
        mm_agrees_with_ieee_away_from_nan_impl(139);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000140() {
        mm_agrees_with_ieee_away_from_nan_impl(140);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000141() {
        mm_agrees_with_ieee_away_from_nan_impl(141);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000142() {
        mm_agrees_with_ieee_away_from_nan_impl(142);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000143() {
        mm_agrees_with_ieee_away_from_nan_impl(143);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000144() {
        mm_agrees_with_ieee_away_from_nan_impl(144);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000145() {
        mm_agrees_with_ieee_away_from_nan_impl(145);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000146() {
        mm_agrees_with_ieee_away_from_nan_impl(146);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000147() {
        mm_agrees_with_ieee_away_from_nan_impl(147);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000148() {
        mm_agrees_with_ieee_away_from_nan_impl(148);
    }
    #[cfg_attr(test, test)]
    fn mm_agrees_with_ieee_seed_000149() {
        mm_agrees_with_ieee_away_from_nan_impl(149);
    }
    // --- mm_nan_second: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000000() {
        mm_nan_second_arg_returns_first_impl(0);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000001() {
        mm_nan_second_arg_returns_first_impl(1);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000002() {
        mm_nan_second_arg_returns_first_impl(2);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000003() {
        mm_nan_second_arg_returns_first_impl(3);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000004() {
        mm_nan_second_arg_returns_first_impl(4);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000005() {
        mm_nan_second_arg_returns_first_impl(5);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000006() {
        mm_nan_second_arg_returns_first_impl(6);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000007() {
        mm_nan_second_arg_returns_first_impl(7);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000008() {
        mm_nan_second_arg_returns_first_impl(8);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000009() {
        mm_nan_second_arg_returns_first_impl(9);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000010() {
        mm_nan_second_arg_returns_first_impl(10);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000011() {
        mm_nan_second_arg_returns_first_impl(11);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000012() {
        mm_nan_second_arg_returns_first_impl(12);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000013() {
        mm_nan_second_arg_returns_first_impl(13);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000014() {
        mm_nan_second_arg_returns_first_impl(14);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000015() {
        mm_nan_second_arg_returns_first_impl(15);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000016() {
        mm_nan_second_arg_returns_first_impl(16);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000017() {
        mm_nan_second_arg_returns_first_impl(17);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000018() {
        mm_nan_second_arg_returns_first_impl(18);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000019() {
        mm_nan_second_arg_returns_first_impl(19);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000020() {
        mm_nan_second_arg_returns_first_impl(20);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000021() {
        mm_nan_second_arg_returns_first_impl(21);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000022() {
        mm_nan_second_arg_returns_first_impl(22);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000023() {
        mm_nan_second_arg_returns_first_impl(23);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000024() {
        mm_nan_second_arg_returns_first_impl(24);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000025() {
        mm_nan_second_arg_returns_first_impl(25);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000026() {
        mm_nan_second_arg_returns_first_impl(26);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000027() {
        mm_nan_second_arg_returns_first_impl(27);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000028() {
        mm_nan_second_arg_returns_first_impl(28);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000029() {
        mm_nan_second_arg_returns_first_impl(29);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000030() {
        mm_nan_second_arg_returns_first_impl(30);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000031() {
        mm_nan_second_arg_returns_first_impl(31);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000032() {
        mm_nan_second_arg_returns_first_impl(32);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000033() {
        mm_nan_second_arg_returns_first_impl(33);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000034() {
        mm_nan_second_arg_returns_first_impl(34);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000035() {
        mm_nan_second_arg_returns_first_impl(35);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000036() {
        mm_nan_second_arg_returns_first_impl(36);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000037() {
        mm_nan_second_arg_returns_first_impl(37);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000038() {
        mm_nan_second_arg_returns_first_impl(38);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000039() {
        mm_nan_second_arg_returns_first_impl(39);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000040() {
        mm_nan_second_arg_returns_first_impl(40);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000041() {
        mm_nan_second_arg_returns_first_impl(41);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000042() {
        mm_nan_second_arg_returns_first_impl(42);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000043() {
        mm_nan_second_arg_returns_first_impl(43);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000044() {
        mm_nan_second_arg_returns_first_impl(44);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000045() {
        mm_nan_second_arg_returns_first_impl(45);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000046() {
        mm_nan_second_arg_returns_first_impl(46);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000047() {
        mm_nan_second_arg_returns_first_impl(47);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000048() {
        mm_nan_second_arg_returns_first_impl(48);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000049() {
        mm_nan_second_arg_returns_first_impl(49);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000050() {
        mm_nan_second_arg_returns_first_impl(50);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000051() {
        mm_nan_second_arg_returns_first_impl(51);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000052() {
        mm_nan_second_arg_returns_first_impl(52);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000053() {
        mm_nan_second_arg_returns_first_impl(53);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000054() {
        mm_nan_second_arg_returns_first_impl(54);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000055() {
        mm_nan_second_arg_returns_first_impl(55);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000056() {
        mm_nan_second_arg_returns_first_impl(56);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000057() {
        mm_nan_second_arg_returns_first_impl(57);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000058() {
        mm_nan_second_arg_returns_first_impl(58);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000059() {
        mm_nan_second_arg_returns_first_impl(59);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000060() {
        mm_nan_second_arg_returns_first_impl(60);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000061() {
        mm_nan_second_arg_returns_first_impl(61);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000062() {
        mm_nan_second_arg_returns_first_impl(62);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000063() {
        mm_nan_second_arg_returns_first_impl(63);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000064() {
        mm_nan_second_arg_returns_first_impl(64);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000065() {
        mm_nan_second_arg_returns_first_impl(65);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000066() {
        mm_nan_second_arg_returns_first_impl(66);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000067() {
        mm_nan_second_arg_returns_first_impl(67);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000068() {
        mm_nan_second_arg_returns_first_impl(68);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000069() {
        mm_nan_second_arg_returns_first_impl(69);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000070() {
        mm_nan_second_arg_returns_first_impl(70);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000071() {
        mm_nan_second_arg_returns_first_impl(71);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000072() {
        mm_nan_second_arg_returns_first_impl(72);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000073() {
        mm_nan_second_arg_returns_first_impl(73);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000074() {
        mm_nan_second_arg_returns_first_impl(74);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000075() {
        mm_nan_second_arg_returns_first_impl(75);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000076() {
        mm_nan_second_arg_returns_first_impl(76);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000077() {
        mm_nan_second_arg_returns_first_impl(77);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000078() {
        mm_nan_second_arg_returns_first_impl(78);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000079() {
        mm_nan_second_arg_returns_first_impl(79);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000080() {
        mm_nan_second_arg_returns_first_impl(80);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000081() {
        mm_nan_second_arg_returns_first_impl(81);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000082() {
        mm_nan_second_arg_returns_first_impl(82);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000083() {
        mm_nan_second_arg_returns_first_impl(83);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000084() {
        mm_nan_second_arg_returns_first_impl(84);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000085() {
        mm_nan_second_arg_returns_first_impl(85);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000086() {
        mm_nan_second_arg_returns_first_impl(86);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000087() {
        mm_nan_second_arg_returns_first_impl(87);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000088() {
        mm_nan_second_arg_returns_first_impl(88);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000089() {
        mm_nan_second_arg_returns_first_impl(89);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000090() {
        mm_nan_second_arg_returns_first_impl(90);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000091() {
        mm_nan_second_arg_returns_first_impl(91);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000092() {
        mm_nan_second_arg_returns_first_impl(92);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000093() {
        mm_nan_second_arg_returns_first_impl(93);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000094() {
        mm_nan_second_arg_returns_first_impl(94);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000095() {
        mm_nan_second_arg_returns_first_impl(95);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000096() {
        mm_nan_second_arg_returns_first_impl(96);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000097() {
        mm_nan_second_arg_returns_first_impl(97);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000098() {
        mm_nan_second_arg_returns_first_impl(98);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000099() {
        mm_nan_second_arg_returns_first_impl(99);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000100() {
        mm_nan_second_arg_returns_first_impl(100);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000101() {
        mm_nan_second_arg_returns_first_impl(101);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000102() {
        mm_nan_second_arg_returns_first_impl(102);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000103() {
        mm_nan_second_arg_returns_first_impl(103);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000104() {
        mm_nan_second_arg_returns_first_impl(104);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000105() {
        mm_nan_second_arg_returns_first_impl(105);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000106() {
        mm_nan_second_arg_returns_first_impl(106);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000107() {
        mm_nan_second_arg_returns_first_impl(107);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000108() {
        mm_nan_second_arg_returns_first_impl(108);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000109() {
        mm_nan_second_arg_returns_first_impl(109);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000110() {
        mm_nan_second_arg_returns_first_impl(110);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000111() {
        mm_nan_second_arg_returns_first_impl(111);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000112() {
        mm_nan_second_arg_returns_first_impl(112);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000113() {
        mm_nan_second_arg_returns_first_impl(113);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000114() {
        mm_nan_second_arg_returns_first_impl(114);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000115() {
        mm_nan_second_arg_returns_first_impl(115);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000116() {
        mm_nan_second_arg_returns_first_impl(116);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000117() {
        mm_nan_second_arg_returns_first_impl(117);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000118() {
        mm_nan_second_arg_returns_first_impl(118);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000119() {
        mm_nan_second_arg_returns_first_impl(119);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000120() {
        mm_nan_second_arg_returns_first_impl(120);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000121() {
        mm_nan_second_arg_returns_first_impl(121);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000122() {
        mm_nan_second_arg_returns_first_impl(122);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000123() {
        mm_nan_second_arg_returns_first_impl(123);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000124() {
        mm_nan_second_arg_returns_first_impl(124);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000125() {
        mm_nan_second_arg_returns_first_impl(125);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000126() {
        mm_nan_second_arg_returns_first_impl(126);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000127() {
        mm_nan_second_arg_returns_first_impl(127);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000128() {
        mm_nan_second_arg_returns_first_impl(128);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000129() {
        mm_nan_second_arg_returns_first_impl(129);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000130() {
        mm_nan_second_arg_returns_first_impl(130);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000131() {
        mm_nan_second_arg_returns_first_impl(131);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000132() {
        mm_nan_second_arg_returns_first_impl(132);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000133() {
        mm_nan_second_arg_returns_first_impl(133);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000134() {
        mm_nan_second_arg_returns_first_impl(134);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000135() {
        mm_nan_second_arg_returns_first_impl(135);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000136() {
        mm_nan_second_arg_returns_first_impl(136);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000137() {
        mm_nan_second_arg_returns_first_impl(137);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000138() {
        mm_nan_second_arg_returns_first_impl(138);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000139() {
        mm_nan_second_arg_returns_first_impl(139);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000140() {
        mm_nan_second_arg_returns_first_impl(140);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000141() {
        mm_nan_second_arg_returns_first_impl(141);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000142() {
        mm_nan_second_arg_returns_first_impl(142);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000143() {
        mm_nan_second_arg_returns_first_impl(143);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000144() {
        mm_nan_second_arg_returns_first_impl(144);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000145() {
        mm_nan_second_arg_returns_first_impl(145);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000146() {
        mm_nan_second_arg_returns_first_impl(146);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000147() {
        mm_nan_second_arg_returns_first_impl(147);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000148() {
        mm_nan_second_arg_returns_first_impl(148);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_second_seed_000149() {
        mm_nan_second_arg_returns_first_impl(149);
    }
    // --- mm_nan_first: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000000() {
        mm_nan_first_arg_propagates_impl(0);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000001() {
        mm_nan_first_arg_propagates_impl(1);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000002() {
        mm_nan_first_arg_propagates_impl(2);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000003() {
        mm_nan_first_arg_propagates_impl(3);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000004() {
        mm_nan_first_arg_propagates_impl(4);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000005() {
        mm_nan_first_arg_propagates_impl(5);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000006() {
        mm_nan_first_arg_propagates_impl(6);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000007() {
        mm_nan_first_arg_propagates_impl(7);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000008() {
        mm_nan_first_arg_propagates_impl(8);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000009() {
        mm_nan_first_arg_propagates_impl(9);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000010() {
        mm_nan_first_arg_propagates_impl(10);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000011() {
        mm_nan_first_arg_propagates_impl(11);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000012() {
        mm_nan_first_arg_propagates_impl(12);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000013() {
        mm_nan_first_arg_propagates_impl(13);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000014() {
        mm_nan_first_arg_propagates_impl(14);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000015() {
        mm_nan_first_arg_propagates_impl(15);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000016() {
        mm_nan_first_arg_propagates_impl(16);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000017() {
        mm_nan_first_arg_propagates_impl(17);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000018() {
        mm_nan_first_arg_propagates_impl(18);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000019() {
        mm_nan_first_arg_propagates_impl(19);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000020() {
        mm_nan_first_arg_propagates_impl(20);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000021() {
        mm_nan_first_arg_propagates_impl(21);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000022() {
        mm_nan_first_arg_propagates_impl(22);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000023() {
        mm_nan_first_arg_propagates_impl(23);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000024() {
        mm_nan_first_arg_propagates_impl(24);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000025() {
        mm_nan_first_arg_propagates_impl(25);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000026() {
        mm_nan_first_arg_propagates_impl(26);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000027() {
        mm_nan_first_arg_propagates_impl(27);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000028() {
        mm_nan_first_arg_propagates_impl(28);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000029() {
        mm_nan_first_arg_propagates_impl(29);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000030() {
        mm_nan_first_arg_propagates_impl(30);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000031() {
        mm_nan_first_arg_propagates_impl(31);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000032() {
        mm_nan_first_arg_propagates_impl(32);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000033() {
        mm_nan_first_arg_propagates_impl(33);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000034() {
        mm_nan_first_arg_propagates_impl(34);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000035() {
        mm_nan_first_arg_propagates_impl(35);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000036() {
        mm_nan_first_arg_propagates_impl(36);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000037() {
        mm_nan_first_arg_propagates_impl(37);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000038() {
        mm_nan_first_arg_propagates_impl(38);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000039() {
        mm_nan_first_arg_propagates_impl(39);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000040() {
        mm_nan_first_arg_propagates_impl(40);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000041() {
        mm_nan_first_arg_propagates_impl(41);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000042() {
        mm_nan_first_arg_propagates_impl(42);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000043() {
        mm_nan_first_arg_propagates_impl(43);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000044() {
        mm_nan_first_arg_propagates_impl(44);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000045() {
        mm_nan_first_arg_propagates_impl(45);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000046() {
        mm_nan_first_arg_propagates_impl(46);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000047() {
        mm_nan_first_arg_propagates_impl(47);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000048() {
        mm_nan_first_arg_propagates_impl(48);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000049() {
        mm_nan_first_arg_propagates_impl(49);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000050() {
        mm_nan_first_arg_propagates_impl(50);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000051() {
        mm_nan_first_arg_propagates_impl(51);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000052() {
        mm_nan_first_arg_propagates_impl(52);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000053() {
        mm_nan_first_arg_propagates_impl(53);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000054() {
        mm_nan_first_arg_propagates_impl(54);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000055() {
        mm_nan_first_arg_propagates_impl(55);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000056() {
        mm_nan_first_arg_propagates_impl(56);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000057() {
        mm_nan_first_arg_propagates_impl(57);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000058() {
        mm_nan_first_arg_propagates_impl(58);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000059() {
        mm_nan_first_arg_propagates_impl(59);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000060() {
        mm_nan_first_arg_propagates_impl(60);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000061() {
        mm_nan_first_arg_propagates_impl(61);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000062() {
        mm_nan_first_arg_propagates_impl(62);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000063() {
        mm_nan_first_arg_propagates_impl(63);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000064() {
        mm_nan_first_arg_propagates_impl(64);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000065() {
        mm_nan_first_arg_propagates_impl(65);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000066() {
        mm_nan_first_arg_propagates_impl(66);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000067() {
        mm_nan_first_arg_propagates_impl(67);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000068() {
        mm_nan_first_arg_propagates_impl(68);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000069() {
        mm_nan_first_arg_propagates_impl(69);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000070() {
        mm_nan_first_arg_propagates_impl(70);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000071() {
        mm_nan_first_arg_propagates_impl(71);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000072() {
        mm_nan_first_arg_propagates_impl(72);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000073() {
        mm_nan_first_arg_propagates_impl(73);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000074() {
        mm_nan_first_arg_propagates_impl(74);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000075() {
        mm_nan_first_arg_propagates_impl(75);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000076() {
        mm_nan_first_arg_propagates_impl(76);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000077() {
        mm_nan_first_arg_propagates_impl(77);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000078() {
        mm_nan_first_arg_propagates_impl(78);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000079() {
        mm_nan_first_arg_propagates_impl(79);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000080() {
        mm_nan_first_arg_propagates_impl(80);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000081() {
        mm_nan_first_arg_propagates_impl(81);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000082() {
        mm_nan_first_arg_propagates_impl(82);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000083() {
        mm_nan_first_arg_propagates_impl(83);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000084() {
        mm_nan_first_arg_propagates_impl(84);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000085() {
        mm_nan_first_arg_propagates_impl(85);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000086() {
        mm_nan_first_arg_propagates_impl(86);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000087() {
        mm_nan_first_arg_propagates_impl(87);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000088() {
        mm_nan_first_arg_propagates_impl(88);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000089() {
        mm_nan_first_arg_propagates_impl(89);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000090() {
        mm_nan_first_arg_propagates_impl(90);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000091() {
        mm_nan_first_arg_propagates_impl(91);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000092() {
        mm_nan_first_arg_propagates_impl(92);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000093() {
        mm_nan_first_arg_propagates_impl(93);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000094() {
        mm_nan_first_arg_propagates_impl(94);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000095() {
        mm_nan_first_arg_propagates_impl(95);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000096() {
        mm_nan_first_arg_propagates_impl(96);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000097() {
        mm_nan_first_arg_propagates_impl(97);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000098() {
        mm_nan_first_arg_propagates_impl(98);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000099() {
        mm_nan_first_arg_propagates_impl(99);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000100() {
        mm_nan_first_arg_propagates_impl(100);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000101() {
        mm_nan_first_arg_propagates_impl(101);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000102() {
        mm_nan_first_arg_propagates_impl(102);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000103() {
        mm_nan_first_arg_propagates_impl(103);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000104() {
        mm_nan_first_arg_propagates_impl(104);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000105() {
        mm_nan_first_arg_propagates_impl(105);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000106() {
        mm_nan_first_arg_propagates_impl(106);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000107() {
        mm_nan_first_arg_propagates_impl(107);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000108() {
        mm_nan_first_arg_propagates_impl(108);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000109() {
        mm_nan_first_arg_propagates_impl(109);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000110() {
        mm_nan_first_arg_propagates_impl(110);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000111() {
        mm_nan_first_arg_propagates_impl(111);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000112() {
        mm_nan_first_arg_propagates_impl(112);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000113() {
        mm_nan_first_arg_propagates_impl(113);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000114() {
        mm_nan_first_arg_propagates_impl(114);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000115() {
        mm_nan_first_arg_propagates_impl(115);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000116() {
        mm_nan_first_arg_propagates_impl(116);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000117() {
        mm_nan_first_arg_propagates_impl(117);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000118() {
        mm_nan_first_arg_propagates_impl(118);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000119() {
        mm_nan_first_arg_propagates_impl(119);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000120() {
        mm_nan_first_arg_propagates_impl(120);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000121() {
        mm_nan_first_arg_propagates_impl(121);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000122() {
        mm_nan_first_arg_propagates_impl(122);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000123() {
        mm_nan_first_arg_propagates_impl(123);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000124() {
        mm_nan_first_arg_propagates_impl(124);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000125() {
        mm_nan_first_arg_propagates_impl(125);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000126() {
        mm_nan_first_arg_propagates_impl(126);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000127() {
        mm_nan_first_arg_propagates_impl(127);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000128() {
        mm_nan_first_arg_propagates_impl(128);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000129() {
        mm_nan_first_arg_propagates_impl(129);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000130() {
        mm_nan_first_arg_propagates_impl(130);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000131() {
        mm_nan_first_arg_propagates_impl(131);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000132() {
        mm_nan_first_arg_propagates_impl(132);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000133() {
        mm_nan_first_arg_propagates_impl(133);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000134() {
        mm_nan_first_arg_propagates_impl(134);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000135() {
        mm_nan_first_arg_propagates_impl(135);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000136() {
        mm_nan_first_arg_propagates_impl(136);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000137() {
        mm_nan_first_arg_propagates_impl(137);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000138() {
        mm_nan_first_arg_propagates_impl(138);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000139() {
        mm_nan_first_arg_propagates_impl(139);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000140() {
        mm_nan_first_arg_propagates_impl(140);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000141() {
        mm_nan_first_arg_propagates_impl(141);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000142() {
        mm_nan_first_arg_propagates_impl(142);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000143() {
        mm_nan_first_arg_propagates_impl(143);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000144() {
        mm_nan_first_arg_propagates_impl(144);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000145() {
        mm_nan_first_arg_propagates_impl(145);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000146() {
        mm_nan_first_arg_propagates_impl(146);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000147() {
        mm_nan_first_arg_propagates_impl(147);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000148() {
        mm_nan_first_arg_propagates_impl(148);
    }
    #[cfg_attr(test, test)]
    fn mm_nan_first_seed_000149() {
        mm_nan_first_arg_propagates_impl(149);
    }
    // --- mm_signed_zero: 100 generated seeds ---
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000000() {
        mm_signed_zero_first_arg_wins_impl(0);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000001() {
        mm_signed_zero_first_arg_wins_impl(1);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000002() {
        mm_signed_zero_first_arg_wins_impl(2);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000003() {
        mm_signed_zero_first_arg_wins_impl(3);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000004() {
        mm_signed_zero_first_arg_wins_impl(4);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000005() {
        mm_signed_zero_first_arg_wins_impl(5);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000006() {
        mm_signed_zero_first_arg_wins_impl(6);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000007() {
        mm_signed_zero_first_arg_wins_impl(7);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000008() {
        mm_signed_zero_first_arg_wins_impl(8);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000009() {
        mm_signed_zero_first_arg_wins_impl(9);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000010() {
        mm_signed_zero_first_arg_wins_impl(10);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000011() {
        mm_signed_zero_first_arg_wins_impl(11);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000012() {
        mm_signed_zero_first_arg_wins_impl(12);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000013() {
        mm_signed_zero_first_arg_wins_impl(13);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000014() {
        mm_signed_zero_first_arg_wins_impl(14);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000015() {
        mm_signed_zero_first_arg_wins_impl(15);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000016() {
        mm_signed_zero_first_arg_wins_impl(16);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000017() {
        mm_signed_zero_first_arg_wins_impl(17);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000018() {
        mm_signed_zero_first_arg_wins_impl(18);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000019() {
        mm_signed_zero_first_arg_wins_impl(19);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000020() {
        mm_signed_zero_first_arg_wins_impl(20);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000021() {
        mm_signed_zero_first_arg_wins_impl(21);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000022() {
        mm_signed_zero_first_arg_wins_impl(22);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000023() {
        mm_signed_zero_first_arg_wins_impl(23);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000024() {
        mm_signed_zero_first_arg_wins_impl(24);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000025() {
        mm_signed_zero_first_arg_wins_impl(25);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000026() {
        mm_signed_zero_first_arg_wins_impl(26);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000027() {
        mm_signed_zero_first_arg_wins_impl(27);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000028() {
        mm_signed_zero_first_arg_wins_impl(28);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000029() {
        mm_signed_zero_first_arg_wins_impl(29);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000030() {
        mm_signed_zero_first_arg_wins_impl(30);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000031() {
        mm_signed_zero_first_arg_wins_impl(31);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000032() {
        mm_signed_zero_first_arg_wins_impl(32);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000033() {
        mm_signed_zero_first_arg_wins_impl(33);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000034() {
        mm_signed_zero_first_arg_wins_impl(34);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000035() {
        mm_signed_zero_first_arg_wins_impl(35);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000036() {
        mm_signed_zero_first_arg_wins_impl(36);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000037() {
        mm_signed_zero_first_arg_wins_impl(37);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000038() {
        mm_signed_zero_first_arg_wins_impl(38);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000039() {
        mm_signed_zero_first_arg_wins_impl(39);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000040() {
        mm_signed_zero_first_arg_wins_impl(40);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000041() {
        mm_signed_zero_first_arg_wins_impl(41);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000042() {
        mm_signed_zero_first_arg_wins_impl(42);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000043() {
        mm_signed_zero_first_arg_wins_impl(43);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000044() {
        mm_signed_zero_first_arg_wins_impl(44);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000045() {
        mm_signed_zero_first_arg_wins_impl(45);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000046() {
        mm_signed_zero_first_arg_wins_impl(46);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000047() {
        mm_signed_zero_first_arg_wins_impl(47);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000048() {
        mm_signed_zero_first_arg_wins_impl(48);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000049() {
        mm_signed_zero_first_arg_wins_impl(49);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000050() {
        mm_signed_zero_first_arg_wins_impl(50);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000051() {
        mm_signed_zero_first_arg_wins_impl(51);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000052() {
        mm_signed_zero_first_arg_wins_impl(52);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000053() {
        mm_signed_zero_first_arg_wins_impl(53);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000054() {
        mm_signed_zero_first_arg_wins_impl(54);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000055() {
        mm_signed_zero_first_arg_wins_impl(55);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000056() {
        mm_signed_zero_first_arg_wins_impl(56);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000057() {
        mm_signed_zero_first_arg_wins_impl(57);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000058() {
        mm_signed_zero_first_arg_wins_impl(58);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000059() {
        mm_signed_zero_first_arg_wins_impl(59);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000060() {
        mm_signed_zero_first_arg_wins_impl(60);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000061() {
        mm_signed_zero_first_arg_wins_impl(61);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000062() {
        mm_signed_zero_first_arg_wins_impl(62);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000063() {
        mm_signed_zero_first_arg_wins_impl(63);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000064() {
        mm_signed_zero_first_arg_wins_impl(64);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000065() {
        mm_signed_zero_first_arg_wins_impl(65);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000066() {
        mm_signed_zero_first_arg_wins_impl(66);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000067() {
        mm_signed_zero_first_arg_wins_impl(67);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000068() {
        mm_signed_zero_first_arg_wins_impl(68);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000069() {
        mm_signed_zero_first_arg_wins_impl(69);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000070() {
        mm_signed_zero_first_arg_wins_impl(70);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000071() {
        mm_signed_zero_first_arg_wins_impl(71);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000072() {
        mm_signed_zero_first_arg_wins_impl(72);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000073() {
        mm_signed_zero_first_arg_wins_impl(73);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000074() {
        mm_signed_zero_first_arg_wins_impl(74);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000075() {
        mm_signed_zero_first_arg_wins_impl(75);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000076() {
        mm_signed_zero_first_arg_wins_impl(76);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000077() {
        mm_signed_zero_first_arg_wins_impl(77);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000078() {
        mm_signed_zero_first_arg_wins_impl(78);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000079() {
        mm_signed_zero_first_arg_wins_impl(79);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000080() {
        mm_signed_zero_first_arg_wins_impl(80);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000081() {
        mm_signed_zero_first_arg_wins_impl(81);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000082() {
        mm_signed_zero_first_arg_wins_impl(82);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000083() {
        mm_signed_zero_first_arg_wins_impl(83);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000084() {
        mm_signed_zero_first_arg_wins_impl(84);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000085() {
        mm_signed_zero_first_arg_wins_impl(85);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000086() {
        mm_signed_zero_first_arg_wins_impl(86);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000087() {
        mm_signed_zero_first_arg_wins_impl(87);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000088() {
        mm_signed_zero_first_arg_wins_impl(88);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000089() {
        mm_signed_zero_first_arg_wins_impl(89);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000090() {
        mm_signed_zero_first_arg_wins_impl(90);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000091() {
        mm_signed_zero_first_arg_wins_impl(91);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000092() {
        mm_signed_zero_first_arg_wins_impl(92);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000093() {
        mm_signed_zero_first_arg_wins_impl(93);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000094() {
        mm_signed_zero_first_arg_wins_impl(94);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000095() {
        mm_signed_zero_first_arg_wins_impl(95);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000096() {
        mm_signed_zero_first_arg_wins_impl(96);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000097() {
        mm_signed_zero_first_arg_wins_impl(97);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000098() {
        mm_signed_zero_first_arg_wins_impl(98);
    }
    #[cfg_attr(test, test)]
    fn mm_signed_zero_seed_000099() {
        mm_signed_zero_first_arg_wins_impl(99);
    }
    // --- sm_scale_invariance: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000000() {
        sm_scale_invariance_pow2_impl(0);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000001() {
        sm_scale_invariance_pow2_impl(1);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000002() {
        sm_scale_invariance_pow2_impl(2);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000003() {
        sm_scale_invariance_pow2_impl(3);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000004() {
        sm_scale_invariance_pow2_impl(4);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000005() {
        sm_scale_invariance_pow2_impl(5);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000006() {
        sm_scale_invariance_pow2_impl(6);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000007() {
        sm_scale_invariance_pow2_impl(7);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000008() {
        sm_scale_invariance_pow2_impl(8);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000009() {
        sm_scale_invariance_pow2_impl(9);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000010() {
        sm_scale_invariance_pow2_impl(10);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000011() {
        sm_scale_invariance_pow2_impl(11);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000012() {
        sm_scale_invariance_pow2_impl(12);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000013() {
        sm_scale_invariance_pow2_impl(13);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000014() {
        sm_scale_invariance_pow2_impl(14);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000015() {
        sm_scale_invariance_pow2_impl(15);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000016() {
        sm_scale_invariance_pow2_impl(16);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000017() {
        sm_scale_invariance_pow2_impl(17);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000018() {
        sm_scale_invariance_pow2_impl(18);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000019() {
        sm_scale_invariance_pow2_impl(19);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000020() {
        sm_scale_invariance_pow2_impl(20);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000021() {
        sm_scale_invariance_pow2_impl(21);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000022() {
        sm_scale_invariance_pow2_impl(22);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000023() {
        sm_scale_invariance_pow2_impl(23);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000024() {
        sm_scale_invariance_pow2_impl(24);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000025() {
        sm_scale_invariance_pow2_impl(25);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000026() {
        sm_scale_invariance_pow2_impl(26);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000027() {
        sm_scale_invariance_pow2_impl(27);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000028() {
        sm_scale_invariance_pow2_impl(28);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000029() {
        sm_scale_invariance_pow2_impl(29);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000030() {
        sm_scale_invariance_pow2_impl(30);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000031() {
        sm_scale_invariance_pow2_impl(31);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000032() {
        sm_scale_invariance_pow2_impl(32);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000033() {
        sm_scale_invariance_pow2_impl(33);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000034() {
        sm_scale_invariance_pow2_impl(34);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000035() {
        sm_scale_invariance_pow2_impl(35);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000036() {
        sm_scale_invariance_pow2_impl(36);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000037() {
        sm_scale_invariance_pow2_impl(37);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000038() {
        sm_scale_invariance_pow2_impl(38);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000039() {
        sm_scale_invariance_pow2_impl(39);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000040() {
        sm_scale_invariance_pow2_impl(40);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000041() {
        sm_scale_invariance_pow2_impl(41);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000042() {
        sm_scale_invariance_pow2_impl(42);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000043() {
        sm_scale_invariance_pow2_impl(43);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000044() {
        sm_scale_invariance_pow2_impl(44);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000045() {
        sm_scale_invariance_pow2_impl(45);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000046() {
        sm_scale_invariance_pow2_impl(46);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000047() {
        sm_scale_invariance_pow2_impl(47);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000048() {
        sm_scale_invariance_pow2_impl(48);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000049() {
        sm_scale_invariance_pow2_impl(49);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000050() {
        sm_scale_invariance_pow2_impl(50);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000051() {
        sm_scale_invariance_pow2_impl(51);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000052() {
        sm_scale_invariance_pow2_impl(52);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000053() {
        sm_scale_invariance_pow2_impl(53);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000054() {
        sm_scale_invariance_pow2_impl(54);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000055() {
        sm_scale_invariance_pow2_impl(55);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000056() {
        sm_scale_invariance_pow2_impl(56);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000057() {
        sm_scale_invariance_pow2_impl(57);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000058() {
        sm_scale_invariance_pow2_impl(58);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000059() {
        sm_scale_invariance_pow2_impl(59);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000060() {
        sm_scale_invariance_pow2_impl(60);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000061() {
        sm_scale_invariance_pow2_impl(61);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000062() {
        sm_scale_invariance_pow2_impl(62);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000063() {
        sm_scale_invariance_pow2_impl(63);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000064() {
        sm_scale_invariance_pow2_impl(64);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000065() {
        sm_scale_invariance_pow2_impl(65);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000066() {
        sm_scale_invariance_pow2_impl(66);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000067() {
        sm_scale_invariance_pow2_impl(67);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000068() {
        sm_scale_invariance_pow2_impl(68);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000069() {
        sm_scale_invariance_pow2_impl(69);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000070() {
        sm_scale_invariance_pow2_impl(70);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000071() {
        sm_scale_invariance_pow2_impl(71);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000072() {
        sm_scale_invariance_pow2_impl(72);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000073() {
        sm_scale_invariance_pow2_impl(73);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000074() {
        sm_scale_invariance_pow2_impl(74);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000075() {
        sm_scale_invariance_pow2_impl(75);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000076() {
        sm_scale_invariance_pow2_impl(76);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000077() {
        sm_scale_invariance_pow2_impl(77);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000078() {
        sm_scale_invariance_pow2_impl(78);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000079() {
        sm_scale_invariance_pow2_impl(79);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000080() {
        sm_scale_invariance_pow2_impl(80);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000081() {
        sm_scale_invariance_pow2_impl(81);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000082() {
        sm_scale_invariance_pow2_impl(82);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000083() {
        sm_scale_invariance_pow2_impl(83);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000084() {
        sm_scale_invariance_pow2_impl(84);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000085() {
        sm_scale_invariance_pow2_impl(85);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000086() {
        sm_scale_invariance_pow2_impl(86);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000087() {
        sm_scale_invariance_pow2_impl(87);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000088() {
        sm_scale_invariance_pow2_impl(88);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000089() {
        sm_scale_invariance_pow2_impl(89);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000090() {
        sm_scale_invariance_pow2_impl(90);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000091() {
        sm_scale_invariance_pow2_impl(91);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000092() {
        sm_scale_invariance_pow2_impl(92);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000093() {
        sm_scale_invariance_pow2_impl(93);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000094() {
        sm_scale_invariance_pow2_impl(94);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000095() {
        sm_scale_invariance_pow2_impl(95);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000096() {
        sm_scale_invariance_pow2_impl(96);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000097() {
        sm_scale_invariance_pow2_impl(97);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000098() {
        sm_scale_invariance_pow2_impl(98);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000099() {
        sm_scale_invariance_pow2_impl(99);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000100() {
        sm_scale_invariance_pow2_impl(100);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000101() {
        sm_scale_invariance_pow2_impl(101);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000102() {
        sm_scale_invariance_pow2_impl(102);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000103() {
        sm_scale_invariance_pow2_impl(103);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000104() {
        sm_scale_invariance_pow2_impl(104);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000105() {
        sm_scale_invariance_pow2_impl(105);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000106() {
        sm_scale_invariance_pow2_impl(106);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000107() {
        sm_scale_invariance_pow2_impl(107);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000108() {
        sm_scale_invariance_pow2_impl(108);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000109() {
        sm_scale_invariance_pow2_impl(109);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000110() {
        sm_scale_invariance_pow2_impl(110);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000111() {
        sm_scale_invariance_pow2_impl(111);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000112() {
        sm_scale_invariance_pow2_impl(112);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000113() {
        sm_scale_invariance_pow2_impl(113);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000114() {
        sm_scale_invariance_pow2_impl(114);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000115() {
        sm_scale_invariance_pow2_impl(115);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000116() {
        sm_scale_invariance_pow2_impl(116);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000117() {
        sm_scale_invariance_pow2_impl(117);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000118() {
        sm_scale_invariance_pow2_impl(118);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000119() {
        sm_scale_invariance_pow2_impl(119);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000120() {
        sm_scale_invariance_pow2_impl(120);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000121() {
        sm_scale_invariance_pow2_impl(121);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000122() {
        sm_scale_invariance_pow2_impl(122);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000123() {
        sm_scale_invariance_pow2_impl(123);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000124() {
        sm_scale_invariance_pow2_impl(124);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000125() {
        sm_scale_invariance_pow2_impl(125);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000126() {
        sm_scale_invariance_pow2_impl(126);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000127() {
        sm_scale_invariance_pow2_impl(127);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000128() {
        sm_scale_invariance_pow2_impl(128);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000129() {
        sm_scale_invariance_pow2_impl(129);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000130() {
        sm_scale_invariance_pow2_impl(130);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000131() {
        sm_scale_invariance_pow2_impl(131);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000132() {
        sm_scale_invariance_pow2_impl(132);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000133() {
        sm_scale_invariance_pow2_impl(133);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000134() {
        sm_scale_invariance_pow2_impl(134);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000135() {
        sm_scale_invariance_pow2_impl(135);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000136() {
        sm_scale_invariance_pow2_impl(136);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000137() {
        sm_scale_invariance_pow2_impl(137);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000138() {
        sm_scale_invariance_pow2_impl(138);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000139() {
        sm_scale_invariance_pow2_impl(139);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000140() {
        sm_scale_invariance_pow2_impl(140);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000141() {
        sm_scale_invariance_pow2_impl(141);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000142() {
        sm_scale_invariance_pow2_impl(142);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000143() {
        sm_scale_invariance_pow2_impl(143);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000144() {
        sm_scale_invariance_pow2_impl(144);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000145() {
        sm_scale_invariance_pow2_impl(145);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000146() {
        sm_scale_invariance_pow2_impl(146);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000147() {
        sm_scale_invariance_pow2_impl(147);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000148() {
        sm_scale_invariance_pow2_impl(148);
    }
    #[cfg_attr(test, test)]
    fn sm_scale_invariance_seed_000149() {
        sm_scale_invariance_pow2_impl(149);
    }
    // --- sm_negation_invariance: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000000() {
        sm_negation_invariance_impl(0);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000001() {
        sm_negation_invariance_impl(1);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000002() {
        sm_negation_invariance_impl(2);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000003() {
        sm_negation_invariance_impl(3);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000004() {
        sm_negation_invariance_impl(4);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000005() {
        sm_negation_invariance_impl(5);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000006() {
        sm_negation_invariance_impl(6);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000007() {
        sm_negation_invariance_impl(7);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000008() {
        sm_negation_invariance_impl(8);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000009() {
        sm_negation_invariance_impl(9);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000010() {
        sm_negation_invariance_impl(10);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000011() {
        sm_negation_invariance_impl(11);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000012() {
        sm_negation_invariance_impl(12);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000013() {
        sm_negation_invariance_impl(13);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000014() {
        sm_negation_invariance_impl(14);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000015() {
        sm_negation_invariance_impl(15);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000016() {
        sm_negation_invariance_impl(16);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000017() {
        sm_negation_invariance_impl(17);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000018() {
        sm_negation_invariance_impl(18);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000019() {
        sm_negation_invariance_impl(19);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000020() {
        sm_negation_invariance_impl(20);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000021() {
        sm_negation_invariance_impl(21);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000022() {
        sm_negation_invariance_impl(22);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000023() {
        sm_negation_invariance_impl(23);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000024() {
        sm_negation_invariance_impl(24);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000025() {
        sm_negation_invariance_impl(25);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000026() {
        sm_negation_invariance_impl(26);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000027() {
        sm_negation_invariance_impl(27);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000028() {
        sm_negation_invariance_impl(28);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000029() {
        sm_negation_invariance_impl(29);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000030() {
        sm_negation_invariance_impl(30);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000031() {
        sm_negation_invariance_impl(31);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000032() {
        sm_negation_invariance_impl(32);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000033() {
        sm_negation_invariance_impl(33);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000034() {
        sm_negation_invariance_impl(34);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000035() {
        sm_negation_invariance_impl(35);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000036() {
        sm_negation_invariance_impl(36);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000037() {
        sm_negation_invariance_impl(37);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000038() {
        sm_negation_invariance_impl(38);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000039() {
        sm_negation_invariance_impl(39);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000040() {
        sm_negation_invariance_impl(40);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000041() {
        sm_negation_invariance_impl(41);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000042() {
        sm_negation_invariance_impl(42);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000043() {
        sm_negation_invariance_impl(43);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000044() {
        sm_negation_invariance_impl(44);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000045() {
        sm_negation_invariance_impl(45);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000046() {
        sm_negation_invariance_impl(46);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000047() {
        sm_negation_invariance_impl(47);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000048() {
        sm_negation_invariance_impl(48);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000049() {
        sm_negation_invariance_impl(49);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000050() {
        sm_negation_invariance_impl(50);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000051() {
        sm_negation_invariance_impl(51);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000052() {
        sm_negation_invariance_impl(52);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000053() {
        sm_negation_invariance_impl(53);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000054() {
        sm_negation_invariance_impl(54);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000055() {
        sm_negation_invariance_impl(55);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000056() {
        sm_negation_invariance_impl(56);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000057() {
        sm_negation_invariance_impl(57);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000058() {
        sm_negation_invariance_impl(58);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000059() {
        sm_negation_invariance_impl(59);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000060() {
        sm_negation_invariance_impl(60);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000061() {
        sm_negation_invariance_impl(61);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000062() {
        sm_negation_invariance_impl(62);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000063() {
        sm_negation_invariance_impl(63);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000064() {
        sm_negation_invariance_impl(64);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000065() {
        sm_negation_invariance_impl(65);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000066() {
        sm_negation_invariance_impl(66);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000067() {
        sm_negation_invariance_impl(67);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000068() {
        sm_negation_invariance_impl(68);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000069() {
        sm_negation_invariance_impl(69);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000070() {
        sm_negation_invariance_impl(70);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000071() {
        sm_negation_invariance_impl(71);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000072() {
        sm_negation_invariance_impl(72);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000073() {
        sm_negation_invariance_impl(73);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000074() {
        sm_negation_invariance_impl(74);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000075() {
        sm_negation_invariance_impl(75);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000076() {
        sm_negation_invariance_impl(76);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000077() {
        sm_negation_invariance_impl(77);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000078() {
        sm_negation_invariance_impl(78);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000079() {
        sm_negation_invariance_impl(79);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000080() {
        sm_negation_invariance_impl(80);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000081() {
        sm_negation_invariance_impl(81);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000082() {
        sm_negation_invariance_impl(82);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000083() {
        sm_negation_invariance_impl(83);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000084() {
        sm_negation_invariance_impl(84);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000085() {
        sm_negation_invariance_impl(85);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000086() {
        sm_negation_invariance_impl(86);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000087() {
        sm_negation_invariance_impl(87);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000088() {
        sm_negation_invariance_impl(88);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000089() {
        sm_negation_invariance_impl(89);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000090() {
        sm_negation_invariance_impl(90);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000091() {
        sm_negation_invariance_impl(91);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000092() {
        sm_negation_invariance_impl(92);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000093() {
        sm_negation_invariance_impl(93);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000094() {
        sm_negation_invariance_impl(94);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000095() {
        sm_negation_invariance_impl(95);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000096() {
        sm_negation_invariance_impl(96);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000097() {
        sm_negation_invariance_impl(97);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000098() {
        sm_negation_invariance_impl(98);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000099() {
        sm_negation_invariance_impl(99);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000100() {
        sm_negation_invariance_impl(100);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000101() {
        sm_negation_invariance_impl(101);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000102() {
        sm_negation_invariance_impl(102);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000103() {
        sm_negation_invariance_impl(103);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000104() {
        sm_negation_invariance_impl(104);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000105() {
        sm_negation_invariance_impl(105);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000106() {
        sm_negation_invariance_impl(106);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000107() {
        sm_negation_invariance_impl(107);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000108() {
        sm_negation_invariance_impl(108);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000109() {
        sm_negation_invariance_impl(109);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000110() {
        sm_negation_invariance_impl(110);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000111() {
        sm_negation_invariance_impl(111);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000112() {
        sm_negation_invariance_impl(112);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000113() {
        sm_negation_invariance_impl(113);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000114() {
        sm_negation_invariance_impl(114);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000115() {
        sm_negation_invariance_impl(115);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000116() {
        sm_negation_invariance_impl(116);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000117() {
        sm_negation_invariance_impl(117);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000118() {
        sm_negation_invariance_impl(118);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000119() {
        sm_negation_invariance_impl(119);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000120() {
        sm_negation_invariance_impl(120);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000121() {
        sm_negation_invariance_impl(121);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000122() {
        sm_negation_invariance_impl(122);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000123() {
        sm_negation_invariance_impl(123);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000124() {
        sm_negation_invariance_impl(124);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000125() {
        sm_negation_invariance_impl(125);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000126() {
        sm_negation_invariance_impl(126);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000127() {
        sm_negation_invariance_impl(127);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000128() {
        sm_negation_invariance_impl(128);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000129() {
        sm_negation_invariance_impl(129);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000130() {
        sm_negation_invariance_impl(130);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000131() {
        sm_negation_invariance_impl(131);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000132() {
        sm_negation_invariance_impl(132);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000133() {
        sm_negation_invariance_impl(133);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000134() {
        sm_negation_invariance_impl(134);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000135() {
        sm_negation_invariance_impl(135);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000136() {
        sm_negation_invariance_impl(136);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000137() {
        sm_negation_invariance_impl(137);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000138() {
        sm_negation_invariance_impl(138);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000139() {
        sm_negation_invariance_impl(139);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000140() {
        sm_negation_invariance_impl(140);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000141() {
        sm_negation_invariance_impl(141);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000142() {
        sm_negation_invariance_impl(142);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000143() {
        sm_negation_invariance_impl(143);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000144() {
        sm_negation_invariance_impl(144);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000145() {
        sm_negation_invariance_impl(145);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000146() {
        sm_negation_invariance_impl(146);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000147() {
        sm_negation_invariance_impl(147);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000148() {
        sm_negation_invariance_impl(148);
    }
    #[cfg_attr(test, test)]
    fn sm_negation_invariance_seed_000149() {
        sm_negation_invariance_impl(149);
    }
    // --- sm_bounded_agreement: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000000() {
        sm_bounded_agreement_with_naive_impl(0);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000001() {
        sm_bounded_agreement_with_naive_impl(1);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000002() {
        sm_bounded_agreement_with_naive_impl(2);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000003() {
        sm_bounded_agreement_with_naive_impl(3);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000004() {
        sm_bounded_agreement_with_naive_impl(4);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000005() {
        sm_bounded_agreement_with_naive_impl(5);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000006() {
        sm_bounded_agreement_with_naive_impl(6);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000007() {
        sm_bounded_agreement_with_naive_impl(7);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000008() {
        sm_bounded_agreement_with_naive_impl(8);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000009() {
        sm_bounded_agreement_with_naive_impl(9);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000010() {
        sm_bounded_agreement_with_naive_impl(10);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000011() {
        sm_bounded_agreement_with_naive_impl(11);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000012() {
        sm_bounded_agreement_with_naive_impl(12);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000013() {
        sm_bounded_agreement_with_naive_impl(13);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000014() {
        sm_bounded_agreement_with_naive_impl(14);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000015() {
        sm_bounded_agreement_with_naive_impl(15);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000016() {
        sm_bounded_agreement_with_naive_impl(16);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000017() {
        sm_bounded_agreement_with_naive_impl(17);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000018() {
        sm_bounded_agreement_with_naive_impl(18);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000019() {
        sm_bounded_agreement_with_naive_impl(19);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000020() {
        sm_bounded_agreement_with_naive_impl(20);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000021() {
        sm_bounded_agreement_with_naive_impl(21);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000022() {
        sm_bounded_agreement_with_naive_impl(22);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000023() {
        sm_bounded_agreement_with_naive_impl(23);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000024() {
        sm_bounded_agreement_with_naive_impl(24);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000025() {
        sm_bounded_agreement_with_naive_impl(25);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000026() {
        sm_bounded_agreement_with_naive_impl(26);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000027() {
        sm_bounded_agreement_with_naive_impl(27);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000028() {
        sm_bounded_agreement_with_naive_impl(28);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000029() {
        sm_bounded_agreement_with_naive_impl(29);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000030() {
        sm_bounded_agreement_with_naive_impl(30);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000031() {
        sm_bounded_agreement_with_naive_impl(31);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000032() {
        sm_bounded_agreement_with_naive_impl(32);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000033() {
        sm_bounded_agreement_with_naive_impl(33);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000034() {
        sm_bounded_agreement_with_naive_impl(34);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000035() {
        sm_bounded_agreement_with_naive_impl(35);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000036() {
        sm_bounded_agreement_with_naive_impl(36);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000037() {
        sm_bounded_agreement_with_naive_impl(37);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000038() {
        sm_bounded_agreement_with_naive_impl(38);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000039() {
        sm_bounded_agreement_with_naive_impl(39);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000040() {
        sm_bounded_agreement_with_naive_impl(40);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000041() {
        sm_bounded_agreement_with_naive_impl(41);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000042() {
        sm_bounded_agreement_with_naive_impl(42);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000043() {
        sm_bounded_agreement_with_naive_impl(43);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000044() {
        sm_bounded_agreement_with_naive_impl(44);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000045() {
        sm_bounded_agreement_with_naive_impl(45);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000046() {
        sm_bounded_agreement_with_naive_impl(46);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000047() {
        sm_bounded_agreement_with_naive_impl(47);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000048() {
        sm_bounded_agreement_with_naive_impl(48);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000049() {
        sm_bounded_agreement_with_naive_impl(49);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000050() {
        sm_bounded_agreement_with_naive_impl(50);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000051() {
        sm_bounded_agreement_with_naive_impl(51);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000052() {
        sm_bounded_agreement_with_naive_impl(52);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000053() {
        sm_bounded_agreement_with_naive_impl(53);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000054() {
        sm_bounded_agreement_with_naive_impl(54);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000055() {
        sm_bounded_agreement_with_naive_impl(55);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000056() {
        sm_bounded_agreement_with_naive_impl(56);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000057() {
        sm_bounded_agreement_with_naive_impl(57);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000058() {
        sm_bounded_agreement_with_naive_impl(58);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000059() {
        sm_bounded_agreement_with_naive_impl(59);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000060() {
        sm_bounded_agreement_with_naive_impl(60);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000061() {
        sm_bounded_agreement_with_naive_impl(61);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000062() {
        sm_bounded_agreement_with_naive_impl(62);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000063() {
        sm_bounded_agreement_with_naive_impl(63);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000064() {
        sm_bounded_agreement_with_naive_impl(64);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000065() {
        sm_bounded_agreement_with_naive_impl(65);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000066() {
        sm_bounded_agreement_with_naive_impl(66);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000067() {
        sm_bounded_agreement_with_naive_impl(67);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000068() {
        sm_bounded_agreement_with_naive_impl(68);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000069() {
        sm_bounded_agreement_with_naive_impl(69);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000070() {
        sm_bounded_agreement_with_naive_impl(70);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000071() {
        sm_bounded_agreement_with_naive_impl(71);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000072() {
        sm_bounded_agreement_with_naive_impl(72);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000073() {
        sm_bounded_agreement_with_naive_impl(73);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000074() {
        sm_bounded_agreement_with_naive_impl(74);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000075() {
        sm_bounded_agreement_with_naive_impl(75);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000076() {
        sm_bounded_agreement_with_naive_impl(76);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000077() {
        sm_bounded_agreement_with_naive_impl(77);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000078() {
        sm_bounded_agreement_with_naive_impl(78);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000079() {
        sm_bounded_agreement_with_naive_impl(79);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000080() {
        sm_bounded_agreement_with_naive_impl(80);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000081() {
        sm_bounded_agreement_with_naive_impl(81);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000082() {
        sm_bounded_agreement_with_naive_impl(82);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000083() {
        sm_bounded_agreement_with_naive_impl(83);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000084() {
        sm_bounded_agreement_with_naive_impl(84);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000085() {
        sm_bounded_agreement_with_naive_impl(85);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000086() {
        sm_bounded_agreement_with_naive_impl(86);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000087() {
        sm_bounded_agreement_with_naive_impl(87);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000088() {
        sm_bounded_agreement_with_naive_impl(88);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000089() {
        sm_bounded_agreement_with_naive_impl(89);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000090() {
        sm_bounded_agreement_with_naive_impl(90);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000091() {
        sm_bounded_agreement_with_naive_impl(91);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000092() {
        sm_bounded_agreement_with_naive_impl(92);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000093() {
        sm_bounded_agreement_with_naive_impl(93);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000094() {
        sm_bounded_agreement_with_naive_impl(94);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000095() {
        sm_bounded_agreement_with_naive_impl(95);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000096() {
        sm_bounded_agreement_with_naive_impl(96);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000097() {
        sm_bounded_agreement_with_naive_impl(97);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000098() {
        sm_bounded_agreement_with_naive_impl(98);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000099() {
        sm_bounded_agreement_with_naive_impl(99);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000100() {
        sm_bounded_agreement_with_naive_impl(100);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000101() {
        sm_bounded_agreement_with_naive_impl(101);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000102() {
        sm_bounded_agreement_with_naive_impl(102);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000103() {
        sm_bounded_agreement_with_naive_impl(103);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000104() {
        sm_bounded_agreement_with_naive_impl(104);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000105() {
        sm_bounded_agreement_with_naive_impl(105);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000106() {
        sm_bounded_agreement_with_naive_impl(106);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000107() {
        sm_bounded_agreement_with_naive_impl(107);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000108() {
        sm_bounded_agreement_with_naive_impl(108);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000109() {
        sm_bounded_agreement_with_naive_impl(109);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000110() {
        sm_bounded_agreement_with_naive_impl(110);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000111() {
        sm_bounded_agreement_with_naive_impl(111);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000112() {
        sm_bounded_agreement_with_naive_impl(112);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000113() {
        sm_bounded_agreement_with_naive_impl(113);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000114() {
        sm_bounded_agreement_with_naive_impl(114);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000115() {
        sm_bounded_agreement_with_naive_impl(115);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000116() {
        sm_bounded_agreement_with_naive_impl(116);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000117() {
        sm_bounded_agreement_with_naive_impl(117);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000118() {
        sm_bounded_agreement_with_naive_impl(118);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000119() {
        sm_bounded_agreement_with_naive_impl(119);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000120() {
        sm_bounded_agreement_with_naive_impl(120);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000121() {
        sm_bounded_agreement_with_naive_impl(121);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000122() {
        sm_bounded_agreement_with_naive_impl(122);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000123() {
        sm_bounded_agreement_with_naive_impl(123);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000124() {
        sm_bounded_agreement_with_naive_impl(124);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000125() {
        sm_bounded_agreement_with_naive_impl(125);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000126() {
        sm_bounded_agreement_with_naive_impl(126);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000127() {
        sm_bounded_agreement_with_naive_impl(127);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000128() {
        sm_bounded_agreement_with_naive_impl(128);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000129() {
        sm_bounded_agreement_with_naive_impl(129);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000130() {
        sm_bounded_agreement_with_naive_impl(130);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000131() {
        sm_bounded_agreement_with_naive_impl(131);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000132() {
        sm_bounded_agreement_with_naive_impl(132);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000133() {
        sm_bounded_agreement_with_naive_impl(133);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000134() {
        sm_bounded_agreement_with_naive_impl(134);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000135() {
        sm_bounded_agreement_with_naive_impl(135);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000136() {
        sm_bounded_agreement_with_naive_impl(136);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000137() {
        sm_bounded_agreement_with_naive_impl(137);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000138() {
        sm_bounded_agreement_with_naive_impl(138);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000139() {
        sm_bounded_agreement_with_naive_impl(139);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000140() {
        sm_bounded_agreement_with_naive_impl(140);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000141() {
        sm_bounded_agreement_with_naive_impl(141);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000142() {
        sm_bounded_agreement_with_naive_impl(142);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000143() {
        sm_bounded_agreement_with_naive_impl(143);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000144() {
        sm_bounded_agreement_with_naive_impl(144);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000145() {
        sm_bounded_agreement_with_naive_impl(145);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000146() {
        sm_bounded_agreement_with_naive_impl(146);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000147() {
        sm_bounded_agreement_with_naive_impl(147);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000148() {
        sm_bounded_agreement_with_naive_impl(148);
    }
    #[cfg_attr(test, test)]
    fn sm_bounded_agreement_seed_000149() {
        sm_bounded_agreement_with_naive_impl(149);
    }
    // --- sm_reversal_invariant: 100 generated seeds ---
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000000() {
        sm_reversal_invariant_small_n_impl(0);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000001() {
        sm_reversal_invariant_small_n_impl(1);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000002() {
        sm_reversal_invariant_small_n_impl(2);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000003() {
        sm_reversal_invariant_small_n_impl(3);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000004() {
        sm_reversal_invariant_small_n_impl(4);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000005() {
        sm_reversal_invariant_small_n_impl(5);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000006() {
        sm_reversal_invariant_small_n_impl(6);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000007() {
        sm_reversal_invariant_small_n_impl(7);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000008() {
        sm_reversal_invariant_small_n_impl(8);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000009() {
        sm_reversal_invariant_small_n_impl(9);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000010() {
        sm_reversal_invariant_small_n_impl(10);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000011() {
        sm_reversal_invariant_small_n_impl(11);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000012() {
        sm_reversal_invariant_small_n_impl(12);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000013() {
        sm_reversal_invariant_small_n_impl(13);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000014() {
        sm_reversal_invariant_small_n_impl(14);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000015() {
        sm_reversal_invariant_small_n_impl(15);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000016() {
        sm_reversal_invariant_small_n_impl(16);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000017() {
        sm_reversal_invariant_small_n_impl(17);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000018() {
        sm_reversal_invariant_small_n_impl(18);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000019() {
        sm_reversal_invariant_small_n_impl(19);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000020() {
        sm_reversal_invariant_small_n_impl(20);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000021() {
        sm_reversal_invariant_small_n_impl(21);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000022() {
        sm_reversal_invariant_small_n_impl(22);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000023() {
        sm_reversal_invariant_small_n_impl(23);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000024() {
        sm_reversal_invariant_small_n_impl(24);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000025() {
        sm_reversal_invariant_small_n_impl(25);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000026() {
        sm_reversal_invariant_small_n_impl(26);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000027() {
        sm_reversal_invariant_small_n_impl(27);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000028() {
        sm_reversal_invariant_small_n_impl(28);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000029() {
        sm_reversal_invariant_small_n_impl(29);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000030() {
        sm_reversal_invariant_small_n_impl(30);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000031() {
        sm_reversal_invariant_small_n_impl(31);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000032() {
        sm_reversal_invariant_small_n_impl(32);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000033() {
        sm_reversal_invariant_small_n_impl(33);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000034() {
        sm_reversal_invariant_small_n_impl(34);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000035() {
        sm_reversal_invariant_small_n_impl(35);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000036() {
        sm_reversal_invariant_small_n_impl(36);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000037() {
        sm_reversal_invariant_small_n_impl(37);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000038() {
        sm_reversal_invariant_small_n_impl(38);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000039() {
        sm_reversal_invariant_small_n_impl(39);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000040() {
        sm_reversal_invariant_small_n_impl(40);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000041() {
        sm_reversal_invariant_small_n_impl(41);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000042() {
        sm_reversal_invariant_small_n_impl(42);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000043() {
        sm_reversal_invariant_small_n_impl(43);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000044() {
        sm_reversal_invariant_small_n_impl(44);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000045() {
        sm_reversal_invariant_small_n_impl(45);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000046() {
        sm_reversal_invariant_small_n_impl(46);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000047() {
        sm_reversal_invariant_small_n_impl(47);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000048() {
        sm_reversal_invariant_small_n_impl(48);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000049() {
        sm_reversal_invariant_small_n_impl(49);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000050() {
        sm_reversal_invariant_small_n_impl(50);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000051() {
        sm_reversal_invariant_small_n_impl(51);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000052() {
        sm_reversal_invariant_small_n_impl(52);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000053() {
        sm_reversal_invariant_small_n_impl(53);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000054() {
        sm_reversal_invariant_small_n_impl(54);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000055() {
        sm_reversal_invariant_small_n_impl(55);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000056() {
        sm_reversal_invariant_small_n_impl(56);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000057() {
        sm_reversal_invariant_small_n_impl(57);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000058() {
        sm_reversal_invariant_small_n_impl(58);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000059() {
        sm_reversal_invariant_small_n_impl(59);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000060() {
        sm_reversal_invariant_small_n_impl(60);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000061() {
        sm_reversal_invariant_small_n_impl(61);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000062() {
        sm_reversal_invariant_small_n_impl(62);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000063() {
        sm_reversal_invariant_small_n_impl(63);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000064() {
        sm_reversal_invariant_small_n_impl(64);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000065() {
        sm_reversal_invariant_small_n_impl(65);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000066() {
        sm_reversal_invariant_small_n_impl(66);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000067() {
        sm_reversal_invariant_small_n_impl(67);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000068() {
        sm_reversal_invariant_small_n_impl(68);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000069() {
        sm_reversal_invariant_small_n_impl(69);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000070() {
        sm_reversal_invariant_small_n_impl(70);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000071() {
        sm_reversal_invariant_small_n_impl(71);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000072() {
        sm_reversal_invariant_small_n_impl(72);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000073() {
        sm_reversal_invariant_small_n_impl(73);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000074() {
        sm_reversal_invariant_small_n_impl(74);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000075() {
        sm_reversal_invariant_small_n_impl(75);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000076() {
        sm_reversal_invariant_small_n_impl(76);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000077() {
        sm_reversal_invariant_small_n_impl(77);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000078() {
        sm_reversal_invariant_small_n_impl(78);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000079() {
        sm_reversal_invariant_small_n_impl(79);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000080() {
        sm_reversal_invariant_small_n_impl(80);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000081() {
        sm_reversal_invariant_small_n_impl(81);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000082() {
        sm_reversal_invariant_small_n_impl(82);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000083() {
        sm_reversal_invariant_small_n_impl(83);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000084() {
        sm_reversal_invariant_small_n_impl(84);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000085() {
        sm_reversal_invariant_small_n_impl(85);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000086() {
        sm_reversal_invariant_small_n_impl(86);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000087() {
        sm_reversal_invariant_small_n_impl(87);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000088() {
        sm_reversal_invariant_small_n_impl(88);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000089() {
        sm_reversal_invariant_small_n_impl(89);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000090() {
        sm_reversal_invariant_small_n_impl(90);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000091() {
        sm_reversal_invariant_small_n_impl(91);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000092() {
        sm_reversal_invariant_small_n_impl(92);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000093() {
        sm_reversal_invariant_small_n_impl(93);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000094() {
        sm_reversal_invariant_small_n_impl(94);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000095() {
        sm_reversal_invariant_small_n_impl(95);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000096() {
        sm_reversal_invariant_small_n_impl(96);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000097() {
        sm_reversal_invariant_small_n_impl(97);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000098() {
        sm_reversal_invariant_small_n_impl(98);
    }
    #[cfg_attr(test, test)]
    fn sm_reversal_invariant_seed_000099() {
        sm_reversal_invariant_small_n_impl(99);
    }
    // --- pm_compactness_translation: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000000() {
        pm_compactness_translation_invariance_impl(0);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000001() {
        pm_compactness_translation_invariance_impl(1);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000002() {
        pm_compactness_translation_invariance_impl(2);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000003() {
        pm_compactness_translation_invariance_impl(3);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000004() {
        pm_compactness_translation_invariance_impl(4);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000005() {
        pm_compactness_translation_invariance_impl(5);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000006() {
        pm_compactness_translation_invariance_impl(6);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000007() {
        pm_compactness_translation_invariance_impl(7);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000008() {
        pm_compactness_translation_invariance_impl(8);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000009() {
        pm_compactness_translation_invariance_impl(9);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000010() {
        pm_compactness_translation_invariance_impl(10);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000011() {
        pm_compactness_translation_invariance_impl(11);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000012() {
        pm_compactness_translation_invariance_impl(12);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000013() {
        pm_compactness_translation_invariance_impl(13);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000014() {
        pm_compactness_translation_invariance_impl(14);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000015() {
        pm_compactness_translation_invariance_impl(15);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000016() {
        pm_compactness_translation_invariance_impl(16);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000017() {
        pm_compactness_translation_invariance_impl(17);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000018() {
        pm_compactness_translation_invariance_impl(18);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000019() {
        pm_compactness_translation_invariance_impl(19);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000020() {
        pm_compactness_translation_invariance_impl(20);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000021() {
        pm_compactness_translation_invariance_impl(21);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000022() {
        pm_compactness_translation_invariance_impl(22);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000023() {
        pm_compactness_translation_invariance_impl(23);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000024() {
        pm_compactness_translation_invariance_impl(24);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000025() {
        pm_compactness_translation_invariance_impl(25);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000026() {
        pm_compactness_translation_invariance_impl(26);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000027() {
        pm_compactness_translation_invariance_impl(27);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000028() {
        pm_compactness_translation_invariance_impl(28);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000029() {
        pm_compactness_translation_invariance_impl(29);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000030() {
        pm_compactness_translation_invariance_impl(30);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000031() {
        pm_compactness_translation_invariance_impl(31);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000032() {
        pm_compactness_translation_invariance_impl(32);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000033() {
        pm_compactness_translation_invariance_impl(33);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000034() {
        pm_compactness_translation_invariance_impl(34);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000035() {
        pm_compactness_translation_invariance_impl(35);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000036() {
        pm_compactness_translation_invariance_impl(36);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000037() {
        pm_compactness_translation_invariance_impl(37);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000038() {
        pm_compactness_translation_invariance_impl(38);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000039() {
        pm_compactness_translation_invariance_impl(39);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000040() {
        pm_compactness_translation_invariance_impl(40);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000041() {
        pm_compactness_translation_invariance_impl(41);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000042() {
        pm_compactness_translation_invariance_impl(42);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000043() {
        pm_compactness_translation_invariance_impl(43);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000044() {
        pm_compactness_translation_invariance_impl(44);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000045() {
        pm_compactness_translation_invariance_impl(45);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000046() {
        pm_compactness_translation_invariance_impl(46);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000047() {
        pm_compactness_translation_invariance_impl(47);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000048() {
        pm_compactness_translation_invariance_impl(48);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000049() {
        pm_compactness_translation_invariance_impl(49);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000050() {
        pm_compactness_translation_invariance_impl(50);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000051() {
        pm_compactness_translation_invariance_impl(51);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000052() {
        pm_compactness_translation_invariance_impl(52);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000053() {
        pm_compactness_translation_invariance_impl(53);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000054() {
        pm_compactness_translation_invariance_impl(54);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000055() {
        pm_compactness_translation_invariance_impl(55);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000056() {
        pm_compactness_translation_invariance_impl(56);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000057() {
        pm_compactness_translation_invariance_impl(57);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000058() {
        pm_compactness_translation_invariance_impl(58);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000059() {
        pm_compactness_translation_invariance_impl(59);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000060() {
        pm_compactness_translation_invariance_impl(60);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000061() {
        pm_compactness_translation_invariance_impl(61);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000062() {
        pm_compactness_translation_invariance_impl(62);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000063() {
        pm_compactness_translation_invariance_impl(63);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000064() {
        pm_compactness_translation_invariance_impl(64);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000065() {
        pm_compactness_translation_invariance_impl(65);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000066() {
        pm_compactness_translation_invariance_impl(66);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000067() {
        pm_compactness_translation_invariance_impl(67);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000068() {
        pm_compactness_translation_invariance_impl(68);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000069() {
        pm_compactness_translation_invariance_impl(69);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000070() {
        pm_compactness_translation_invariance_impl(70);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000071() {
        pm_compactness_translation_invariance_impl(71);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000072() {
        pm_compactness_translation_invariance_impl(72);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000073() {
        pm_compactness_translation_invariance_impl(73);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000074() {
        pm_compactness_translation_invariance_impl(74);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000075() {
        pm_compactness_translation_invariance_impl(75);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000076() {
        pm_compactness_translation_invariance_impl(76);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000077() {
        pm_compactness_translation_invariance_impl(77);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000078() {
        pm_compactness_translation_invariance_impl(78);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000079() {
        pm_compactness_translation_invariance_impl(79);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000080() {
        pm_compactness_translation_invariance_impl(80);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000081() {
        pm_compactness_translation_invariance_impl(81);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000082() {
        pm_compactness_translation_invariance_impl(82);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000083() {
        pm_compactness_translation_invariance_impl(83);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000084() {
        pm_compactness_translation_invariance_impl(84);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000085() {
        pm_compactness_translation_invariance_impl(85);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000086() {
        pm_compactness_translation_invariance_impl(86);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000087() {
        pm_compactness_translation_invariance_impl(87);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000088() {
        pm_compactness_translation_invariance_impl(88);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000089() {
        pm_compactness_translation_invariance_impl(89);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000090() {
        pm_compactness_translation_invariance_impl(90);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000091() {
        pm_compactness_translation_invariance_impl(91);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000092() {
        pm_compactness_translation_invariance_impl(92);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000093() {
        pm_compactness_translation_invariance_impl(93);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000094() {
        pm_compactness_translation_invariance_impl(94);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000095() {
        pm_compactness_translation_invariance_impl(95);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000096() {
        pm_compactness_translation_invariance_impl(96);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000097() {
        pm_compactness_translation_invariance_impl(97);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000098() {
        pm_compactness_translation_invariance_impl(98);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000099() {
        pm_compactness_translation_invariance_impl(99);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000100() {
        pm_compactness_translation_invariance_impl(100);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000101() {
        pm_compactness_translation_invariance_impl(101);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000102() {
        pm_compactness_translation_invariance_impl(102);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000103() {
        pm_compactness_translation_invariance_impl(103);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000104() {
        pm_compactness_translation_invariance_impl(104);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000105() {
        pm_compactness_translation_invariance_impl(105);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000106() {
        pm_compactness_translation_invariance_impl(106);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000107() {
        pm_compactness_translation_invariance_impl(107);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000108() {
        pm_compactness_translation_invariance_impl(108);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000109() {
        pm_compactness_translation_invariance_impl(109);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000110() {
        pm_compactness_translation_invariance_impl(110);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000111() {
        pm_compactness_translation_invariance_impl(111);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000112() {
        pm_compactness_translation_invariance_impl(112);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000113() {
        pm_compactness_translation_invariance_impl(113);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000114() {
        pm_compactness_translation_invariance_impl(114);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000115() {
        pm_compactness_translation_invariance_impl(115);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000116() {
        pm_compactness_translation_invariance_impl(116);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000117() {
        pm_compactness_translation_invariance_impl(117);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000118() {
        pm_compactness_translation_invariance_impl(118);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000119() {
        pm_compactness_translation_invariance_impl(119);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000120() {
        pm_compactness_translation_invariance_impl(120);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000121() {
        pm_compactness_translation_invariance_impl(121);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000122() {
        pm_compactness_translation_invariance_impl(122);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000123() {
        pm_compactness_translation_invariance_impl(123);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000124() {
        pm_compactness_translation_invariance_impl(124);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000125() {
        pm_compactness_translation_invariance_impl(125);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000126() {
        pm_compactness_translation_invariance_impl(126);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000127() {
        pm_compactness_translation_invariance_impl(127);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000128() {
        pm_compactness_translation_invariance_impl(128);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000129() {
        pm_compactness_translation_invariance_impl(129);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000130() {
        pm_compactness_translation_invariance_impl(130);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000131() {
        pm_compactness_translation_invariance_impl(131);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000132() {
        pm_compactness_translation_invariance_impl(132);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000133() {
        pm_compactness_translation_invariance_impl(133);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000134() {
        pm_compactness_translation_invariance_impl(134);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000135() {
        pm_compactness_translation_invariance_impl(135);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000136() {
        pm_compactness_translation_invariance_impl(136);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000137() {
        pm_compactness_translation_invariance_impl(137);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000138() {
        pm_compactness_translation_invariance_impl(138);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000139() {
        pm_compactness_translation_invariance_impl(139);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000140() {
        pm_compactness_translation_invariance_impl(140);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000141() {
        pm_compactness_translation_invariance_impl(141);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000142() {
        pm_compactness_translation_invariance_impl(142);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000143() {
        pm_compactness_translation_invariance_impl(143);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000144() {
        pm_compactness_translation_invariance_impl(144);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000145() {
        pm_compactness_translation_invariance_impl(145);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000146() {
        pm_compactness_translation_invariance_impl(146);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000147() {
        pm_compactness_translation_invariance_impl(147);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000148() {
        pm_compactness_translation_invariance_impl(148);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_translation_seed_000149() {
        pm_compactness_translation_invariance_impl(149);
    }
    // --- pm_compactness_scale_law: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000000() {
        pm_compactness_scale_law_pow2_impl(0);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000001() {
        pm_compactness_scale_law_pow2_impl(1);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000002() {
        pm_compactness_scale_law_pow2_impl(2);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000003() {
        pm_compactness_scale_law_pow2_impl(3);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000004() {
        pm_compactness_scale_law_pow2_impl(4);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000005() {
        pm_compactness_scale_law_pow2_impl(5);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000006() {
        pm_compactness_scale_law_pow2_impl(6);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000007() {
        pm_compactness_scale_law_pow2_impl(7);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000008() {
        pm_compactness_scale_law_pow2_impl(8);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000009() {
        pm_compactness_scale_law_pow2_impl(9);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000010() {
        pm_compactness_scale_law_pow2_impl(10);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000011() {
        pm_compactness_scale_law_pow2_impl(11);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000012() {
        pm_compactness_scale_law_pow2_impl(12);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000013() {
        pm_compactness_scale_law_pow2_impl(13);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000014() {
        pm_compactness_scale_law_pow2_impl(14);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000015() {
        pm_compactness_scale_law_pow2_impl(15);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000016() {
        pm_compactness_scale_law_pow2_impl(16);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000017() {
        pm_compactness_scale_law_pow2_impl(17);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000018() {
        pm_compactness_scale_law_pow2_impl(18);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000019() {
        pm_compactness_scale_law_pow2_impl(19);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000020() {
        pm_compactness_scale_law_pow2_impl(20);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000021() {
        pm_compactness_scale_law_pow2_impl(21);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000022() {
        pm_compactness_scale_law_pow2_impl(22);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000023() {
        pm_compactness_scale_law_pow2_impl(23);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000024() {
        pm_compactness_scale_law_pow2_impl(24);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000025() {
        pm_compactness_scale_law_pow2_impl(25);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000026() {
        pm_compactness_scale_law_pow2_impl(26);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000027() {
        pm_compactness_scale_law_pow2_impl(27);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000028() {
        pm_compactness_scale_law_pow2_impl(28);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000029() {
        pm_compactness_scale_law_pow2_impl(29);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000030() {
        pm_compactness_scale_law_pow2_impl(30);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000031() {
        pm_compactness_scale_law_pow2_impl(31);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000032() {
        pm_compactness_scale_law_pow2_impl(32);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000033() {
        pm_compactness_scale_law_pow2_impl(33);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000034() {
        pm_compactness_scale_law_pow2_impl(34);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000035() {
        pm_compactness_scale_law_pow2_impl(35);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000036() {
        pm_compactness_scale_law_pow2_impl(36);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000037() {
        pm_compactness_scale_law_pow2_impl(37);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000038() {
        pm_compactness_scale_law_pow2_impl(38);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000039() {
        pm_compactness_scale_law_pow2_impl(39);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000040() {
        pm_compactness_scale_law_pow2_impl(40);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000041() {
        pm_compactness_scale_law_pow2_impl(41);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000042() {
        pm_compactness_scale_law_pow2_impl(42);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000043() {
        pm_compactness_scale_law_pow2_impl(43);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000044() {
        pm_compactness_scale_law_pow2_impl(44);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000045() {
        pm_compactness_scale_law_pow2_impl(45);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000046() {
        pm_compactness_scale_law_pow2_impl(46);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000047() {
        pm_compactness_scale_law_pow2_impl(47);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000048() {
        pm_compactness_scale_law_pow2_impl(48);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000049() {
        pm_compactness_scale_law_pow2_impl(49);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000050() {
        pm_compactness_scale_law_pow2_impl(50);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000051() {
        pm_compactness_scale_law_pow2_impl(51);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000052() {
        pm_compactness_scale_law_pow2_impl(52);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000053() {
        pm_compactness_scale_law_pow2_impl(53);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000054() {
        pm_compactness_scale_law_pow2_impl(54);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000055() {
        pm_compactness_scale_law_pow2_impl(55);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000056() {
        pm_compactness_scale_law_pow2_impl(56);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000057() {
        pm_compactness_scale_law_pow2_impl(57);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000058() {
        pm_compactness_scale_law_pow2_impl(58);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000059() {
        pm_compactness_scale_law_pow2_impl(59);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000060() {
        pm_compactness_scale_law_pow2_impl(60);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000061() {
        pm_compactness_scale_law_pow2_impl(61);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000062() {
        pm_compactness_scale_law_pow2_impl(62);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000063() {
        pm_compactness_scale_law_pow2_impl(63);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000064() {
        pm_compactness_scale_law_pow2_impl(64);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000065() {
        pm_compactness_scale_law_pow2_impl(65);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000066() {
        pm_compactness_scale_law_pow2_impl(66);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000067() {
        pm_compactness_scale_law_pow2_impl(67);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000068() {
        pm_compactness_scale_law_pow2_impl(68);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000069() {
        pm_compactness_scale_law_pow2_impl(69);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000070() {
        pm_compactness_scale_law_pow2_impl(70);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000071() {
        pm_compactness_scale_law_pow2_impl(71);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000072() {
        pm_compactness_scale_law_pow2_impl(72);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000073() {
        pm_compactness_scale_law_pow2_impl(73);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000074() {
        pm_compactness_scale_law_pow2_impl(74);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000075() {
        pm_compactness_scale_law_pow2_impl(75);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000076() {
        pm_compactness_scale_law_pow2_impl(76);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000077() {
        pm_compactness_scale_law_pow2_impl(77);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000078() {
        pm_compactness_scale_law_pow2_impl(78);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000079() {
        pm_compactness_scale_law_pow2_impl(79);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000080() {
        pm_compactness_scale_law_pow2_impl(80);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000081() {
        pm_compactness_scale_law_pow2_impl(81);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000082() {
        pm_compactness_scale_law_pow2_impl(82);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000083() {
        pm_compactness_scale_law_pow2_impl(83);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000084() {
        pm_compactness_scale_law_pow2_impl(84);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000085() {
        pm_compactness_scale_law_pow2_impl(85);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000086() {
        pm_compactness_scale_law_pow2_impl(86);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000087() {
        pm_compactness_scale_law_pow2_impl(87);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000088() {
        pm_compactness_scale_law_pow2_impl(88);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000089() {
        pm_compactness_scale_law_pow2_impl(89);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000090() {
        pm_compactness_scale_law_pow2_impl(90);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000091() {
        pm_compactness_scale_law_pow2_impl(91);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000092() {
        pm_compactness_scale_law_pow2_impl(92);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000093() {
        pm_compactness_scale_law_pow2_impl(93);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000094() {
        pm_compactness_scale_law_pow2_impl(94);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000095() {
        pm_compactness_scale_law_pow2_impl(95);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000096() {
        pm_compactness_scale_law_pow2_impl(96);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000097() {
        pm_compactness_scale_law_pow2_impl(97);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000098() {
        pm_compactness_scale_law_pow2_impl(98);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000099() {
        pm_compactness_scale_law_pow2_impl(99);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000100() {
        pm_compactness_scale_law_pow2_impl(100);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000101() {
        pm_compactness_scale_law_pow2_impl(101);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000102() {
        pm_compactness_scale_law_pow2_impl(102);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000103() {
        pm_compactness_scale_law_pow2_impl(103);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000104() {
        pm_compactness_scale_law_pow2_impl(104);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000105() {
        pm_compactness_scale_law_pow2_impl(105);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000106() {
        pm_compactness_scale_law_pow2_impl(106);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000107() {
        pm_compactness_scale_law_pow2_impl(107);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000108() {
        pm_compactness_scale_law_pow2_impl(108);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000109() {
        pm_compactness_scale_law_pow2_impl(109);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000110() {
        pm_compactness_scale_law_pow2_impl(110);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000111() {
        pm_compactness_scale_law_pow2_impl(111);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000112() {
        pm_compactness_scale_law_pow2_impl(112);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000113() {
        pm_compactness_scale_law_pow2_impl(113);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000114() {
        pm_compactness_scale_law_pow2_impl(114);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000115() {
        pm_compactness_scale_law_pow2_impl(115);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000116() {
        pm_compactness_scale_law_pow2_impl(116);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000117() {
        pm_compactness_scale_law_pow2_impl(117);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000118() {
        pm_compactness_scale_law_pow2_impl(118);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000119() {
        pm_compactness_scale_law_pow2_impl(119);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000120() {
        pm_compactness_scale_law_pow2_impl(120);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000121() {
        pm_compactness_scale_law_pow2_impl(121);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000122() {
        pm_compactness_scale_law_pow2_impl(122);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000123() {
        pm_compactness_scale_law_pow2_impl(123);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000124() {
        pm_compactness_scale_law_pow2_impl(124);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000125() {
        pm_compactness_scale_law_pow2_impl(125);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000126() {
        pm_compactness_scale_law_pow2_impl(126);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000127() {
        pm_compactness_scale_law_pow2_impl(127);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000128() {
        pm_compactness_scale_law_pow2_impl(128);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000129() {
        pm_compactness_scale_law_pow2_impl(129);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000130() {
        pm_compactness_scale_law_pow2_impl(130);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000131() {
        pm_compactness_scale_law_pow2_impl(131);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000132() {
        pm_compactness_scale_law_pow2_impl(132);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000133() {
        pm_compactness_scale_law_pow2_impl(133);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000134() {
        pm_compactness_scale_law_pow2_impl(134);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000135() {
        pm_compactness_scale_law_pow2_impl(135);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000136() {
        pm_compactness_scale_law_pow2_impl(136);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000137() {
        pm_compactness_scale_law_pow2_impl(137);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000138() {
        pm_compactness_scale_law_pow2_impl(138);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000139() {
        pm_compactness_scale_law_pow2_impl(139);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000140() {
        pm_compactness_scale_law_pow2_impl(140);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000141() {
        pm_compactness_scale_law_pow2_impl(141);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000142() {
        pm_compactness_scale_law_pow2_impl(142);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000143() {
        pm_compactness_scale_law_pow2_impl(143);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000144() {
        pm_compactness_scale_law_pow2_impl(144);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000145() {
        pm_compactness_scale_law_pow2_impl(145);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000146() {
        pm_compactness_scale_law_pow2_impl(146);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000147() {
        pm_compactness_scale_law_pow2_impl(147);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000148() {
        pm_compactness_scale_law_pow2_impl(148);
    }
    #[cfg_attr(test, test)]
    fn pm_compactness_scale_law_seed_000149() {
        pm_compactness_scale_law_pow2_impl(149);
    }
    // --- pm_connectivity_monotone: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000000() {
        pm_connectivity_monotone_under_shrink_impl(0);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000001() {
        pm_connectivity_monotone_under_shrink_impl(1);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000002() {
        pm_connectivity_monotone_under_shrink_impl(2);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000003() {
        pm_connectivity_monotone_under_shrink_impl(3);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000004() {
        pm_connectivity_monotone_under_shrink_impl(4);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000005() {
        pm_connectivity_monotone_under_shrink_impl(5);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000006() {
        pm_connectivity_monotone_under_shrink_impl(6);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000007() {
        pm_connectivity_monotone_under_shrink_impl(7);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000008() {
        pm_connectivity_monotone_under_shrink_impl(8);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000009() {
        pm_connectivity_monotone_under_shrink_impl(9);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000010() {
        pm_connectivity_monotone_under_shrink_impl(10);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000011() {
        pm_connectivity_monotone_under_shrink_impl(11);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000012() {
        pm_connectivity_monotone_under_shrink_impl(12);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000013() {
        pm_connectivity_monotone_under_shrink_impl(13);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000014() {
        pm_connectivity_monotone_under_shrink_impl(14);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000015() {
        pm_connectivity_monotone_under_shrink_impl(15);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000016() {
        pm_connectivity_monotone_under_shrink_impl(16);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000017() {
        pm_connectivity_monotone_under_shrink_impl(17);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000018() {
        pm_connectivity_monotone_under_shrink_impl(18);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000019() {
        pm_connectivity_monotone_under_shrink_impl(19);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000020() {
        pm_connectivity_monotone_under_shrink_impl(20);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000021() {
        pm_connectivity_monotone_under_shrink_impl(21);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000022() {
        pm_connectivity_monotone_under_shrink_impl(22);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000023() {
        pm_connectivity_monotone_under_shrink_impl(23);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000024() {
        pm_connectivity_monotone_under_shrink_impl(24);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000025() {
        pm_connectivity_monotone_under_shrink_impl(25);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000026() {
        pm_connectivity_monotone_under_shrink_impl(26);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000027() {
        pm_connectivity_monotone_under_shrink_impl(27);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000028() {
        pm_connectivity_monotone_under_shrink_impl(28);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000029() {
        pm_connectivity_monotone_under_shrink_impl(29);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000030() {
        pm_connectivity_monotone_under_shrink_impl(30);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000031() {
        pm_connectivity_monotone_under_shrink_impl(31);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000032() {
        pm_connectivity_monotone_under_shrink_impl(32);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000033() {
        pm_connectivity_monotone_under_shrink_impl(33);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000034() {
        pm_connectivity_monotone_under_shrink_impl(34);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000035() {
        pm_connectivity_monotone_under_shrink_impl(35);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000036() {
        pm_connectivity_monotone_under_shrink_impl(36);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000037() {
        pm_connectivity_monotone_under_shrink_impl(37);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000038() {
        pm_connectivity_monotone_under_shrink_impl(38);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000039() {
        pm_connectivity_monotone_under_shrink_impl(39);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000040() {
        pm_connectivity_monotone_under_shrink_impl(40);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000041() {
        pm_connectivity_monotone_under_shrink_impl(41);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000042() {
        pm_connectivity_monotone_under_shrink_impl(42);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000043() {
        pm_connectivity_monotone_under_shrink_impl(43);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000044() {
        pm_connectivity_monotone_under_shrink_impl(44);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000045() {
        pm_connectivity_monotone_under_shrink_impl(45);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000046() {
        pm_connectivity_monotone_under_shrink_impl(46);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000047() {
        pm_connectivity_monotone_under_shrink_impl(47);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000048() {
        pm_connectivity_monotone_under_shrink_impl(48);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000049() {
        pm_connectivity_monotone_under_shrink_impl(49);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000050() {
        pm_connectivity_monotone_under_shrink_impl(50);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000051() {
        pm_connectivity_monotone_under_shrink_impl(51);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000052() {
        pm_connectivity_monotone_under_shrink_impl(52);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000053() {
        pm_connectivity_monotone_under_shrink_impl(53);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000054() {
        pm_connectivity_monotone_under_shrink_impl(54);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000055() {
        pm_connectivity_monotone_under_shrink_impl(55);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000056() {
        pm_connectivity_monotone_under_shrink_impl(56);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000057() {
        pm_connectivity_monotone_under_shrink_impl(57);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000058() {
        pm_connectivity_monotone_under_shrink_impl(58);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000059() {
        pm_connectivity_monotone_under_shrink_impl(59);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000060() {
        pm_connectivity_monotone_under_shrink_impl(60);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000061() {
        pm_connectivity_monotone_under_shrink_impl(61);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000062() {
        pm_connectivity_monotone_under_shrink_impl(62);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000063() {
        pm_connectivity_monotone_under_shrink_impl(63);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000064() {
        pm_connectivity_monotone_under_shrink_impl(64);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000065() {
        pm_connectivity_monotone_under_shrink_impl(65);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000066() {
        pm_connectivity_monotone_under_shrink_impl(66);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000067() {
        pm_connectivity_monotone_under_shrink_impl(67);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000068() {
        pm_connectivity_monotone_under_shrink_impl(68);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000069() {
        pm_connectivity_monotone_under_shrink_impl(69);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000070() {
        pm_connectivity_monotone_under_shrink_impl(70);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000071() {
        pm_connectivity_monotone_under_shrink_impl(71);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000072() {
        pm_connectivity_monotone_under_shrink_impl(72);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000073() {
        pm_connectivity_monotone_under_shrink_impl(73);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000074() {
        pm_connectivity_monotone_under_shrink_impl(74);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000075() {
        pm_connectivity_monotone_under_shrink_impl(75);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000076() {
        pm_connectivity_monotone_under_shrink_impl(76);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000077() {
        pm_connectivity_monotone_under_shrink_impl(77);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000078() {
        pm_connectivity_monotone_under_shrink_impl(78);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000079() {
        pm_connectivity_monotone_under_shrink_impl(79);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000080() {
        pm_connectivity_monotone_under_shrink_impl(80);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000081() {
        pm_connectivity_monotone_under_shrink_impl(81);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000082() {
        pm_connectivity_monotone_under_shrink_impl(82);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000083() {
        pm_connectivity_monotone_under_shrink_impl(83);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000084() {
        pm_connectivity_monotone_under_shrink_impl(84);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000085() {
        pm_connectivity_monotone_under_shrink_impl(85);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000086() {
        pm_connectivity_monotone_under_shrink_impl(86);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000087() {
        pm_connectivity_monotone_under_shrink_impl(87);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000088() {
        pm_connectivity_monotone_under_shrink_impl(88);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000089() {
        pm_connectivity_monotone_under_shrink_impl(89);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000090() {
        pm_connectivity_monotone_under_shrink_impl(90);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000091() {
        pm_connectivity_monotone_under_shrink_impl(91);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000092() {
        pm_connectivity_monotone_under_shrink_impl(92);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000093() {
        pm_connectivity_monotone_under_shrink_impl(93);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000094() {
        pm_connectivity_monotone_under_shrink_impl(94);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000095() {
        pm_connectivity_monotone_under_shrink_impl(95);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000096() {
        pm_connectivity_monotone_under_shrink_impl(96);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000097() {
        pm_connectivity_monotone_under_shrink_impl(97);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000098() {
        pm_connectivity_monotone_under_shrink_impl(98);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000099() {
        pm_connectivity_monotone_under_shrink_impl(99);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000100() {
        pm_connectivity_monotone_under_shrink_impl(100);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000101() {
        pm_connectivity_monotone_under_shrink_impl(101);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000102() {
        pm_connectivity_monotone_under_shrink_impl(102);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000103() {
        pm_connectivity_monotone_under_shrink_impl(103);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000104() {
        pm_connectivity_monotone_under_shrink_impl(104);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000105() {
        pm_connectivity_monotone_under_shrink_impl(105);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000106() {
        pm_connectivity_monotone_under_shrink_impl(106);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000107() {
        pm_connectivity_monotone_under_shrink_impl(107);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000108() {
        pm_connectivity_monotone_under_shrink_impl(108);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000109() {
        pm_connectivity_monotone_under_shrink_impl(109);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000110() {
        pm_connectivity_monotone_under_shrink_impl(110);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000111() {
        pm_connectivity_monotone_under_shrink_impl(111);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000112() {
        pm_connectivity_monotone_under_shrink_impl(112);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000113() {
        pm_connectivity_monotone_under_shrink_impl(113);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000114() {
        pm_connectivity_monotone_under_shrink_impl(114);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000115() {
        pm_connectivity_monotone_under_shrink_impl(115);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000116() {
        pm_connectivity_monotone_under_shrink_impl(116);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000117() {
        pm_connectivity_monotone_under_shrink_impl(117);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000118() {
        pm_connectivity_monotone_under_shrink_impl(118);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000119() {
        pm_connectivity_monotone_under_shrink_impl(119);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000120() {
        pm_connectivity_monotone_under_shrink_impl(120);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000121() {
        pm_connectivity_monotone_under_shrink_impl(121);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000122() {
        pm_connectivity_monotone_under_shrink_impl(122);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000123() {
        pm_connectivity_monotone_under_shrink_impl(123);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000124() {
        pm_connectivity_monotone_under_shrink_impl(124);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000125() {
        pm_connectivity_monotone_under_shrink_impl(125);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000126() {
        pm_connectivity_monotone_under_shrink_impl(126);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000127() {
        pm_connectivity_monotone_under_shrink_impl(127);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000128() {
        pm_connectivity_monotone_under_shrink_impl(128);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000129() {
        pm_connectivity_monotone_under_shrink_impl(129);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000130() {
        pm_connectivity_monotone_under_shrink_impl(130);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000131() {
        pm_connectivity_monotone_under_shrink_impl(131);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000132() {
        pm_connectivity_monotone_under_shrink_impl(132);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000133() {
        pm_connectivity_monotone_under_shrink_impl(133);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000134() {
        pm_connectivity_monotone_under_shrink_impl(134);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000135() {
        pm_connectivity_monotone_under_shrink_impl(135);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000136() {
        pm_connectivity_monotone_under_shrink_impl(136);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000137() {
        pm_connectivity_monotone_under_shrink_impl(137);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000138() {
        pm_connectivity_monotone_under_shrink_impl(138);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000139() {
        pm_connectivity_monotone_under_shrink_impl(139);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000140() {
        pm_connectivity_monotone_under_shrink_impl(140);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000141() {
        pm_connectivity_monotone_under_shrink_impl(141);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000142() {
        pm_connectivity_monotone_under_shrink_impl(142);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000143() {
        pm_connectivity_monotone_under_shrink_impl(143);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000144() {
        pm_connectivity_monotone_under_shrink_impl(144);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000145() {
        pm_connectivity_monotone_under_shrink_impl(145);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000146() {
        pm_connectivity_monotone_under_shrink_impl(146);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000147() {
        pm_connectivity_monotone_under_shrink_impl(147);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000148() {
        pm_connectivity_monotone_under_shrink_impl(148);
    }
    #[cfg_attr(test, test)]
    fn pm_connectivity_monotone_seed_000149() {
        pm_connectivity_monotone_under_shrink_impl(149);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("property_campaigns::tests::splitmix64_is_deterministic_in_seed", splitmix64_is_deterministic_in_seed),
        ("property_campaigns::tests::splitmix64_varies_with_seed", splitmix64_varies_with_seed),
        ("property_campaigns::tests::mm_gen_pair_is_well_separated", mm_gen_pair_is_well_separated),
        ("property_campaigns::tests::mm_gen_zero_pair_produces_true_signed_zeros", mm_gen_zero_pair_produces_true_signed_zeros),
        ("property_campaigns::tests::mm_signed_zero_first_arg_wins_on_a_hand_worked_example", mm_signed_zero_first_arg_wins_on_a_hand_worked_example),
        ("property_campaigns::tests::sm_gen_array_length_in_expected_range", sm_gen_array_length_in_expected_range),
        ("property_campaigns::tests::sm_gen_small_array_length_in_expected_range", sm_gen_small_array_length_in_expected_range),
        ("property_campaigns::tests::sm_scale_invariance_on_a_hand_built_array", sm_scale_invariance_on_a_hand_built_array),
        ("property_campaigns::tests::sm_reversal_invariant_on_a_hand_built_pair", sm_reversal_invariant_on_a_hand_built_pair),
        ("property_campaigns::tests::pm_gen_compactness_case_dims_in_expected_range", pm_gen_compactness_case_dims_in_expected_range),
        ("property_campaigns::tests::pm_gen_net_dims_in_expected_range", pm_gen_net_dims_in_expected_range),
        ("property_campaigns::tests::pm_compactness_translation_invariance_on_a_hand_built_case", pm_compactness_translation_invariance_on_a_hand_built_case),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000000", mm_agrees_with_ieee_seed_000000),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000001", mm_agrees_with_ieee_seed_000001),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000002", mm_agrees_with_ieee_seed_000002),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000003", mm_agrees_with_ieee_seed_000003),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000004", mm_agrees_with_ieee_seed_000004),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000005", mm_agrees_with_ieee_seed_000005),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000006", mm_agrees_with_ieee_seed_000006),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000007", mm_agrees_with_ieee_seed_000007),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000008", mm_agrees_with_ieee_seed_000008),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000009", mm_agrees_with_ieee_seed_000009),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000010", mm_agrees_with_ieee_seed_000010),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000011", mm_agrees_with_ieee_seed_000011),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000012", mm_agrees_with_ieee_seed_000012),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000013", mm_agrees_with_ieee_seed_000013),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000014", mm_agrees_with_ieee_seed_000014),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000015", mm_agrees_with_ieee_seed_000015),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000016", mm_agrees_with_ieee_seed_000016),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000017", mm_agrees_with_ieee_seed_000017),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000018", mm_agrees_with_ieee_seed_000018),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000019", mm_agrees_with_ieee_seed_000019),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000020", mm_agrees_with_ieee_seed_000020),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000021", mm_agrees_with_ieee_seed_000021),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000022", mm_agrees_with_ieee_seed_000022),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000023", mm_agrees_with_ieee_seed_000023),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000024", mm_agrees_with_ieee_seed_000024),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000025", mm_agrees_with_ieee_seed_000025),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000026", mm_agrees_with_ieee_seed_000026),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000027", mm_agrees_with_ieee_seed_000027),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000028", mm_agrees_with_ieee_seed_000028),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000029", mm_agrees_with_ieee_seed_000029),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000030", mm_agrees_with_ieee_seed_000030),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000031", mm_agrees_with_ieee_seed_000031),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000032", mm_agrees_with_ieee_seed_000032),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000033", mm_agrees_with_ieee_seed_000033),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000034", mm_agrees_with_ieee_seed_000034),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000035", mm_agrees_with_ieee_seed_000035),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000036", mm_agrees_with_ieee_seed_000036),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000037", mm_agrees_with_ieee_seed_000037),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000038", mm_agrees_with_ieee_seed_000038),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000039", mm_agrees_with_ieee_seed_000039),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000040", mm_agrees_with_ieee_seed_000040),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000041", mm_agrees_with_ieee_seed_000041),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000042", mm_agrees_with_ieee_seed_000042),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000043", mm_agrees_with_ieee_seed_000043),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000044", mm_agrees_with_ieee_seed_000044),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000045", mm_agrees_with_ieee_seed_000045),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000046", mm_agrees_with_ieee_seed_000046),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000047", mm_agrees_with_ieee_seed_000047),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000048", mm_agrees_with_ieee_seed_000048),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000049", mm_agrees_with_ieee_seed_000049),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000050", mm_agrees_with_ieee_seed_000050),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000051", mm_agrees_with_ieee_seed_000051),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000052", mm_agrees_with_ieee_seed_000052),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000053", mm_agrees_with_ieee_seed_000053),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000054", mm_agrees_with_ieee_seed_000054),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000055", mm_agrees_with_ieee_seed_000055),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000056", mm_agrees_with_ieee_seed_000056),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000057", mm_agrees_with_ieee_seed_000057),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000058", mm_agrees_with_ieee_seed_000058),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000059", mm_agrees_with_ieee_seed_000059),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000060", mm_agrees_with_ieee_seed_000060),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000061", mm_agrees_with_ieee_seed_000061),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000062", mm_agrees_with_ieee_seed_000062),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000063", mm_agrees_with_ieee_seed_000063),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000064", mm_agrees_with_ieee_seed_000064),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000065", mm_agrees_with_ieee_seed_000065),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000066", mm_agrees_with_ieee_seed_000066),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000067", mm_agrees_with_ieee_seed_000067),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000068", mm_agrees_with_ieee_seed_000068),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000069", mm_agrees_with_ieee_seed_000069),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000070", mm_agrees_with_ieee_seed_000070),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000071", mm_agrees_with_ieee_seed_000071),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000072", mm_agrees_with_ieee_seed_000072),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000073", mm_agrees_with_ieee_seed_000073),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000074", mm_agrees_with_ieee_seed_000074),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000075", mm_agrees_with_ieee_seed_000075),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000076", mm_agrees_with_ieee_seed_000076),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000077", mm_agrees_with_ieee_seed_000077),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000078", mm_agrees_with_ieee_seed_000078),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000079", mm_agrees_with_ieee_seed_000079),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000080", mm_agrees_with_ieee_seed_000080),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000081", mm_agrees_with_ieee_seed_000081),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000082", mm_agrees_with_ieee_seed_000082),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000083", mm_agrees_with_ieee_seed_000083),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000084", mm_agrees_with_ieee_seed_000084),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000085", mm_agrees_with_ieee_seed_000085),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000086", mm_agrees_with_ieee_seed_000086),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000087", mm_agrees_with_ieee_seed_000087),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000088", mm_agrees_with_ieee_seed_000088),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000089", mm_agrees_with_ieee_seed_000089),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000090", mm_agrees_with_ieee_seed_000090),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000091", mm_agrees_with_ieee_seed_000091),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000092", mm_agrees_with_ieee_seed_000092),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000093", mm_agrees_with_ieee_seed_000093),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000094", mm_agrees_with_ieee_seed_000094),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000095", mm_agrees_with_ieee_seed_000095),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000096", mm_agrees_with_ieee_seed_000096),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000097", mm_agrees_with_ieee_seed_000097),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000098", mm_agrees_with_ieee_seed_000098),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000099", mm_agrees_with_ieee_seed_000099),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000100", mm_agrees_with_ieee_seed_000100),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000101", mm_agrees_with_ieee_seed_000101),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000102", mm_agrees_with_ieee_seed_000102),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000103", mm_agrees_with_ieee_seed_000103),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000104", mm_agrees_with_ieee_seed_000104),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000105", mm_agrees_with_ieee_seed_000105),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000106", mm_agrees_with_ieee_seed_000106),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000107", mm_agrees_with_ieee_seed_000107),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000108", mm_agrees_with_ieee_seed_000108),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000109", mm_agrees_with_ieee_seed_000109),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000110", mm_agrees_with_ieee_seed_000110),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000111", mm_agrees_with_ieee_seed_000111),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000112", mm_agrees_with_ieee_seed_000112),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000113", mm_agrees_with_ieee_seed_000113),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000114", mm_agrees_with_ieee_seed_000114),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000115", mm_agrees_with_ieee_seed_000115),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000116", mm_agrees_with_ieee_seed_000116),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000117", mm_agrees_with_ieee_seed_000117),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000118", mm_agrees_with_ieee_seed_000118),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000119", mm_agrees_with_ieee_seed_000119),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000120", mm_agrees_with_ieee_seed_000120),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000121", mm_agrees_with_ieee_seed_000121),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000122", mm_agrees_with_ieee_seed_000122),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000123", mm_agrees_with_ieee_seed_000123),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000124", mm_agrees_with_ieee_seed_000124),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000125", mm_agrees_with_ieee_seed_000125),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000126", mm_agrees_with_ieee_seed_000126),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000127", mm_agrees_with_ieee_seed_000127),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000128", mm_agrees_with_ieee_seed_000128),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000129", mm_agrees_with_ieee_seed_000129),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000130", mm_agrees_with_ieee_seed_000130),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000131", mm_agrees_with_ieee_seed_000131),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000132", mm_agrees_with_ieee_seed_000132),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000133", mm_agrees_with_ieee_seed_000133),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000134", mm_agrees_with_ieee_seed_000134),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000135", mm_agrees_with_ieee_seed_000135),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000136", mm_agrees_with_ieee_seed_000136),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000137", mm_agrees_with_ieee_seed_000137),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000138", mm_agrees_with_ieee_seed_000138),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000139", mm_agrees_with_ieee_seed_000139),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000140", mm_agrees_with_ieee_seed_000140),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000141", mm_agrees_with_ieee_seed_000141),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000142", mm_agrees_with_ieee_seed_000142),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000143", mm_agrees_with_ieee_seed_000143),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000144", mm_agrees_with_ieee_seed_000144),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000145", mm_agrees_with_ieee_seed_000145),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000146", mm_agrees_with_ieee_seed_000146),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000147", mm_agrees_with_ieee_seed_000147),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000148", mm_agrees_with_ieee_seed_000148),
        ("property_campaigns::tests::mm_agrees_with_ieee_seed_000149", mm_agrees_with_ieee_seed_000149),
        ("property_campaigns::tests::mm_nan_second_seed_000000", mm_nan_second_seed_000000),
        ("property_campaigns::tests::mm_nan_second_seed_000001", mm_nan_second_seed_000001),
        ("property_campaigns::tests::mm_nan_second_seed_000002", mm_nan_second_seed_000002),
        ("property_campaigns::tests::mm_nan_second_seed_000003", mm_nan_second_seed_000003),
        ("property_campaigns::tests::mm_nan_second_seed_000004", mm_nan_second_seed_000004),
        ("property_campaigns::tests::mm_nan_second_seed_000005", mm_nan_second_seed_000005),
        ("property_campaigns::tests::mm_nan_second_seed_000006", mm_nan_second_seed_000006),
        ("property_campaigns::tests::mm_nan_second_seed_000007", mm_nan_second_seed_000007),
        ("property_campaigns::tests::mm_nan_second_seed_000008", mm_nan_second_seed_000008),
        ("property_campaigns::tests::mm_nan_second_seed_000009", mm_nan_second_seed_000009),
        ("property_campaigns::tests::mm_nan_second_seed_000010", mm_nan_second_seed_000010),
        ("property_campaigns::tests::mm_nan_second_seed_000011", mm_nan_second_seed_000011),
        ("property_campaigns::tests::mm_nan_second_seed_000012", mm_nan_second_seed_000012),
        ("property_campaigns::tests::mm_nan_second_seed_000013", mm_nan_second_seed_000013),
        ("property_campaigns::tests::mm_nan_second_seed_000014", mm_nan_second_seed_000014),
        ("property_campaigns::tests::mm_nan_second_seed_000015", mm_nan_second_seed_000015),
        ("property_campaigns::tests::mm_nan_second_seed_000016", mm_nan_second_seed_000016),
        ("property_campaigns::tests::mm_nan_second_seed_000017", mm_nan_second_seed_000017),
        ("property_campaigns::tests::mm_nan_second_seed_000018", mm_nan_second_seed_000018),
        ("property_campaigns::tests::mm_nan_second_seed_000019", mm_nan_second_seed_000019),
        ("property_campaigns::tests::mm_nan_second_seed_000020", mm_nan_second_seed_000020),
        ("property_campaigns::tests::mm_nan_second_seed_000021", mm_nan_second_seed_000021),
        ("property_campaigns::tests::mm_nan_second_seed_000022", mm_nan_second_seed_000022),
        ("property_campaigns::tests::mm_nan_second_seed_000023", mm_nan_second_seed_000023),
        ("property_campaigns::tests::mm_nan_second_seed_000024", mm_nan_second_seed_000024),
        ("property_campaigns::tests::mm_nan_second_seed_000025", mm_nan_second_seed_000025),
        ("property_campaigns::tests::mm_nan_second_seed_000026", mm_nan_second_seed_000026),
        ("property_campaigns::tests::mm_nan_second_seed_000027", mm_nan_second_seed_000027),
        ("property_campaigns::tests::mm_nan_second_seed_000028", mm_nan_second_seed_000028),
        ("property_campaigns::tests::mm_nan_second_seed_000029", mm_nan_second_seed_000029),
        ("property_campaigns::tests::mm_nan_second_seed_000030", mm_nan_second_seed_000030),
        ("property_campaigns::tests::mm_nan_second_seed_000031", mm_nan_second_seed_000031),
        ("property_campaigns::tests::mm_nan_second_seed_000032", mm_nan_second_seed_000032),
        ("property_campaigns::tests::mm_nan_second_seed_000033", mm_nan_second_seed_000033),
        ("property_campaigns::tests::mm_nan_second_seed_000034", mm_nan_second_seed_000034),
        ("property_campaigns::tests::mm_nan_second_seed_000035", mm_nan_second_seed_000035),
        ("property_campaigns::tests::mm_nan_second_seed_000036", mm_nan_second_seed_000036),
        ("property_campaigns::tests::mm_nan_second_seed_000037", mm_nan_second_seed_000037),
        ("property_campaigns::tests::mm_nan_second_seed_000038", mm_nan_second_seed_000038),
        ("property_campaigns::tests::mm_nan_second_seed_000039", mm_nan_second_seed_000039),
        ("property_campaigns::tests::mm_nan_second_seed_000040", mm_nan_second_seed_000040),
        ("property_campaigns::tests::mm_nan_second_seed_000041", mm_nan_second_seed_000041),
        ("property_campaigns::tests::mm_nan_second_seed_000042", mm_nan_second_seed_000042),
        ("property_campaigns::tests::mm_nan_second_seed_000043", mm_nan_second_seed_000043),
        ("property_campaigns::tests::mm_nan_second_seed_000044", mm_nan_second_seed_000044),
        ("property_campaigns::tests::mm_nan_second_seed_000045", mm_nan_second_seed_000045),
        ("property_campaigns::tests::mm_nan_second_seed_000046", mm_nan_second_seed_000046),
        ("property_campaigns::tests::mm_nan_second_seed_000047", mm_nan_second_seed_000047),
        ("property_campaigns::tests::mm_nan_second_seed_000048", mm_nan_second_seed_000048),
        ("property_campaigns::tests::mm_nan_second_seed_000049", mm_nan_second_seed_000049),
        ("property_campaigns::tests::mm_nan_second_seed_000050", mm_nan_second_seed_000050),
        ("property_campaigns::tests::mm_nan_second_seed_000051", mm_nan_second_seed_000051),
        ("property_campaigns::tests::mm_nan_second_seed_000052", mm_nan_second_seed_000052),
        ("property_campaigns::tests::mm_nan_second_seed_000053", mm_nan_second_seed_000053),
        ("property_campaigns::tests::mm_nan_second_seed_000054", mm_nan_second_seed_000054),
        ("property_campaigns::tests::mm_nan_second_seed_000055", mm_nan_second_seed_000055),
        ("property_campaigns::tests::mm_nan_second_seed_000056", mm_nan_second_seed_000056),
        ("property_campaigns::tests::mm_nan_second_seed_000057", mm_nan_second_seed_000057),
        ("property_campaigns::tests::mm_nan_second_seed_000058", mm_nan_second_seed_000058),
        ("property_campaigns::tests::mm_nan_second_seed_000059", mm_nan_second_seed_000059),
        ("property_campaigns::tests::mm_nan_second_seed_000060", mm_nan_second_seed_000060),
        ("property_campaigns::tests::mm_nan_second_seed_000061", mm_nan_second_seed_000061),
        ("property_campaigns::tests::mm_nan_second_seed_000062", mm_nan_second_seed_000062),
        ("property_campaigns::tests::mm_nan_second_seed_000063", mm_nan_second_seed_000063),
        ("property_campaigns::tests::mm_nan_second_seed_000064", mm_nan_second_seed_000064),
        ("property_campaigns::tests::mm_nan_second_seed_000065", mm_nan_second_seed_000065),
        ("property_campaigns::tests::mm_nan_second_seed_000066", mm_nan_second_seed_000066),
        ("property_campaigns::tests::mm_nan_second_seed_000067", mm_nan_second_seed_000067),
        ("property_campaigns::tests::mm_nan_second_seed_000068", mm_nan_second_seed_000068),
        ("property_campaigns::tests::mm_nan_second_seed_000069", mm_nan_second_seed_000069),
        ("property_campaigns::tests::mm_nan_second_seed_000070", mm_nan_second_seed_000070),
        ("property_campaigns::tests::mm_nan_second_seed_000071", mm_nan_second_seed_000071),
        ("property_campaigns::tests::mm_nan_second_seed_000072", mm_nan_second_seed_000072),
        ("property_campaigns::tests::mm_nan_second_seed_000073", mm_nan_second_seed_000073),
        ("property_campaigns::tests::mm_nan_second_seed_000074", mm_nan_second_seed_000074),
        ("property_campaigns::tests::mm_nan_second_seed_000075", mm_nan_second_seed_000075),
        ("property_campaigns::tests::mm_nan_second_seed_000076", mm_nan_second_seed_000076),
        ("property_campaigns::tests::mm_nan_second_seed_000077", mm_nan_second_seed_000077),
        ("property_campaigns::tests::mm_nan_second_seed_000078", mm_nan_second_seed_000078),
        ("property_campaigns::tests::mm_nan_second_seed_000079", mm_nan_second_seed_000079),
        ("property_campaigns::tests::mm_nan_second_seed_000080", mm_nan_second_seed_000080),
        ("property_campaigns::tests::mm_nan_second_seed_000081", mm_nan_second_seed_000081),
        ("property_campaigns::tests::mm_nan_second_seed_000082", mm_nan_second_seed_000082),
        ("property_campaigns::tests::mm_nan_second_seed_000083", mm_nan_second_seed_000083),
        ("property_campaigns::tests::mm_nan_second_seed_000084", mm_nan_second_seed_000084),
        ("property_campaigns::tests::mm_nan_second_seed_000085", mm_nan_second_seed_000085),
        ("property_campaigns::tests::mm_nan_second_seed_000086", mm_nan_second_seed_000086),
        ("property_campaigns::tests::mm_nan_second_seed_000087", mm_nan_second_seed_000087),
        ("property_campaigns::tests::mm_nan_second_seed_000088", mm_nan_second_seed_000088),
        ("property_campaigns::tests::mm_nan_second_seed_000089", mm_nan_second_seed_000089),
        ("property_campaigns::tests::mm_nan_second_seed_000090", mm_nan_second_seed_000090),
        ("property_campaigns::tests::mm_nan_second_seed_000091", mm_nan_second_seed_000091),
        ("property_campaigns::tests::mm_nan_second_seed_000092", mm_nan_second_seed_000092),
        ("property_campaigns::tests::mm_nan_second_seed_000093", mm_nan_second_seed_000093),
        ("property_campaigns::tests::mm_nan_second_seed_000094", mm_nan_second_seed_000094),
        ("property_campaigns::tests::mm_nan_second_seed_000095", mm_nan_second_seed_000095),
        ("property_campaigns::tests::mm_nan_second_seed_000096", mm_nan_second_seed_000096),
        ("property_campaigns::tests::mm_nan_second_seed_000097", mm_nan_second_seed_000097),
        ("property_campaigns::tests::mm_nan_second_seed_000098", mm_nan_second_seed_000098),
        ("property_campaigns::tests::mm_nan_second_seed_000099", mm_nan_second_seed_000099),
        ("property_campaigns::tests::mm_nan_second_seed_000100", mm_nan_second_seed_000100),
        ("property_campaigns::tests::mm_nan_second_seed_000101", mm_nan_second_seed_000101),
        ("property_campaigns::tests::mm_nan_second_seed_000102", mm_nan_second_seed_000102),
        ("property_campaigns::tests::mm_nan_second_seed_000103", mm_nan_second_seed_000103),
        ("property_campaigns::tests::mm_nan_second_seed_000104", mm_nan_second_seed_000104),
        ("property_campaigns::tests::mm_nan_second_seed_000105", mm_nan_second_seed_000105),
        ("property_campaigns::tests::mm_nan_second_seed_000106", mm_nan_second_seed_000106),
        ("property_campaigns::tests::mm_nan_second_seed_000107", mm_nan_second_seed_000107),
        ("property_campaigns::tests::mm_nan_second_seed_000108", mm_nan_second_seed_000108),
        ("property_campaigns::tests::mm_nan_second_seed_000109", mm_nan_second_seed_000109),
        ("property_campaigns::tests::mm_nan_second_seed_000110", mm_nan_second_seed_000110),
        ("property_campaigns::tests::mm_nan_second_seed_000111", mm_nan_second_seed_000111),
        ("property_campaigns::tests::mm_nan_second_seed_000112", mm_nan_second_seed_000112),
        ("property_campaigns::tests::mm_nan_second_seed_000113", mm_nan_second_seed_000113),
        ("property_campaigns::tests::mm_nan_second_seed_000114", mm_nan_second_seed_000114),
        ("property_campaigns::tests::mm_nan_second_seed_000115", mm_nan_second_seed_000115),
        ("property_campaigns::tests::mm_nan_second_seed_000116", mm_nan_second_seed_000116),
        ("property_campaigns::tests::mm_nan_second_seed_000117", mm_nan_second_seed_000117),
        ("property_campaigns::tests::mm_nan_second_seed_000118", mm_nan_second_seed_000118),
        ("property_campaigns::tests::mm_nan_second_seed_000119", mm_nan_second_seed_000119),
        ("property_campaigns::tests::mm_nan_second_seed_000120", mm_nan_second_seed_000120),
        ("property_campaigns::tests::mm_nan_second_seed_000121", mm_nan_second_seed_000121),
        ("property_campaigns::tests::mm_nan_second_seed_000122", mm_nan_second_seed_000122),
        ("property_campaigns::tests::mm_nan_second_seed_000123", mm_nan_second_seed_000123),
        ("property_campaigns::tests::mm_nan_second_seed_000124", mm_nan_second_seed_000124),
        ("property_campaigns::tests::mm_nan_second_seed_000125", mm_nan_second_seed_000125),
        ("property_campaigns::tests::mm_nan_second_seed_000126", mm_nan_second_seed_000126),
        ("property_campaigns::tests::mm_nan_second_seed_000127", mm_nan_second_seed_000127),
        ("property_campaigns::tests::mm_nan_second_seed_000128", mm_nan_second_seed_000128),
        ("property_campaigns::tests::mm_nan_second_seed_000129", mm_nan_second_seed_000129),
        ("property_campaigns::tests::mm_nan_second_seed_000130", mm_nan_second_seed_000130),
        ("property_campaigns::tests::mm_nan_second_seed_000131", mm_nan_second_seed_000131),
        ("property_campaigns::tests::mm_nan_second_seed_000132", mm_nan_second_seed_000132),
        ("property_campaigns::tests::mm_nan_second_seed_000133", mm_nan_second_seed_000133),
        ("property_campaigns::tests::mm_nan_second_seed_000134", mm_nan_second_seed_000134),
        ("property_campaigns::tests::mm_nan_second_seed_000135", mm_nan_second_seed_000135),
        ("property_campaigns::tests::mm_nan_second_seed_000136", mm_nan_second_seed_000136),
        ("property_campaigns::tests::mm_nan_second_seed_000137", mm_nan_second_seed_000137),
        ("property_campaigns::tests::mm_nan_second_seed_000138", mm_nan_second_seed_000138),
        ("property_campaigns::tests::mm_nan_second_seed_000139", mm_nan_second_seed_000139),
        ("property_campaigns::tests::mm_nan_second_seed_000140", mm_nan_second_seed_000140),
        ("property_campaigns::tests::mm_nan_second_seed_000141", mm_nan_second_seed_000141),
        ("property_campaigns::tests::mm_nan_second_seed_000142", mm_nan_second_seed_000142),
        ("property_campaigns::tests::mm_nan_second_seed_000143", mm_nan_second_seed_000143),
        ("property_campaigns::tests::mm_nan_second_seed_000144", mm_nan_second_seed_000144),
        ("property_campaigns::tests::mm_nan_second_seed_000145", mm_nan_second_seed_000145),
        ("property_campaigns::tests::mm_nan_second_seed_000146", mm_nan_second_seed_000146),
        ("property_campaigns::tests::mm_nan_second_seed_000147", mm_nan_second_seed_000147),
        ("property_campaigns::tests::mm_nan_second_seed_000148", mm_nan_second_seed_000148),
        ("property_campaigns::tests::mm_nan_second_seed_000149", mm_nan_second_seed_000149),
        ("property_campaigns::tests::mm_nan_first_seed_000000", mm_nan_first_seed_000000),
        ("property_campaigns::tests::mm_nan_first_seed_000001", mm_nan_first_seed_000001),
        ("property_campaigns::tests::mm_nan_first_seed_000002", mm_nan_first_seed_000002),
        ("property_campaigns::tests::mm_nan_first_seed_000003", mm_nan_first_seed_000003),
        ("property_campaigns::tests::mm_nan_first_seed_000004", mm_nan_first_seed_000004),
        ("property_campaigns::tests::mm_nan_first_seed_000005", mm_nan_first_seed_000005),
        ("property_campaigns::tests::mm_nan_first_seed_000006", mm_nan_first_seed_000006),
        ("property_campaigns::tests::mm_nan_first_seed_000007", mm_nan_first_seed_000007),
        ("property_campaigns::tests::mm_nan_first_seed_000008", mm_nan_first_seed_000008),
        ("property_campaigns::tests::mm_nan_first_seed_000009", mm_nan_first_seed_000009),
        ("property_campaigns::tests::mm_nan_first_seed_000010", mm_nan_first_seed_000010),
        ("property_campaigns::tests::mm_nan_first_seed_000011", mm_nan_first_seed_000011),
        ("property_campaigns::tests::mm_nan_first_seed_000012", mm_nan_first_seed_000012),
        ("property_campaigns::tests::mm_nan_first_seed_000013", mm_nan_first_seed_000013),
        ("property_campaigns::tests::mm_nan_first_seed_000014", mm_nan_first_seed_000014),
        ("property_campaigns::tests::mm_nan_first_seed_000015", mm_nan_first_seed_000015),
        ("property_campaigns::tests::mm_nan_first_seed_000016", mm_nan_first_seed_000016),
        ("property_campaigns::tests::mm_nan_first_seed_000017", mm_nan_first_seed_000017),
        ("property_campaigns::tests::mm_nan_first_seed_000018", mm_nan_first_seed_000018),
        ("property_campaigns::tests::mm_nan_first_seed_000019", mm_nan_first_seed_000019),
        ("property_campaigns::tests::mm_nan_first_seed_000020", mm_nan_first_seed_000020),
        ("property_campaigns::tests::mm_nan_first_seed_000021", mm_nan_first_seed_000021),
        ("property_campaigns::tests::mm_nan_first_seed_000022", mm_nan_first_seed_000022),
        ("property_campaigns::tests::mm_nan_first_seed_000023", mm_nan_first_seed_000023),
        ("property_campaigns::tests::mm_nan_first_seed_000024", mm_nan_first_seed_000024),
        ("property_campaigns::tests::mm_nan_first_seed_000025", mm_nan_first_seed_000025),
        ("property_campaigns::tests::mm_nan_first_seed_000026", mm_nan_first_seed_000026),
        ("property_campaigns::tests::mm_nan_first_seed_000027", mm_nan_first_seed_000027),
        ("property_campaigns::tests::mm_nan_first_seed_000028", mm_nan_first_seed_000028),
        ("property_campaigns::tests::mm_nan_first_seed_000029", mm_nan_first_seed_000029),
        ("property_campaigns::tests::mm_nan_first_seed_000030", mm_nan_first_seed_000030),
        ("property_campaigns::tests::mm_nan_first_seed_000031", mm_nan_first_seed_000031),
        ("property_campaigns::tests::mm_nan_first_seed_000032", mm_nan_first_seed_000032),
        ("property_campaigns::tests::mm_nan_first_seed_000033", mm_nan_first_seed_000033),
        ("property_campaigns::tests::mm_nan_first_seed_000034", mm_nan_first_seed_000034),
        ("property_campaigns::tests::mm_nan_first_seed_000035", mm_nan_first_seed_000035),
        ("property_campaigns::tests::mm_nan_first_seed_000036", mm_nan_first_seed_000036),
        ("property_campaigns::tests::mm_nan_first_seed_000037", mm_nan_first_seed_000037),
        ("property_campaigns::tests::mm_nan_first_seed_000038", mm_nan_first_seed_000038),
        ("property_campaigns::tests::mm_nan_first_seed_000039", mm_nan_first_seed_000039),
        ("property_campaigns::tests::mm_nan_first_seed_000040", mm_nan_first_seed_000040),
        ("property_campaigns::tests::mm_nan_first_seed_000041", mm_nan_first_seed_000041),
        ("property_campaigns::tests::mm_nan_first_seed_000042", mm_nan_first_seed_000042),
        ("property_campaigns::tests::mm_nan_first_seed_000043", mm_nan_first_seed_000043),
        ("property_campaigns::tests::mm_nan_first_seed_000044", mm_nan_first_seed_000044),
        ("property_campaigns::tests::mm_nan_first_seed_000045", mm_nan_first_seed_000045),
        ("property_campaigns::tests::mm_nan_first_seed_000046", mm_nan_first_seed_000046),
        ("property_campaigns::tests::mm_nan_first_seed_000047", mm_nan_first_seed_000047),
        ("property_campaigns::tests::mm_nan_first_seed_000048", mm_nan_first_seed_000048),
        ("property_campaigns::tests::mm_nan_first_seed_000049", mm_nan_first_seed_000049),
        ("property_campaigns::tests::mm_nan_first_seed_000050", mm_nan_first_seed_000050),
        ("property_campaigns::tests::mm_nan_first_seed_000051", mm_nan_first_seed_000051),
        ("property_campaigns::tests::mm_nan_first_seed_000052", mm_nan_first_seed_000052),
        ("property_campaigns::tests::mm_nan_first_seed_000053", mm_nan_first_seed_000053),
        ("property_campaigns::tests::mm_nan_first_seed_000054", mm_nan_first_seed_000054),
        ("property_campaigns::tests::mm_nan_first_seed_000055", mm_nan_first_seed_000055),
        ("property_campaigns::tests::mm_nan_first_seed_000056", mm_nan_first_seed_000056),
        ("property_campaigns::tests::mm_nan_first_seed_000057", mm_nan_first_seed_000057),
        ("property_campaigns::tests::mm_nan_first_seed_000058", mm_nan_first_seed_000058),
        ("property_campaigns::tests::mm_nan_first_seed_000059", mm_nan_first_seed_000059),
        ("property_campaigns::tests::mm_nan_first_seed_000060", mm_nan_first_seed_000060),
        ("property_campaigns::tests::mm_nan_first_seed_000061", mm_nan_first_seed_000061),
        ("property_campaigns::tests::mm_nan_first_seed_000062", mm_nan_first_seed_000062),
        ("property_campaigns::tests::mm_nan_first_seed_000063", mm_nan_first_seed_000063),
        ("property_campaigns::tests::mm_nan_first_seed_000064", mm_nan_first_seed_000064),
        ("property_campaigns::tests::mm_nan_first_seed_000065", mm_nan_first_seed_000065),
        ("property_campaigns::tests::mm_nan_first_seed_000066", mm_nan_first_seed_000066),
        ("property_campaigns::tests::mm_nan_first_seed_000067", mm_nan_first_seed_000067),
        ("property_campaigns::tests::mm_nan_first_seed_000068", mm_nan_first_seed_000068),
        ("property_campaigns::tests::mm_nan_first_seed_000069", mm_nan_first_seed_000069),
        ("property_campaigns::tests::mm_nan_first_seed_000070", mm_nan_first_seed_000070),
        ("property_campaigns::tests::mm_nan_first_seed_000071", mm_nan_first_seed_000071),
        ("property_campaigns::tests::mm_nan_first_seed_000072", mm_nan_first_seed_000072),
        ("property_campaigns::tests::mm_nan_first_seed_000073", mm_nan_first_seed_000073),
        ("property_campaigns::tests::mm_nan_first_seed_000074", mm_nan_first_seed_000074),
        ("property_campaigns::tests::mm_nan_first_seed_000075", mm_nan_first_seed_000075),
        ("property_campaigns::tests::mm_nan_first_seed_000076", mm_nan_first_seed_000076),
        ("property_campaigns::tests::mm_nan_first_seed_000077", mm_nan_first_seed_000077),
        ("property_campaigns::tests::mm_nan_first_seed_000078", mm_nan_first_seed_000078),
        ("property_campaigns::tests::mm_nan_first_seed_000079", mm_nan_first_seed_000079),
        ("property_campaigns::tests::mm_nan_first_seed_000080", mm_nan_first_seed_000080),
        ("property_campaigns::tests::mm_nan_first_seed_000081", mm_nan_first_seed_000081),
        ("property_campaigns::tests::mm_nan_first_seed_000082", mm_nan_first_seed_000082),
        ("property_campaigns::tests::mm_nan_first_seed_000083", mm_nan_first_seed_000083),
        ("property_campaigns::tests::mm_nan_first_seed_000084", mm_nan_first_seed_000084),
        ("property_campaigns::tests::mm_nan_first_seed_000085", mm_nan_first_seed_000085),
        ("property_campaigns::tests::mm_nan_first_seed_000086", mm_nan_first_seed_000086),
        ("property_campaigns::tests::mm_nan_first_seed_000087", mm_nan_first_seed_000087),
        ("property_campaigns::tests::mm_nan_first_seed_000088", mm_nan_first_seed_000088),
        ("property_campaigns::tests::mm_nan_first_seed_000089", mm_nan_first_seed_000089),
        ("property_campaigns::tests::mm_nan_first_seed_000090", mm_nan_first_seed_000090),
        ("property_campaigns::tests::mm_nan_first_seed_000091", mm_nan_first_seed_000091),
        ("property_campaigns::tests::mm_nan_first_seed_000092", mm_nan_first_seed_000092),
        ("property_campaigns::tests::mm_nan_first_seed_000093", mm_nan_first_seed_000093),
        ("property_campaigns::tests::mm_nan_first_seed_000094", mm_nan_first_seed_000094),
        ("property_campaigns::tests::mm_nan_first_seed_000095", mm_nan_first_seed_000095),
        ("property_campaigns::tests::mm_nan_first_seed_000096", mm_nan_first_seed_000096),
        ("property_campaigns::tests::mm_nan_first_seed_000097", mm_nan_first_seed_000097),
        ("property_campaigns::tests::mm_nan_first_seed_000098", mm_nan_first_seed_000098),
        ("property_campaigns::tests::mm_nan_first_seed_000099", mm_nan_first_seed_000099),
        ("property_campaigns::tests::mm_nan_first_seed_000100", mm_nan_first_seed_000100),
        ("property_campaigns::tests::mm_nan_first_seed_000101", mm_nan_first_seed_000101),
        ("property_campaigns::tests::mm_nan_first_seed_000102", mm_nan_first_seed_000102),
        ("property_campaigns::tests::mm_nan_first_seed_000103", mm_nan_first_seed_000103),
        ("property_campaigns::tests::mm_nan_first_seed_000104", mm_nan_first_seed_000104),
        ("property_campaigns::tests::mm_nan_first_seed_000105", mm_nan_first_seed_000105),
        ("property_campaigns::tests::mm_nan_first_seed_000106", mm_nan_first_seed_000106),
        ("property_campaigns::tests::mm_nan_first_seed_000107", mm_nan_first_seed_000107),
        ("property_campaigns::tests::mm_nan_first_seed_000108", mm_nan_first_seed_000108),
        ("property_campaigns::tests::mm_nan_first_seed_000109", mm_nan_first_seed_000109),
        ("property_campaigns::tests::mm_nan_first_seed_000110", mm_nan_first_seed_000110),
        ("property_campaigns::tests::mm_nan_first_seed_000111", mm_nan_first_seed_000111),
        ("property_campaigns::tests::mm_nan_first_seed_000112", mm_nan_first_seed_000112),
        ("property_campaigns::tests::mm_nan_first_seed_000113", mm_nan_first_seed_000113),
        ("property_campaigns::tests::mm_nan_first_seed_000114", mm_nan_first_seed_000114),
        ("property_campaigns::tests::mm_nan_first_seed_000115", mm_nan_first_seed_000115),
        ("property_campaigns::tests::mm_nan_first_seed_000116", mm_nan_first_seed_000116),
        ("property_campaigns::tests::mm_nan_first_seed_000117", mm_nan_first_seed_000117),
        ("property_campaigns::tests::mm_nan_first_seed_000118", mm_nan_first_seed_000118),
        ("property_campaigns::tests::mm_nan_first_seed_000119", mm_nan_first_seed_000119),
        ("property_campaigns::tests::mm_nan_first_seed_000120", mm_nan_first_seed_000120),
        ("property_campaigns::tests::mm_nan_first_seed_000121", mm_nan_first_seed_000121),
        ("property_campaigns::tests::mm_nan_first_seed_000122", mm_nan_first_seed_000122),
        ("property_campaigns::tests::mm_nan_first_seed_000123", mm_nan_first_seed_000123),
        ("property_campaigns::tests::mm_nan_first_seed_000124", mm_nan_first_seed_000124),
        ("property_campaigns::tests::mm_nan_first_seed_000125", mm_nan_first_seed_000125),
        ("property_campaigns::tests::mm_nan_first_seed_000126", mm_nan_first_seed_000126),
        ("property_campaigns::tests::mm_nan_first_seed_000127", mm_nan_first_seed_000127),
        ("property_campaigns::tests::mm_nan_first_seed_000128", mm_nan_first_seed_000128),
        ("property_campaigns::tests::mm_nan_first_seed_000129", mm_nan_first_seed_000129),
        ("property_campaigns::tests::mm_nan_first_seed_000130", mm_nan_first_seed_000130),
        ("property_campaigns::tests::mm_nan_first_seed_000131", mm_nan_first_seed_000131),
        ("property_campaigns::tests::mm_nan_first_seed_000132", mm_nan_first_seed_000132),
        ("property_campaigns::tests::mm_nan_first_seed_000133", mm_nan_first_seed_000133),
        ("property_campaigns::tests::mm_nan_first_seed_000134", mm_nan_first_seed_000134),
        ("property_campaigns::tests::mm_nan_first_seed_000135", mm_nan_first_seed_000135),
        ("property_campaigns::tests::mm_nan_first_seed_000136", mm_nan_first_seed_000136),
        ("property_campaigns::tests::mm_nan_first_seed_000137", mm_nan_first_seed_000137),
        ("property_campaigns::tests::mm_nan_first_seed_000138", mm_nan_first_seed_000138),
        ("property_campaigns::tests::mm_nan_first_seed_000139", mm_nan_first_seed_000139),
        ("property_campaigns::tests::mm_nan_first_seed_000140", mm_nan_first_seed_000140),
        ("property_campaigns::tests::mm_nan_first_seed_000141", mm_nan_first_seed_000141),
        ("property_campaigns::tests::mm_nan_first_seed_000142", mm_nan_first_seed_000142),
        ("property_campaigns::tests::mm_nan_first_seed_000143", mm_nan_first_seed_000143),
        ("property_campaigns::tests::mm_nan_first_seed_000144", mm_nan_first_seed_000144),
        ("property_campaigns::tests::mm_nan_first_seed_000145", mm_nan_first_seed_000145),
        ("property_campaigns::tests::mm_nan_first_seed_000146", mm_nan_first_seed_000146),
        ("property_campaigns::tests::mm_nan_first_seed_000147", mm_nan_first_seed_000147),
        ("property_campaigns::tests::mm_nan_first_seed_000148", mm_nan_first_seed_000148),
        ("property_campaigns::tests::mm_nan_first_seed_000149", mm_nan_first_seed_000149),
        ("property_campaigns::tests::mm_signed_zero_seed_000000", mm_signed_zero_seed_000000),
        ("property_campaigns::tests::mm_signed_zero_seed_000001", mm_signed_zero_seed_000001),
        ("property_campaigns::tests::mm_signed_zero_seed_000002", mm_signed_zero_seed_000002),
        ("property_campaigns::tests::mm_signed_zero_seed_000003", mm_signed_zero_seed_000003),
        ("property_campaigns::tests::mm_signed_zero_seed_000004", mm_signed_zero_seed_000004),
        ("property_campaigns::tests::mm_signed_zero_seed_000005", mm_signed_zero_seed_000005),
        ("property_campaigns::tests::mm_signed_zero_seed_000006", mm_signed_zero_seed_000006),
        ("property_campaigns::tests::mm_signed_zero_seed_000007", mm_signed_zero_seed_000007),
        ("property_campaigns::tests::mm_signed_zero_seed_000008", mm_signed_zero_seed_000008),
        ("property_campaigns::tests::mm_signed_zero_seed_000009", mm_signed_zero_seed_000009),
        ("property_campaigns::tests::mm_signed_zero_seed_000010", mm_signed_zero_seed_000010),
        ("property_campaigns::tests::mm_signed_zero_seed_000011", mm_signed_zero_seed_000011),
        ("property_campaigns::tests::mm_signed_zero_seed_000012", mm_signed_zero_seed_000012),
        ("property_campaigns::tests::mm_signed_zero_seed_000013", mm_signed_zero_seed_000013),
        ("property_campaigns::tests::mm_signed_zero_seed_000014", mm_signed_zero_seed_000014),
        ("property_campaigns::tests::mm_signed_zero_seed_000015", mm_signed_zero_seed_000015),
        ("property_campaigns::tests::mm_signed_zero_seed_000016", mm_signed_zero_seed_000016),
        ("property_campaigns::tests::mm_signed_zero_seed_000017", mm_signed_zero_seed_000017),
        ("property_campaigns::tests::mm_signed_zero_seed_000018", mm_signed_zero_seed_000018),
        ("property_campaigns::tests::mm_signed_zero_seed_000019", mm_signed_zero_seed_000019),
        ("property_campaigns::tests::mm_signed_zero_seed_000020", mm_signed_zero_seed_000020),
        ("property_campaigns::tests::mm_signed_zero_seed_000021", mm_signed_zero_seed_000021),
        ("property_campaigns::tests::mm_signed_zero_seed_000022", mm_signed_zero_seed_000022),
        ("property_campaigns::tests::mm_signed_zero_seed_000023", mm_signed_zero_seed_000023),
        ("property_campaigns::tests::mm_signed_zero_seed_000024", mm_signed_zero_seed_000024),
        ("property_campaigns::tests::mm_signed_zero_seed_000025", mm_signed_zero_seed_000025),
        ("property_campaigns::tests::mm_signed_zero_seed_000026", mm_signed_zero_seed_000026),
        ("property_campaigns::tests::mm_signed_zero_seed_000027", mm_signed_zero_seed_000027),
        ("property_campaigns::tests::mm_signed_zero_seed_000028", mm_signed_zero_seed_000028),
        ("property_campaigns::tests::mm_signed_zero_seed_000029", mm_signed_zero_seed_000029),
        ("property_campaigns::tests::mm_signed_zero_seed_000030", mm_signed_zero_seed_000030),
        ("property_campaigns::tests::mm_signed_zero_seed_000031", mm_signed_zero_seed_000031),
        ("property_campaigns::tests::mm_signed_zero_seed_000032", mm_signed_zero_seed_000032),
        ("property_campaigns::tests::mm_signed_zero_seed_000033", mm_signed_zero_seed_000033),
        ("property_campaigns::tests::mm_signed_zero_seed_000034", mm_signed_zero_seed_000034),
        ("property_campaigns::tests::mm_signed_zero_seed_000035", mm_signed_zero_seed_000035),
        ("property_campaigns::tests::mm_signed_zero_seed_000036", mm_signed_zero_seed_000036),
        ("property_campaigns::tests::mm_signed_zero_seed_000037", mm_signed_zero_seed_000037),
        ("property_campaigns::tests::mm_signed_zero_seed_000038", mm_signed_zero_seed_000038),
        ("property_campaigns::tests::mm_signed_zero_seed_000039", mm_signed_zero_seed_000039),
        ("property_campaigns::tests::mm_signed_zero_seed_000040", mm_signed_zero_seed_000040),
        ("property_campaigns::tests::mm_signed_zero_seed_000041", mm_signed_zero_seed_000041),
        ("property_campaigns::tests::mm_signed_zero_seed_000042", mm_signed_zero_seed_000042),
        ("property_campaigns::tests::mm_signed_zero_seed_000043", mm_signed_zero_seed_000043),
        ("property_campaigns::tests::mm_signed_zero_seed_000044", mm_signed_zero_seed_000044),
        ("property_campaigns::tests::mm_signed_zero_seed_000045", mm_signed_zero_seed_000045),
        ("property_campaigns::tests::mm_signed_zero_seed_000046", mm_signed_zero_seed_000046),
        ("property_campaigns::tests::mm_signed_zero_seed_000047", mm_signed_zero_seed_000047),
        ("property_campaigns::tests::mm_signed_zero_seed_000048", mm_signed_zero_seed_000048),
        ("property_campaigns::tests::mm_signed_zero_seed_000049", mm_signed_zero_seed_000049),
        ("property_campaigns::tests::mm_signed_zero_seed_000050", mm_signed_zero_seed_000050),
        ("property_campaigns::tests::mm_signed_zero_seed_000051", mm_signed_zero_seed_000051),
        ("property_campaigns::tests::mm_signed_zero_seed_000052", mm_signed_zero_seed_000052),
        ("property_campaigns::tests::mm_signed_zero_seed_000053", mm_signed_zero_seed_000053),
        ("property_campaigns::tests::mm_signed_zero_seed_000054", mm_signed_zero_seed_000054),
        ("property_campaigns::tests::mm_signed_zero_seed_000055", mm_signed_zero_seed_000055),
        ("property_campaigns::tests::mm_signed_zero_seed_000056", mm_signed_zero_seed_000056),
        ("property_campaigns::tests::mm_signed_zero_seed_000057", mm_signed_zero_seed_000057),
        ("property_campaigns::tests::mm_signed_zero_seed_000058", mm_signed_zero_seed_000058),
        ("property_campaigns::tests::mm_signed_zero_seed_000059", mm_signed_zero_seed_000059),
        ("property_campaigns::tests::mm_signed_zero_seed_000060", mm_signed_zero_seed_000060),
        ("property_campaigns::tests::mm_signed_zero_seed_000061", mm_signed_zero_seed_000061),
        ("property_campaigns::tests::mm_signed_zero_seed_000062", mm_signed_zero_seed_000062),
        ("property_campaigns::tests::mm_signed_zero_seed_000063", mm_signed_zero_seed_000063),
        ("property_campaigns::tests::mm_signed_zero_seed_000064", mm_signed_zero_seed_000064),
        ("property_campaigns::tests::mm_signed_zero_seed_000065", mm_signed_zero_seed_000065),
        ("property_campaigns::tests::mm_signed_zero_seed_000066", mm_signed_zero_seed_000066),
        ("property_campaigns::tests::mm_signed_zero_seed_000067", mm_signed_zero_seed_000067),
        ("property_campaigns::tests::mm_signed_zero_seed_000068", mm_signed_zero_seed_000068),
        ("property_campaigns::tests::mm_signed_zero_seed_000069", mm_signed_zero_seed_000069),
        ("property_campaigns::tests::mm_signed_zero_seed_000070", mm_signed_zero_seed_000070),
        ("property_campaigns::tests::mm_signed_zero_seed_000071", mm_signed_zero_seed_000071),
        ("property_campaigns::tests::mm_signed_zero_seed_000072", mm_signed_zero_seed_000072),
        ("property_campaigns::tests::mm_signed_zero_seed_000073", mm_signed_zero_seed_000073),
        ("property_campaigns::tests::mm_signed_zero_seed_000074", mm_signed_zero_seed_000074),
        ("property_campaigns::tests::mm_signed_zero_seed_000075", mm_signed_zero_seed_000075),
        ("property_campaigns::tests::mm_signed_zero_seed_000076", mm_signed_zero_seed_000076),
        ("property_campaigns::tests::mm_signed_zero_seed_000077", mm_signed_zero_seed_000077),
        ("property_campaigns::tests::mm_signed_zero_seed_000078", mm_signed_zero_seed_000078),
        ("property_campaigns::tests::mm_signed_zero_seed_000079", mm_signed_zero_seed_000079),
        ("property_campaigns::tests::mm_signed_zero_seed_000080", mm_signed_zero_seed_000080),
        ("property_campaigns::tests::mm_signed_zero_seed_000081", mm_signed_zero_seed_000081),
        ("property_campaigns::tests::mm_signed_zero_seed_000082", mm_signed_zero_seed_000082),
        ("property_campaigns::tests::mm_signed_zero_seed_000083", mm_signed_zero_seed_000083),
        ("property_campaigns::tests::mm_signed_zero_seed_000084", mm_signed_zero_seed_000084),
        ("property_campaigns::tests::mm_signed_zero_seed_000085", mm_signed_zero_seed_000085),
        ("property_campaigns::tests::mm_signed_zero_seed_000086", mm_signed_zero_seed_000086),
        ("property_campaigns::tests::mm_signed_zero_seed_000087", mm_signed_zero_seed_000087),
        ("property_campaigns::tests::mm_signed_zero_seed_000088", mm_signed_zero_seed_000088),
        ("property_campaigns::tests::mm_signed_zero_seed_000089", mm_signed_zero_seed_000089),
        ("property_campaigns::tests::mm_signed_zero_seed_000090", mm_signed_zero_seed_000090),
        ("property_campaigns::tests::mm_signed_zero_seed_000091", mm_signed_zero_seed_000091),
        ("property_campaigns::tests::mm_signed_zero_seed_000092", mm_signed_zero_seed_000092),
        ("property_campaigns::tests::mm_signed_zero_seed_000093", mm_signed_zero_seed_000093),
        ("property_campaigns::tests::mm_signed_zero_seed_000094", mm_signed_zero_seed_000094),
        ("property_campaigns::tests::mm_signed_zero_seed_000095", mm_signed_zero_seed_000095),
        ("property_campaigns::tests::mm_signed_zero_seed_000096", mm_signed_zero_seed_000096),
        ("property_campaigns::tests::mm_signed_zero_seed_000097", mm_signed_zero_seed_000097),
        ("property_campaigns::tests::mm_signed_zero_seed_000098", mm_signed_zero_seed_000098),
        ("property_campaigns::tests::mm_signed_zero_seed_000099", mm_signed_zero_seed_000099),
        ("property_campaigns::tests::sm_scale_invariance_seed_000000", sm_scale_invariance_seed_000000),
        ("property_campaigns::tests::sm_scale_invariance_seed_000001", sm_scale_invariance_seed_000001),
        ("property_campaigns::tests::sm_scale_invariance_seed_000002", sm_scale_invariance_seed_000002),
        ("property_campaigns::tests::sm_scale_invariance_seed_000003", sm_scale_invariance_seed_000003),
        ("property_campaigns::tests::sm_scale_invariance_seed_000004", sm_scale_invariance_seed_000004),
        ("property_campaigns::tests::sm_scale_invariance_seed_000005", sm_scale_invariance_seed_000005),
        ("property_campaigns::tests::sm_scale_invariance_seed_000006", sm_scale_invariance_seed_000006),
        ("property_campaigns::tests::sm_scale_invariance_seed_000007", sm_scale_invariance_seed_000007),
        ("property_campaigns::tests::sm_scale_invariance_seed_000008", sm_scale_invariance_seed_000008),
        ("property_campaigns::tests::sm_scale_invariance_seed_000009", sm_scale_invariance_seed_000009),
        ("property_campaigns::tests::sm_scale_invariance_seed_000010", sm_scale_invariance_seed_000010),
        ("property_campaigns::tests::sm_scale_invariance_seed_000011", sm_scale_invariance_seed_000011),
        ("property_campaigns::tests::sm_scale_invariance_seed_000012", sm_scale_invariance_seed_000012),
        ("property_campaigns::tests::sm_scale_invariance_seed_000013", sm_scale_invariance_seed_000013),
        ("property_campaigns::tests::sm_scale_invariance_seed_000014", sm_scale_invariance_seed_000014),
        ("property_campaigns::tests::sm_scale_invariance_seed_000015", sm_scale_invariance_seed_000015),
        ("property_campaigns::tests::sm_scale_invariance_seed_000016", sm_scale_invariance_seed_000016),
        ("property_campaigns::tests::sm_scale_invariance_seed_000017", sm_scale_invariance_seed_000017),
        ("property_campaigns::tests::sm_scale_invariance_seed_000018", sm_scale_invariance_seed_000018),
        ("property_campaigns::tests::sm_scale_invariance_seed_000019", sm_scale_invariance_seed_000019),
        ("property_campaigns::tests::sm_scale_invariance_seed_000020", sm_scale_invariance_seed_000020),
        ("property_campaigns::tests::sm_scale_invariance_seed_000021", sm_scale_invariance_seed_000021),
        ("property_campaigns::tests::sm_scale_invariance_seed_000022", sm_scale_invariance_seed_000022),
        ("property_campaigns::tests::sm_scale_invariance_seed_000023", sm_scale_invariance_seed_000023),
        ("property_campaigns::tests::sm_scale_invariance_seed_000024", sm_scale_invariance_seed_000024),
        ("property_campaigns::tests::sm_scale_invariance_seed_000025", sm_scale_invariance_seed_000025),
        ("property_campaigns::tests::sm_scale_invariance_seed_000026", sm_scale_invariance_seed_000026),
        ("property_campaigns::tests::sm_scale_invariance_seed_000027", sm_scale_invariance_seed_000027),
        ("property_campaigns::tests::sm_scale_invariance_seed_000028", sm_scale_invariance_seed_000028),
        ("property_campaigns::tests::sm_scale_invariance_seed_000029", sm_scale_invariance_seed_000029),
        ("property_campaigns::tests::sm_scale_invariance_seed_000030", sm_scale_invariance_seed_000030),
        ("property_campaigns::tests::sm_scale_invariance_seed_000031", sm_scale_invariance_seed_000031),
        ("property_campaigns::tests::sm_scale_invariance_seed_000032", sm_scale_invariance_seed_000032),
        ("property_campaigns::tests::sm_scale_invariance_seed_000033", sm_scale_invariance_seed_000033),
        ("property_campaigns::tests::sm_scale_invariance_seed_000034", sm_scale_invariance_seed_000034),
        ("property_campaigns::tests::sm_scale_invariance_seed_000035", sm_scale_invariance_seed_000035),
        ("property_campaigns::tests::sm_scale_invariance_seed_000036", sm_scale_invariance_seed_000036),
        ("property_campaigns::tests::sm_scale_invariance_seed_000037", sm_scale_invariance_seed_000037),
        ("property_campaigns::tests::sm_scale_invariance_seed_000038", sm_scale_invariance_seed_000038),
        ("property_campaigns::tests::sm_scale_invariance_seed_000039", sm_scale_invariance_seed_000039),
        ("property_campaigns::tests::sm_scale_invariance_seed_000040", sm_scale_invariance_seed_000040),
        ("property_campaigns::tests::sm_scale_invariance_seed_000041", sm_scale_invariance_seed_000041),
        ("property_campaigns::tests::sm_scale_invariance_seed_000042", sm_scale_invariance_seed_000042),
        ("property_campaigns::tests::sm_scale_invariance_seed_000043", sm_scale_invariance_seed_000043),
        ("property_campaigns::tests::sm_scale_invariance_seed_000044", sm_scale_invariance_seed_000044),
        ("property_campaigns::tests::sm_scale_invariance_seed_000045", sm_scale_invariance_seed_000045),
        ("property_campaigns::tests::sm_scale_invariance_seed_000046", sm_scale_invariance_seed_000046),
        ("property_campaigns::tests::sm_scale_invariance_seed_000047", sm_scale_invariance_seed_000047),
        ("property_campaigns::tests::sm_scale_invariance_seed_000048", sm_scale_invariance_seed_000048),
        ("property_campaigns::tests::sm_scale_invariance_seed_000049", sm_scale_invariance_seed_000049),
        ("property_campaigns::tests::sm_scale_invariance_seed_000050", sm_scale_invariance_seed_000050),
        ("property_campaigns::tests::sm_scale_invariance_seed_000051", sm_scale_invariance_seed_000051),
        ("property_campaigns::tests::sm_scale_invariance_seed_000052", sm_scale_invariance_seed_000052),
        ("property_campaigns::tests::sm_scale_invariance_seed_000053", sm_scale_invariance_seed_000053),
        ("property_campaigns::tests::sm_scale_invariance_seed_000054", sm_scale_invariance_seed_000054),
        ("property_campaigns::tests::sm_scale_invariance_seed_000055", sm_scale_invariance_seed_000055),
        ("property_campaigns::tests::sm_scale_invariance_seed_000056", sm_scale_invariance_seed_000056),
        ("property_campaigns::tests::sm_scale_invariance_seed_000057", sm_scale_invariance_seed_000057),
        ("property_campaigns::tests::sm_scale_invariance_seed_000058", sm_scale_invariance_seed_000058),
        ("property_campaigns::tests::sm_scale_invariance_seed_000059", sm_scale_invariance_seed_000059),
        ("property_campaigns::tests::sm_scale_invariance_seed_000060", sm_scale_invariance_seed_000060),
        ("property_campaigns::tests::sm_scale_invariance_seed_000061", sm_scale_invariance_seed_000061),
        ("property_campaigns::tests::sm_scale_invariance_seed_000062", sm_scale_invariance_seed_000062),
        ("property_campaigns::tests::sm_scale_invariance_seed_000063", sm_scale_invariance_seed_000063),
        ("property_campaigns::tests::sm_scale_invariance_seed_000064", sm_scale_invariance_seed_000064),
        ("property_campaigns::tests::sm_scale_invariance_seed_000065", sm_scale_invariance_seed_000065),
        ("property_campaigns::tests::sm_scale_invariance_seed_000066", sm_scale_invariance_seed_000066),
        ("property_campaigns::tests::sm_scale_invariance_seed_000067", sm_scale_invariance_seed_000067),
        ("property_campaigns::tests::sm_scale_invariance_seed_000068", sm_scale_invariance_seed_000068),
        ("property_campaigns::tests::sm_scale_invariance_seed_000069", sm_scale_invariance_seed_000069),
        ("property_campaigns::tests::sm_scale_invariance_seed_000070", sm_scale_invariance_seed_000070),
        ("property_campaigns::tests::sm_scale_invariance_seed_000071", sm_scale_invariance_seed_000071),
        ("property_campaigns::tests::sm_scale_invariance_seed_000072", sm_scale_invariance_seed_000072),
        ("property_campaigns::tests::sm_scale_invariance_seed_000073", sm_scale_invariance_seed_000073),
        ("property_campaigns::tests::sm_scale_invariance_seed_000074", sm_scale_invariance_seed_000074),
        ("property_campaigns::tests::sm_scale_invariance_seed_000075", sm_scale_invariance_seed_000075),
        ("property_campaigns::tests::sm_scale_invariance_seed_000076", sm_scale_invariance_seed_000076),
        ("property_campaigns::tests::sm_scale_invariance_seed_000077", sm_scale_invariance_seed_000077),
        ("property_campaigns::tests::sm_scale_invariance_seed_000078", sm_scale_invariance_seed_000078),
        ("property_campaigns::tests::sm_scale_invariance_seed_000079", sm_scale_invariance_seed_000079),
        ("property_campaigns::tests::sm_scale_invariance_seed_000080", sm_scale_invariance_seed_000080),
        ("property_campaigns::tests::sm_scale_invariance_seed_000081", sm_scale_invariance_seed_000081),
        ("property_campaigns::tests::sm_scale_invariance_seed_000082", sm_scale_invariance_seed_000082),
        ("property_campaigns::tests::sm_scale_invariance_seed_000083", sm_scale_invariance_seed_000083),
        ("property_campaigns::tests::sm_scale_invariance_seed_000084", sm_scale_invariance_seed_000084),
        ("property_campaigns::tests::sm_scale_invariance_seed_000085", sm_scale_invariance_seed_000085),
        ("property_campaigns::tests::sm_scale_invariance_seed_000086", sm_scale_invariance_seed_000086),
        ("property_campaigns::tests::sm_scale_invariance_seed_000087", sm_scale_invariance_seed_000087),
        ("property_campaigns::tests::sm_scale_invariance_seed_000088", sm_scale_invariance_seed_000088),
        ("property_campaigns::tests::sm_scale_invariance_seed_000089", sm_scale_invariance_seed_000089),
        ("property_campaigns::tests::sm_scale_invariance_seed_000090", sm_scale_invariance_seed_000090),
        ("property_campaigns::tests::sm_scale_invariance_seed_000091", sm_scale_invariance_seed_000091),
        ("property_campaigns::tests::sm_scale_invariance_seed_000092", sm_scale_invariance_seed_000092),
        ("property_campaigns::tests::sm_scale_invariance_seed_000093", sm_scale_invariance_seed_000093),
        ("property_campaigns::tests::sm_scale_invariance_seed_000094", sm_scale_invariance_seed_000094),
        ("property_campaigns::tests::sm_scale_invariance_seed_000095", sm_scale_invariance_seed_000095),
        ("property_campaigns::tests::sm_scale_invariance_seed_000096", sm_scale_invariance_seed_000096),
        ("property_campaigns::tests::sm_scale_invariance_seed_000097", sm_scale_invariance_seed_000097),
        ("property_campaigns::tests::sm_scale_invariance_seed_000098", sm_scale_invariance_seed_000098),
        ("property_campaigns::tests::sm_scale_invariance_seed_000099", sm_scale_invariance_seed_000099),
        ("property_campaigns::tests::sm_scale_invariance_seed_000100", sm_scale_invariance_seed_000100),
        ("property_campaigns::tests::sm_scale_invariance_seed_000101", sm_scale_invariance_seed_000101),
        ("property_campaigns::tests::sm_scale_invariance_seed_000102", sm_scale_invariance_seed_000102),
        ("property_campaigns::tests::sm_scale_invariance_seed_000103", sm_scale_invariance_seed_000103),
        ("property_campaigns::tests::sm_scale_invariance_seed_000104", sm_scale_invariance_seed_000104),
        ("property_campaigns::tests::sm_scale_invariance_seed_000105", sm_scale_invariance_seed_000105),
        ("property_campaigns::tests::sm_scale_invariance_seed_000106", sm_scale_invariance_seed_000106),
        ("property_campaigns::tests::sm_scale_invariance_seed_000107", sm_scale_invariance_seed_000107),
        ("property_campaigns::tests::sm_scale_invariance_seed_000108", sm_scale_invariance_seed_000108),
        ("property_campaigns::tests::sm_scale_invariance_seed_000109", sm_scale_invariance_seed_000109),
        ("property_campaigns::tests::sm_scale_invariance_seed_000110", sm_scale_invariance_seed_000110),
        ("property_campaigns::tests::sm_scale_invariance_seed_000111", sm_scale_invariance_seed_000111),
        ("property_campaigns::tests::sm_scale_invariance_seed_000112", sm_scale_invariance_seed_000112),
        ("property_campaigns::tests::sm_scale_invariance_seed_000113", sm_scale_invariance_seed_000113),
        ("property_campaigns::tests::sm_scale_invariance_seed_000114", sm_scale_invariance_seed_000114),
        ("property_campaigns::tests::sm_scale_invariance_seed_000115", sm_scale_invariance_seed_000115),
        ("property_campaigns::tests::sm_scale_invariance_seed_000116", sm_scale_invariance_seed_000116),
        ("property_campaigns::tests::sm_scale_invariance_seed_000117", sm_scale_invariance_seed_000117),
        ("property_campaigns::tests::sm_scale_invariance_seed_000118", sm_scale_invariance_seed_000118),
        ("property_campaigns::tests::sm_scale_invariance_seed_000119", sm_scale_invariance_seed_000119),
        ("property_campaigns::tests::sm_scale_invariance_seed_000120", sm_scale_invariance_seed_000120),
        ("property_campaigns::tests::sm_scale_invariance_seed_000121", sm_scale_invariance_seed_000121),
        ("property_campaigns::tests::sm_scale_invariance_seed_000122", sm_scale_invariance_seed_000122),
        ("property_campaigns::tests::sm_scale_invariance_seed_000123", sm_scale_invariance_seed_000123),
        ("property_campaigns::tests::sm_scale_invariance_seed_000124", sm_scale_invariance_seed_000124),
        ("property_campaigns::tests::sm_scale_invariance_seed_000125", sm_scale_invariance_seed_000125),
        ("property_campaigns::tests::sm_scale_invariance_seed_000126", sm_scale_invariance_seed_000126),
        ("property_campaigns::tests::sm_scale_invariance_seed_000127", sm_scale_invariance_seed_000127),
        ("property_campaigns::tests::sm_scale_invariance_seed_000128", sm_scale_invariance_seed_000128),
        ("property_campaigns::tests::sm_scale_invariance_seed_000129", sm_scale_invariance_seed_000129),
        ("property_campaigns::tests::sm_scale_invariance_seed_000130", sm_scale_invariance_seed_000130),
        ("property_campaigns::tests::sm_scale_invariance_seed_000131", sm_scale_invariance_seed_000131),
        ("property_campaigns::tests::sm_scale_invariance_seed_000132", sm_scale_invariance_seed_000132),
        ("property_campaigns::tests::sm_scale_invariance_seed_000133", sm_scale_invariance_seed_000133),
        ("property_campaigns::tests::sm_scale_invariance_seed_000134", sm_scale_invariance_seed_000134),
        ("property_campaigns::tests::sm_scale_invariance_seed_000135", sm_scale_invariance_seed_000135),
        ("property_campaigns::tests::sm_scale_invariance_seed_000136", sm_scale_invariance_seed_000136),
        ("property_campaigns::tests::sm_scale_invariance_seed_000137", sm_scale_invariance_seed_000137),
        ("property_campaigns::tests::sm_scale_invariance_seed_000138", sm_scale_invariance_seed_000138),
        ("property_campaigns::tests::sm_scale_invariance_seed_000139", sm_scale_invariance_seed_000139),
        ("property_campaigns::tests::sm_scale_invariance_seed_000140", sm_scale_invariance_seed_000140),
        ("property_campaigns::tests::sm_scale_invariance_seed_000141", sm_scale_invariance_seed_000141),
        ("property_campaigns::tests::sm_scale_invariance_seed_000142", sm_scale_invariance_seed_000142),
        ("property_campaigns::tests::sm_scale_invariance_seed_000143", sm_scale_invariance_seed_000143),
        ("property_campaigns::tests::sm_scale_invariance_seed_000144", sm_scale_invariance_seed_000144),
        ("property_campaigns::tests::sm_scale_invariance_seed_000145", sm_scale_invariance_seed_000145),
        ("property_campaigns::tests::sm_scale_invariance_seed_000146", sm_scale_invariance_seed_000146),
        ("property_campaigns::tests::sm_scale_invariance_seed_000147", sm_scale_invariance_seed_000147),
        ("property_campaigns::tests::sm_scale_invariance_seed_000148", sm_scale_invariance_seed_000148),
        ("property_campaigns::tests::sm_scale_invariance_seed_000149", sm_scale_invariance_seed_000149),
        ("property_campaigns::tests::sm_negation_invariance_seed_000000", sm_negation_invariance_seed_000000),
        ("property_campaigns::tests::sm_negation_invariance_seed_000001", sm_negation_invariance_seed_000001),
        ("property_campaigns::tests::sm_negation_invariance_seed_000002", sm_negation_invariance_seed_000002),
        ("property_campaigns::tests::sm_negation_invariance_seed_000003", sm_negation_invariance_seed_000003),
        ("property_campaigns::tests::sm_negation_invariance_seed_000004", sm_negation_invariance_seed_000004),
        ("property_campaigns::tests::sm_negation_invariance_seed_000005", sm_negation_invariance_seed_000005),
        ("property_campaigns::tests::sm_negation_invariance_seed_000006", sm_negation_invariance_seed_000006),
        ("property_campaigns::tests::sm_negation_invariance_seed_000007", sm_negation_invariance_seed_000007),
        ("property_campaigns::tests::sm_negation_invariance_seed_000008", sm_negation_invariance_seed_000008),
        ("property_campaigns::tests::sm_negation_invariance_seed_000009", sm_negation_invariance_seed_000009),
        ("property_campaigns::tests::sm_negation_invariance_seed_000010", sm_negation_invariance_seed_000010),
        ("property_campaigns::tests::sm_negation_invariance_seed_000011", sm_negation_invariance_seed_000011),
        ("property_campaigns::tests::sm_negation_invariance_seed_000012", sm_negation_invariance_seed_000012),
        ("property_campaigns::tests::sm_negation_invariance_seed_000013", sm_negation_invariance_seed_000013),
        ("property_campaigns::tests::sm_negation_invariance_seed_000014", sm_negation_invariance_seed_000014),
        ("property_campaigns::tests::sm_negation_invariance_seed_000015", sm_negation_invariance_seed_000015),
        ("property_campaigns::tests::sm_negation_invariance_seed_000016", sm_negation_invariance_seed_000016),
        ("property_campaigns::tests::sm_negation_invariance_seed_000017", sm_negation_invariance_seed_000017),
        ("property_campaigns::tests::sm_negation_invariance_seed_000018", sm_negation_invariance_seed_000018),
        ("property_campaigns::tests::sm_negation_invariance_seed_000019", sm_negation_invariance_seed_000019),
        ("property_campaigns::tests::sm_negation_invariance_seed_000020", sm_negation_invariance_seed_000020),
        ("property_campaigns::tests::sm_negation_invariance_seed_000021", sm_negation_invariance_seed_000021),
        ("property_campaigns::tests::sm_negation_invariance_seed_000022", sm_negation_invariance_seed_000022),
        ("property_campaigns::tests::sm_negation_invariance_seed_000023", sm_negation_invariance_seed_000023),
        ("property_campaigns::tests::sm_negation_invariance_seed_000024", sm_negation_invariance_seed_000024),
        ("property_campaigns::tests::sm_negation_invariance_seed_000025", sm_negation_invariance_seed_000025),
        ("property_campaigns::tests::sm_negation_invariance_seed_000026", sm_negation_invariance_seed_000026),
        ("property_campaigns::tests::sm_negation_invariance_seed_000027", sm_negation_invariance_seed_000027),
        ("property_campaigns::tests::sm_negation_invariance_seed_000028", sm_negation_invariance_seed_000028),
        ("property_campaigns::tests::sm_negation_invariance_seed_000029", sm_negation_invariance_seed_000029),
        ("property_campaigns::tests::sm_negation_invariance_seed_000030", sm_negation_invariance_seed_000030),
        ("property_campaigns::tests::sm_negation_invariance_seed_000031", sm_negation_invariance_seed_000031),
        ("property_campaigns::tests::sm_negation_invariance_seed_000032", sm_negation_invariance_seed_000032),
        ("property_campaigns::tests::sm_negation_invariance_seed_000033", sm_negation_invariance_seed_000033),
        ("property_campaigns::tests::sm_negation_invariance_seed_000034", sm_negation_invariance_seed_000034),
        ("property_campaigns::tests::sm_negation_invariance_seed_000035", sm_negation_invariance_seed_000035),
        ("property_campaigns::tests::sm_negation_invariance_seed_000036", sm_negation_invariance_seed_000036),
        ("property_campaigns::tests::sm_negation_invariance_seed_000037", sm_negation_invariance_seed_000037),
        ("property_campaigns::tests::sm_negation_invariance_seed_000038", sm_negation_invariance_seed_000038),
        ("property_campaigns::tests::sm_negation_invariance_seed_000039", sm_negation_invariance_seed_000039),
        ("property_campaigns::tests::sm_negation_invariance_seed_000040", sm_negation_invariance_seed_000040),
        ("property_campaigns::tests::sm_negation_invariance_seed_000041", sm_negation_invariance_seed_000041),
        ("property_campaigns::tests::sm_negation_invariance_seed_000042", sm_negation_invariance_seed_000042),
        ("property_campaigns::tests::sm_negation_invariance_seed_000043", sm_negation_invariance_seed_000043),
        ("property_campaigns::tests::sm_negation_invariance_seed_000044", sm_negation_invariance_seed_000044),
        ("property_campaigns::tests::sm_negation_invariance_seed_000045", sm_negation_invariance_seed_000045),
        ("property_campaigns::tests::sm_negation_invariance_seed_000046", sm_negation_invariance_seed_000046),
        ("property_campaigns::tests::sm_negation_invariance_seed_000047", sm_negation_invariance_seed_000047),
        ("property_campaigns::tests::sm_negation_invariance_seed_000048", sm_negation_invariance_seed_000048),
        ("property_campaigns::tests::sm_negation_invariance_seed_000049", sm_negation_invariance_seed_000049),
        ("property_campaigns::tests::sm_negation_invariance_seed_000050", sm_negation_invariance_seed_000050),
        ("property_campaigns::tests::sm_negation_invariance_seed_000051", sm_negation_invariance_seed_000051),
        ("property_campaigns::tests::sm_negation_invariance_seed_000052", sm_negation_invariance_seed_000052),
        ("property_campaigns::tests::sm_negation_invariance_seed_000053", sm_negation_invariance_seed_000053),
        ("property_campaigns::tests::sm_negation_invariance_seed_000054", sm_negation_invariance_seed_000054),
        ("property_campaigns::tests::sm_negation_invariance_seed_000055", sm_negation_invariance_seed_000055),
        ("property_campaigns::tests::sm_negation_invariance_seed_000056", sm_negation_invariance_seed_000056),
        ("property_campaigns::tests::sm_negation_invariance_seed_000057", sm_negation_invariance_seed_000057),
        ("property_campaigns::tests::sm_negation_invariance_seed_000058", sm_negation_invariance_seed_000058),
        ("property_campaigns::tests::sm_negation_invariance_seed_000059", sm_negation_invariance_seed_000059),
        ("property_campaigns::tests::sm_negation_invariance_seed_000060", sm_negation_invariance_seed_000060),
        ("property_campaigns::tests::sm_negation_invariance_seed_000061", sm_negation_invariance_seed_000061),
        ("property_campaigns::tests::sm_negation_invariance_seed_000062", sm_negation_invariance_seed_000062),
        ("property_campaigns::tests::sm_negation_invariance_seed_000063", sm_negation_invariance_seed_000063),
        ("property_campaigns::tests::sm_negation_invariance_seed_000064", sm_negation_invariance_seed_000064),
        ("property_campaigns::tests::sm_negation_invariance_seed_000065", sm_negation_invariance_seed_000065),
        ("property_campaigns::tests::sm_negation_invariance_seed_000066", sm_negation_invariance_seed_000066),
        ("property_campaigns::tests::sm_negation_invariance_seed_000067", sm_negation_invariance_seed_000067),
        ("property_campaigns::tests::sm_negation_invariance_seed_000068", sm_negation_invariance_seed_000068),
        ("property_campaigns::tests::sm_negation_invariance_seed_000069", sm_negation_invariance_seed_000069),
        ("property_campaigns::tests::sm_negation_invariance_seed_000070", sm_negation_invariance_seed_000070),
        ("property_campaigns::tests::sm_negation_invariance_seed_000071", sm_negation_invariance_seed_000071),
        ("property_campaigns::tests::sm_negation_invariance_seed_000072", sm_negation_invariance_seed_000072),
        ("property_campaigns::tests::sm_negation_invariance_seed_000073", sm_negation_invariance_seed_000073),
        ("property_campaigns::tests::sm_negation_invariance_seed_000074", sm_negation_invariance_seed_000074),
        ("property_campaigns::tests::sm_negation_invariance_seed_000075", sm_negation_invariance_seed_000075),
        ("property_campaigns::tests::sm_negation_invariance_seed_000076", sm_negation_invariance_seed_000076),
        ("property_campaigns::tests::sm_negation_invariance_seed_000077", sm_negation_invariance_seed_000077),
        ("property_campaigns::tests::sm_negation_invariance_seed_000078", sm_negation_invariance_seed_000078),
        ("property_campaigns::tests::sm_negation_invariance_seed_000079", sm_negation_invariance_seed_000079),
        ("property_campaigns::tests::sm_negation_invariance_seed_000080", sm_negation_invariance_seed_000080),
        ("property_campaigns::tests::sm_negation_invariance_seed_000081", sm_negation_invariance_seed_000081),
        ("property_campaigns::tests::sm_negation_invariance_seed_000082", sm_negation_invariance_seed_000082),
        ("property_campaigns::tests::sm_negation_invariance_seed_000083", sm_negation_invariance_seed_000083),
        ("property_campaigns::tests::sm_negation_invariance_seed_000084", sm_negation_invariance_seed_000084),
        ("property_campaigns::tests::sm_negation_invariance_seed_000085", sm_negation_invariance_seed_000085),
        ("property_campaigns::tests::sm_negation_invariance_seed_000086", sm_negation_invariance_seed_000086),
        ("property_campaigns::tests::sm_negation_invariance_seed_000087", sm_negation_invariance_seed_000087),
        ("property_campaigns::tests::sm_negation_invariance_seed_000088", sm_negation_invariance_seed_000088),
        ("property_campaigns::tests::sm_negation_invariance_seed_000089", sm_negation_invariance_seed_000089),
        ("property_campaigns::tests::sm_negation_invariance_seed_000090", sm_negation_invariance_seed_000090),
        ("property_campaigns::tests::sm_negation_invariance_seed_000091", sm_negation_invariance_seed_000091),
        ("property_campaigns::tests::sm_negation_invariance_seed_000092", sm_negation_invariance_seed_000092),
        ("property_campaigns::tests::sm_negation_invariance_seed_000093", sm_negation_invariance_seed_000093),
        ("property_campaigns::tests::sm_negation_invariance_seed_000094", sm_negation_invariance_seed_000094),
        ("property_campaigns::tests::sm_negation_invariance_seed_000095", sm_negation_invariance_seed_000095),
        ("property_campaigns::tests::sm_negation_invariance_seed_000096", sm_negation_invariance_seed_000096),
        ("property_campaigns::tests::sm_negation_invariance_seed_000097", sm_negation_invariance_seed_000097),
        ("property_campaigns::tests::sm_negation_invariance_seed_000098", sm_negation_invariance_seed_000098),
        ("property_campaigns::tests::sm_negation_invariance_seed_000099", sm_negation_invariance_seed_000099),
        ("property_campaigns::tests::sm_negation_invariance_seed_000100", sm_negation_invariance_seed_000100),
        ("property_campaigns::tests::sm_negation_invariance_seed_000101", sm_negation_invariance_seed_000101),
        ("property_campaigns::tests::sm_negation_invariance_seed_000102", sm_negation_invariance_seed_000102),
        ("property_campaigns::tests::sm_negation_invariance_seed_000103", sm_negation_invariance_seed_000103),
        ("property_campaigns::tests::sm_negation_invariance_seed_000104", sm_negation_invariance_seed_000104),
        ("property_campaigns::tests::sm_negation_invariance_seed_000105", sm_negation_invariance_seed_000105),
        ("property_campaigns::tests::sm_negation_invariance_seed_000106", sm_negation_invariance_seed_000106),
        ("property_campaigns::tests::sm_negation_invariance_seed_000107", sm_negation_invariance_seed_000107),
        ("property_campaigns::tests::sm_negation_invariance_seed_000108", sm_negation_invariance_seed_000108),
        ("property_campaigns::tests::sm_negation_invariance_seed_000109", sm_negation_invariance_seed_000109),
        ("property_campaigns::tests::sm_negation_invariance_seed_000110", sm_negation_invariance_seed_000110),
        ("property_campaigns::tests::sm_negation_invariance_seed_000111", sm_negation_invariance_seed_000111),
        ("property_campaigns::tests::sm_negation_invariance_seed_000112", sm_negation_invariance_seed_000112),
        ("property_campaigns::tests::sm_negation_invariance_seed_000113", sm_negation_invariance_seed_000113),
        ("property_campaigns::tests::sm_negation_invariance_seed_000114", sm_negation_invariance_seed_000114),
        ("property_campaigns::tests::sm_negation_invariance_seed_000115", sm_negation_invariance_seed_000115),
        ("property_campaigns::tests::sm_negation_invariance_seed_000116", sm_negation_invariance_seed_000116),
        ("property_campaigns::tests::sm_negation_invariance_seed_000117", sm_negation_invariance_seed_000117),
        ("property_campaigns::tests::sm_negation_invariance_seed_000118", sm_negation_invariance_seed_000118),
        ("property_campaigns::tests::sm_negation_invariance_seed_000119", sm_negation_invariance_seed_000119),
        ("property_campaigns::tests::sm_negation_invariance_seed_000120", sm_negation_invariance_seed_000120),
        ("property_campaigns::tests::sm_negation_invariance_seed_000121", sm_negation_invariance_seed_000121),
        ("property_campaigns::tests::sm_negation_invariance_seed_000122", sm_negation_invariance_seed_000122),
        ("property_campaigns::tests::sm_negation_invariance_seed_000123", sm_negation_invariance_seed_000123),
        ("property_campaigns::tests::sm_negation_invariance_seed_000124", sm_negation_invariance_seed_000124),
        ("property_campaigns::tests::sm_negation_invariance_seed_000125", sm_negation_invariance_seed_000125),
        ("property_campaigns::tests::sm_negation_invariance_seed_000126", sm_negation_invariance_seed_000126),
        ("property_campaigns::tests::sm_negation_invariance_seed_000127", sm_negation_invariance_seed_000127),
        ("property_campaigns::tests::sm_negation_invariance_seed_000128", sm_negation_invariance_seed_000128),
        ("property_campaigns::tests::sm_negation_invariance_seed_000129", sm_negation_invariance_seed_000129),
        ("property_campaigns::tests::sm_negation_invariance_seed_000130", sm_negation_invariance_seed_000130),
        ("property_campaigns::tests::sm_negation_invariance_seed_000131", sm_negation_invariance_seed_000131),
        ("property_campaigns::tests::sm_negation_invariance_seed_000132", sm_negation_invariance_seed_000132),
        ("property_campaigns::tests::sm_negation_invariance_seed_000133", sm_negation_invariance_seed_000133),
        ("property_campaigns::tests::sm_negation_invariance_seed_000134", sm_negation_invariance_seed_000134),
        ("property_campaigns::tests::sm_negation_invariance_seed_000135", sm_negation_invariance_seed_000135),
        ("property_campaigns::tests::sm_negation_invariance_seed_000136", sm_negation_invariance_seed_000136),
        ("property_campaigns::tests::sm_negation_invariance_seed_000137", sm_negation_invariance_seed_000137),
        ("property_campaigns::tests::sm_negation_invariance_seed_000138", sm_negation_invariance_seed_000138),
        ("property_campaigns::tests::sm_negation_invariance_seed_000139", sm_negation_invariance_seed_000139),
        ("property_campaigns::tests::sm_negation_invariance_seed_000140", sm_negation_invariance_seed_000140),
        ("property_campaigns::tests::sm_negation_invariance_seed_000141", sm_negation_invariance_seed_000141),
        ("property_campaigns::tests::sm_negation_invariance_seed_000142", sm_negation_invariance_seed_000142),
        ("property_campaigns::tests::sm_negation_invariance_seed_000143", sm_negation_invariance_seed_000143),
        ("property_campaigns::tests::sm_negation_invariance_seed_000144", sm_negation_invariance_seed_000144),
        ("property_campaigns::tests::sm_negation_invariance_seed_000145", sm_negation_invariance_seed_000145),
        ("property_campaigns::tests::sm_negation_invariance_seed_000146", sm_negation_invariance_seed_000146),
        ("property_campaigns::tests::sm_negation_invariance_seed_000147", sm_negation_invariance_seed_000147),
        ("property_campaigns::tests::sm_negation_invariance_seed_000148", sm_negation_invariance_seed_000148),
        ("property_campaigns::tests::sm_negation_invariance_seed_000149", sm_negation_invariance_seed_000149),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000000", sm_bounded_agreement_seed_000000),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000001", sm_bounded_agreement_seed_000001),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000002", sm_bounded_agreement_seed_000002),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000003", sm_bounded_agreement_seed_000003),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000004", sm_bounded_agreement_seed_000004),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000005", sm_bounded_agreement_seed_000005),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000006", sm_bounded_agreement_seed_000006),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000007", sm_bounded_agreement_seed_000007),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000008", sm_bounded_agreement_seed_000008),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000009", sm_bounded_agreement_seed_000009),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000010", sm_bounded_agreement_seed_000010),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000011", sm_bounded_agreement_seed_000011),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000012", sm_bounded_agreement_seed_000012),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000013", sm_bounded_agreement_seed_000013),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000014", sm_bounded_agreement_seed_000014),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000015", sm_bounded_agreement_seed_000015),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000016", sm_bounded_agreement_seed_000016),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000017", sm_bounded_agreement_seed_000017),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000018", sm_bounded_agreement_seed_000018),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000019", sm_bounded_agreement_seed_000019),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000020", sm_bounded_agreement_seed_000020),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000021", sm_bounded_agreement_seed_000021),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000022", sm_bounded_agreement_seed_000022),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000023", sm_bounded_agreement_seed_000023),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000024", sm_bounded_agreement_seed_000024),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000025", sm_bounded_agreement_seed_000025),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000026", sm_bounded_agreement_seed_000026),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000027", sm_bounded_agreement_seed_000027),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000028", sm_bounded_agreement_seed_000028),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000029", sm_bounded_agreement_seed_000029),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000030", sm_bounded_agreement_seed_000030),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000031", sm_bounded_agreement_seed_000031),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000032", sm_bounded_agreement_seed_000032),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000033", sm_bounded_agreement_seed_000033),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000034", sm_bounded_agreement_seed_000034),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000035", sm_bounded_agreement_seed_000035),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000036", sm_bounded_agreement_seed_000036),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000037", sm_bounded_agreement_seed_000037),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000038", sm_bounded_agreement_seed_000038),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000039", sm_bounded_agreement_seed_000039),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000040", sm_bounded_agreement_seed_000040),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000041", sm_bounded_agreement_seed_000041),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000042", sm_bounded_agreement_seed_000042),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000043", sm_bounded_agreement_seed_000043),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000044", sm_bounded_agreement_seed_000044),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000045", sm_bounded_agreement_seed_000045),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000046", sm_bounded_agreement_seed_000046),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000047", sm_bounded_agreement_seed_000047),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000048", sm_bounded_agreement_seed_000048),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000049", sm_bounded_agreement_seed_000049),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000050", sm_bounded_agreement_seed_000050),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000051", sm_bounded_agreement_seed_000051),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000052", sm_bounded_agreement_seed_000052),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000053", sm_bounded_agreement_seed_000053),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000054", sm_bounded_agreement_seed_000054),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000055", sm_bounded_agreement_seed_000055),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000056", sm_bounded_agreement_seed_000056),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000057", sm_bounded_agreement_seed_000057),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000058", sm_bounded_agreement_seed_000058),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000059", sm_bounded_agreement_seed_000059),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000060", sm_bounded_agreement_seed_000060),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000061", sm_bounded_agreement_seed_000061),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000062", sm_bounded_agreement_seed_000062),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000063", sm_bounded_agreement_seed_000063),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000064", sm_bounded_agreement_seed_000064),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000065", sm_bounded_agreement_seed_000065),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000066", sm_bounded_agreement_seed_000066),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000067", sm_bounded_agreement_seed_000067),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000068", sm_bounded_agreement_seed_000068),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000069", sm_bounded_agreement_seed_000069),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000070", sm_bounded_agreement_seed_000070),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000071", sm_bounded_agreement_seed_000071),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000072", sm_bounded_agreement_seed_000072),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000073", sm_bounded_agreement_seed_000073),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000074", sm_bounded_agreement_seed_000074),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000075", sm_bounded_agreement_seed_000075),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000076", sm_bounded_agreement_seed_000076),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000077", sm_bounded_agreement_seed_000077),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000078", sm_bounded_agreement_seed_000078),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000079", sm_bounded_agreement_seed_000079),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000080", sm_bounded_agreement_seed_000080),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000081", sm_bounded_agreement_seed_000081),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000082", sm_bounded_agreement_seed_000082),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000083", sm_bounded_agreement_seed_000083),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000084", sm_bounded_agreement_seed_000084),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000085", sm_bounded_agreement_seed_000085),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000086", sm_bounded_agreement_seed_000086),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000087", sm_bounded_agreement_seed_000087),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000088", sm_bounded_agreement_seed_000088),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000089", sm_bounded_agreement_seed_000089),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000090", sm_bounded_agreement_seed_000090),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000091", sm_bounded_agreement_seed_000091),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000092", sm_bounded_agreement_seed_000092),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000093", sm_bounded_agreement_seed_000093),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000094", sm_bounded_agreement_seed_000094),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000095", sm_bounded_agreement_seed_000095),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000096", sm_bounded_agreement_seed_000096),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000097", sm_bounded_agreement_seed_000097),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000098", sm_bounded_agreement_seed_000098),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000099", sm_bounded_agreement_seed_000099),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000100", sm_bounded_agreement_seed_000100),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000101", sm_bounded_agreement_seed_000101),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000102", sm_bounded_agreement_seed_000102),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000103", sm_bounded_agreement_seed_000103),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000104", sm_bounded_agreement_seed_000104),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000105", sm_bounded_agreement_seed_000105),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000106", sm_bounded_agreement_seed_000106),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000107", sm_bounded_agreement_seed_000107),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000108", sm_bounded_agreement_seed_000108),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000109", sm_bounded_agreement_seed_000109),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000110", sm_bounded_agreement_seed_000110),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000111", sm_bounded_agreement_seed_000111),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000112", sm_bounded_agreement_seed_000112),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000113", sm_bounded_agreement_seed_000113),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000114", sm_bounded_agreement_seed_000114),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000115", sm_bounded_agreement_seed_000115),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000116", sm_bounded_agreement_seed_000116),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000117", sm_bounded_agreement_seed_000117),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000118", sm_bounded_agreement_seed_000118),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000119", sm_bounded_agreement_seed_000119),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000120", sm_bounded_agreement_seed_000120),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000121", sm_bounded_agreement_seed_000121),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000122", sm_bounded_agreement_seed_000122),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000123", sm_bounded_agreement_seed_000123),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000124", sm_bounded_agreement_seed_000124),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000125", sm_bounded_agreement_seed_000125),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000126", sm_bounded_agreement_seed_000126),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000127", sm_bounded_agreement_seed_000127),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000128", sm_bounded_agreement_seed_000128),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000129", sm_bounded_agreement_seed_000129),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000130", sm_bounded_agreement_seed_000130),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000131", sm_bounded_agreement_seed_000131),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000132", sm_bounded_agreement_seed_000132),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000133", sm_bounded_agreement_seed_000133),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000134", sm_bounded_agreement_seed_000134),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000135", sm_bounded_agreement_seed_000135),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000136", sm_bounded_agreement_seed_000136),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000137", sm_bounded_agreement_seed_000137),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000138", sm_bounded_agreement_seed_000138),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000139", sm_bounded_agreement_seed_000139),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000140", sm_bounded_agreement_seed_000140),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000141", sm_bounded_agreement_seed_000141),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000142", sm_bounded_agreement_seed_000142),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000143", sm_bounded_agreement_seed_000143),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000144", sm_bounded_agreement_seed_000144),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000145", sm_bounded_agreement_seed_000145),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000146", sm_bounded_agreement_seed_000146),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000147", sm_bounded_agreement_seed_000147),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000148", sm_bounded_agreement_seed_000148),
        ("property_campaigns::tests::sm_bounded_agreement_seed_000149", sm_bounded_agreement_seed_000149),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000000", sm_reversal_invariant_seed_000000),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000001", sm_reversal_invariant_seed_000001),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000002", sm_reversal_invariant_seed_000002),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000003", sm_reversal_invariant_seed_000003),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000004", sm_reversal_invariant_seed_000004),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000005", sm_reversal_invariant_seed_000005),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000006", sm_reversal_invariant_seed_000006),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000007", sm_reversal_invariant_seed_000007),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000008", sm_reversal_invariant_seed_000008),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000009", sm_reversal_invariant_seed_000009),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000010", sm_reversal_invariant_seed_000010),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000011", sm_reversal_invariant_seed_000011),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000012", sm_reversal_invariant_seed_000012),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000013", sm_reversal_invariant_seed_000013),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000014", sm_reversal_invariant_seed_000014),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000015", sm_reversal_invariant_seed_000015),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000016", sm_reversal_invariant_seed_000016),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000017", sm_reversal_invariant_seed_000017),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000018", sm_reversal_invariant_seed_000018),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000019", sm_reversal_invariant_seed_000019),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000020", sm_reversal_invariant_seed_000020),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000021", sm_reversal_invariant_seed_000021),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000022", sm_reversal_invariant_seed_000022),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000023", sm_reversal_invariant_seed_000023),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000024", sm_reversal_invariant_seed_000024),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000025", sm_reversal_invariant_seed_000025),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000026", sm_reversal_invariant_seed_000026),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000027", sm_reversal_invariant_seed_000027),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000028", sm_reversal_invariant_seed_000028),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000029", sm_reversal_invariant_seed_000029),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000030", sm_reversal_invariant_seed_000030),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000031", sm_reversal_invariant_seed_000031),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000032", sm_reversal_invariant_seed_000032),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000033", sm_reversal_invariant_seed_000033),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000034", sm_reversal_invariant_seed_000034),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000035", sm_reversal_invariant_seed_000035),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000036", sm_reversal_invariant_seed_000036),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000037", sm_reversal_invariant_seed_000037),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000038", sm_reversal_invariant_seed_000038),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000039", sm_reversal_invariant_seed_000039),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000040", sm_reversal_invariant_seed_000040),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000041", sm_reversal_invariant_seed_000041),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000042", sm_reversal_invariant_seed_000042),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000043", sm_reversal_invariant_seed_000043),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000044", sm_reversal_invariant_seed_000044),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000045", sm_reversal_invariant_seed_000045),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000046", sm_reversal_invariant_seed_000046),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000047", sm_reversal_invariant_seed_000047),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000048", sm_reversal_invariant_seed_000048),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000049", sm_reversal_invariant_seed_000049),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000050", sm_reversal_invariant_seed_000050),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000051", sm_reversal_invariant_seed_000051),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000052", sm_reversal_invariant_seed_000052),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000053", sm_reversal_invariant_seed_000053),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000054", sm_reversal_invariant_seed_000054),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000055", sm_reversal_invariant_seed_000055),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000056", sm_reversal_invariant_seed_000056),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000057", sm_reversal_invariant_seed_000057),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000058", sm_reversal_invariant_seed_000058),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000059", sm_reversal_invariant_seed_000059),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000060", sm_reversal_invariant_seed_000060),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000061", sm_reversal_invariant_seed_000061),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000062", sm_reversal_invariant_seed_000062),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000063", sm_reversal_invariant_seed_000063),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000064", sm_reversal_invariant_seed_000064),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000065", sm_reversal_invariant_seed_000065),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000066", sm_reversal_invariant_seed_000066),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000067", sm_reversal_invariant_seed_000067),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000068", sm_reversal_invariant_seed_000068),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000069", sm_reversal_invariant_seed_000069),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000070", sm_reversal_invariant_seed_000070),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000071", sm_reversal_invariant_seed_000071),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000072", sm_reversal_invariant_seed_000072),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000073", sm_reversal_invariant_seed_000073),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000074", sm_reversal_invariant_seed_000074),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000075", sm_reversal_invariant_seed_000075),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000076", sm_reversal_invariant_seed_000076),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000077", sm_reversal_invariant_seed_000077),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000078", sm_reversal_invariant_seed_000078),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000079", sm_reversal_invariant_seed_000079),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000080", sm_reversal_invariant_seed_000080),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000081", sm_reversal_invariant_seed_000081),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000082", sm_reversal_invariant_seed_000082),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000083", sm_reversal_invariant_seed_000083),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000084", sm_reversal_invariant_seed_000084),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000085", sm_reversal_invariant_seed_000085),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000086", sm_reversal_invariant_seed_000086),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000087", sm_reversal_invariant_seed_000087),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000088", sm_reversal_invariant_seed_000088),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000089", sm_reversal_invariant_seed_000089),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000090", sm_reversal_invariant_seed_000090),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000091", sm_reversal_invariant_seed_000091),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000092", sm_reversal_invariant_seed_000092),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000093", sm_reversal_invariant_seed_000093),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000094", sm_reversal_invariant_seed_000094),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000095", sm_reversal_invariant_seed_000095),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000096", sm_reversal_invariant_seed_000096),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000097", sm_reversal_invariant_seed_000097),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000098", sm_reversal_invariant_seed_000098),
        ("property_campaigns::tests::sm_reversal_invariant_seed_000099", sm_reversal_invariant_seed_000099),
        ("property_campaigns::tests::pm_compactness_translation_seed_000000", pm_compactness_translation_seed_000000),
        ("property_campaigns::tests::pm_compactness_translation_seed_000001", pm_compactness_translation_seed_000001),
        ("property_campaigns::tests::pm_compactness_translation_seed_000002", pm_compactness_translation_seed_000002),
        ("property_campaigns::tests::pm_compactness_translation_seed_000003", pm_compactness_translation_seed_000003),
        ("property_campaigns::tests::pm_compactness_translation_seed_000004", pm_compactness_translation_seed_000004),
        ("property_campaigns::tests::pm_compactness_translation_seed_000005", pm_compactness_translation_seed_000005),
        ("property_campaigns::tests::pm_compactness_translation_seed_000006", pm_compactness_translation_seed_000006),
        ("property_campaigns::tests::pm_compactness_translation_seed_000007", pm_compactness_translation_seed_000007),
        ("property_campaigns::tests::pm_compactness_translation_seed_000008", pm_compactness_translation_seed_000008),
        ("property_campaigns::tests::pm_compactness_translation_seed_000009", pm_compactness_translation_seed_000009),
        ("property_campaigns::tests::pm_compactness_translation_seed_000010", pm_compactness_translation_seed_000010),
        ("property_campaigns::tests::pm_compactness_translation_seed_000011", pm_compactness_translation_seed_000011),
        ("property_campaigns::tests::pm_compactness_translation_seed_000012", pm_compactness_translation_seed_000012),
        ("property_campaigns::tests::pm_compactness_translation_seed_000013", pm_compactness_translation_seed_000013),
        ("property_campaigns::tests::pm_compactness_translation_seed_000014", pm_compactness_translation_seed_000014),
        ("property_campaigns::tests::pm_compactness_translation_seed_000015", pm_compactness_translation_seed_000015),
        ("property_campaigns::tests::pm_compactness_translation_seed_000016", pm_compactness_translation_seed_000016),
        ("property_campaigns::tests::pm_compactness_translation_seed_000017", pm_compactness_translation_seed_000017),
        ("property_campaigns::tests::pm_compactness_translation_seed_000018", pm_compactness_translation_seed_000018),
        ("property_campaigns::tests::pm_compactness_translation_seed_000019", pm_compactness_translation_seed_000019),
        ("property_campaigns::tests::pm_compactness_translation_seed_000020", pm_compactness_translation_seed_000020),
        ("property_campaigns::tests::pm_compactness_translation_seed_000021", pm_compactness_translation_seed_000021),
        ("property_campaigns::tests::pm_compactness_translation_seed_000022", pm_compactness_translation_seed_000022),
        ("property_campaigns::tests::pm_compactness_translation_seed_000023", pm_compactness_translation_seed_000023),
        ("property_campaigns::tests::pm_compactness_translation_seed_000024", pm_compactness_translation_seed_000024),
        ("property_campaigns::tests::pm_compactness_translation_seed_000025", pm_compactness_translation_seed_000025),
        ("property_campaigns::tests::pm_compactness_translation_seed_000026", pm_compactness_translation_seed_000026),
        ("property_campaigns::tests::pm_compactness_translation_seed_000027", pm_compactness_translation_seed_000027),
        ("property_campaigns::tests::pm_compactness_translation_seed_000028", pm_compactness_translation_seed_000028),
        ("property_campaigns::tests::pm_compactness_translation_seed_000029", pm_compactness_translation_seed_000029),
        ("property_campaigns::tests::pm_compactness_translation_seed_000030", pm_compactness_translation_seed_000030),
        ("property_campaigns::tests::pm_compactness_translation_seed_000031", pm_compactness_translation_seed_000031),
        ("property_campaigns::tests::pm_compactness_translation_seed_000032", pm_compactness_translation_seed_000032),
        ("property_campaigns::tests::pm_compactness_translation_seed_000033", pm_compactness_translation_seed_000033),
        ("property_campaigns::tests::pm_compactness_translation_seed_000034", pm_compactness_translation_seed_000034),
        ("property_campaigns::tests::pm_compactness_translation_seed_000035", pm_compactness_translation_seed_000035),
        ("property_campaigns::tests::pm_compactness_translation_seed_000036", pm_compactness_translation_seed_000036),
        ("property_campaigns::tests::pm_compactness_translation_seed_000037", pm_compactness_translation_seed_000037),
        ("property_campaigns::tests::pm_compactness_translation_seed_000038", pm_compactness_translation_seed_000038),
        ("property_campaigns::tests::pm_compactness_translation_seed_000039", pm_compactness_translation_seed_000039),
        ("property_campaigns::tests::pm_compactness_translation_seed_000040", pm_compactness_translation_seed_000040),
        ("property_campaigns::tests::pm_compactness_translation_seed_000041", pm_compactness_translation_seed_000041),
        ("property_campaigns::tests::pm_compactness_translation_seed_000042", pm_compactness_translation_seed_000042),
        ("property_campaigns::tests::pm_compactness_translation_seed_000043", pm_compactness_translation_seed_000043),
        ("property_campaigns::tests::pm_compactness_translation_seed_000044", pm_compactness_translation_seed_000044),
        ("property_campaigns::tests::pm_compactness_translation_seed_000045", pm_compactness_translation_seed_000045),
        ("property_campaigns::tests::pm_compactness_translation_seed_000046", pm_compactness_translation_seed_000046),
        ("property_campaigns::tests::pm_compactness_translation_seed_000047", pm_compactness_translation_seed_000047),
        ("property_campaigns::tests::pm_compactness_translation_seed_000048", pm_compactness_translation_seed_000048),
        ("property_campaigns::tests::pm_compactness_translation_seed_000049", pm_compactness_translation_seed_000049),
        ("property_campaigns::tests::pm_compactness_translation_seed_000050", pm_compactness_translation_seed_000050),
        ("property_campaigns::tests::pm_compactness_translation_seed_000051", pm_compactness_translation_seed_000051),
        ("property_campaigns::tests::pm_compactness_translation_seed_000052", pm_compactness_translation_seed_000052),
        ("property_campaigns::tests::pm_compactness_translation_seed_000053", pm_compactness_translation_seed_000053),
        ("property_campaigns::tests::pm_compactness_translation_seed_000054", pm_compactness_translation_seed_000054),
        ("property_campaigns::tests::pm_compactness_translation_seed_000055", pm_compactness_translation_seed_000055),
        ("property_campaigns::tests::pm_compactness_translation_seed_000056", pm_compactness_translation_seed_000056),
        ("property_campaigns::tests::pm_compactness_translation_seed_000057", pm_compactness_translation_seed_000057),
        ("property_campaigns::tests::pm_compactness_translation_seed_000058", pm_compactness_translation_seed_000058),
        ("property_campaigns::tests::pm_compactness_translation_seed_000059", pm_compactness_translation_seed_000059),
        ("property_campaigns::tests::pm_compactness_translation_seed_000060", pm_compactness_translation_seed_000060),
        ("property_campaigns::tests::pm_compactness_translation_seed_000061", pm_compactness_translation_seed_000061),
        ("property_campaigns::tests::pm_compactness_translation_seed_000062", pm_compactness_translation_seed_000062),
        ("property_campaigns::tests::pm_compactness_translation_seed_000063", pm_compactness_translation_seed_000063),
        ("property_campaigns::tests::pm_compactness_translation_seed_000064", pm_compactness_translation_seed_000064),
        ("property_campaigns::tests::pm_compactness_translation_seed_000065", pm_compactness_translation_seed_000065),
        ("property_campaigns::tests::pm_compactness_translation_seed_000066", pm_compactness_translation_seed_000066),
        ("property_campaigns::tests::pm_compactness_translation_seed_000067", pm_compactness_translation_seed_000067),
        ("property_campaigns::tests::pm_compactness_translation_seed_000068", pm_compactness_translation_seed_000068),
        ("property_campaigns::tests::pm_compactness_translation_seed_000069", pm_compactness_translation_seed_000069),
        ("property_campaigns::tests::pm_compactness_translation_seed_000070", pm_compactness_translation_seed_000070),
        ("property_campaigns::tests::pm_compactness_translation_seed_000071", pm_compactness_translation_seed_000071),
        ("property_campaigns::tests::pm_compactness_translation_seed_000072", pm_compactness_translation_seed_000072),
        ("property_campaigns::tests::pm_compactness_translation_seed_000073", pm_compactness_translation_seed_000073),
        ("property_campaigns::tests::pm_compactness_translation_seed_000074", pm_compactness_translation_seed_000074),
        ("property_campaigns::tests::pm_compactness_translation_seed_000075", pm_compactness_translation_seed_000075),
        ("property_campaigns::tests::pm_compactness_translation_seed_000076", pm_compactness_translation_seed_000076),
        ("property_campaigns::tests::pm_compactness_translation_seed_000077", pm_compactness_translation_seed_000077),
        ("property_campaigns::tests::pm_compactness_translation_seed_000078", pm_compactness_translation_seed_000078),
        ("property_campaigns::tests::pm_compactness_translation_seed_000079", pm_compactness_translation_seed_000079),
        ("property_campaigns::tests::pm_compactness_translation_seed_000080", pm_compactness_translation_seed_000080),
        ("property_campaigns::tests::pm_compactness_translation_seed_000081", pm_compactness_translation_seed_000081),
        ("property_campaigns::tests::pm_compactness_translation_seed_000082", pm_compactness_translation_seed_000082),
        ("property_campaigns::tests::pm_compactness_translation_seed_000083", pm_compactness_translation_seed_000083),
        ("property_campaigns::tests::pm_compactness_translation_seed_000084", pm_compactness_translation_seed_000084),
        ("property_campaigns::tests::pm_compactness_translation_seed_000085", pm_compactness_translation_seed_000085),
        ("property_campaigns::tests::pm_compactness_translation_seed_000086", pm_compactness_translation_seed_000086),
        ("property_campaigns::tests::pm_compactness_translation_seed_000087", pm_compactness_translation_seed_000087),
        ("property_campaigns::tests::pm_compactness_translation_seed_000088", pm_compactness_translation_seed_000088),
        ("property_campaigns::tests::pm_compactness_translation_seed_000089", pm_compactness_translation_seed_000089),
        ("property_campaigns::tests::pm_compactness_translation_seed_000090", pm_compactness_translation_seed_000090),
        ("property_campaigns::tests::pm_compactness_translation_seed_000091", pm_compactness_translation_seed_000091),
        ("property_campaigns::tests::pm_compactness_translation_seed_000092", pm_compactness_translation_seed_000092),
        ("property_campaigns::tests::pm_compactness_translation_seed_000093", pm_compactness_translation_seed_000093),
        ("property_campaigns::tests::pm_compactness_translation_seed_000094", pm_compactness_translation_seed_000094),
        ("property_campaigns::tests::pm_compactness_translation_seed_000095", pm_compactness_translation_seed_000095),
        ("property_campaigns::tests::pm_compactness_translation_seed_000096", pm_compactness_translation_seed_000096),
        ("property_campaigns::tests::pm_compactness_translation_seed_000097", pm_compactness_translation_seed_000097),
        ("property_campaigns::tests::pm_compactness_translation_seed_000098", pm_compactness_translation_seed_000098),
        ("property_campaigns::tests::pm_compactness_translation_seed_000099", pm_compactness_translation_seed_000099),
        ("property_campaigns::tests::pm_compactness_translation_seed_000100", pm_compactness_translation_seed_000100),
        ("property_campaigns::tests::pm_compactness_translation_seed_000101", pm_compactness_translation_seed_000101),
        ("property_campaigns::tests::pm_compactness_translation_seed_000102", pm_compactness_translation_seed_000102),
        ("property_campaigns::tests::pm_compactness_translation_seed_000103", pm_compactness_translation_seed_000103),
        ("property_campaigns::tests::pm_compactness_translation_seed_000104", pm_compactness_translation_seed_000104),
        ("property_campaigns::tests::pm_compactness_translation_seed_000105", pm_compactness_translation_seed_000105),
        ("property_campaigns::tests::pm_compactness_translation_seed_000106", pm_compactness_translation_seed_000106),
        ("property_campaigns::tests::pm_compactness_translation_seed_000107", pm_compactness_translation_seed_000107),
        ("property_campaigns::tests::pm_compactness_translation_seed_000108", pm_compactness_translation_seed_000108),
        ("property_campaigns::tests::pm_compactness_translation_seed_000109", pm_compactness_translation_seed_000109),
        ("property_campaigns::tests::pm_compactness_translation_seed_000110", pm_compactness_translation_seed_000110),
        ("property_campaigns::tests::pm_compactness_translation_seed_000111", pm_compactness_translation_seed_000111),
        ("property_campaigns::tests::pm_compactness_translation_seed_000112", pm_compactness_translation_seed_000112),
        ("property_campaigns::tests::pm_compactness_translation_seed_000113", pm_compactness_translation_seed_000113),
        ("property_campaigns::tests::pm_compactness_translation_seed_000114", pm_compactness_translation_seed_000114),
        ("property_campaigns::tests::pm_compactness_translation_seed_000115", pm_compactness_translation_seed_000115),
        ("property_campaigns::tests::pm_compactness_translation_seed_000116", pm_compactness_translation_seed_000116),
        ("property_campaigns::tests::pm_compactness_translation_seed_000117", pm_compactness_translation_seed_000117),
        ("property_campaigns::tests::pm_compactness_translation_seed_000118", pm_compactness_translation_seed_000118),
        ("property_campaigns::tests::pm_compactness_translation_seed_000119", pm_compactness_translation_seed_000119),
        ("property_campaigns::tests::pm_compactness_translation_seed_000120", pm_compactness_translation_seed_000120),
        ("property_campaigns::tests::pm_compactness_translation_seed_000121", pm_compactness_translation_seed_000121),
        ("property_campaigns::tests::pm_compactness_translation_seed_000122", pm_compactness_translation_seed_000122),
        ("property_campaigns::tests::pm_compactness_translation_seed_000123", pm_compactness_translation_seed_000123),
        ("property_campaigns::tests::pm_compactness_translation_seed_000124", pm_compactness_translation_seed_000124),
        ("property_campaigns::tests::pm_compactness_translation_seed_000125", pm_compactness_translation_seed_000125),
        ("property_campaigns::tests::pm_compactness_translation_seed_000126", pm_compactness_translation_seed_000126),
        ("property_campaigns::tests::pm_compactness_translation_seed_000127", pm_compactness_translation_seed_000127),
        ("property_campaigns::tests::pm_compactness_translation_seed_000128", pm_compactness_translation_seed_000128),
        ("property_campaigns::tests::pm_compactness_translation_seed_000129", pm_compactness_translation_seed_000129),
        ("property_campaigns::tests::pm_compactness_translation_seed_000130", pm_compactness_translation_seed_000130),
        ("property_campaigns::tests::pm_compactness_translation_seed_000131", pm_compactness_translation_seed_000131),
        ("property_campaigns::tests::pm_compactness_translation_seed_000132", pm_compactness_translation_seed_000132),
        ("property_campaigns::tests::pm_compactness_translation_seed_000133", pm_compactness_translation_seed_000133),
        ("property_campaigns::tests::pm_compactness_translation_seed_000134", pm_compactness_translation_seed_000134),
        ("property_campaigns::tests::pm_compactness_translation_seed_000135", pm_compactness_translation_seed_000135),
        ("property_campaigns::tests::pm_compactness_translation_seed_000136", pm_compactness_translation_seed_000136),
        ("property_campaigns::tests::pm_compactness_translation_seed_000137", pm_compactness_translation_seed_000137),
        ("property_campaigns::tests::pm_compactness_translation_seed_000138", pm_compactness_translation_seed_000138),
        ("property_campaigns::tests::pm_compactness_translation_seed_000139", pm_compactness_translation_seed_000139),
        ("property_campaigns::tests::pm_compactness_translation_seed_000140", pm_compactness_translation_seed_000140),
        ("property_campaigns::tests::pm_compactness_translation_seed_000141", pm_compactness_translation_seed_000141),
        ("property_campaigns::tests::pm_compactness_translation_seed_000142", pm_compactness_translation_seed_000142),
        ("property_campaigns::tests::pm_compactness_translation_seed_000143", pm_compactness_translation_seed_000143),
        ("property_campaigns::tests::pm_compactness_translation_seed_000144", pm_compactness_translation_seed_000144),
        ("property_campaigns::tests::pm_compactness_translation_seed_000145", pm_compactness_translation_seed_000145),
        ("property_campaigns::tests::pm_compactness_translation_seed_000146", pm_compactness_translation_seed_000146),
        ("property_campaigns::tests::pm_compactness_translation_seed_000147", pm_compactness_translation_seed_000147),
        ("property_campaigns::tests::pm_compactness_translation_seed_000148", pm_compactness_translation_seed_000148),
        ("property_campaigns::tests::pm_compactness_translation_seed_000149", pm_compactness_translation_seed_000149),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000000", pm_compactness_scale_law_seed_000000),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000001", pm_compactness_scale_law_seed_000001),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000002", pm_compactness_scale_law_seed_000002),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000003", pm_compactness_scale_law_seed_000003),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000004", pm_compactness_scale_law_seed_000004),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000005", pm_compactness_scale_law_seed_000005),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000006", pm_compactness_scale_law_seed_000006),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000007", pm_compactness_scale_law_seed_000007),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000008", pm_compactness_scale_law_seed_000008),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000009", pm_compactness_scale_law_seed_000009),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000010", pm_compactness_scale_law_seed_000010),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000011", pm_compactness_scale_law_seed_000011),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000012", pm_compactness_scale_law_seed_000012),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000013", pm_compactness_scale_law_seed_000013),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000014", pm_compactness_scale_law_seed_000014),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000015", pm_compactness_scale_law_seed_000015),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000016", pm_compactness_scale_law_seed_000016),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000017", pm_compactness_scale_law_seed_000017),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000018", pm_compactness_scale_law_seed_000018),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000019", pm_compactness_scale_law_seed_000019),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000020", pm_compactness_scale_law_seed_000020),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000021", pm_compactness_scale_law_seed_000021),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000022", pm_compactness_scale_law_seed_000022),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000023", pm_compactness_scale_law_seed_000023),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000024", pm_compactness_scale_law_seed_000024),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000025", pm_compactness_scale_law_seed_000025),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000026", pm_compactness_scale_law_seed_000026),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000027", pm_compactness_scale_law_seed_000027),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000028", pm_compactness_scale_law_seed_000028),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000029", pm_compactness_scale_law_seed_000029),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000030", pm_compactness_scale_law_seed_000030),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000031", pm_compactness_scale_law_seed_000031),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000032", pm_compactness_scale_law_seed_000032),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000033", pm_compactness_scale_law_seed_000033),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000034", pm_compactness_scale_law_seed_000034),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000035", pm_compactness_scale_law_seed_000035),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000036", pm_compactness_scale_law_seed_000036),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000037", pm_compactness_scale_law_seed_000037),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000038", pm_compactness_scale_law_seed_000038),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000039", pm_compactness_scale_law_seed_000039),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000040", pm_compactness_scale_law_seed_000040),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000041", pm_compactness_scale_law_seed_000041),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000042", pm_compactness_scale_law_seed_000042),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000043", pm_compactness_scale_law_seed_000043),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000044", pm_compactness_scale_law_seed_000044),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000045", pm_compactness_scale_law_seed_000045),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000046", pm_compactness_scale_law_seed_000046),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000047", pm_compactness_scale_law_seed_000047),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000048", pm_compactness_scale_law_seed_000048),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000049", pm_compactness_scale_law_seed_000049),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000050", pm_compactness_scale_law_seed_000050),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000051", pm_compactness_scale_law_seed_000051),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000052", pm_compactness_scale_law_seed_000052),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000053", pm_compactness_scale_law_seed_000053),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000054", pm_compactness_scale_law_seed_000054),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000055", pm_compactness_scale_law_seed_000055),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000056", pm_compactness_scale_law_seed_000056),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000057", pm_compactness_scale_law_seed_000057),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000058", pm_compactness_scale_law_seed_000058),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000059", pm_compactness_scale_law_seed_000059),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000060", pm_compactness_scale_law_seed_000060),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000061", pm_compactness_scale_law_seed_000061),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000062", pm_compactness_scale_law_seed_000062),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000063", pm_compactness_scale_law_seed_000063),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000064", pm_compactness_scale_law_seed_000064),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000065", pm_compactness_scale_law_seed_000065),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000066", pm_compactness_scale_law_seed_000066),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000067", pm_compactness_scale_law_seed_000067),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000068", pm_compactness_scale_law_seed_000068),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000069", pm_compactness_scale_law_seed_000069),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000070", pm_compactness_scale_law_seed_000070),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000071", pm_compactness_scale_law_seed_000071),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000072", pm_compactness_scale_law_seed_000072),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000073", pm_compactness_scale_law_seed_000073),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000074", pm_compactness_scale_law_seed_000074),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000075", pm_compactness_scale_law_seed_000075),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000076", pm_compactness_scale_law_seed_000076),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000077", pm_compactness_scale_law_seed_000077),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000078", pm_compactness_scale_law_seed_000078),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000079", pm_compactness_scale_law_seed_000079),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000080", pm_compactness_scale_law_seed_000080),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000081", pm_compactness_scale_law_seed_000081),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000082", pm_compactness_scale_law_seed_000082),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000083", pm_compactness_scale_law_seed_000083),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000084", pm_compactness_scale_law_seed_000084),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000085", pm_compactness_scale_law_seed_000085),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000086", pm_compactness_scale_law_seed_000086),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000087", pm_compactness_scale_law_seed_000087),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000088", pm_compactness_scale_law_seed_000088),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000089", pm_compactness_scale_law_seed_000089),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000090", pm_compactness_scale_law_seed_000090),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000091", pm_compactness_scale_law_seed_000091),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000092", pm_compactness_scale_law_seed_000092),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000093", pm_compactness_scale_law_seed_000093),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000094", pm_compactness_scale_law_seed_000094),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000095", pm_compactness_scale_law_seed_000095),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000096", pm_compactness_scale_law_seed_000096),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000097", pm_compactness_scale_law_seed_000097),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000098", pm_compactness_scale_law_seed_000098),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000099", pm_compactness_scale_law_seed_000099),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000100", pm_compactness_scale_law_seed_000100),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000101", pm_compactness_scale_law_seed_000101),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000102", pm_compactness_scale_law_seed_000102),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000103", pm_compactness_scale_law_seed_000103),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000104", pm_compactness_scale_law_seed_000104),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000105", pm_compactness_scale_law_seed_000105),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000106", pm_compactness_scale_law_seed_000106),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000107", pm_compactness_scale_law_seed_000107),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000108", pm_compactness_scale_law_seed_000108),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000109", pm_compactness_scale_law_seed_000109),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000110", pm_compactness_scale_law_seed_000110),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000111", pm_compactness_scale_law_seed_000111),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000112", pm_compactness_scale_law_seed_000112),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000113", pm_compactness_scale_law_seed_000113),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000114", pm_compactness_scale_law_seed_000114),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000115", pm_compactness_scale_law_seed_000115),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000116", pm_compactness_scale_law_seed_000116),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000117", pm_compactness_scale_law_seed_000117),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000118", pm_compactness_scale_law_seed_000118),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000119", pm_compactness_scale_law_seed_000119),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000120", pm_compactness_scale_law_seed_000120),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000121", pm_compactness_scale_law_seed_000121),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000122", pm_compactness_scale_law_seed_000122),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000123", pm_compactness_scale_law_seed_000123),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000124", pm_compactness_scale_law_seed_000124),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000125", pm_compactness_scale_law_seed_000125),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000126", pm_compactness_scale_law_seed_000126),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000127", pm_compactness_scale_law_seed_000127),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000128", pm_compactness_scale_law_seed_000128),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000129", pm_compactness_scale_law_seed_000129),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000130", pm_compactness_scale_law_seed_000130),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000131", pm_compactness_scale_law_seed_000131),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000132", pm_compactness_scale_law_seed_000132),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000133", pm_compactness_scale_law_seed_000133),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000134", pm_compactness_scale_law_seed_000134),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000135", pm_compactness_scale_law_seed_000135),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000136", pm_compactness_scale_law_seed_000136),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000137", pm_compactness_scale_law_seed_000137),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000138", pm_compactness_scale_law_seed_000138),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000139", pm_compactness_scale_law_seed_000139),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000140", pm_compactness_scale_law_seed_000140),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000141", pm_compactness_scale_law_seed_000141),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000142", pm_compactness_scale_law_seed_000142),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000143", pm_compactness_scale_law_seed_000143),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000144", pm_compactness_scale_law_seed_000144),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000145", pm_compactness_scale_law_seed_000145),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000146", pm_compactness_scale_law_seed_000146),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000147", pm_compactness_scale_law_seed_000147),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000148", pm_compactness_scale_law_seed_000148),
        ("property_campaigns::tests::pm_compactness_scale_law_seed_000149", pm_compactness_scale_law_seed_000149),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000000", pm_connectivity_monotone_seed_000000),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000001", pm_connectivity_monotone_seed_000001),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000002", pm_connectivity_monotone_seed_000002),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000003", pm_connectivity_monotone_seed_000003),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000004", pm_connectivity_monotone_seed_000004),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000005", pm_connectivity_monotone_seed_000005),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000006", pm_connectivity_monotone_seed_000006),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000007", pm_connectivity_monotone_seed_000007),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000008", pm_connectivity_monotone_seed_000008),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000009", pm_connectivity_monotone_seed_000009),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000010", pm_connectivity_monotone_seed_000010),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000011", pm_connectivity_monotone_seed_000011),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000012", pm_connectivity_monotone_seed_000012),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000013", pm_connectivity_monotone_seed_000013),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000014", pm_connectivity_monotone_seed_000014),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000015", pm_connectivity_monotone_seed_000015),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000016", pm_connectivity_monotone_seed_000016),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000017", pm_connectivity_monotone_seed_000017),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000018", pm_connectivity_monotone_seed_000018),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000019", pm_connectivity_monotone_seed_000019),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000020", pm_connectivity_monotone_seed_000020),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000021", pm_connectivity_monotone_seed_000021),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000022", pm_connectivity_monotone_seed_000022),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000023", pm_connectivity_monotone_seed_000023),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000024", pm_connectivity_monotone_seed_000024),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000025", pm_connectivity_monotone_seed_000025),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000026", pm_connectivity_monotone_seed_000026),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000027", pm_connectivity_monotone_seed_000027),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000028", pm_connectivity_monotone_seed_000028),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000029", pm_connectivity_monotone_seed_000029),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000030", pm_connectivity_monotone_seed_000030),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000031", pm_connectivity_monotone_seed_000031),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000032", pm_connectivity_monotone_seed_000032),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000033", pm_connectivity_monotone_seed_000033),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000034", pm_connectivity_monotone_seed_000034),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000035", pm_connectivity_monotone_seed_000035),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000036", pm_connectivity_monotone_seed_000036),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000037", pm_connectivity_monotone_seed_000037),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000038", pm_connectivity_monotone_seed_000038),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000039", pm_connectivity_monotone_seed_000039),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000040", pm_connectivity_monotone_seed_000040),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000041", pm_connectivity_monotone_seed_000041),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000042", pm_connectivity_monotone_seed_000042),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000043", pm_connectivity_monotone_seed_000043),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000044", pm_connectivity_monotone_seed_000044),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000045", pm_connectivity_monotone_seed_000045),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000046", pm_connectivity_monotone_seed_000046),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000047", pm_connectivity_monotone_seed_000047),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000048", pm_connectivity_monotone_seed_000048),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000049", pm_connectivity_monotone_seed_000049),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000050", pm_connectivity_monotone_seed_000050),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000051", pm_connectivity_monotone_seed_000051),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000052", pm_connectivity_monotone_seed_000052),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000053", pm_connectivity_monotone_seed_000053),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000054", pm_connectivity_monotone_seed_000054),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000055", pm_connectivity_monotone_seed_000055),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000056", pm_connectivity_monotone_seed_000056),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000057", pm_connectivity_monotone_seed_000057),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000058", pm_connectivity_monotone_seed_000058),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000059", pm_connectivity_monotone_seed_000059),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000060", pm_connectivity_monotone_seed_000060),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000061", pm_connectivity_monotone_seed_000061),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000062", pm_connectivity_monotone_seed_000062),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000063", pm_connectivity_monotone_seed_000063),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000064", pm_connectivity_monotone_seed_000064),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000065", pm_connectivity_monotone_seed_000065),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000066", pm_connectivity_monotone_seed_000066),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000067", pm_connectivity_monotone_seed_000067),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000068", pm_connectivity_monotone_seed_000068),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000069", pm_connectivity_monotone_seed_000069),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000070", pm_connectivity_monotone_seed_000070),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000071", pm_connectivity_monotone_seed_000071),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000072", pm_connectivity_monotone_seed_000072),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000073", pm_connectivity_monotone_seed_000073),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000074", pm_connectivity_monotone_seed_000074),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000075", pm_connectivity_monotone_seed_000075),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000076", pm_connectivity_monotone_seed_000076),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000077", pm_connectivity_monotone_seed_000077),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000078", pm_connectivity_monotone_seed_000078),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000079", pm_connectivity_monotone_seed_000079),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000080", pm_connectivity_monotone_seed_000080),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000081", pm_connectivity_monotone_seed_000081),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000082", pm_connectivity_monotone_seed_000082),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000083", pm_connectivity_monotone_seed_000083),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000084", pm_connectivity_monotone_seed_000084),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000085", pm_connectivity_monotone_seed_000085),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000086", pm_connectivity_monotone_seed_000086),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000087", pm_connectivity_monotone_seed_000087),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000088", pm_connectivity_monotone_seed_000088),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000089", pm_connectivity_monotone_seed_000089),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000090", pm_connectivity_monotone_seed_000090),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000091", pm_connectivity_monotone_seed_000091),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000092", pm_connectivity_monotone_seed_000092),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000093", pm_connectivity_monotone_seed_000093),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000094", pm_connectivity_monotone_seed_000094),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000095", pm_connectivity_monotone_seed_000095),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000096", pm_connectivity_monotone_seed_000096),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000097", pm_connectivity_monotone_seed_000097),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000098", pm_connectivity_monotone_seed_000098),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000099", pm_connectivity_monotone_seed_000099),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000100", pm_connectivity_monotone_seed_000100),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000101", pm_connectivity_monotone_seed_000101),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000102", pm_connectivity_monotone_seed_000102),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000103", pm_connectivity_monotone_seed_000103),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000104", pm_connectivity_monotone_seed_000104),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000105", pm_connectivity_monotone_seed_000105),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000106", pm_connectivity_monotone_seed_000106),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000107", pm_connectivity_monotone_seed_000107),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000108", pm_connectivity_monotone_seed_000108),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000109", pm_connectivity_monotone_seed_000109),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000110", pm_connectivity_monotone_seed_000110),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000111", pm_connectivity_monotone_seed_000111),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000112", pm_connectivity_monotone_seed_000112),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000113", pm_connectivity_monotone_seed_000113),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000114", pm_connectivity_monotone_seed_000114),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000115", pm_connectivity_monotone_seed_000115),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000116", pm_connectivity_monotone_seed_000116),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000117", pm_connectivity_monotone_seed_000117),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000118", pm_connectivity_monotone_seed_000118),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000119", pm_connectivity_monotone_seed_000119),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000120", pm_connectivity_monotone_seed_000120),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000121", pm_connectivity_monotone_seed_000121),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000122", pm_connectivity_monotone_seed_000122),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000123", pm_connectivity_monotone_seed_000123),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000124", pm_connectivity_monotone_seed_000124),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000125", pm_connectivity_monotone_seed_000125),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000126", pm_connectivity_monotone_seed_000126),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000127", pm_connectivity_monotone_seed_000127),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000128", pm_connectivity_monotone_seed_000128),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000129", pm_connectivity_monotone_seed_000129),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000130", pm_connectivity_monotone_seed_000130),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000131", pm_connectivity_monotone_seed_000131),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000132", pm_connectivity_monotone_seed_000132),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000133", pm_connectivity_monotone_seed_000133),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000134", pm_connectivity_monotone_seed_000134),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000135", pm_connectivity_monotone_seed_000135),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000136", pm_connectivity_monotone_seed_000136),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000137", pm_connectivity_monotone_seed_000137),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000138", pm_connectivity_monotone_seed_000138),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000139", pm_connectivity_monotone_seed_000139),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000140", pm_connectivity_monotone_seed_000140),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000141", pm_connectivity_monotone_seed_000141),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000142", pm_connectivity_monotone_seed_000142),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000143", pm_connectivity_monotone_seed_000143),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000144", pm_connectivity_monotone_seed_000144),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000145", pm_connectivity_monotone_seed_000145),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000146", pm_connectivity_monotone_seed_000146),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000147", pm_connectivity_monotone_seed_000147),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000148", pm_connectivity_monotone_seed_000148),
        ("property_campaigns::tests::pm_connectivity_monotone_seed_000149", pm_connectivity_monotone_seed_000149),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
