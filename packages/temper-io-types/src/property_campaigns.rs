// Property-based campaigns over three independent, pure, deterministic
// `temper-io-types` kernels: net classification's precedence and
// case-folding contract (`placer_core::netclass`), the placer's netlist
// adjacency builder (`placer_core::adjacency::build_adjacency_matrix`), and
// CPython-exact float `repr()` (`placer_core::pyrepr::repr_f64` /
// `format_fixed`).
//
// Why this exists (R7 / the WASM-tier volume payload)
// -----------------------------------------------------------------------
// A fixed, hand-written unit-test fixture explores the same handful of
// inputs every time it runs. This module gives the wasm32 tier a payload
// where each registered test explores a *distinct* generated input: every
// property below is a pure function of a `u64` seed through the
// `SplitMix64` generator below, so e.g. `nc_precedence_core_seed_000042`
// and `nc_precedence_core_seed_000043` exercise different net names, and a
// failure is reproducible from its seed alone.
//
// Each property is a metamorphic or invariant relation over the real
// kernel -- a relationship that must hold between two *related* calls --
// never a restatement of the implementation (i.e. never "recompute X, and
// assert X equals X"). Every one is picked so that a plausible bug in the
// kernel it covers flips it from green to red; see this crate's PR body for
// the mutation-testing evidence: each property was checked against a
// deliberately broken kernel and shown to fail on exactly the cases it
// should, then the kernel was reverted.
//
// The pattern-set trap (read `netclass.rs` before touching this file)
// -----------------------------------------------------------------------
// `netclass.rs` deliberately holds two POWER pattern sets --
// `POWER_NET_PATTERNS` (core, 7 entries) and `POWER_NET_PATTERNS_V6` (11
// entries, plus a "starts with '+'" heuristic `is_power_net_v6` alone has)
// -- because `core.net_classification` and `router_v6.net_classification`
// classify differently and, per that module's own docstring, "must not
// silently converge". Nothing below asserts `is_power_net` and
// `is_power_net_v6` agree, or that `classify_net_type` and
// `classify_net_type_v6` agree: the core and v6 properties are independent
// pairs, each checked only against its own precedence law and its own
// case-folding contract.
//
// No `proptest`: it is a dev-dependency, absent from the ordinary
// (non-test) build this crate's `wasm-registry` feature compiles into (see
// `scripts/gen_wasm_test_registry.py`'s `PROPTEST_USE` exclusion and
// `packages/temper-geometry/src/property_campaigns.rs`, the module this one
// copies the shape of). No RNG crate either: `SplitMix64` below is a small,
// self-contained, portable PRNG -- wasm32-unknown-unknown has no OS entropy
// source, and fixed seeds are what make a wasm32 trap reproducible from its
// seed by a human reading the failing test's name.
//
// Every item below (down to `mod tests`) is reachable ONLY from that
// module's `#[test]` functions -- which `scripts/gen_wasm_test_registry.py`
// turns into `pub(crate)` and reaches indirectly through
// `tests::WASM_TESTS` once this module is registered. A build with neither
// `test` nor `wasm-registry` active (e.g. `--features python` alone) sees
// every item below as unused, same reason this crate's own
// `#![cfg_attr(not(feature = "python"), allow(dead_code))]` exists in
// `lib.rs` and `property_campaigns.rs` in the sibling crates apply their
// own `#![allow(dead_code)]`.
#![allow(dead_code)]

// ---------------------------------------------------------------------------
// Deterministic PRNG (SplitMix64) -- pure, no external dependency, portable
// to wasm32-unknown-unknown without an entropy source. Shared by all three
// kernels' properties below; each property draws its own generated case
// from `seed` directly, and any extra randomized parameter (case pattern,
// shuffle order, precision, ...) from an independent `sub_rng(seed, salt)`
// stream so a property's own parameters never correlate with which base
// case `seed` produced.
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
// Kernel 1: placer_core::netclass -- net-name classification precedence
// (ground > power > hv > signal) and its case-folding contract, for BOTH
// the core and router_v6 pattern sets independently. See this file's module
// doc for why core and v6 are never compared to each other.
// ===========================================================================

use crate::placer_core::netclass::{
    self, classify_net_type, classify_net_type_v6, is_ground_net, is_hv_net, is_power_net,
    is_power_net_v6, is_signal_net, is_signal_net_v6,
};

/// Tokens that match no pattern in any set -- mixed into the generated
/// names so not every case trivially resolves to a matching class, and the
/// generated corpus also exercises pure-signal names.
const NC_JUNK_TOKENS: [&str; 8] = ["SDA", "SCL", "RST", "LED1", "MOSI", "CLK2", "ADCIN", "BOOT0"];

const NC_SALT_CASE: u64 = 0xC1;

/// The core module's classification vocabulary: ground, power (core), hv,
/// and junk tokens combined. Read from `netclass`'s own `pub const` pattern
/// arrays rather than duplicated literals, so a pattern added or removed
/// there is picked up here automatically instead of drifting out of sync.
fn nc_token_pool_core() -> Vec<&'static str> {
    let mut v: Vec<&'static str> = Vec::new();
    v.extend_from_slice(&netclass::GROUND_NET_PATTERNS);
    v.extend_from_slice(&netclass::POWER_NET_PATTERNS);
    v.extend_from_slice(&netclass::HV_NET_PATTERNS);
    v.extend_from_slice(&NC_JUNK_TOKENS);
    v
}

/// The router_v6 module's classification vocabulary: ground + power (v6,
/// 11 entries) + hv + junk. Deliberately a SEPARATE pool from
/// [`nc_token_pool_core`] -- see this file's module doc on the pattern-set
/// trap -- even though ground/hv/junk overlap, so a change to either pool
/// cannot silently make the two properties share a generator by accident.
fn nc_token_pool_v6() -> Vec<&'static str> {
    let mut v: Vec<&'static str> = Vec::new();
    v.extend_from_slice(&netclass::GROUND_NET_PATTERNS);
    v.extend_from_slice(&netclass::POWER_NET_PATTERNS_V6);
    v.extend_from_slice(&netclass::HV_NET_PATTERNS);
    v.extend_from_slice(&NC_JUNK_TOKENS);
    v
}

/// A canonical (already-uppercase) net name built from 1-3 tokens drawn
/// from `pool`, `_`-joined, with an occasional numeric suffix -- wide
/// enough to hit every precedence combination (ground+power, power+hv, all
/// three, junk-only) without hard-coding any single case by hand.
fn nc_gen_name(seed: u64, pool: &[&'static str]) -> String {
    let mut rng = SplitMix64::new(seed);
    let n_tokens = 1 + rng.index(3); // 1..=3
    let mut parts: Vec<String> = Vec::with_capacity(n_tokens);
    for _ in 0..n_tokens {
        parts.push(pool[rng.index(pool.len())].to_string());
    }
    let mut name = parts.join("_");
    if rng.index(3) == 0 {
        name.push_str(&rng.index(100).to_string());
    }
    name
}

/// Precedence law for `core.net_classification`: ground > power > hv >
/// signal, re-derived from the three independent boolean predicates
/// (NOT from `classify_net_type`'s own if/elif chain) and checked against
/// what `classify_net_type` actually returns.
///
/// Bug this would catch: a refactor that reorders `classify_net_type`'s
/// checks (e.g. power before ground) would keep every single-category name
/// correctly classified -- only a name matching two or more pattern sets at
/// once (which the `_`-joined multi-token generator deliberately produces)
/// exposes the reordering, exactly the case `netclass.rs`'s own hand test
/// `precedence_is_ground_power_hv_signal` covers once (`"GND_PE"`); this
/// property covers it at volume with generated combinations.
pub(crate) fn nc_precedence_core_impl(seed: u64) {
    let pool = nc_token_pool_core();
    let name = nc_gen_name(seed, &pool);
    let expected = if is_ground_net(&name) {
        "ground"
    } else if is_power_net(&name) {
        "power"
    } else if is_hv_net(&name) {
        "hv"
    } else {
        "signal"
    };
    assert_eq!(
        classify_net_type(&name),
        expected,
        "classify_net_type disagreed with the ground>power>hv>signal \
         precedence law: seed={seed} name={name:?}"
    );
    assert_eq!(
        is_signal_net(&name),
        expected == "signal",
        "is_signal_net disagreed with classify_net_type's signal verdict: \
         seed={seed} name={name:?}"
    );
}

/// Precedence law for `router_v6.net_classification`: ground > power(v6) >
/// hv > signal(v6). Same shape as [`nc_precedence_core_impl`] but entirely
/// on the v6 functions -- never compared against the core ones.
///
/// Bug this would catch: same class of reordering bug as
/// [`nc_precedence_core_impl`], but scoped to the v6 precedence chain
/// (`classify_net_type_v6`) and its 11-entry power pattern set plus the
/// "starts with '+'" heuristic [`is_power_net_v6`] alone has.
pub(crate) fn nc_precedence_v6_impl(seed: u64) {
    let pool = nc_token_pool_v6();
    let name = nc_gen_name(seed, &pool);
    let expected = if is_ground_net(&name) {
        "ground"
    } else if is_power_net_v6(&name) {
        "power"
    } else if is_hv_net(&name) {
        "hv"
    } else {
        "signal"
    };
    assert_eq!(
        classify_net_type_v6(&name),
        expected,
        "classify_net_type_v6 disagreed with the ground>power>hv>signal \
         precedence law: seed={seed} name={name:?}"
    );
    assert_eq!(
        is_signal_net_v6(&name),
        expected == "signal",
        "is_signal_net_v6 disagreed with classify_net_type_v6's signal \
         verdict: seed={seed} name={name:?}"
    );
}

/// `netclass.rs`'s own doc comment states the contract: classification is
/// case-insensitive because `matches_any` upper-cases its input before
/// matching. A canonical (already-uppercase) generated name, its
/// `to_lowercase()`, and a per-character randomly-mixed-case rendering must
/// all classify identically under every core predicate.
///
/// Bug this would catch: dropping or narrowing the `name.to_uppercase()`
/// call in `matches_any` (e.g. replacing it with a no-op, or with
/// `to_ascii_uppercase()` -- which is NOT what the module doc claims: it
/// documents full Unicode case folding, `'ß' -> "SS"` included).
pub(crate) fn nc_case_invariance_core_impl(seed: u64) {
    let pool = nc_token_pool_core();
    let canonical = nc_gen_name(seed, &pool);
    let lower = canonical.to_lowercase();
    let mut mix_rng = sub_rng(seed, NC_SALT_CASE);
    let mixed: String = canonical
        .chars()
        .map(|c| {
            if mix_rng.next_u64().is_multiple_of(2) {
                c.to_ascii_lowercase()
            } else {
                c.to_ascii_uppercase()
            }
        })
        .collect();
    let g0 = is_ground_net(&canonical);
    let p0 = is_power_net(&canonical);
    let h0 = is_hv_net(&canonical);
    let c0 = classify_net_type(&canonical);
    for variant in [&lower, &mixed] {
        assert_eq!(
            is_ground_net(variant), g0,
            "is_ground_net not case-invariant: seed={seed} canonical={canonical:?} variant={variant:?}"
        );
        assert_eq!(
            is_power_net(variant), p0,
            "is_power_net not case-invariant: seed={seed} canonical={canonical:?} variant={variant:?}"
        );
        assert_eq!(
            is_hv_net(variant), h0,
            "is_hv_net not case-invariant: seed={seed} canonical={canonical:?} variant={variant:?}"
        );
        assert_eq!(
            classify_net_type(variant), c0,
            "classify_net_type not case-invariant: seed={seed} canonical={canonical:?} variant={variant:?}"
        );
    }
}

/// Same case-folding contract as [`nc_case_invariance_core_impl`], on the
/// v6 predicates (including the "starts with '+'" heuristic, which is
/// case-blind by construction since `'+'` has no case -- included here so a
/// regression that made the heuristic case-SENSITIVE by accident would
/// still be caught if it were ever rewritten to inspect the un-uppercased
/// string).
pub(crate) fn nc_case_invariance_v6_impl(seed: u64) {
    let pool = nc_token_pool_v6();
    let canonical = nc_gen_name(seed, &pool);
    let lower = canonical.to_lowercase();
    let mut mix_rng = sub_rng(seed, NC_SALT_CASE);
    let mixed: String = canonical
        .chars()
        .map(|c| {
            if mix_rng.next_u64().is_multiple_of(2) {
                c.to_ascii_lowercase()
            } else {
                c.to_ascii_uppercase()
            }
        })
        .collect();
    let p0 = is_power_net_v6(&canonical);
    let c0 = classify_net_type_v6(&canonical);
    for variant in [&lower, &mixed] {
        assert_eq!(
            is_power_net_v6(variant), p0,
            "is_power_net_v6 not case-invariant: seed={seed} canonical={canonical:?} variant={variant:?}"
        );
        assert_eq!(
            classify_net_type_v6(variant), c0,
            "classify_net_type_v6 not case-invariant: seed={seed} canonical={canonical:?} variant={variant:?}"
        );
    }
}

// ===========================================================================
// Kernel 2: placer_core::adjacency::build_adjacency_matrix -- the placer's
// weighted co-occurrence graph. See adjacency.rs's own module doc for the
// order-invariance argument this section exercises at volume.
// ===========================================================================

use crate::placer_core::adjacency::build_adjacency_matrix;

const ADJ_SALT_SHUFFLE: u64 = 0xD1;
const ADJ_SALT_PERM: u64 = 0xD2;

/// A small random netlist: 2-6 uniquely-named components (`"R0"..`) and
/// 1-5 nets, each net a list of 0..=n pin refs drawn (with repeats
/// allowed) from the component refs, occasionally substituting an unknown
/// ref to also exercise the "unknown refs are dropped" path documented on
/// the kernel.
fn adj_gen_case(seed: u64) -> (Vec<String>, Vec<Vec<String>>) {
    let mut rng = SplitMix64::new(seed);
    let n = 2 + rng.index(5); // 2..=6
    let refs: Vec<String> = (0..n).map(|i| format!("R{i}")).collect();
    let n_nets = 1 + rng.index(5); // 1..=5
    let mut nets = Vec::with_capacity(n_nets);
    for _ in 0..n_nets {
        let k = rng.index(n + 1); // 0..=n pins in this net
        let mut pins = Vec::with_capacity(k);
        for _ in 0..k {
            if rng.index(10) == 0 {
                pins.push("ZZ_UNKNOWN".to_string());
            } else {
                pins.push(refs[rng.index(n)].clone());
            }
        }
        nets.push(pins);
    }
    (refs, nets)
}

/// Fisher-Yates over an owned `Vec`, driven by `rng`.
fn adj_shuffle(mut v: Vec<String>, rng: &mut SplitMix64) -> Vec<String> {
    for i in (1..v.len()).rev() {
        let j = rng.index(i + 1);
        v.swap(i, j);
    }
    v
}

/// The matrix is symmetric: `adj[i][j] == adj[j][i]` for every cell, since
/// the kernel increments both directions for every co-occurring pair.
///
/// Bug this would catch: writing only the forward cell (`data[i*n+j]`) and
/// dropping the mirrored `data[j*n+i]` update -- a plausible copy-paste
/// slip given the two lines are adjacent and near-identical in the source.
pub(crate) fn adj_symmetry_impl(seed: u64) {
    let (refs, nets) = adj_gen_case(seed);
    let adj = build_adjacency_matrix(&refs, &nets);
    for i in 0..adj.n {
        for j in 0..adj.n {
            assert_eq!(
                adj.data[i * adj.n + j],
                adj.data[j * adj.n + i],
                "adjacency matrix not symmetric at ({i},{j}): seed={seed}"
            );
        }
    }
}

/// The diagonal is always zero: the kernel's `a in 0..len, b in (a+1)..len`
/// loop only ever pairs DISTINCT deduplicated component indices, so no
/// component is ever counted as adjacent to itself.
///
/// Bug this would catch: an off-by-one that widens the inner loop to
/// `a..len` (including `a == b`), which would put a nonzero count on the
/// diagonal for any net with 2+ pins on the same component.
pub(crate) fn adj_diagonal_zero_impl(seed: u64) {
    let (refs, nets) = adj_gen_case(seed);
    let adj = build_adjacency_matrix(&refs, &nets);
    for i in 0..adj.n {
        assert_eq!(
            adj.data[i * adj.n + i],
            0.0,
            "self-adjacency nonzero at diagonal {i}: seed={seed}"
        );
    }
}

/// Permuting the pin order WITHIN each net must not change the resulting
/// matrix -- the kernel's own module doc argues this from the `i < j`
/// enumeration visiting every unordered pair exactly once; this property
/// checks it holds at volume rather than on the doc's one hand-built case.
///
/// Bug this would catch: replacing the dedup-and-pair logic with something
/// that (incorrectly) depends on pin POSITION rather than pin IDENTITY --
/// e.g. only pairing adjacent pins in the list instead of every pair.
pub(crate) fn adj_pin_order_invariance_impl(seed: u64) {
    let (refs, nets) = adj_gen_case(seed);
    let base = build_adjacency_matrix(&refs, &nets);
    let mut shuffle_rng = sub_rng(seed, ADJ_SALT_SHUFFLE);
    let shuffled_nets: Vec<Vec<String>> =
        nets.iter().map(|pins| adj_shuffle(pins.clone(), &mut shuffle_rng)).collect();
    let shuffled = build_adjacency_matrix(&refs, &shuffled_nets);
    assert_eq!(
        base.data, shuffled.data,
        "permuting pin order within each net changed the adjacency matrix: seed={seed}"
    );
}

/// Relabelling invariance: permuting the ORDER of `component_refs` (while
/// leaving `net_pin_refs` -- which addresses components by name, not
/// index -- untouched) must permute the matrix's rows/columns by exactly
/// the same permutation, with every edge weight preserved. This is the
/// "invariance under net relabelling" property named in the campaign brief:
/// `build_adjacency_matrix`'s graph structure is a property of which REFS
/// co-occur, not of which numeric index a ref happens to be assigned.
///
/// Bug this would catch: any dependency on a component's numeric index
/// beyond addressing its own matrix cell -- e.g. an accidental
/// `idx_i < idx_j` ordering assumption instead of the intended `a < b`
/// pin-list-position ordering (which this property, unlike
/// [`adj_pin_order_invariance_impl`], holds pin order fixed and only
/// permutes component labels, so the two properties are independent
/// detectors).
pub(crate) fn adj_relabeling_invariance_impl(seed: u64) {
    let (refs, nets) = adj_gen_case(seed);
    let base = build_adjacency_matrix(&refs, &nets);
    let n = refs.len();
    let mut perm_rng = sub_rng(seed, ADJ_SALT_PERM);
    let mut perm: Vec<usize> = (0..n).collect();
    for i in (1..n).rev() {
        let j = perm_rng.index(i + 1);
        perm.swap(i, j);
    }
    // `perm[new_index] == old_index`.
    let relabeled_refs: Vec<String> = perm.iter().map(|&old| refs[old].clone()).collect();
    let relabeled = build_adjacency_matrix(&relabeled_refs, &nets);
    for new_i in 0..n {
        for new_j in 0..n {
            let old_i = perm[new_i];
            let old_j = perm[new_j];
            assert_eq!(
                relabeled.data[new_i * n + new_j],
                base.data[old_i * n + old_j],
                "adjacency did not relabel consistently under a component \
                 permutation: seed={seed} new=({new_i},{new_j}) old=({old_i},{old_j})"
            );
        }
    }
}

// ===========================================================================
// Kernel 3: placer_core::pyrepr -- CPython-exact float rendering
// (`repr_f64`, `format_fixed`). See pyrepr.rs's own module doc for the four
// measured divergences from Rust's native float formatting this exists to
// close.
// ===========================================================================

use crate::placer_core::pyrepr::{format_fixed, repr_f64};

const PR_SALT_PRECISION: u64 = 0xE1;

/// A random finite f64 spanning subnormal through huge magnitudes: sign,
/// a decade exponent in `[-320, 300)` (past both the exponential-notation
/// threshold at decpt 16 and subnormal/underflow territory), and a mantissa
/// in `[1, 10)`. Values that underflow to exactly `0.0` are legitimate
/// (and handled by [`pr_gen_nonzero_f64`] for the one property that needs
/// to exclude them).
fn pr_gen_f64(seed: u64) -> f64 {
    let mut rng = SplitMix64::new(seed);
    let sign = if rng.index(2) == 0 { 1.0 } else { -1.0 };
    let exp = rng.range(-320.0, 300.0) as i32;
    let mantissa = 1.0 + rng.next_f64() * 9.0; // [1, 10)
    sign * mantissa * 10f64.powi(exp)
}

/// [`pr_gen_f64`], but never exactly zero (substitutes `1.0` on the rare
/// underflow) -- for properties where zero's signed-zero special case would
/// need separate handling rather than sharpen the property.
fn pr_gen_nonzero_f64(seed: u64) -> f64 {
    let v = pr_gen_f64(seed);
    if v == 0.0 { 1.0 } else { v }
}

/// CPython's `repr()` of a float is DEFINED as the shortest decimal string
/// that parses back to the exact same value -- so `repr_f64(x)`, run back
/// through Rust's own `f64::from_str`, must recover `x` bit-for-bit. This
/// is the defining round-trip law of the kernel, not an implementation
/// restatement: `repr_f64` and `f64::from_str` share no code.
///
/// Bug this would catch: any digit-generation or decimal-point-placement
/// error in `shortest_digits`/`render_fixed_repr`/`render_exponential` that
/// produces a string which is well-formed but numerically wrong (a dropped
/// digit, a decimal point shifted by one column, an exponent off by one).
pub(crate) fn pyrepr_round_trip_impl(seed: u64) {
    let x = pr_gen_f64(seed);
    let s = repr_f64(x);
    let parsed: f64 = match s.parse() {
        Ok(p) => p,
        Err(e) => panic!("repr_f64({x:?}) = {s:?} did not parse back as f64: {e}"),
    };
    assert_eq!(
        parsed.to_bits(),
        x.to_bits(),
        "repr_f64 did not round-trip: seed={seed} x={x:?} repr={s:?} parsed={parsed:?}"
    );
}

/// `format_fixed(x, prec)` must (a) render exactly `prec` digits after the
/// decimal point and (b) parse back within the correctly-rounded tolerance
/// of `x` at that precision -- the metamorphic relation between the VALUE
/// and its fixed-precision rendering that CPython's `f"{x:.Nf}"` promises.
///
/// Bug this would catch: precision handled as `prec - 1` or `prec + 1`
/// (digit-count mismatch), or a rounding-direction bug that displaces the
/// output by more than the format's own granularity.
pub(crate) fn pyrepr_format_fixed_rounding_impl(seed: u64) {
    let x = pr_gen_f64(seed);
    let mut prec_rng = sub_rng(seed, PR_SALT_PRECISION);
    let prec = prec_rng.index(7); // 0..=6
    let s = format_fixed(x, prec);
    match s.find('.') {
        Some(dot) => {
            let after = &s[dot + 1..];
            assert_eq!(
                after.len(),
                prec,
                "format_fixed({x:?}, {prec}) = {s:?} has {} digits after '.', expected {prec}: seed={seed}",
                after.len()
            );
        }
        None => assert_eq!(
            prec, 0,
            "format_fixed({x:?}, {prec}) = {s:?} has no decimal point but prec != 0: seed={seed}"
        ),
    }
    let parsed: f64 = match s.parse() {
        Ok(p) => p,
        Err(e) => panic!("format_fixed({x:?}, {prec}) = {s:?} did not parse back as f64: {e}"),
    };
    let tol = 0.5 * 10f64.powi(-(prec as i32)) + 1e-9 * x.abs().max(1.0);
    assert!(
        (parsed - x).abs() <= tol,
        "format_fixed({x:?}, {prec}) = {s:?} parsed to {parsed:?}, outside rounding \
         tolerance {tol}: seed={seed}"
    );
}

/// `repr_f64`'s magnitude rendering does not depend on sign: for any
/// nonzero finite `x`, `repr_f64(-|x|)` must equal `repr_f64(|x|)` with
/// exactly a `"-"` prepended -- sign is applied once, uniformly, never
/// folded into the digit generator or the exponent threshold decision.
///
/// Bug this would catch: a sign computed from the wrong value (e.g. reading
/// it off the exponent instead of the mantissa), or a threshold comparison
/// that accidentally uses the signed value instead of its magnitude and so
/// picks a different notation (fixed vs exponential) for `x` than for
/// `-x`.
pub(crate) fn pyrepr_sign_symmetry_impl(seed: u64) {
    let x = pr_gen_nonzero_f64(seed);
    let pos = x.abs();
    let neg = -pos;
    let rp = repr_f64(pos);
    let rn = repr_f64(neg);
    assert_eq!(
        rn,
        format!("-{rp}"),
        "repr_f64 not sign-symmetric: seed={seed} pos={pos:?} rp={rp:?} neg={neg:?} rn={rn:?}"
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
    fn nc_gen_name_is_deterministic() {
        let pool = nc_token_pool_core();
        assert_eq!(nc_gen_name(42, &pool), nc_gen_name(42, &pool));
    }

    #[cfg_attr(test, test)]
    fn nc_token_pools_are_distinct_sizes() {
        // core: 6 ground + 7 power + 6 hv + 8 junk = 27.
        // v6:   6 ground + 11 power + 6 hv + 8 junk = 31.
        assert_eq!(nc_token_pool_core().len(), 27);
        assert_eq!(nc_token_pool_v6().len(), 31);
    }

    #[cfg_attr(test, test)]
    fn nc_precedence_hand_example_matches_the_documented_law() {
        // The exact case netclass.rs's own hand test uses: a name matching
        // both ground and hv patterns resolves to ground.
        assert_eq!(classify_net_type("GND_PE"), "ground");
        assert_eq!(classify_net_type_v6("GND_PE"), "ground");
    }

    #[cfg_attr(test, test)]
    fn adj_gen_case_is_deterministic() {
        assert_eq!(adj_gen_case(123), adj_gen_case(123));
    }

    #[cfg_attr(test, test)]
    fn adj_gen_case_dims_in_expected_range() {
        for seed in [0u64, 1, 500, 999_999] {
            let (refs, nets) = adj_gen_case(seed);
            assert!((2..=6).contains(&refs.len()), "seed={seed} n={}", refs.len());
            assert!((1..=5).contains(&nets.len()), "seed={seed} nets={}", nets.len());
        }
    }

    #[cfg_attr(test, test)]
    fn pr_gen_f64_is_deterministic() {
        assert_eq!(pr_gen_f64(99).to_bits(), pr_gen_f64(99).to_bits());
    }

    #[cfg_attr(test, test)]
    fn pr_gen_f64_is_finite() {
        for seed in [0u64, 1, 500, 999_999] {
            assert!(pr_gen_f64(seed).is_finite(), "seed={seed}");
        }
    }

    // --- nc_precedence_core: 200 generated seeds ---
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000000() { nc_precedence_core_impl(0); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000001() { nc_precedence_core_impl(1); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000002() { nc_precedence_core_impl(2); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000003() { nc_precedence_core_impl(3); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000004() { nc_precedence_core_impl(4); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000005() { nc_precedence_core_impl(5); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000006() { nc_precedence_core_impl(6); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000007() { nc_precedence_core_impl(7); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000008() { nc_precedence_core_impl(8); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000009() { nc_precedence_core_impl(9); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000010() { nc_precedence_core_impl(10); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000011() { nc_precedence_core_impl(11); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000012() { nc_precedence_core_impl(12); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000013() { nc_precedence_core_impl(13); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000014() { nc_precedence_core_impl(14); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000015() { nc_precedence_core_impl(15); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000016() { nc_precedence_core_impl(16); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000017() { nc_precedence_core_impl(17); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000018() { nc_precedence_core_impl(18); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000019() { nc_precedence_core_impl(19); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000020() { nc_precedence_core_impl(20); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000021() { nc_precedence_core_impl(21); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000022() { nc_precedence_core_impl(22); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000023() { nc_precedence_core_impl(23); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000024() { nc_precedence_core_impl(24); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000025() { nc_precedence_core_impl(25); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000026() { nc_precedence_core_impl(26); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000027() { nc_precedence_core_impl(27); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000028() { nc_precedence_core_impl(28); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000029() { nc_precedence_core_impl(29); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000030() { nc_precedence_core_impl(30); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000031() { nc_precedence_core_impl(31); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000032() { nc_precedence_core_impl(32); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000033() { nc_precedence_core_impl(33); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000034() { nc_precedence_core_impl(34); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000035() { nc_precedence_core_impl(35); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000036() { nc_precedence_core_impl(36); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000037() { nc_precedence_core_impl(37); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000038() { nc_precedence_core_impl(38); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000039() { nc_precedence_core_impl(39); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000040() { nc_precedence_core_impl(40); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000041() { nc_precedence_core_impl(41); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000042() { nc_precedence_core_impl(42); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000043() { nc_precedence_core_impl(43); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000044() { nc_precedence_core_impl(44); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000045() { nc_precedence_core_impl(45); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000046() { nc_precedence_core_impl(46); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000047() { nc_precedence_core_impl(47); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000048() { nc_precedence_core_impl(48); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000049() { nc_precedence_core_impl(49); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000050() { nc_precedence_core_impl(50); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000051() { nc_precedence_core_impl(51); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000052() { nc_precedence_core_impl(52); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000053() { nc_precedence_core_impl(53); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000054() { nc_precedence_core_impl(54); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000055() { nc_precedence_core_impl(55); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000056() { nc_precedence_core_impl(56); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000057() { nc_precedence_core_impl(57); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000058() { nc_precedence_core_impl(58); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000059() { nc_precedence_core_impl(59); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000060() { nc_precedence_core_impl(60); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000061() { nc_precedence_core_impl(61); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000062() { nc_precedence_core_impl(62); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000063() { nc_precedence_core_impl(63); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000064() { nc_precedence_core_impl(64); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000065() { nc_precedence_core_impl(65); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000066() { nc_precedence_core_impl(66); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000067() { nc_precedence_core_impl(67); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000068() { nc_precedence_core_impl(68); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000069() { nc_precedence_core_impl(69); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000070() { nc_precedence_core_impl(70); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000071() { nc_precedence_core_impl(71); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000072() { nc_precedence_core_impl(72); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000073() { nc_precedence_core_impl(73); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000074() { nc_precedence_core_impl(74); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000075() { nc_precedence_core_impl(75); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000076() { nc_precedence_core_impl(76); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000077() { nc_precedence_core_impl(77); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000078() { nc_precedence_core_impl(78); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000079() { nc_precedence_core_impl(79); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000080() { nc_precedence_core_impl(80); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000081() { nc_precedence_core_impl(81); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000082() { nc_precedence_core_impl(82); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000083() { nc_precedence_core_impl(83); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000084() { nc_precedence_core_impl(84); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000085() { nc_precedence_core_impl(85); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000086() { nc_precedence_core_impl(86); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000087() { nc_precedence_core_impl(87); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000088() { nc_precedence_core_impl(88); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000089() { nc_precedence_core_impl(89); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000090() { nc_precedence_core_impl(90); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000091() { nc_precedence_core_impl(91); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000092() { nc_precedence_core_impl(92); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000093() { nc_precedence_core_impl(93); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000094() { nc_precedence_core_impl(94); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000095() { nc_precedence_core_impl(95); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000096() { nc_precedence_core_impl(96); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000097() { nc_precedence_core_impl(97); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000098() { nc_precedence_core_impl(98); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000099() { nc_precedence_core_impl(99); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000100() { nc_precedence_core_impl(100); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000101() { nc_precedence_core_impl(101); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000102() { nc_precedence_core_impl(102); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000103() { nc_precedence_core_impl(103); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000104() { nc_precedence_core_impl(104); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000105() { nc_precedence_core_impl(105); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000106() { nc_precedence_core_impl(106); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000107() { nc_precedence_core_impl(107); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000108() { nc_precedence_core_impl(108); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000109() { nc_precedence_core_impl(109); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000110() { nc_precedence_core_impl(110); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000111() { nc_precedence_core_impl(111); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000112() { nc_precedence_core_impl(112); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000113() { nc_precedence_core_impl(113); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000114() { nc_precedence_core_impl(114); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000115() { nc_precedence_core_impl(115); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000116() { nc_precedence_core_impl(116); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000117() { nc_precedence_core_impl(117); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000118() { nc_precedence_core_impl(118); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000119() { nc_precedence_core_impl(119); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000120() { nc_precedence_core_impl(120); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000121() { nc_precedence_core_impl(121); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000122() { nc_precedence_core_impl(122); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000123() { nc_precedence_core_impl(123); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000124() { nc_precedence_core_impl(124); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000125() { nc_precedence_core_impl(125); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000126() { nc_precedence_core_impl(126); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000127() { nc_precedence_core_impl(127); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000128() { nc_precedence_core_impl(128); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000129() { nc_precedence_core_impl(129); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000130() { nc_precedence_core_impl(130); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000131() { nc_precedence_core_impl(131); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000132() { nc_precedence_core_impl(132); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000133() { nc_precedence_core_impl(133); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000134() { nc_precedence_core_impl(134); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000135() { nc_precedence_core_impl(135); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000136() { nc_precedence_core_impl(136); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000137() { nc_precedence_core_impl(137); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000138() { nc_precedence_core_impl(138); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000139() { nc_precedence_core_impl(139); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000140() { nc_precedence_core_impl(140); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000141() { nc_precedence_core_impl(141); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000142() { nc_precedence_core_impl(142); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000143() { nc_precedence_core_impl(143); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000144() { nc_precedence_core_impl(144); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000145() { nc_precedence_core_impl(145); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000146() { nc_precedence_core_impl(146); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000147() { nc_precedence_core_impl(147); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000148() { nc_precedence_core_impl(148); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000149() { nc_precedence_core_impl(149); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000150() { nc_precedence_core_impl(150); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000151() { nc_precedence_core_impl(151); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000152() { nc_precedence_core_impl(152); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000153() { nc_precedence_core_impl(153); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000154() { nc_precedence_core_impl(154); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000155() { nc_precedence_core_impl(155); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000156() { nc_precedence_core_impl(156); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000157() { nc_precedence_core_impl(157); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000158() { nc_precedence_core_impl(158); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000159() { nc_precedence_core_impl(159); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000160() { nc_precedence_core_impl(160); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000161() { nc_precedence_core_impl(161); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000162() { nc_precedence_core_impl(162); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000163() { nc_precedence_core_impl(163); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000164() { nc_precedence_core_impl(164); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000165() { nc_precedence_core_impl(165); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000166() { nc_precedence_core_impl(166); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000167() { nc_precedence_core_impl(167); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000168() { nc_precedence_core_impl(168); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000169() { nc_precedence_core_impl(169); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000170() { nc_precedence_core_impl(170); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000171() { nc_precedence_core_impl(171); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000172() { nc_precedence_core_impl(172); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000173() { nc_precedence_core_impl(173); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000174() { nc_precedence_core_impl(174); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000175() { nc_precedence_core_impl(175); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000176() { nc_precedence_core_impl(176); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000177() { nc_precedence_core_impl(177); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000178() { nc_precedence_core_impl(178); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000179() { nc_precedence_core_impl(179); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000180() { nc_precedence_core_impl(180); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000181() { nc_precedence_core_impl(181); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000182() { nc_precedence_core_impl(182); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000183() { nc_precedence_core_impl(183); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000184() { nc_precedence_core_impl(184); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000185() { nc_precedence_core_impl(185); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000186() { nc_precedence_core_impl(186); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000187() { nc_precedence_core_impl(187); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000188() { nc_precedence_core_impl(188); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000189() { nc_precedence_core_impl(189); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000190() { nc_precedence_core_impl(190); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000191() { nc_precedence_core_impl(191); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000192() { nc_precedence_core_impl(192); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000193() { nc_precedence_core_impl(193); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000194() { nc_precedence_core_impl(194); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000195() { nc_precedence_core_impl(195); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000196() { nc_precedence_core_impl(196); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000197() { nc_precedence_core_impl(197); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000198() { nc_precedence_core_impl(198); }
    #[cfg_attr(test, test)]
    fn nc_precedence_core_seed_000199() { nc_precedence_core_impl(199); }
    // --- nc_precedence_v6: 200 generated seeds ---
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000000() { nc_precedence_v6_impl(0); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000001() { nc_precedence_v6_impl(1); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000002() { nc_precedence_v6_impl(2); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000003() { nc_precedence_v6_impl(3); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000004() { nc_precedence_v6_impl(4); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000005() { nc_precedence_v6_impl(5); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000006() { nc_precedence_v6_impl(6); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000007() { nc_precedence_v6_impl(7); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000008() { nc_precedence_v6_impl(8); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000009() { nc_precedence_v6_impl(9); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000010() { nc_precedence_v6_impl(10); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000011() { nc_precedence_v6_impl(11); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000012() { nc_precedence_v6_impl(12); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000013() { nc_precedence_v6_impl(13); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000014() { nc_precedence_v6_impl(14); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000015() { nc_precedence_v6_impl(15); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000016() { nc_precedence_v6_impl(16); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000017() { nc_precedence_v6_impl(17); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000018() { nc_precedence_v6_impl(18); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000019() { nc_precedence_v6_impl(19); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000020() { nc_precedence_v6_impl(20); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000021() { nc_precedence_v6_impl(21); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000022() { nc_precedence_v6_impl(22); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000023() { nc_precedence_v6_impl(23); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000024() { nc_precedence_v6_impl(24); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000025() { nc_precedence_v6_impl(25); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000026() { nc_precedence_v6_impl(26); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000027() { nc_precedence_v6_impl(27); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000028() { nc_precedence_v6_impl(28); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000029() { nc_precedence_v6_impl(29); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000030() { nc_precedence_v6_impl(30); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000031() { nc_precedence_v6_impl(31); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000032() { nc_precedence_v6_impl(32); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000033() { nc_precedence_v6_impl(33); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000034() { nc_precedence_v6_impl(34); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000035() { nc_precedence_v6_impl(35); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000036() { nc_precedence_v6_impl(36); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000037() { nc_precedence_v6_impl(37); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000038() { nc_precedence_v6_impl(38); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000039() { nc_precedence_v6_impl(39); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000040() { nc_precedence_v6_impl(40); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000041() { nc_precedence_v6_impl(41); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000042() { nc_precedence_v6_impl(42); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000043() { nc_precedence_v6_impl(43); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000044() { nc_precedence_v6_impl(44); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000045() { nc_precedence_v6_impl(45); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000046() { nc_precedence_v6_impl(46); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000047() { nc_precedence_v6_impl(47); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000048() { nc_precedence_v6_impl(48); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000049() { nc_precedence_v6_impl(49); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000050() { nc_precedence_v6_impl(50); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000051() { nc_precedence_v6_impl(51); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000052() { nc_precedence_v6_impl(52); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000053() { nc_precedence_v6_impl(53); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000054() { nc_precedence_v6_impl(54); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000055() { nc_precedence_v6_impl(55); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000056() { nc_precedence_v6_impl(56); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000057() { nc_precedence_v6_impl(57); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000058() { nc_precedence_v6_impl(58); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000059() { nc_precedence_v6_impl(59); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000060() { nc_precedence_v6_impl(60); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000061() { nc_precedence_v6_impl(61); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000062() { nc_precedence_v6_impl(62); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000063() { nc_precedence_v6_impl(63); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000064() { nc_precedence_v6_impl(64); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000065() { nc_precedence_v6_impl(65); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000066() { nc_precedence_v6_impl(66); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000067() { nc_precedence_v6_impl(67); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000068() { nc_precedence_v6_impl(68); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000069() { nc_precedence_v6_impl(69); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000070() { nc_precedence_v6_impl(70); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000071() { nc_precedence_v6_impl(71); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000072() { nc_precedence_v6_impl(72); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000073() { nc_precedence_v6_impl(73); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000074() { nc_precedence_v6_impl(74); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000075() { nc_precedence_v6_impl(75); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000076() { nc_precedence_v6_impl(76); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000077() { nc_precedence_v6_impl(77); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000078() { nc_precedence_v6_impl(78); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000079() { nc_precedence_v6_impl(79); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000080() { nc_precedence_v6_impl(80); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000081() { nc_precedence_v6_impl(81); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000082() { nc_precedence_v6_impl(82); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000083() { nc_precedence_v6_impl(83); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000084() { nc_precedence_v6_impl(84); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000085() { nc_precedence_v6_impl(85); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000086() { nc_precedence_v6_impl(86); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000087() { nc_precedence_v6_impl(87); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000088() { nc_precedence_v6_impl(88); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000089() { nc_precedence_v6_impl(89); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000090() { nc_precedence_v6_impl(90); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000091() { nc_precedence_v6_impl(91); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000092() { nc_precedence_v6_impl(92); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000093() { nc_precedence_v6_impl(93); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000094() { nc_precedence_v6_impl(94); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000095() { nc_precedence_v6_impl(95); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000096() { nc_precedence_v6_impl(96); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000097() { nc_precedence_v6_impl(97); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000098() { nc_precedence_v6_impl(98); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000099() { nc_precedence_v6_impl(99); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000100() { nc_precedence_v6_impl(100); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000101() { nc_precedence_v6_impl(101); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000102() { nc_precedence_v6_impl(102); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000103() { nc_precedence_v6_impl(103); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000104() { nc_precedence_v6_impl(104); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000105() { nc_precedence_v6_impl(105); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000106() { nc_precedence_v6_impl(106); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000107() { nc_precedence_v6_impl(107); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000108() { nc_precedence_v6_impl(108); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000109() { nc_precedence_v6_impl(109); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000110() { nc_precedence_v6_impl(110); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000111() { nc_precedence_v6_impl(111); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000112() { nc_precedence_v6_impl(112); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000113() { nc_precedence_v6_impl(113); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000114() { nc_precedence_v6_impl(114); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000115() { nc_precedence_v6_impl(115); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000116() { nc_precedence_v6_impl(116); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000117() { nc_precedence_v6_impl(117); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000118() { nc_precedence_v6_impl(118); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000119() { nc_precedence_v6_impl(119); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000120() { nc_precedence_v6_impl(120); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000121() { nc_precedence_v6_impl(121); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000122() { nc_precedence_v6_impl(122); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000123() { nc_precedence_v6_impl(123); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000124() { nc_precedence_v6_impl(124); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000125() { nc_precedence_v6_impl(125); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000126() { nc_precedence_v6_impl(126); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000127() { nc_precedence_v6_impl(127); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000128() { nc_precedence_v6_impl(128); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000129() { nc_precedence_v6_impl(129); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000130() { nc_precedence_v6_impl(130); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000131() { nc_precedence_v6_impl(131); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000132() { nc_precedence_v6_impl(132); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000133() { nc_precedence_v6_impl(133); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000134() { nc_precedence_v6_impl(134); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000135() { nc_precedence_v6_impl(135); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000136() { nc_precedence_v6_impl(136); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000137() { nc_precedence_v6_impl(137); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000138() { nc_precedence_v6_impl(138); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000139() { nc_precedence_v6_impl(139); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000140() { nc_precedence_v6_impl(140); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000141() { nc_precedence_v6_impl(141); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000142() { nc_precedence_v6_impl(142); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000143() { nc_precedence_v6_impl(143); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000144() { nc_precedence_v6_impl(144); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000145() { nc_precedence_v6_impl(145); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000146() { nc_precedence_v6_impl(146); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000147() { nc_precedence_v6_impl(147); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000148() { nc_precedence_v6_impl(148); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000149() { nc_precedence_v6_impl(149); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000150() { nc_precedence_v6_impl(150); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000151() { nc_precedence_v6_impl(151); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000152() { nc_precedence_v6_impl(152); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000153() { nc_precedence_v6_impl(153); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000154() { nc_precedence_v6_impl(154); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000155() { nc_precedence_v6_impl(155); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000156() { nc_precedence_v6_impl(156); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000157() { nc_precedence_v6_impl(157); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000158() { nc_precedence_v6_impl(158); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000159() { nc_precedence_v6_impl(159); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000160() { nc_precedence_v6_impl(160); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000161() { nc_precedence_v6_impl(161); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000162() { nc_precedence_v6_impl(162); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000163() { nc_precedence_v6_impl(163); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000164() { nc_precedence_v6_impl(164); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000165() { nc_precedence_v6_impl(165); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000166() { nc_precedence_v6_impl(166); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000167() { nc_precedence_v6_impl(167); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000168() { nc_precedence_v6_impl(168); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000169() { nc_precedence_v6_impl(169); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000170() { nc_precedence_v6_impl(170); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000171() { nc_precedence_v6_impl(171); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000172() { nc_precedence_v6_impl(172); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000173() { nc_precedence_v6_impl(173); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000174() { nc_precedence_v6_impl(174); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000175() { nc_precedence_v6_impl(175); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000176() { nc_precedence_v6_impl(176); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000177() { nc_precedence_v6_impl(177); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000178() { nc_precedence_v6_impl(178); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000179() { nc_precedence_v6_impl(179); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000180() { nc_precedence_v6_impl(180); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000181() { nc_precedence_v6_impl(181); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000182() { nc_precedence_v6_impl(182); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000183() { nc_precedence_v6_impl(183); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000184() { nc_precedence_v6_impl(184); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000185() { nc_precedence_v6_impl(185); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000186() { nc_precedence_v6_impl(186); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000187() { nc_precedence_v6_impl(187); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000188() { nc_precedence_v6_impl(188); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000189() { nc_precedence_v6_impl(189); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000190() { nc_precedence_v6_impl(190); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000191() { nc_precedence_v6_impl(191); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000192() { nc_precedence_v6_impl(192); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000193() { nc_precedence_v6_impl(193); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000194() { nc_precedence_v6_impl(194); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000195() { nc_precedence_v6_impl(195); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000196() { nc_precedence_v6_impl(196); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000197() { nc_precedence_v6_impl(197); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000198() { nc_precedence_v6_impl(198); }
    #[cfg_attr(test, test)]
    fn nc_precedence_v6_seed_000199() { nc_precedence_v6_impl(199); }
    // --- nc_case_invariance_core: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000000() { nc_case_invariance_core_impl(0); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000001() { nc_case_invariance_core_impl(1); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000002() { nc_case_invariance_core_impl(2); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000003() { nc_case_invariance_core_impl(3); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000004() { nc_case_invariance_core_impl(4); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000005() { nc_case_invariance_core_impl(5); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000006() { nc_case_invariance_core_impl(6); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000007() { nc_case_invariance_core_impl(7); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000008() { nc_case_invariance_core_impl(8); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000009() { nc_case_invariance_core_impl(9); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000010() { nc_case_invariance_core_impl(10); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000011() { nc_case_invariance_core_impl(11); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000012() { nc_case_invariance_core_impl(12); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000013() { nc_case_invariance_core_impl(13); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000014() { nc_case_invariance_core_impl(14); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000015() { nc_case_invariance_core_impl(15); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000016() { nc_case_invariance_core_impl(16); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000017() { nc_case_invariance_core_impl(17); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000018() { nc_case_invariance_core_impl(18); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000019() { nc_case_invariance_core_impl(19); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000020() { nc_case_invariance_core_impl(20); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000021() { nc_case_invariance_core_impl(21); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000022() { nc_case_invariance_core_impl(22); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000023() { nc_case_invariance_core_impl(23); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000024() { nc_case_invariance_core_impl(24); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000025() { nc_case_invariance_core_impl(25); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000026() { nc_case_invariance_core_impl(26); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000027() { nc_case_invariance_core_impl(27); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000028() { nc_case_invariance_core_impl(28); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000029() { nc_case_invariance_core_impl(29); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000030() { nc_case_invariance_core_impl(30); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000031() { nc_case_invariance_core_impl(31); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000032() { nc_case_invariance_core_impl(32); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000033() { nc_case_invariance_core_impl(33); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000034() { nc_case_invariance_core_impl(34); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000035() { nc_case_invariance_core_impl(35); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000036() { nc_case_invariance_core_impl(36); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000037() { nc_case_invariance_core_impl(37); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000038() { nc_case_invariance_core_impl(38); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000039() { nc_case_invariance_core_impl(39); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000040() { nc_case_invariance_core_impl(40); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000041() { nc_case_invariance_core_impl(41); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000042() { nc_case_invariance_core_impl(42); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000043() { nc_case_invariance_core_impl(43); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000044() { nc_case_invariance_core_impl(44); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000045() { nc_case_invariance_core_impl(45); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000046() { nc_case_invariance_core_impl(46); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000047() { nc_case_invariance_core_impl(47); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000048() { nc_case_invariance_core_impl(48); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000049() { nc_case_invariance_core_impl(49); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000050() { nc_case_invariance_core_impl(50); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000051() { nc_case_invariance_core_impl(51); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000052() { nc_case_invariance_core_impl(52); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000053() { nc_case_invariance_core_impl(53); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000054() { nc_case_invariance_core_impl(54); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000055() { nc_case_invariance_core_impl(55); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000056() { nc_case_invariance_core_impl(56); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000057() { nc_case_invariance_core_impl(57); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000058() { nc_case_invariance_core_impl(58); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000059() { nc_case_invariance_core_impl(59); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000060() { nc_case_invariance_core_impl(60); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000061() { nc_case_invariance_core_impl(61); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000062() { nc_case_invariance_core_impl(62); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000063() { nc_case_invariance_core_impl(63); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000064() { nc_case_invariance_core_impl(64); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000065() { nc_case_invariance_core_impl(65); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000066() { nc_case_invariance_core_impl(66); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000067() { nc_case_invariance_core_impl(67); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000068() { nc_case_invariance_core_impl(68); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000069() { nc_case_invariance_core_impl(69); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000070() { nc_case_invariance_core_impl(70); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000071() { nc_case_invariance_core_impl(71); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000072() { nc_case_invariance_core_impl(72); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000073() { nc_case_invariance_core_impl(73); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000074() { nc_case_invariance_core_impl(74); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000075() { nc_case_invariance_core_impl(75); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000076() { nc_case_invariance_core_impl(76); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000077() { nc_case_invariance_core_impl(77); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000078() { nc_case_invariance_core_impl(78); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000079() { nc_case_invariance_core_impl(79); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000080() { nc_case_invariance_core_impl(80); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000081() { nc_case_invariance_core_impl(81); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000082() { nc_case_invariance_core_impl(82); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000083() { nc_case_invariance_core_impl(83); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000084() { nc_case_invariance_core_impl(84); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000085() { nc_case_invariance_core_impl(85); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000086() { nc_case_invariance_core_impl(86); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000087() { nc_case_invariance_core_impl(87); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000088() { nc_case_invariance_core_impl(88); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000089() { nc_case_invariance_core_impl(89); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000090() { nc_case_invariance_core_impl(90); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000091() { nc_case_invariance_core_impl(91); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000092() { nc_case_invariance_core_impl(92); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000093() { nc_case_invariance_core_impl(93); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000094() { nc_case_invariance_core_impl(94); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000095() { nc_case_invariance_core_impl(95); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000096() { nc_case_invariance_core_impl(96); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000097() { nc_case_invariance_core_impl(97); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000098() { nc_case_invariance_core_impl(98); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000099() { nc_case_invariance_core_impl(99); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000100() { nc_case_invariance_core_impl(100); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000101() { nc_case_invariance_core_impl(101); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000102() { nc_case_invariance_core_impl(102); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000103() { nc_case_invariance_core_impl(103); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000104() { nc_case_invariance_core_impl(104); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000105() { nc_case_invariance_core_impl(105); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000106() { nc_case_invariance_core_impl(106); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000107() { nc_case_invariance_core_impl(107); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000108() { nc_case_invariance_core_impl(108); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000109() { nc_case_invariance_core_impl(109); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000110() { nc_case_invariance_core_impl(110); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000111() { nc_case_invariance_core_impl(111); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000112() { nc_case_invariance_core_impl(112); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000113() { nc_case_invariance_core_impl(113); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000114() { nc_case_invariance_core_impl(114); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000115() { nc_case_invariance_core_impl(115); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000116() { nc_case_invariance_core_impl(116); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000117() { nc_case_invariance_core_impl(117); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000118() { nc_case_invariance_core_impl(118); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000119() { nc_case_invariance_core_impl(119); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000120() { nc_case_invariance_core_impl(120); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000121() { nc_case_invariance_core_impl(121); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000122() { nc_case_invariance_core_impl(122); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000123() { nc_case_invariance_core_impl(123); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000124() { nc_case_invariance_core_impl(124); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000125() { nc_case_invariance_core_impl(125); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000126() { nc_case_invariance_core_impl(126); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000127() { nc_case_invariance_core_impl(127); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000128() { nc_case_invariance_core_impl(128); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000129() { nc_case_invariance_core_impl(129); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000130() { nc_case_invariance_core_impl(130); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000131() { nc_case_invariance_core_impl(131); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000132() { nc_case_invariance_core_impl(132); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000133() { nc_case_invariance_core_impl(133); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000134() { nc_case_invariance_core_impl(134); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000135() { nc_case_invariance_core_impl(135); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000136() { nc_case_invariance_core_impl(136); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000137() { nc_case_invariance_core_impl(137); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000138() { nc_case_invariance_core_impl(138); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000139() { nc_case_invariance_core_impl(139); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000140() { nc_case_invariance_core_impl(140); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000141() { nc_case_invariance_core_impl(141); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000142() { nc_case_invariance_core_impl(142); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000143() { nc_case_invariance_core_impl(143); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000144() { nc_case_invariance_core_impl(144); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000145() { nc_case_invariance_core_impl(145); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000146() { nc_case_invariance_core_impl(146); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000147() { nc_case_invariance_core_impl(147); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000148() { nc_case_invariance_core_impl(148); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_core_seed_000149() { nc_case_invariance_core_impl(149); }
    // --- nc_case_invariance_v6: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000000() { nc_case_invariance_v6_impl(0); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000001() { nc_case_invariance_v6_impl(1); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000002() { nc_case_invariance_v6_impl(2); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000003() { nc_case_invariance_v6_impl(3); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000004() { nc_case_invariance_v6_impl(4); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000005() { nc_case_invariance_v6_impl(5); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000006() { nc_case_invariance_v6_impl(6); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000007() { nc_case_invariance_v6_impl(7); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000008() { nc_case_invariance_v6_impl(8); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000009() { nc_case_invariance_v6_impl(9); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000010() { nc_case_invariance_v6_impl(10); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000011() { nc_case_invariance_v6_impl(11); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000012() { nc_case_invariance_v6_impl(12); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000013() { nc_case_invariance_v6_impl(13); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000014() { nc_case_invariance_v6_impl(14); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000015() { nc_case_invariance_v6_impl(15); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000016() { nc_case_invariance_v6_impl(16); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000017() { nc_case_invariance_v6_impl(17); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000018() { nc_case_invariance_v6_impl(18); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000019() { nc_case_invariance_v6_impl(19); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000020() { nc_case_invariance_v6_impl(20); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000021() { nc_case_invariance_v6_impl(21); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000022() { nc_case_invariance_v6_impl(22); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000023() { nc_case_invariance_v6_impl(23); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000024() { nc_case_invariance_v6_impl(24); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000025() { nc_case_invariance_v6_impl(25); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000026() { nc_case_invariance_v6_impl(26); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000027() { nc_case_invariance_v6_impl(27); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000028() { nc_case_invariance_v6_impl(28); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000029() { nc_case_invariance_v6_impl(29); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000030() { nc_case_invariance_v6_impl(30); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000031() { nc_case_invariance_v6_impl(31); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000032() { nc_case_invariance_v6_impl(32); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000033() { nc_case_invariance_v6_impl(33); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000034() { nc_case_invariance_v6_impl(34); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000035() { nc_case_invariance_v6_impl(35); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000036() { nc_case_invariance_v6_impl(36); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000037() { nc_case_invariance_v6_impl(37); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000038() { nc_case_invariance_v6_impl(38); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000039() { nc_case_invariance_v6_impl(39); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000040() { nc_case_invariance_v6_impl(40); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000041() { nc_case_invariance_v6_impl(41); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000042() { nc_case_invariance_v6_impl(42); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000043() { nc_case_invariance_v6_impl(43); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000044() { nc_case_invariance_v6_impl(44); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000045() { nc_case_invariance_v6_impl(45); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000046() { nc_case_invariance_v6_impl(46); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000047() { nc_case_invariance_v6_impl(47); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000048() { nc_case_invariance_v6_impl(48); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000049() { nc_case_invariance_v6_impl(49); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000050() { nc_case_invariance_v6_impl(50); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000051() { nc_case_invariance_v6_impl(51); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000052() { nc_case_invariance_v6_impl(52); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000053() { nc_case_invariance_v6_impl(53); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000054() { nc_case_invariance_v6_impl(54); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000055() { nc_case_invariance_v6_impl(55); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000056() { nc_case_invariance_v6_impl(56); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000057() { nc_case_invariance_v6_impl(57); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000058() { nc_case_invariance_v6_impl(58); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000059() { nc_case_invariance_v6_impl(59); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000060() { nc_case_invariance_v6_impl(60); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000061() { nc_case_invariance_v6_impl(61); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000062() { nc_case_invariance_v6_impl(62); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000063() { nc_case_invariance_v6_impl(63); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000064() { nc_case_invariance_v6_impl(64); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000065() { nc_case_invariance_v6_impl(65); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000066() { nc_case_invariance_v6_impl(66); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000067() { nc_case_invariance_v6_impl(67); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000068() { nc_case_invariance_v6_impl(68); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000069() { nc_case_invariance_v6_impl(69); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000070() { nc_case_invariance_v6_impl(70); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000071() { nc_case_invariance_v6_impl(71); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000072() { nc_case_invariance_v6_impl(72); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000073() { nc_case_invariance_v6_impl(73); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000074() { nc_case_invariance_v6_impl(74); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000075() { nc_case_invariance_v6_impl(75); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000076() { nc_case_invariance_v6_impl(76); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000077() { nc_case_invariance_v6_impl(77); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000078() { nc_case_invariance_v6_impl(78); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000079() { nc_case_invariance_v6_impl(79); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000080() { nc_case_invariance_v6_impl(80); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000081() { nc_case_invariance_v6_impl(81); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000082() { nc_case_invariance_v6_impl(82); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000083() { nc_case_invariance_v6_impl(83); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000084() { nc_case_invariance_v6_impl(84); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000085() { nc_case_invariance_v6_impl(85); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000086() { nc_case_invariance_v6_impl(86); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000087() { nc_case_invariance_v6_impl(87); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000088() { nc_case_invariance_v6_impl(88); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000089() { nc_case_invariance_v6_impl(89); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000090() { nc_case_invariance_v6_impl(90); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000091() { nc_case_invariance_v6_impl(91); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000092() { nc_case_invariance_v6_impl(92); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000093() { nc_case_invariance_v6_impl(93); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000094() { nc_case_invariance_v6_impl(94); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000095() { nc_case_invariance_v6_impl(95); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000096() { nc_case_invariance_v6_impl(96); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000097() { nc_case_invariance_v6_impl(97); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000098() { nc_case_invariance_v6_impl(98); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000099() { nc_case_invariance_v6_impl(99); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000100() { nc_case_invariance_v6_impl(100); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000101() { nc_case_invariance_v6_impl(101); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000102() { nc_case_invariance_v6_impl(102); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000103() { nc_case_invariance_v6_impl(103); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000104() { nc_case_invariance_v6_impl(104); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000105() { nc_case_invariance_v6_impl(105); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000106() { nc_case_invariance_v6_impl(106); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000107() { nc_case_invariance_v6_impl(107); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000108() { nc_case_invariance_v6_impl(108); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000109() { nc_case_invariance_v6_impl(109); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000110() { nc_case_invariance_v6_impl(110); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000111() { nc_case_invariance_v6_impl(111); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000112() { nc_case_invariance_v6_impl(112); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000113() { nc_case_invariance_v6_impl(113); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000114() { nc_case_invariance_v6_impl(114); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000115() { nc_case_invariance_v6_impl(115); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000116() { nc_case_invariance_v6_impl(116); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000117() { nc_case_invariance_v6_impl(117); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000118() { nc_case_invariance_v6_impl(118); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000119() { nc_case_invariance_v6_impl(119); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000120() { nc_case_invariance_v6_impl(120); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000121() { nc_case_invariance_v6_impl(121); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000122() { nc_case_invariance_v6_impl(122); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000123() { nc_case_invariance_v6_impl(123); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000124() { nc_case_invariance_v6_impl(124); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000125() { nc_case_invariance_v6_impl(125); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000126() { nc_case_invariance_v6_impl(126); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000127() { nc_case_invariance_v6_impl(127); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000128() { nc_case_invariance_v6_impl(128); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000129() { nc_case_invariance_v6_impl(129); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000130() { nc_case_invariance_v6_impl(130); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000131() { nc_case_invariance_v6_impl(131); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000132() { nc_case_invariance_v6_impl(132); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000133() { nc_case_invariance_v6_impl(133); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000134() { nc_case_invariance_v6_impl(134); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000135() { nc_case_invariance_v6_impl(135); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000136() { nc_case_invariance_v6_impl(136); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000137() { nc_case_invariance_v6_impl(137); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000138() { nc_case_invariance_v6_impl(138); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000139() { nc_case_invariance_v6_impl(139); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000140() { nc_case_invariance_v6_impl(140); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000141() { nc_case_invariance_v6_impl(141); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000142() { nc_case_invariance_v6_impl(142); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000143() { nc_case_invariance_v6_impl(143); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000144() { nc_case_invariance_v6_impl(144); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000145() { nc_case_invariance_v6_impl(145); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000146() { nc_case_invariance_v6_impl(146); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000147() { nc_case_invariance_v6_impl(147); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000148() { nc_case_invariance_v6_impl(148); }
    #[cfg_attr(test, test)]
    fn nc_case_invariance_v6_seed_000149() { nc_case_invariance_v6_impl(149); }
    // --- adj_symmetry: 120 generated seeds ---
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000000() { adj_symmetry_impl(0); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000001() { adj_symmetry_impl(1); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000002() { adj_symmetry_impl(2); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000003() { adj_symmetry_impl(3); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000004() { adj_symmetry_impl(4); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000005() { adj_symmetry_impl(5); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000006() { adj_symmetry_impl(6); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000007() { adj_symmetry_impl(7); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000008() { adj_symmetry_impl(8); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000009() { adj_symmetry_impl(9); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000010() { adj_symmetry_impl(10); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000011() { adj_symmetry_impl(11); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000012() { adj_symmetry_impl(12); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000013() { adj_symmetry_impl(13); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000014() { adj_symmetry_impl(14); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000015() { adj_symmetry_impl(15); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000016() { adj_symmetry_impl(16); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000017() { adj_symmetry_impl(17); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000018() { adj_symmetry_impl(18); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000019() { adj_symmetry_impl(19); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000020() { adj_symmetry_impl(20); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000021() { adj_symmetry_impl(21); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000022() { adj_symmetry_impl(22); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000023() { adj_symmetry_impl(23); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000024() { adj_symmetry_impl(24); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000025() { adj_symmetry_impl(25); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000026() { adj_symmetry_impl(26); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000027() { adj_symmetry_impl(27); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000028() { adj_symmetry_impl(28); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000029() { adj_symmetry_impl(29); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000030() { adj_symmetry_impl(30); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000031() { adj_symmetry_impl(31); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000032() { adj_symmetry_impl(32); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000033() { adj_symmetry_impl(33); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000034() { adj_symmetry_impl(34); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000035() { adj_symmetry_impl(35); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000036() { adj_symmetry_impl(36); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000037() { adj_symmetry_impl(37); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000038() { adj_symmetry_impl(38); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000039() { adj_symmetry_impl(39); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000040() { adj_symmetry_impl(40); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000041() { adj_symmetry_impl(41); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000042() { adj_symmetry_impl(42); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000043() { adj_symmetry_impl(43); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000044() { adj_symmetry_impl(44); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000045() { adj_symmetry_impl(45); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000046() { adj_symmetry_impl(46); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000047() { adj_symmetry_impl(47); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000048() { adj_symmetry_impl(48); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000049() { adj_symmetry_impl(49); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000050() { adj_symmetry_impl(50); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000051() { adj_symmetry_impl(51); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000052() { adj_symmetry_impl(52); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000053() { adj_symmetry_impl(53); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000054() { adj_symmetry_impl(54); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000055() { adj_symmetry_impl(55); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000056() { adj_symmetry_impl(56); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000057() { adj_symmetry_impl(57); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000058() { adj_symmetry_impl(58); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000059() { adj_symmetry_impl(59); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000060() { adj_symmetry_impl(60); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000061() { adj_symmetry_impl(61); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000062() { adj_symmetry_impl(62); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000063() { adj_symmetry_impl(63); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000064() { adj_symmetry_impl(64); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000065() { adj_symmetry_impl(65); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000066() { adj_symmetry_impl(66); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000067() { adj_symmetry_impl(67); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000068() { adj_symmetry_impl(68); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000069() { adj_symmetry_impl(69); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000070() { adj_symmetry_impl(70); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000071() { adj_symmetry_impl(71); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000072() { adj_symmetry_impl(72); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000073() { adj_symmetry_impl(73); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000074() { adj_symmetry_impl(74); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000075() { adj_symmetry_impl(75); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000076() { adj_symmetry_impl(76); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000077() { adj_symmetry_impl(77); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000078() { adj_symmetry_impl(78); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000079() { adj_symmetry_impl(79); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000080() { adj_symmetry_impl(80); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000081() { adj_symmetry_impl(81); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000082() { adj_symmetry_impl(82); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000083() { adj_symmetry_impl(83); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000084() { adj_symmetry_impl(84); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000085() { adj_symmetry_impl(85); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000086() { adj_symmetry_impl(86); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000087() { adj_symmetry_impl(87); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000088() { adj_symmetry_impl(88); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000089() { adj_symmetry_impl(89); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000090() { adj_symmetry_impl(90); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000091() { adj_symmetry_impl(91); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000092() { adj_symmetry_impl(92); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000093() { adj_symmetry_impl(93); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000094() { adj_symmetry_impl(94); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000095() { adj_symmetry_impl(95); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000096() { adj_symmetry_impl(96); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000097() { adj_symmetry_impl(97); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000098() { adj_symmetry_impl(98); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000099() { adj_symmetry_impl(99); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000100() { adj_symmetry_impl(100); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000101() { adj_symmetry_impl(101); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000102() { adj_symmetry_impl(102); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000103() { adj_symmetry_impl(103); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000104() { adj_symmetry_impl(104); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000105() { adj_symmetry_impl(105); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000106() { adj_symmetry_impl(106); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000107() { adj_symmetry_impl(107); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000108() { adj_symmetry_impl(108); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000109() { adj_symmetry_impl(109); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000110() { adj_symmetry_impl(110); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000111() { adj_symmetry_impl(111); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000112() { adj_symmetry_impl(112); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000113() { adj_symmetry_impl(113); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000114() { adj_symmetry_impl(114); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000115() { adj_symmetry_impl(115); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000116() { adj_symmetry_impl(116); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000117() { adj_symmetry_impl(117); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000118() { adj_symmetry_impl(118); }
    #[cfg_attr(test, test)]
    fn adj_symmetry_seed_000119() { adj_symmetry_impl(119); }
    // --- adj_diagonal_zero: 120 generated seeds ---
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000000() { adj_diagonal_zero_impl(0); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000001() { adj_diagonal_zero_impl(1); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000002() { adj_diagonal_zero_impl(2); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000003() { adj_diagonal_zero_impl(3); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000004() { adj_diagonal_zero_impl(4); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000005() { adj_diagonal_zero_impl(5); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000006() { adj_diagonal_zero_impl(6); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000007() { adj_diagonal_zero_impl(7); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000008() { adj_diagonal_zero_impl(8); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000009() { adj_diagonal_zero_impl(9); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000010() { adj_diagonal_zero_impl(10); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000011() { adj_diagonal_zero_impl(11); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000012() { adj_diagonal_zero_impl(12); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000013() { adj_diagonal_zero_impl(13); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000014() { adj_diagonal_zero_impl(14); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000015() { adj_diagonal_zero_impl(15); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000016() { adj_diagonal_zero_impl(16); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000017() { adj_diagonal_zero_impl(17); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000018() { adj_diagonal_zero_impl(18); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000019() { adj_diagonal_zero_impl(19); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000020() { adj_diagonal_zero_impl(20); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000021() { adj_diagonal_zero_impl(21); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000022() { adj_diagonal_zero_impl(22); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000023() { adj_diagonal_zero_impl(23); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000024() { adj_diagonal_zero_impl(24); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000025() { adj_diagonal_zero_impl(25); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000026() { adj_diagonal_zero_impl(26); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000027() { adj_diagonal_zero_impl(27); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000028() { adj_diagonal_zero_impl(28); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000029() { adj_diagonal_zero_impl(29); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000030() { adj_diagonal_zero_impl(30); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000031() { adj_diagonal_zero_impl(31); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000032() { adj_diagonal_zero_impl(32); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000033() { adj_diagonal_zero_impl(33); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000034() { adj_diagonal_zero_impl(34); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000035() { adj_diagonal_zero_impl(35); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000036() { adj_diagonal_zero_impl(36); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000037() { adj_diagonal_zero_impl(37); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000038() { adj_diagonal_zero_impl(38); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000039() { adj_diagonal_zero_impl(39); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000040() { adj_diagonal_zero_impl(40); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000041() { adj_diagonal_zero_impl(41); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000042() { adj_diagonal_zero_impl(42); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000043() { adj_diagonal_zero_impl(43); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000044() { adj_diagonal_zero_impl(44); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000045() { adj_diagonal_zero_impl(45); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000046() { adj_diagonal_zero_impl(46); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000047() { adj_diagonal_zero_impl(47); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000048() { adj_diagonal_zero_impl(48); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000049() { adj_diagonal_zero_impl(49); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000050() { adj_diagonal_zero_impl(50); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000051() { adj_diagonal_zero_impl(51); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000052() { adj_diagonal_zero_impl(52); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000053() { adj_diagonal_zero_impl(53); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000054() { adj_diagonal_zero_impl(54); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000055() { adj_diagonal_zero_impl(55); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000056() { adj_diagonal_zero_impl(56); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000057() { adj_diagonal_zero_impl(57); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000058() { adj_diagonal_zero_impl(58); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000059() { adj_diagonal_zero_impl(59); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000060() { adj_diagonal_zero_impl(60); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000061() { adj_diagonal_zero_impl(61); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000062() { adj_diagonal_zero_impl(62); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000063() { adj_diagonal_zero_impl(63); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000064() { adj_diagonal_zero_impl(64); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000065() { adj_diagonal_zero_impl(65); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000066() { adj_diagonal_zero_impl(66); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000067() { adj_diagonal_zero_impl(67); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000068() { adj_diagonal_zero_impl(68); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000069() { adj_diagonal_zero_impl(69); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000070() { adj_diagonal_zero_impl(70); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000071() { adj_diagonal_zero_impl(71); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000072() { adj_diagonal_zero_impl(72); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000073() { adj_diagonal_zero_impl(73); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000074() { adj_diagonal_zero_impl(74); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000075() { adj_diagonal_zero_impl(75); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000076() { adj_diagonal_zero_impl(76); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000077() { adj_diagonal_zero_impl(77); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000078() { adj_diagonal_zero_impl(78); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000079() { adj_diagonal_zero_impl(79); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000080() { adj_diagonal_zero_impl(80); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000081() { adj_diagonal_zero_impl(81); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000082() { adj_diagonal_zero_impl(82); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000083() { adj_diagonal_zero_impl(83); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000084() { adj_diagonal_zero_impl(84); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000085() { adj_diagonal_zero_impl(85); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000086() { adj_diagonal_zero_impl(86); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000087() { adj_diagonal_zero_impl(87); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000088() { adj_diagonal_zero_impl(88); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000089() { adj_diagonal_zero_impl(89); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000090() { adj_diagonal_zero_impl(90); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000091() { adj_diagonal_zero_impl(91); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000092() { adj_diagonal_zero_impl(92); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000093() { adj_diagonal_zero_impl(93); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000094() { adj_diagonal_zero_impl(94); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000095() { adj_diagonal_zero_impl(95); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000096() { adj_diagonal_zero_impl(96); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000097() { adj_diagonal_zero_impl(97); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000098() { adj_diagonal_zero_impl(98); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000099() { adj_diagonal_zero_impl(99); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000100() { adj_diagonal_zero_impl(100); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000101() { adj_diagonal_zero_impl(101); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000102() { adj_diagonal_zero_impl(102); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000103() { adj_diagonal_zero_impl(103); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000104() { adj_diagonal_zero_impl(104); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000105() { adj_diagonal_zero_impl(105); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000106() { adj_diagonal_zero_impl(106); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000107() { adj_diagonal_zero_impl(107); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000108() { adj_diagonal_zero_impl(108); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000109() { adj_diagonal_zero_impl(109); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000110() { adj_diagonal_zero_impl(110); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000111() { adj_diagonal_zero_impl(111); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000112() { adj_diagonal_zero_impl(112); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000113() { adj_diagonal_zero_impl(113); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000114() { adj_diagonal_zero_impl(114); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000115() { adj_diagonal_zero_impl(115); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000116() { adj_diagonal_zero_impl(116); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000117() { adj_diagonal_zero_impl(117); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000118() { adj_diagonal_zero_impl(118); }
    #[cfg_attr(test, test)]
    fn adj_diagonal_zero_seed_000119() { adj_diagonal_zero_impl(119); }
    // --- adj_pin_order_invariance: 120 generated seeds ---
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000000() { adj_pin_order_invariance_impl(0); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000001() { adj_pin_order_invariance_impl(1); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000002() { adj_pin_order_invariance_impl(2); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000003() { adj_pin_order_invariance_impl(3); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000004() { adj_pin_order_invariance_impl(4); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000005() { adj_pin_order_invariance_impl(5); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000006() { adj_pin_order_invariance_impl(6); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000007() { adj_pin_order_invariance_impl(7); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000008() { adj_pin_order_invariance_impl(8); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000009() { adj_pin_order_invariance_impl(9); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000010() { adj_pin_order_invariance_impl(10); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000011() { adj_pin_order_invariance_impl(11); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000012() { adj_pin_order_invariance_impl(12); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000013() { adj_pin_order_invariance_impl(13); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000014() { adj_pin_order_invariance_impl(14); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000015() { adj_pin_order_invariance_impl(15); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000016() { adj_pin_order_invariance_impl(16); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000017() { adj_pin_order_invariance_impl(17); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000018() { adj_pin_order_invariance_impl(18); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000019() { adj_pin_order_invariance_impl(19); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000020() { adj_pin_order_invariance_impl(20); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000021() { adj_pin_order_invariance_impl(21); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000022() { adj_pin_order_invariance_impl(22); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000023() { adj_pin_order_invariance_impl(23); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000024() { adj_pin_order_invariance_impl(24); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000025() { adj_pin_order_invariance_impl(25); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000026() { adj_pin_order_invariance_impl(26); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000027() { adj_pin_order_invariance_impl(27); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000028() { adj_pin_order_invariance_impl(28); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000029() { adj_pin_order_invariance_impl(29); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000030() { adj_pin_order_invariance_impl(30); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000031() { adj_pin_order_invariance_impl(31); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000032() { adj_pin_order_invariance_impl(32); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000033() { adj_pin_order_invariance_impl(33); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000034() { adj_pin_order_invariance_impl(34); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000035() { adj_pin_order_invariance_impl(35); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000036() { adj_pin_order_invariance_impl(36); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000037() { adj_pin_order_invariance_impl(37); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000038() { adj_pin_order_invariance_impl(38); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000039() { adj_pin_order_invariance_impl(39); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000040() { adj_pin_order_invariance_impl(40); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000041() { adj_pin_order_invariance_impl(41); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000042() { adj_pin_order_invariance_impl(42); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000043() { adj_pin_order_invariance_impl(43); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000044() { adj_pin_order_invariance_impl(44); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000045() { adj_pin_order_invariance_impl(45); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000046() { adj_pin_order_invariance_impl(46); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000047() { adj_pin_order_invariance_impl(47); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000048() { adj_pin_order_invariance_impl(48); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000049() { adj_pin_order_invariance_impl(49); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000050() { adj_pin_order_invariance_impl(50); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000051() { adj_pin_order_invariance_impl(51); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000052() { adj_pin_order_invariance_impl(52); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000053() { adj_pin_order_invariance_impl(53); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000054() { adj_pin_order_invariance_impl(54); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000055() { adj_pin_order_invariance_impl(55); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000056() { adj_pin_order_invariance_impl(56); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000057() { adj_pin_order_invariance_impl(57); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000058() { adj_pin_order_invariance_impl(58); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000059() { adj_pin_order_invariance_impl(59); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000060() { adj_pin_order_invariance_impl(60); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000061() { adj_pin_order_invariance_impl(61); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000062() { adj_pin_order_invariance_impl(62); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000063() { adj_pin_order_invariance_impl(63); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000064() { adj_pin_order_invariance_impl(64); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000065() { adj_pin_order_invariance_impl(65); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000066() { adj_pin_order_invariance_impl(66); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000067() { adj_pin_order_invariance_impl(67); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000068() { adj_pin_order_invariance_impl(68); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000069() { adj_pin_order_invariance_impl(69); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000070() { adj_pin_order_invariance_impl(70); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000071() { adj_pin_order_invariance_impl(71); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000072() { adj_pin_order_invariance_impl(72); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000073() { adj_pin_order_invariance_impl(73); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000074() { adj_pin_order_invariance_impl(74); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000075() { adj_pin_order_invariance_impl(75); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000076() { adj_pin_order_invariance_impl(76); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000077() { adj_pin_order_invariance_impl(77); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000078() { adj_pin_order_invariance_impl(78); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000079() { adj_pin_order_invariance_impl(79); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000080() { adj_pin_order_invariance_impl(80); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000081() { adj_pin_order_invariance_impl(81); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000082() { adj_pin_order_invariance_impl(82); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000083() { adj_pin_order_invariance_impl(83); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000084() { adj_pin_order_invariance_impl(84); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000085() { adj_pin_order_invariance_impl(85); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000086() { adj_pin_order_invariance_impl(86); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000087() { adj_pin_order_invariance_impl(87); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000088() { adj_pin_order_invariance_impl(88); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000089() { adj_pin_order_invariance_impl(89); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000090() { adj_pin_order_invariance_impl(90); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000091() { adj_pin_order_invariance_impl(91); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000092() { adj_pin_order_invariance_impl(92); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000093() { adj_pin_order_invariance_impl(93); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000094() { adj_pin_order_invariance_impl(94); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000095() { adj_pin_order_invariance_impl(95); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000096() { adj_pin_order_invariance_impl(96); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000097() { adj_pin_order_invariance_impl(97); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000098() { adj_pin_order_invariance_impl(98); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000099() { adj_pin_order_invariance_impl(99); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000100() { adj_pin_order_invariance_impl(100); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000101() { adj_pin_order_invariance_impl(101); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000102() { adj_pin_order_invariance_impl(102); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000103() { adj_pin_order_invariance_impl(103); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000104() { adj_pin_order_invariance_impl(104); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000105() { adj_pin_order_invariance_impl(105); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000106() { adj_pin_order_invariance_impl(106); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000107() { adj_pin_order_invariance_impl(107); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000108() { adj_pin_order_invariance_impl(108); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000109() { adj_pin_order_invariance_impl(109); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000110() { adj_pin_order_invariance_impl(110); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000111() { adj_pin_order_invariance_impl(111); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000112() { adj_pin_order_invariance_impl(112); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000113() { adj_pin_order_invariance_impl(113); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000114() { adj_pin_order_invariance_impl(114); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000115() { adj_pin_order_invariance_impl(115); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000116() { adj_pin_order_invariance_impl(116); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000117() { adj_pin_order_invariance_impl(117); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000118() { adj_pin_order_invariance_impl(118); }
    #[cfg_attr(test, test)]
    fn adj_pin_order_invariance_seed_000119() { adj_pin_order_invariance_impl(119); }
    // --- adj_relabeling_invariance: 120 generated seeds ---
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000000() { adj_relabeling_invariance_impl(0); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000001() { adj_relabeling_invariance_impl(1); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000002() { adj_relabeling_invariance_impl(2); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000003() { adj_relabeling_invariance_impl(3); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000004() { adj_relabeling_invariance_impl(4); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000005() { adj_relabeling_invariance_impl(5); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000006() { adj_relabeling_invariance_impl(6); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000007() { adj_relabeling_invariance_impl(7); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000008() { adj_relabeling_invariance_impl(8); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000009() { adj_relabeling_invariance_impl(9); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000010() { adj_relabeling_invariance_impl(10); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000011() { adj_relabeling_invariance_impl(11); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000012() { adj_relabeling_invariance_impl(12); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000013() { adj_relabeling_invariance_impl(13); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000014() { adj_relabeling_invariance_impl(14); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000015() { adj_relabeling_invariance_impl(15); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000016() { adj_relabeling_invariance_impl(16); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000017() { adj_relabeling_invariance_impl(17); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000018() { adj_relabeling_invariance_impl(18); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000019() { adj_relabeling_invariance_impl(19); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000020() { adj_relabeling_invariance_impl(20); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000021() { adj_relabeling_invariance_impl(21); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000022() { adj_relabeling_invariance_impl(22); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000023() { adj_relabeling_invariance_impl(23); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000024() { adj_relabeling_invariance_impl(24); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000025() { adj_relabeling_invariance_impl(25); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000026() { adj_relabeling_invariance_impl(26); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000027() { adj_relabeling_invariance_impl(27); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000028() { adj_relabeling_invariance_impl(28); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000029() { adj_relabeling_invariance_impl(29); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000030() { adj_relabeling_invariance_impl(30); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000031() { adj_relabeling_invariance_impl(31); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000032() { adj_relabeling_invariance_impl(32); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000033() { adj_relabeling_invariance_impl(33); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000034() { adj_relabeling_invariance_impl(34); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000035() { adj_relabeling_invariance_impl(35); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000036() { adj_relabeling_invariance_impl(36); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000037() { adj_relabeling_invariance_impl(37); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000038() { adj_relabeling_invariance_impl(38); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000039() { adj_relabeling_invariance_impl(39); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000040() { adj_relabeling_invariance_impl(40); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000041() { adj_relabeling_invariance_impl(41); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000042() { adj_relabeling_invariance_impl(42); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000043() { adj_relabeling_invariance_impl(43); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000044() { adj_relabeling_invariance_impl(44); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000045() { adj_relabeling_invariance_impl(45); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000046() { adj_relabeling_invariance_impl(46); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000047() { adj_relabeling_invariance_impl(47); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000048() { adj_relabeling_invariance_impl(48); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000049() { adj_relabeling_invariance_impl(49); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000050() { adj_relabeling_invariance_impl(50); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000051() { adj_relabeling_invariance_impl(51); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000052() { adj_relabeling_invariance_impl(52); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000053() { adj_relabeling_invariance_impl(53); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000054() { adj_relabeling_invariance_impl(54); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000055() { adj_relabeling_invariance_impl(55); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000056() { adj_relabeling_invariance_impl(56); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000057() { adj_relabeling_invariance_impl(57); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000058() { adj_relabeling_invariance_impl(58); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000059() { adj_relabeling_invariance_impl(59); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000060() { adj_relabeling_invariance_impl(60); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000061() { adj_relabeling_invariance_impl(61); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000062() { adj_relabeling_invariance_impl(62); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000063() { adj_relabeling_invariance_impl(63); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000064() { adj_relabeling_invariance_impl(64); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000065() { adj_relabeling_invariance_impl(65); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000066() { adj_relabeling_invariance_impl(66); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000067() { adj_relabeling_invariance_impl(67); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000068() { adj_relabeling_invariance_impl(68); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000069() { adj_relabeling_invariance_impl(69); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000070() { adj_relabeling_invariance_impl(70); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000071() { adj_relabeling_invariance_impl(71); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000072() { adj_relabeling_invariance_impl(72); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000073() { adj_relabeling_invariance_impl(73); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000074() { adj_relabeling_invariance_impl(74); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000075() { adj_relabeling_invariance_impl(75); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000076() { adj_relabeling_invariance_impl(76); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000077() { adj_relabeling_invariance_impl(77); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000078() { adj_relabeling_invariance_impl(78); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000079() { adj_relabeling_invariance_impl(79); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000080() { adj_relabeling_invariance_impl(80); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000081() { adj_relabeling_invariance_impl(81); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000082() { adj_relabeling_invariance_impl(82); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000083() { adj_relabeling_invariance_impl(83); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000084() { adj_relabeling_invariance_impl(84); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000085() { adj_relabeling_invariance_impl(85); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000086() { adj_relabeling_invariance_impl(86); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000087() { adj_relabeling_invariance_impl(87); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000088() { adj_relabeling_invariance_impl(88); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000089() { adj_relabeling_invariance_impl(89); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000090() { adj_relabeling_invariance_impl(90); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000091() { adj_relabeling_invariance_impl(91); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000092() { adj_relabeling_invariance_impl(92); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000093() { adj_relabeling_invariance_impl(93); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000094() { adj_relabeling_invariance_impl(94); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000095() { adj_relabeling_invariance_impl(95); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000096() { adj_relabeling_invariance_impl(96); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000097() { adj_relabeling_invariance_impl(97); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000098() { adj_relabeling_invariance_impl(98); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000099() { adj_relabeling_invariance_impl(99); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000100() { adj_relabeling_invariance_impl(100); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000101() { adj_relabeling_invariance_impl(101); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000102() { adj_relabeling_invariance_impl(102); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000103() { adj_relabeling_invariance_impl(103); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000104() { adj_relabeling_invariance_impl(104); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000105() { adj_relabeling_invariance_impl(105); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000106() { adj_relabeling_invariance_impl(106); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000107() { adj_relabeling_invariance_impl(107); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000108() { adj_relabeling_invariance_impl(108); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000109() { adj_relabeling_invariance_impl(109); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000110() { adj_relabeling_invariance_impl(110); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000111() { adj_relabeling_invariance_impl(111); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000112() { adj_relabeling_invariance_impl(112); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000113() { adj_relabeling_invariance_impl(113); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000114() { adj_relabeling_invariance_impl(114); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000115() { adj_relabeling_invariance_impl(115); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000116() { adj_relabeling_invariance_impl(116); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000117() { adj_relabeling_invariance_impl(117); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000118() { adj_relabeling_invariance_impl(118); }
    #[cfg_attr(test, test)]
    fn adj_relabeling_invariance_seed_000119() { adj_relabeling_invariance_impl(119); }
    // --- pyrepr_round_trip: 250 generated seeds ---
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000000() { pyrepr_round_trip_impl(0); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000001() { pyrepr_round_trip_impl(1); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000002() { pyrepr_round_trip_impl(2); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000003() { pyrepr_round_trip_impl(3); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000004() { pyrepr_round_trip_impl(4); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000005() { pyrepr_round_trip_impl(5); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000006() { pyrepr_round_trip_impl(6); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000007() { pyrepr_round_trip_impl(7); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000008() { pyrepr_round_trip_impl(8); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000009() { pyrepr_round_trip_impl(9); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000010() { pyrepr_round_trip_impl(10); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000011() { pyrepr_round_trip_impl(11); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000012() { pyrepr_round_trip_impl(12); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000013() { pyrepr_round_trip_impl(13); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000014() { pyrepr_round_trip_impl(14); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000015() { pyrepr_round_trip_impl(15); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000016() { pyrepr_round_trip_impl(16); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000017() { pyrepr_round_trip_impl(17); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000018() { pyrepr_round_trip_impl(18); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000019() { pyrepr_round_trip_impl(19); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000020() { pyrepr_round_trip_impl(20); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000021() { pyrepr_round_trip_impl(21); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000022() { pyrepr_round_trip_impl(22); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000023() { pyrepr_round_trip_impl(23); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000024() { pyrepr_round_trip_impl(24); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000025() { pyrepr_round_trip_impl(25); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000026() { pyrepr_round_trip_impl(26); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000027() { pyrepr_round_trip_impl(27); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000028() { pyrepr_round_trip_impl(28); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000029() { pyrepr_round_trip_impl(29); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000030() { pyrepr_round_trip_impl(30); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000031() { pyrepr_round_trip_impl(31); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000032() { pyrepr_round_trip_impl(32); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000033() { pyrepr_round_trip_impl(33); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000034() { pyrepr_round_trip_impl(34); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000035() { pyrepr_round_trip_impl(35); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000036() { pyrepr_round_trip_impl(36); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000037() { pyrepr_round_trip_impl(37); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000038() { pyrepr_round_trip_impl(38); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000039() { pyrepr_round_trip_impl(39); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000040() { pyrepr_round_trip_impl(40); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000041() { pyrepr_round_trip_impl(41); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000042() { pyrepr_round_trip_impl(42); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000043() { pyrepr_round_trip_impl(43); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000044() { pyrepr_round_trip_impl(44); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000045() { pyrepr_round_trip_impl(45); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000046() { pyrepr_round_trip_impl(46); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000047() { pyrepr_round_trip_impl(47); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000048() { pyrepr_round_trip_impl(48); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000049() { pyrepr_round_trip_impl(49); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000050() { pyrepr_round_trip_impl(50); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000051() { pyrepr_round_trip_impl(51); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000052() { pyrepr_round_trip_impl(52); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000053() { pyrepr_round_trip_impl(53); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000054() { pyrepr_round_trip_impl(54); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000055() { pyrepr_round_trip_impl(55); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000056() { pyrepr_round_trip_impl(56); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000057() { pyrepr_round_trip_impl(57); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000058() { pyrepr_round_trip_impl(58); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000059() { pyrepr_round_trip_impl(59); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000060() { pyrepr_round_trip_impl(60); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000061() { pyrepr_round_trip_impl(61); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000062() { pyrepr_round_trip_impl(62); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000063() { pyrepr_round_trip_impl(63); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000064() { pyrepr_round_trip_impl(64); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000065() { pyrepr_round_trip_impl(65); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000066() { pyrepr_round_trip_impl(66); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000067() { pyrepr_round_trip_impl(67); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000068() { pyrepr_round_trip_impl(68); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000069() { pyrepr_round_trip_impl(69); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000070() { pyrepr_round_trip_impl(70); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000071() { pyrepr_round_trip_impl(71); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000072() { pyrepr_round_trip_impl(72); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000073() { pyrepr_round_trip_impl(73); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000074() { pyrepr_round_trip_impl(74); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000075() { pyrepr_round_trip_impl(75); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000076() { pyrepr_round_trip_impl(76); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000077() { pyrepr_round_trip_impl(77); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000078() { pyrepr_round_trip_impl(78); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000079() { pyrepr_round_trip_impl(79); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000080() { pyrepr_round_trip_impl(80); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000081() { pyrepr_round_trip_impl(81); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000082() { pyrepr_round_trip_impl(82); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000083() { pyrepr_round_trip_impl(83); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000084() { pyrepr_round_trip_impl(84); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000085() { pyrepr_round_trip_impl(85); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000086() { pyrepr_round_trip_impl(86); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000087() { pyrepr_round_trip_impl(87); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000088() { pyrepr_round_trip_impl(88); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000089() { pyrepr_round_trip_impl(89); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000090() { pyrepr_round_trip_impl(90); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000091() { pyrepr_round_trip_impl(91); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000092() { pyrepr_round_trip_impl(92); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000093() { pyrepr_round_trip_impl(93); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000094() { pyrepr_round_trip_impl(94); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000095() { pyrepr_round_trip_impl(95); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000096() { pyrepr_round_trip_impl(96); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000097() { pyrepr_round_trip_impl(97); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000098() { pyrepr_round_trip_impl(98); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000099() { pyrepr_round_trip_impl(99); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000100() { pyrepr_round_trip_impl(100); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000101() { pyrepr_round_trip_impl(101); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000102() { pyrepr_round_trip_impl(102); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000103() { pyrepr_round_trip_impl(103); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000104() { pyrepr_round_trip_impl(104); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000105() { pyrepr_round_trip_impl(105); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000106() { pyrepr_round_trip_impl(106); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000107() { pyrepr_round_trip_impl(107); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000108() { pyrepr_round_trip_impl(108); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000109() { pyrepr_round_trip_impl(109); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000110() { pyrepr_round_trip_impl(110); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000111() { pyrepr_round_trip_impl(111); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000112() { pyrepr_round_trip_impl(112); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000113() { pyrepr_round_trip_impl(113); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000114() { pyrepr_round_trip_impl(114); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000115() { pyrepr_round_trip_impl(115); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000116() { pyrepr_round_trip_impl(116); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000117() { pyrepr_round_trip_impl(117); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000118() { pyrepr_round_trip_impl(118); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000119() { pyrepr_round_trip_impl(119); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000120() { pyrepr_round_trip_impl(120); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000121() { pyrepr_round_trip_impl(121); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000122() { pyrepr_round_trip_impl(122); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000123() { pyrepr_round_trip_impl(123); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000124() { pyrepr_round_trip_impl(124); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000125() { pyrepr_round_trip_impl(125); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000126() { pyrepr_round_trip_impl(126); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000127() { pyrepr_round_trip_impl(127); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000128() { pyrepr_round_trip_impl(128); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000129() { pyrepr_round_trip_impl(129); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000130() { pyrepr_round_trip_impl(130); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000131() { pyrepr_round_trip_impl(131); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000132() { pyrepr_round_trip_impl(132); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000133() { pyrepr_round_trip_impl(133); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000134() { pyrepr_round_trip_impl(134); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000135() { pyrepr_round_trip_impl(135); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000136() { pyrepr_round_trip_impl(136); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000137() { pyrepr_round_trip_impl(137); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000138() { pyrepr_round_trip_impl(138); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000139() { pyrepr_round_trip_impl(139); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000140() { pyrepr_round_trip_impl(140); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000141() { pyrepr_round_trip_impl(141); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000142() { pyrepr_round_trip_impl(142); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000143() { pyrepr_round_trip_impl(143); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000144() { pyrepr_round_trip_impl(144); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000145() { pyrepr_round_trip_impl(145); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000146() { pyrepr_round_trip_impl(146); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000147() { pyrepr_round_trip_impl(147); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000148() { pyrepr_round_trip_impl(148); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000149() { pyrepr_round_trip_impl(149); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000150() { pyrepr_round_trip_impl(150); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000151() { pyrepr_round_trip_impl(151); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000152() { pyrepr_round_trip_impl(152); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000153() { pyrepr_round_trip_impl(153); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000154() { pyrepr_round_trip_impl(154); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000155() { pyrepr_round_trip_impl(155); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000156() { pyrepr_round_trip_impl(156); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000157() { pyrepr_round_trip_impl(157); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000158() { pyrepr_round_trip_impl(158); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000159() { pyrepr_round_trip_impl(159); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000160() { pyrepr_round_trip_impl(160); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000161() { pyrepr_round_trip_impl(161); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000162() { pyrepr_round_trip_impl(162); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000163() { pyrepr_round_trip_impl(163); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000164() { pyrepr_round_trip_impl(164); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000165() { pyrepr_round_trip_impl(165); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000166() { pyrepr_round_trip_impl(166); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000167() { pyrepr_round_trip_impl(167); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000168() { pyrepr_round_trip_impl(168); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000169() { pyrepr_round_trip_impl(169); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000170() { pyrepr_round_trip_impl(170); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000171() { pyrepr_round_trip_impl(171); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000172() { pyrepr_round_trip_impl(172); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000173() { pyrepr_round_trip_impl(173); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000174() { pyrepr_round_trip_impl(174); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000175() { pyrepr_round_trip_impl(175); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000176() { pyrepr_round_trip_impl(176); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000177() { pyrepr_round_trip_impl(177); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000178() { pyrepr_round_trip_impl(178); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000179() { pyrepr_round_trip_impl(179); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000180() { pyrepr_round_trip_impl(180); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000181() { pyrepr_round_trip_impl(181); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000182() { pyrepr_round_trip_impl(182); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000183() { pyrepr_round_trip_impl(183); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000184() { pyrepr_round_trip_impl(184); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000185() { pyrepr_round_trip_impl(185); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000186() { pyrepr_round_trip_impl(186); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000187() { pyrepr_round_trip_impl(187); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000188() { pyrepr_round_trip_impl(188); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000189() { pyrepr_round_trip_impl(189); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000190() { pyrepr_round_trip_impl(190); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000191() { pyrepr_round_trip_impl(191); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000192() { pyrepr_round_trip_impl(192); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000193() { pyrepr_round_trip_impl(193); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000194() { pyrepr_round_trip_impl(194); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000195() { pyrepr_round_trip_impl(195); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000196() { pyrepr_round_trip_impl(196); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000197() { pyrepr_round_trip_impl(197); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000198() { pyrepr_round_trip_impl(198); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000199() { pyrepr_round_trip_impl(199); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000200() { pyrepr_round_trip_impl(200); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000201() { pyrepr_round_trip_impl(201); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000202() { pyrepr_round_trip_impl(202); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000203() { pyrepr_round_trip_impl(203); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000204() { pyrepr_round_trip_impl(204); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000205() { pyrepr_round_trip_impl(205); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000206() { pyrepr_round_trip_impl(206); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000207() { pyrepr_round_trip_impl(207); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000208() { pyrepr_round_trip_impl(208); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000209() { pyrepr_round_trip_impl(209); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000210() { pyrepr_round_trip_impl(210); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000211() { pyrepr_round_trip_impl(211); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000212() { pyrepr_round_trip_impl(212); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000213() { pyrepr_round_trip_impl(213); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000214() { pyrepr_round_trip_impl(214); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000215() { pyrepr_round_trip_impl(215); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000216() { pyrepr_round_trip_impl(216); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000217() { pyrepr_round_trip_impl(217); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000218() { pyrepr_round_trip_impl(218); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000219() { pyrepr_round_trip_impl(219); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000220() { pyrepr_round_trip_impl(220); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000221() { pyrepr_round_trip_impl(221); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000222() { pyrepr_round_trip_impl(222); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000223() { pyrepr_round_trip_impl(223); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000224() { pyrepr_round_trip_impl(224); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000225() { pyrepr_round_trip_impl(225); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000226() { pyrepr_round_trip_impl(226); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000227() { pyrepr_round_trip_impl(227); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000228() { pyrepr_round_trip_impl(228); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000229() { pyrepr_round_trip_impl(229); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000230() { pyrepr_round_trip_impl(230); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000231() { pyrepr_round_trip_impl(231); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000232() { pyrepr_round_trip_impl(232); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000233() { pyrepr_round_trip_impl(233); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000234() { pyrepr_round_trip_impl(234); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000235() { pyrepr_round_trip_impl(235); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000236() { pyrepr_round_trip_impl(236); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000237() { pyrepr_round_trip_impl(237); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000238() { pyrepr_round_trip_impl(238); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000239() { pyrepr_round_trip_impl(239); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000240() { pyrepr_round_trip_impl(240); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000241() { pyrepr_round_trip_impl(241); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000242() { pyrepr_round_trip_impl(242); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000243() { pyrepr_round_trip_impl(243); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000244() { pyrepr_round_trip_impl(244); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000245() { pyrepr_round_trip_impl(245); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000246() { pyrepr_round_trip_impl(246); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000247() { pyrepr_round_trip_impl(247); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000248() { pyrepr_round_trip_impl(248); }
    #[cfg_attr(test, test)]
    fn pyrepr_round_trip_seed_000249() { pyrepr_round_trip_impl(249); }
    // --- pyrepr_format_fixed_rounding: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000000() { pyrepr_format_fixed_rounding_impl(0); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000001() { pyrepr_format_fixed_rounding_impl(1); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000002() { pyrepr_format_fixed_rounding_impl(2); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000003() { pyrepr_format_fixed_rounding_impl(3); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000004() { pyrepr_format_fixed_rounding_impl(4); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000005() { pyrepr_format_fixed_rounding_impl(5); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000006() { pyrepr_format_fixed_rounding_impl(6); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000007() { pyrepr_format_fixed_rounding_impl(7); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000008() { pyrepr_format_fixed_rounding_impl(8); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000009() { pyrepr_format_fixed_rounding_impl(9); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000010() { pyrepr_format_fixed_rounding_impl(10); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000011() { pyrepr_format_fixed_rounding_impl(11); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000012() { pyrepr_format_fixed_rounding_impl(12); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000013() { pyrepr_format_fixed_rounding_impl(13); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000014() { pyrepr_format_fixed_rounding_impl(14); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000015() { pyrepr_format_fixed_rounding_impl(15); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000016() { pyrepr_format_fixed_rounding_impl(16); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000017() { pyrepr_format_fixed_rounding_impl(17); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000018() { pyrepr_format_fixed_rounding_impl(18); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000019() { pyrepr_format_fixed_rounding_impl(19); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000020() { pyrepr_format_fixed_rounding_impl(20); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000021() { pyrepr_format_fixed_rounding_impl(21); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000022() { pyrepr_format_fixed_rounding_impl(22); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000023() { pyrepr_format_fixed_rounding_impl(23); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000024() { pyrepr_format_fixed_rounding_impl(24); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000025() { pyrepr_format_fixed_rounding_impl(25); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000026() { pyrepr_format_fixed_rounding_impl(26); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000027() { pyrepr_format_fixed_rounding_impl(27); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000028() { pyrepr_format_fixed_rounding_impl(28); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000029() { pyrepr_format_fixed_rounding_impl(29); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000030() { pyrepr_format_fixed_rounding_impl(30); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000031() { pyrepr_format_fixed_rounding_impl(31); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000032() { pyrepr_format_fixed_rounding_impl(32); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000033() { pyrepr_format_fixed_rounding_impl(33); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000034() { pyrepr_format_fixed_rounding_impl(34); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000035() { pyrepr_format_fixed_rounding_impl(35); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000036() { pyrepr_format_fixed_rounding_impl(36); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000037() { pyrepr_format_fixed_rounding_impl(37); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000038() { pyrepr_format_fixed_rounding_impl(38); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000039() { pyrepr_format_fixed_rounding_impl(39); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000040() { pyrepr_format_fixed_rounding_impl(40); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000041() { pyrepr_format_fixed_rounding_impl(41); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000042() { pyrepr_format_fixed_rounding_impl(42); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000043() { pyrepr_format_fixed_rounding_impl(43); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000044() { pyrepr_format_fixed_rounding_impl(44); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000045() { pyrepr_format_fixed_rounding_impl(45); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000046() { pyrepr_format_fixed_rounding_impl(46); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000047() { pyrepr_format_fixed_rounding_impl(47); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000048() { pyrepr_format_fixed_rounding_impl(48); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000049() { pyrepr_format_fixed_rounding_impl(49); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000050() { pyrepr_format_fixed_rounding_impl(50); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000051() { pyrepr_format_fixed_rounding_impl(51); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000052() { pyrepr_format_fixed_rounding_impl(52); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000053() { pyrepr_format_fixed_rounding_impl(53); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000054() { pyrepr_format_fixed_rounding_impl(54); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000055() { pyrepr_format_fixed_rounding_impl(55); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000056() { pyrepr_format_fixed_rounding_impl(56); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000057() { pyrepr_format_fixed_rounding_impl(57); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000058() { pyrepr_format_fixed_rounding_impl(58); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000059() { pyrepr_format_fixed_rounding_impl(59); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000060() { pyrepr_format_fixed_rounding_impl(60); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000061() { pyrepr_format_fixed_rounding_impl(61); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000062() { pyrepr_format_fixed_rounding_impl(62); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000063() { pyrepr_format_fixed_rounding_impl(63); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000064() { pyrepr_format_fixed_rounding_impl(64); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000065() { pyrepr_format_fixed_rounding_impl(65); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000066() { pyrepr_format_fixed_rounding_impl(66); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000067() { pyrepr_format_fixed_rounding_impl(67); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000068() { pyrepr_format_fixed_rounding_impl(68); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000069() { pyrepr_format_fixed_rounding_impl(69); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000070() { pyrepr_format_fixed_rounding_impl(70); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000071() { pyrepr_format_fixed_rounding_impl(71); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000072() { pyrepr_format_fixed_rounding_impl(72); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000073() { pyrepr_format_fixed_rounding_impl(73); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000074() { pyrepr_format_fixed_rounding_impl(74); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000075() { pyrepr_format_fixed_rounding_impl(75); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000076() { pyrepr_format_fixed_rounding_impl(76); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000077() { pyrepr_format_fixed_rounding_impl(77); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000078() { pyrepr_format_fixed_rounding_impl(78); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000079() { pyrepr_format_fixed_rounding_impl(79); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000080() { pyrepr_format_fixed_rounding_impl(80); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000081() { pyrepr_format_fixed_rounding_impl(81); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000082() { pyrepr_format_fixed_rounding_impl(82); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000083() { pyrepr_format_fixed_rounding_impl(83); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000084() { pyrepr_format_fixed_rounding_impl(84); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000085() { pyrepr_format_fixed_rounding_impl(85); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000086() { pyrepr_format_fixed_rounding_impl(86); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000087() { pyrepr_format_fixed_rounding_impl(87); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000088() { pyrepr_format_fixed_rounding_impl(88); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000089() { pyrepr_format_fixed_rounding_impl(89); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000090() { pyrepr_format_fixed_rounding_impl(90); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000091() { pyrepr_format_fixed_rounding_impl(91); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000092() { pyrepr_format_fixed_rounding_impl(92); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000093() { pyrepr_format_fixed_rounding_impl(93); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000094() { pyrepr_format_fixed_rounding_impl(94); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000095() { pyrepr_format_fixed_rounding_impl(95); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000096() { pyrepr_format_fixed_rounding_impl(96); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000097() { pyrepr_format_fixed_rounding_impl(97); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000098() { pyrepr_format_fixed_rounding_impl(98); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000099() { pyrepr_format_fixed_rounding_impl(99); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000100() { pyrepr_format_fixed_rounding_impl(100); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000101() { pyrepr_format_fixed_rounding_impl(101); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000102() { pyrepr_format_fixed_rounding_impl(102); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000103() { pyrepr_format_fixed_rounding_impl(103); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000104() { pyrepr_format_fixed_rounding_impl(104); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000105() { pyrepr_format_fixed_rounding_impl(105); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000106() { pyrepr_format_fixed_rounding_impl(106); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000107() { pyrepr_format_fixed_rounding_impl(107); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000108() { pyrepr_format_fixed_rounding_impl(108); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000109() { pyrepr_format_fixed_rounding_impl(109); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000110() { pyrepr_format_fixed_rounding_impl(110); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000111() { pyrepr_format_fixed_rounding_impl(111); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000112() { pyrepr_format_fixed_rounding_impl(112); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000113() { pyrepr_format_fixed_rounding_impl(113); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000114() { pyrepr_format_fixed_rounding_impl(114); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000115() { pyrepr_format_fixed_rounding_impl(115); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000116() { pyrepr_format_fixed_rounding_impl(116); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000117() { pyrepr_format_fixed_rounding_impl(117); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000118() { pyrepr_format_fixed_rounding_impl(118); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000119() { pyrepr_format_fixed_rounding_impl(119); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000120() { pyrepr_format_fixed_rounding_impl(120); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000121() { pyrepr_format_fixed_rounding_impl(121); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000122() { pyrepr_format_fixed_rounding_impl(122); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000123() { pyrepr_format_fixed_rounding_impl(123); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000124() { pyrepr_format_fixed_rounding_impl(124); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000125() { pyrepr_format_fixed_rounding_impl(125); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000126() { pyrepr_format_fixed_rounding_impl(126); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000127() { pyrepr_format_fixed_rounding_impl(127); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000128() { pyrepr_format_fixed_rounding_impl(128); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000129() { pyrepr_format_fixed_rounding_impl(129); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000130() { pyrepr_format_fixed_rounding_impl(130); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000131() { pyrepr_format_fixed_rounding_impl(131); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000132() { pyrepr_format_fixed_rounding_impl(132); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000133() { pyrepr_format_fixed_rounding_impl(133); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000134() { pyrepr_format_fixed_rounding_impl(134); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000135() { pyrepr_format_fixed_rounding_impl(135); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000136() { pyrepr_format_fixed_rounding_impl(136); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000137() { pyrepr_format_fixed_rounding_impl(137); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000138() { pyrepr_format_fixed_rounding_impl(138); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000139() { pyrepr_format_fixed_rounding_impl(139); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000140() { pyrepr_format_fixed_rounding_impl(140); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000141() { pyrepr_format_fixed_rounding_impl(141); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000142() { pyrepr_format_fixed_rounding_impl(142); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000143() { pyrepr_format_fixed_rounding_impl(143); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000144() { pyrepr_format_fixed_rounding_impl(144); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000145() { pyrepr_format_fixed_rounding_impl(145); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000146() { pyrepr_format_fixed_rounding_impl(146); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000147() { pyrepr_format_fixed_rounding_impl(147); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000148() { pyrepr_format_fixed_rounding_impl(148); }
    #[cfg_attr(test, test)]
    fn pyrepr_format_fixed_rounding_seed_000149() { pyrepr_format_fixed_rounding_impl(149); }
    // --- pyrepr_sign_symmetry: 100 generated seeds ---
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000000() { pyrepr_sign_symmetry_impl(0); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000001() { pyrepr_sign_symmetry_impl(1); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000002() { pyrepr_sign_symmetry_impl(2); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000003() { pyrepr_sign_symmetry_impl(3); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000004() { pyrepr_sign_symmetry_impl(4); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000005() { pyrepr_sign_symmetry_impl(5); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000006() { pyrepr_sign_symmetry_impl(6); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000007() { pyrepr_sign_symmetry_impl(7); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000008() { pyrepr_sign_symmetry_impl(8); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000009() { pyrepr_sign_symmetry_impl(9); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000010() { pyrepr_sign_symmetry_impl(10); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000011() { pyrepr_sign_symmetry_impl(11); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000012() { pyrepr_sign_symmetry_impl(12); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000013() { pyrepr_sign_symmetry_impl(13); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000014() { pyrepr_sign_symmetry_impl(14); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000015() { pyrepr_sign_symmetry_impl(15); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000016() { pyrepr_sign_symmetry_impl(16); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000017() { pyrepr_sign_symmetry_impl(17); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000018() { pyrepr_sign_symmetry_impl(18); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000019() { pyrepr_sign_symmetry_impl(19); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000020() { pyrepr_sign_symmetry_impl(20); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000021() { pyrepr_sign_symmetry_impl(21); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000022() { pyrepr_sign_symmetry_impl(22); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000023() { pyrepr_sign_symmetry_impl(23); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000024() { pyrepr_sign_symmetry_impl(24); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000025() { pyrepr_sign_symmetry_impl(25); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000026() { pyrepr_sign_symmetry_impl(26); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000027() { pyrepr_sign_symmetry_impl(27); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000028() { pyrepr_sign_symmetry_impl(28); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000029() { pyrepr_sign_symmetry_impl(29); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000030() { pyrepr_sign_symmetry_impl(30); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000031() { pyrepr_sign_symmetry_impl(31); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000032() { pyrepr_sign_symmetry_impl(32); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000033() { pyrepr_sign_symmetry_impl(33); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000034() { pyrepr_sign_symmetry_impl(34); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000035() { pyrepr_sign_symmetry_impl(35); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000036() { pyrepr_sign_symmetry_impl(36); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000037() { pyrepr_sign_symmetry_impl(37); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000038() { pyrepr_sign_symmetry_impl(38); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000039() { pyrepr_sign_symmetry_impl(39); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000040() { pyrepr_sign_symmetry_impl(40); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000041() { pyrepr_sign_symmetry_impl(41); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000042() { pyrepr_sign_symmetry_impl(42); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000043() { pyrepr_sign_symmetry_impl(43); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000044() { pyrepr_sign_symmetry_impl(44); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000045() { pyrepr_sign_symmetry_impl(45); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000046() { pyrepr_sign_symmetry_impl(46); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000047() { pyrepr_sign_symmetry_impl(47); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000048() { pyrepr_sign_symmetry_impl(48); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000049() { pyrepr_sign_symmetry_impl(49); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000050() { pyrepr_sign_symmetry_impl(50); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000051() { pyrepr_sign_symmetry_impl(51); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000052() { pyrepr_sign_symmetry_impl(52); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000053() { pyrepr_sign_symmetry_impl(53); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000054() { pyrepr_sign_symmetry_impl(54); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000055() { pyrepr_sign_symmetry_impl(55); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000056() { pyrepr_sign_symmetry_impl(56); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000057() { pyrepr_sign_symmetry_impl(57); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000058() { pyrepr_sign_symmetry_impl(58); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000059() { pyrepr_sign_symmetry_impl(59); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000060() { pyrepr_sign_symmetry_impl(60); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000061() { pyrepr_sign_symmetry_impl(61); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000062() { pyrepr_sign_symmetry_impl(62); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000063() { pyrepr_sign_symmetry_impl(63); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000064() { pyrepr_sign_symmetry_impl(64); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000065() { pyrepr_sign_symmetry_impl(65); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000066() { pyrepr_sign_symmetry_impl(66); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000067() { pyrepr_sign_symmetry_impl(67); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000068() { pyrepr_sign_symmetry_impl(68); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000069() { pyrepr_sign_symmetry_impl(69); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000070() { pyrepr_sign_symmetry_impl(70); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000071() { pyrepr_sign_symmetry_impl(71); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000072() { pyrepr_sign_symmetry_impl(72); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000073() { pyrepr_sign_symmetry_impl(73); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000074() { pyrepr_sign_symmetry_impl(74); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000075() { pyrepr_sign_symmetry_impl(75); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000076() { pyrepr_sign_symmetry_impl(76); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000077() { pyrepr_sign_symmetry_impl(77); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000078() { pyrepr_sign_symmetry_impl(78); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000079() { pyrepr_sign_symmetry_impl(79); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000080() { pyrepr_sign_symmetry_impl(80); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000081() { pyrepr_sign_symmetry_impl(81); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000082() { pyrepr_sign_symmetry_impl(82); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000083() { pyrepr_sign_symmetry_impl(83); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000084() { pyrepr_sign_symmetry_impl(84); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000085() { pyrepr_sign_symmetry_impl(85); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000086() { pyrepr_sign_symmetry_impl(86); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000087() { pyrepr_sign_symmetry_impl(87); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000088() { pyrepr_sign_symmetry_impl(88); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000089() { pyrepr_sign_symmetry_impl(89); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000090() { pyrepr_sign_symmetry_impl(90); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000091() { pyrepr_sign_symmetry_impl(91); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000092() { pyrepr_sign_symmetry_impl(92); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000093() { pyrepr_sign_symmetry_impl(93); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000094() { pyrepr_sign_symmetry_impl(94); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000095() { pyrepr_sign_symmetry_impl(95); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000096() { pyrepr_sign_symmetry_impl(96); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000097() { pyrepr_sign_symmetry_impl(97); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000098() { pyrepr_sign_symmetry_impl(98); }
    #[cfg_attr(test, test)]
    fn pyrepr_sign_symmetry_seed_000099() { pyrepr_sign_symmetry_impl(99); }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("property_campaigns::tests::splitmix64_is_deterministic_in_seed", splitmix64_is_deterministic_in_seed),
        ("property_campaigns::tests::splitmix64_varies_with_seed", splitmix64_varies_with_seed),
        ("property_campaigns::tests::nc_gen_name_is_deterministic", nc_gen_name_is_deterministic),
        ("property_campaigns::tests::nc_token_pools_are_distinct_sizes", nc_token_pools_are_distinct_sizes),
        ("property_campaigns::tests::nc_precedence_hand_example_matches_the_documented_law", nc_precedence_hand_example_matches_the_documented_law),
        ("property_campaigns::tests::adj_gen_case_is_deterministic", adj_gen_case_is_deterministic),
        ("property_campaigns::tests::adj_gen_case_dims_in_expected_range", adj_gen_case_dims_in_expected_range),
        ("property_campaigns::tests::pr_gen_f64_is_deterministic", pr_gen_f64_is_deterministic),
        ("property_campaigns::tests::pr_gen_f64_is_finite", pr_gen_f64_is_finite),
        ("property_campaigns::tests::nc_precedence_core_seed_000000", nc_precedence_core_seed_000000),
        ("property_campaigns::tests::nc_precedence_core_seed_000001", nc_precedence_core_seed_000001),
        ("property_campaigns::tests::nc_precedence_core_seed_000002", nc_precedence_core_seed_000002),
        ("property_campaigns::tests::nc_precedence_core_seed_000003", nc_precedence_core_seed_000003),
        ("property_campaigns::tests::nc_precedence_core_seed_000004", nc_precedence_core_seed_000004),
        ("property_campaigns::tests::nc_precedence_core_seed_000005", nc_precedence_core_seed_000005),
        ("property_campaigns::tests::nc_precedence_core_seed_000006", nc_precedence_core_seed_000006),
        ("property_campaigns::tests::nc_precedence_core_seed_000007", nc_precedence_core_seed_000007),
        ("property_campaigns::tests::nc_precedence_core_seed_000008", nc_precedence_core_seed_000008),
        ("property_campaigns::tests::nc_precedence_core_seed_000009", nc_precedence_core_seed_000009),
        ("property_campaigns::tests::nc_precedence_core_seed_000010", nc_precedence_core_seed_000010),
        ("property_campaigns::tests::nc_precedence_core_seed_000011", nc_precedence_core_seed_000011),
        ("property_campaigns::tests::nc_precedence_core_seed_000012", nc_precedence_core_seed_000012),
        ("property_campaigns::tests::nc_precedence_core_seed_000013", nc_precedence_core_seed_000013),
        ("property_campaigns::tests::nc_precedence_core_seed_000014", nc_precedence_core_seed_000014),
        ("property_campaigns::tests::nc_precedence_core_seed_000015", nc_precedence_core_seed_000015),
        ("property_campaigns::tests::nc_precedence_core_seed_000016", nc_precedence_core_seed_000016),
        ("property_campaigns::tests::nc_precedence_core_seed_000017", nc_precedence_core_seed_000017),
        ("property_campaigns::tests::nc_precedence_core_seed_000018", nc_precedence_core_seed_000018),
        ("property_campaigns::tests::nc_precedence_core_seed_000019", nc_precedence_core_seed_000019),
        ("property_campaigns::tests::nc_precedence_core_seed_000020", nc_precedence_core_seed_000020),
        ("property_campaigns::tests::nc_precedence_core_seed_000021", nc_precedence_core_seed_000021),
        ("property_campaigns::tests::nc_precedence_core_seed_000022", nc_precedence_core_seed_000022),
        ("property_campaigns::tests::nc_precedence_core_seed_000023", nc_precedence_core_seed_000023),
        ("property_campaigns::tests::nc_precedence_core_seed_000024", nc_precedence_core_seed_000024),
        ("property_campaigns::tests::nc_precedence_core_seed_000025", nc_precedence_core_seed_000025),
        ("property_campaigns::tests::nc_precedence_core_seed_000026", nc_precedence_core_seed_000026),
        ("property_campaigns::tests::nc_precedence_core_seed_000027", nc_precedence_core_seed_000027),
        ("property_campaigns::tests::nc_precedence_core_seed_000028", nc_precedence_core_seed_000028),
        ("property_campaigns::tests::nc_precedence_core_seed_000029", nc_precedence_core_seed_000029),
        ("property_campaigns::tests::nc_precedence_core_seed_000030", nc_precedence_core_seed_000030),
        ("property_campaigns::tests::nc_precedence_core_seed_000031", nc_precedence_core_seed_000031),
        ("property_campaigns::tests::nc_precedence_core_seed_000032", nc_precedence_core_seed_000032),
        ("property_campaigns::tests::nc_precedence_core_seed_000033", nc_precedence_core_seed_000033),
        ("property_campaigns::tests::nc_precedence_core_seed_000034", nc_precedence_core_seed_000034),
        ("property_campaigns::tests::nc_precedence_core_seed_000035", nc_precedence_core_seed_000035),
        ("property_campaigns::tests::nc_precedence_core_seed_000036", nc_precedence_core_seed_000036),
        ("property_campaigns::tests::nc_precedence_core_seed_000037", nc_precedence_core_seed_000037),
        ("property_campaigns::tests::nc_precedence_core_seed_000038", nc_precedence_core_seed_000038),
        ("property_campaigns::tests::nc_precedence_core_seed_000039", nc_precedence_core_seed_000039),
        ("property_campaigns::tests::nc_precedence_core_seed_000040", nc_precedence_core_seed_000040),
        ("property_campaigns::tests::nc_precedence_core_seed_000041", nc_precedence_core_seed_000041),
        ("property_campaigns::tests::nc_precedence_core_seed_000042", nc_precedence_core_seed_000042),
        ("property_campaigns::tests::nc_precedence_core_seed_000043", nc_precedence_core_seed_000043),
        ("property_campaigns::tests::nc_precedence_core_seed_000044", nc_precedence_core_seed_000044),
        ("property_campaigns::tests::nc_precedence_core_seed_000045", nc_precedence_core_seed_000045),
        ("property_campaigns::tests::nc_precedence_core_seed_000046", nc_precedence_core_seed_000046),
        ("property_campaigns::tests::nc_precedence_core_seed_000047", nc_precedence_core_seed_000047),
        ("property_campaigns::tests::nc_precedence_core_seed_000048", nc_precedence_core_seed_000048),
        ("property_campaigns::tests::nc_precedence_core_seed_000049", nc_precedence_core_seed_000049),
        ("property_campaigns::tests::nc_precedence_core_seed_000050", nc_precedence_core_seed_000050),
        ("property_campaigns::tests::nc_precedence_core_seed_000051", nc_precedence_core_seed_000051),
        ("property_campaigns::tests::nc_precedence_core_seed_000052", nc_precedence_core_seed_000052),
        ("property_campaigns::tests::nc_precedence_core_seed_000053", nc_precedence_core_seed_000053),
        ("property_campaigns::tests::nc_precedence_core_seed_000054", nc_precedence_core_seed_000054),
        ("property_campaigns::tests::nc_precedence_core_seed_000055", nc_precedence_core_seed_000055),
        ("property_campaigns::tests::nc_precedence_core_seed_000056", nc_precedence_core_seed_000056),
        ("property_campaigns::tests::nc_precedence_core_seed_000057", nc_precedence_core_seed_000057),
        ("property_campaigns::tests::nc_precedence_core_seed_000058", nc_precedence_core_seed_000058),
        ("property_campaigns::tests::nc_precedence_core_seed_000059", nc_precedence_core_seed_000059),
        ("property_campaigns::tests::nc_precedence_core_seed_000060", nc_precedence_core_seed_000060),
        ("property_campaigns::tests::nc_precedence_core_seed_000061", nc_precedence_core_seed_000061),
        ("property_campaigns::tests::nc_precedence_core_seed_000062", nc_precedence_core_seed_000062),
        ("property_campaigns::tests::nc_precedence_core_seed_000063", nc_precedence_core_seed_000063),
        ("property_campaigns::tests::nc_precedence_core_seed_000064", nc_precedence_core_seed_000064),
        ("property_campaigns::tests::nc_precedence_core_seed_000065", nc_precedence_core_seed_000065),
        ("property_campaigns::tests::nc_precedence_core_seed_000066", nc_precedence_core_seed_000066),
        ("property_campaigns::tests::nc_precedence_core_seed_000067", nc_precedence_core_seed_000067),
        ("property_campaigns::tests::nc_precedence_core_seed_000068", nc_precedence_core_seed_000068),
        ("property_campaigns::tests::nc_precedence_core_seed_000069", nc_precedence_core_seed_000069),
        ("property_campaigns::tests::nc_precedence_core_seed_000070", nc_precedence_core_seed_000070),
        ("property_campaigns::tests::nc_precedence_core_seed_000071", nc_precedence_core_seed_000071),
        ("property_campaigns::tests::nc_precedence_core_seed_000072", nc_precedence_core_seed_000072),
        ("property_campaigns::tests::nc_precedence_core_seed_000073", nc_precedence_core_seed_000073),
        ("property_campaigns::tests::nc_precedence_core_seed_000074", nc_precedence_core_seed_000074),
        ("property_campaigns::tests::nc_precedence_core_seed_000075", nc_precedence_core_seed_000075),
        ("property_campaigns::tests::nc_precedence_core_seed_000076", nc_precedence_core_seed_000076),
        ("property_campaigns::tests::nc_precedence_core_seed_000077", nc_precedence_core_seed_000077),
        ("property_campaigns::tests::nc_precedence_core_seed_000078", nc_precedence_core_seed_000078),
        ("property_campaigns::tests::nc_precedence_core_seed_000079", nc_precedence_core_seed_000079),
        ("property_campaigns::tests::nc_precedence_core_seed_000080", nc_precedence_core_seed_000080),
        ("property_campaigns::tests::nc_precedence_core_seed_000081", nc_precedence_core_seed_000081),
        ("property_campaigns::tests::nc_precedence_core_seed_000082", nc_precedence_core_seed_000082),
        ("property_campaigns::tests::nc_precedence_core_seed_000083", nc_precedence_core_seed_000083),
        ("property_campaigns::tests::nc_precedence_core_seed_000084", nc_precedence_core_seed_000084),
        ("property_campaigns::tests::nc_precedence_core_seed_000085", nc_precedence_core_seed_000085),
        ("property_campaigns::tests::nc_precedence_core_seed_000086", nc_precedence_core_seed_000086),
        ("property_campaigns::tests::nc_precedence_core_seed_000087", nc_precedence_core_seed_000087),
        ("property_campaigns::tests::nc_precedence_core_seed_000088", nc_precedence_core_seed_000088),
        ("property_campaigns::tests::nc_precedence_core_seed_000089", nc_precedence_core_seed_000089),
        ("property_campaigns::tests::nc_precedence_core_seed_000090", nc_precedence_core_seed_000090),
        ("property_campaigns::tests::nc_precedence_core_seed_000091", nc_precedence_core_seed_000091),
        ("property_campaigns::tests::nc_precedence_core_seed_000092", nc_precedence_core_seed_000092),
        ("property_campaigns::tests::nc_precedence_core_seed_000093", nc_precedence_core_seed_000093),
        ("property_campaigns::tests::nc_precedence_core_seed_000094", nc_precedence_core_seed_000094),
        ("property_campaigns::tests::nc_precedence_core_seed_000095", nc_precedence_core_seed_000095),
        ("property_campaigns::tests::nc_precedence_core_seed_000096", nc_precedence_core_seed_000096),
        ("property_campaigns::tests::nc_precedence_core_seed_000097", nc_precedence_core_seed_000097),
        ("property_campaigns::tests::nc_precedence_core_seed_000098", nc_precedence_core_seed_000098),
        ("property_campaigns::tests::nc_precedence_core_seed_000099", nc_precedence_core_seed_000099),
        ("property_campaigns::tests::nc_precedence_core_seed_000100", nc_precedence_core_seed_000100),
        ("property_campaigns::tests::nc_precedence_core_seed_000101", nc_precedence_core_seed_000101),
        ("property_campaigns::tests::nc_precedence_core_seed_000102", nc_precedence_core_seed_000102),
        ("property_campaigns::tests::nc_precedence_core_seed_000103", nc_precedence_core_seed_000103),
        ("property_campaigns::tests::nc_precedence_core_seed_000104", nc_precedence_core_seed_000104),
        ("property_campaigns::tests::nc_precedence_core_seed_000105", nc_precedence_core_seed_000105),
        ("property_campaigns::tests::nc_precedence_core_seed_000106", nc_precedence_core_seed_000106),
        ("property_campaigns::tests::nc_precedence_core_seed_000107", nc_precedence_core_seed_000107),
        ("property_campaigns::tests::nc_precedence_core_seed_000108", nc_precedence_core_seed_000108),
        ("property_campaigns::tests::nc_precedence_core_seed_000109", nc_precedence_core_seed_000109),
        ("property_campaigns::tests::nc_precedence_core_seed_000110", nc_precedence_core_seed_000110),
        ("property_campaigns::tests::nc_precedence_core_seed_000111", nc_precedence_core_seed_000111),
        ("property_campaigns::tests::nc_precedence_core_seed_000112", nc_precedence_core_seed_000112),
        ("property_campaigns::tests::nc_precedence_core_seed_000113", nc_precedence_core_seed_000113),
        ("property_campaigns::tests::nc_precedence_core_seed_000114", nc_precedence_core_seed_000114),
        ("property_campaigns::tests::nc_precedence_core_seed_000115", nc_precedence_core_seed_000115),
        ("property_campaigns::tests::nc_precedence_core_seed_000116", nc_precedence_core_seed_000116),
        ("property_campaigns::tests::nc_precedence_core_seed_000117", nc_precedence_core_seed_000117),
        ("property_campaigns::tests::nc_precedence_core_seed_000118", nc_precedence_core_seed_000118),
        ("property_campaigns::tests::nc_precedence_core_seed_000119", nc_precedence_core_seed_000119),
        ("property_campaigns::tests::nc_precedence_core_seed_000120", nc_precedence_core_seed_000120),
        ("property_campaigns::tests::nc_precedence_core_seed_000121", nc_precedence_core_seed_000121),
        ("property_campaigns::tests::nc_precedence_core_seed_000122", nc_precedence_core_seed_000122),
        ("property_campaigns::tests::nc_precedence_core_seed_000123", nc_precedence_core_seed_000123),
        ("property_campaigns::tests::nc_precedence_core_seed_000124", nc_precedence_core_seed_000124),
        ("property_campaigns::tests::nc_precedence_core_seed_000125", nc_precedence_core_seed_000125),
        ("property_campaigns::tests::nc_precedence_core_seed_000126", nc_precedence_core_seed_000126),
        ("property_campaigns::tests::nc_precedence_core_seed_000127", nc_precedence_core_seed_000127),
        ("property_campaigns::tests::nc_precedence_core_seed_000128", nc_precedence_core_seed_000128),
        ("property_campaigns::tests::nc_precedence_core_seed_000129", nc_precedence_core_seed_000129),
        ("property_campaigns::tests::nc_precedence_core_seed_000130", nc_precedence_core_seed_000130),
        ("property_campaigns::tests::nc_precedence_core_seed_000131", nc_precedence_core_seed_000131),
        ("property_campaigns::tests::nc_precedence_core_seed_000132", nc_precedence_core_seed_000132),
        ("property_campaigns::tests::nc_precedence_core_seed_000133", nc_precedence_core_seed_000133),
        ("property_campaigns::tests::nc_precedence_core_seed_000134", nc_precedence_core_seed_000134),
        ("property_campaigns::tests::nc_precedence_core_seed_000135", nc_precedence_core_seed_000135),
        ("property_campaigns::tests::nc_precedence_core_seed_000136", nc_precedence_core_seed_000136),
        ("property_campaigns::tests::nc_precedence_core_seed_000137", nc_precedence_core_seed_000137),
        ("property_campaigns::tests::nc_precedence_core_seed_000138", nc_precedence_core_seed_000138),
        ("property_campaigns::tests::nc_precedence_core_seed_000139", nc_precedence_core_seed_000139),
        ("property_campaigns::tests::nc_precedence_core_seed_000140", nc_precedence_core_seed_000140),
        ("property_campaigns::tests::nc_precedence_core_seed_000141", nc_precedence_core_seed_000141),
        ("property_campaigns::tests::nc_precedence_core_seed_000142", nc_precedence_core_seed_000142),
        ("property_campaigns::tests::nc_precedence_core_seed_000143", nc_precedence_core_seed_000143),
        ("property_campaigns::tests::nc_precedence_core_seed_000144", nc_precedence_core_seed_000144),
        ("property_campaigns::tests::nc_precedence_core_seed_000145", nc_precedence_core_seed_000145),
        ("property_campaigns::tests::nc_precedence_core_seed_000146", nc_precedence_core_seed_000146),
        ("property_campaigns::tests::nc_precedence_core_seed_000147", nc_precedence_core_seed_000147),
        ("property_campaigns::tests::nc_precedence_core_seed_000148", nc_precedence_core_seed_000148),
        ("property_campaigns::tests::nc_precedence_core_seed_000149", nc_precedence_core_seed_000149),
        ("property_campaigns::tests::nc_precedence_core_seed_000150", nc_precedence_core_seed_000150),
        ("property_campaigns::tests::nc_precedence_core_seed_000151", nc_precedence_core_seed_000151),
        ("property_campaigns::tests::nc_precedence_core_seed_000152", nc_precedence_core_seed_000152),
        ("property_campaigns::tests::nc_precedence_core_seed_000153", nc_precedence_core_seed_000153),
        ("property_campaigns::tests::nc_precedence_core_seed_000154", nc_precedence_core_seed_000154),
        ("property_campaigns::tests::nc_precedence_core_seed_000155", nc_precedence_core_seed_000155),
        ("property_campaigns::tests::nc_precedence_core_seed_000156", nc_precedence_core_seed_000156),
        ("property_campaigns::tests::nc_precedence_core_seed_000157", nc_precedence_core_seed_000157),
        ("property_campaigns::tests::nc_precedence_core_seed_000158", nc_precedence_core_seed_000158),
        ("property_campaigns::tests::nc_precedence_core_seed_000159", nc_precedence_core_seed_000159),
        ("property_campaigns::tests::nc_precedence_core_seed_000160", nc_precedence_core_seed_000160),
        ("property_campaigns::tests::nc_precedence_core_seed_000161", nc_precedence_core_seed_000161),
        ("property_campaigns::tests::nc_precedence_core_seed_000162", nc_precedence_core_seed_000162),
        ("property_campaigns::tests::nc_precedence_core_seed_000163", nc_precedence_core_seed_000163),
        ("property_campaigns::tests::nc_precedence_core_seed_000164", nc_precedence_core_seed_000164),
        ("property_campaigns::tests::nc_precedence_core_seed_000165", nc_precedence_core_seed_000165),
        ("property_campaigns::tests::nc_precedence_core_seed_000166", nc_precedence_core_seed_000166),
        ("property_campaigns::tests::nc_precedence_core_seed_000167", nc_precedence_core_seed_000167),
        ("property_campaigns::tests::nc_precedence_core_seed_000168", nc_precedence_core_seed_000168),
        ("property_campaigns::tests::nc_precedence_core_seed_000169", nc_precedence_core_seed_000169),
        ("property_campaigns::tests::nc_precedence_core_seed_000170", nc_precedence_core_seed_000170),
        ("property_campaigns::tests::nc_precedence_core_seed_000171", nc_precedence_core_seed_000171),
        ("property_campaigns::tests::nc_precedence_core_seed_000172", nc_precedence_core_seed_000172),
        ("property_campaigns::tests::nc_precedence_core_seed_000173", nc_precedence_core_seed_000173),
        ("property_campaigns::tests::nc_precedence_core_seed_000174", nc_precedence_core_seed_000174),
        ("property_campaigns::tests::nc_precedence_core_seed_000175", nc_precedence_core_seed_000175),
        ("property_campaigns::tests::nc_precedence_core_seed_000176", nc_precedence_core_seed_000176),
        ("property_campaigns::tests::nc_precedence_core_seed_000177", nc_precedence_core_seed_000177),
        ("property_campaigns::tests::nc_precedence_core_seed_000178", nc_precedence_core_seed_000178),
        ("property_campaigns::tests::nc_precedence_core_seed_000179", nc_precedence_core_seed_000179),
        ("property_campaigns::tests::nc_precedence_core_seed_000180", nc_precedence_core_seed_000180),
        ("property_campaigns::tests::nc_precedence_core_seed_000181", nc_precedence_core_seed_000181),
        ("property_campaigns::tests::nc_precedence_core_seed_000182", nc_precedence_core_seed_000182),
        ("property_campaigns::tests::nc_precedence_core_seed_000183", nc_precedence_core_seed_000183),
        ("property_campaigns::tests::nc_precedence_core_seed_000184", nc_precedence_core_seed_000184),
        ("property_campaigns::tests::nc_precedence_core_seed_000185", nc_precedence_core_seed_000185),
        ("property_campaigns::tests::nc_precedence_core_seed_000186", nc_precedence_core_seed_000186),
        ("property_campaigns::tests::nc_precedence_core_seed_000187", nc_precedence_core_seed_000187),
        ("property_campaigns::tests::nc_precedence_core_seed_000188", nc_precedence_core_seed_000188),
        ("property_campaigns::tests::nc_precedence_core_seed_000189", nc_precedence_core_seed_000189),
        ("property_campaigns::tests::nc_precedence_core_seed_000190", nc_precedence_core_seed_000190),
        ("property_campaigns::tests::nc_precedence_core_seed_000191", nc_precedence_core_seed_000191),
        ("property_campaigns::tests::nc_precedence_core_seed_000192", nc_precedence_core_seed_000192),
        ("property_campaigns::tests::nc_precedence_core_seed_000193", nc_precedence_core_seed_000193),
        ("property_campaigns::tests::nc_precedence_core_seed_000194", nc_precedence_core_seed_000194),
        ("property_campaigns::tests::nc_precedence_core_seed_000195", nc_precedence_core_seed_000195),
        ("property_campaigns::tests::nc_precedence_core_seed_000196", nc_precedence_core_seed_000196),
        ("property_campaigns::tests::nc_precedence_core_seed_000197", nc_precedence_core_seed_000197),
        ("property_campaigns::tests::nc_precedence_core_seed_000198", nc_precedence_core_seed_000198),
        ("property_campaigns::tests::nc_precedence_core_seed_000199", nc_precedence_core_seed_000199),
        ("property_campaigns::tests::nc_precedence_v6_seed_000000", nc_precedence_v6_seed_000000),
        ("property_campaigns::tests::nc_precedence_v6_seed_000001", nc_precedence_v6_seed_000001),
        ("property_campaigns::tests::nc_precedence_v6_seed_000002", nc_precedence_v6_seed_000002),
        ("property_campaigns::tests::nc_precedence_v6_seed_000003", nc_precedence_v6_seed_000003),
        ("property_campaigns::tests::nc_precedence_v6_seed_000004", nc_precedence_v6_seed_000004),
        ("property_campaigns::tests::nc_precedence_v6_seed_000005", nc_precedence_v6_seed_000005),
        ("property_campaigns::tests::nc_precedence_v6_seed_000006", nc_precedence_v6_seed_000006),
        ("property_campaigns::tests::nc_precedence_v6_seed_000007", nc_precedence_v6_seed_000007),
        ("property_campaigns::tests::nc_precedence_v6_seed_000008", nc_precedence_v6_seed_000008),
        ("property_campaigns::tests::nc_precedence_v6_seed_000009", nc_precedence_v6_seed_000009),
        ("property_campaigns::tests::nc_precedence_v6_seed_000010", nc_precedence_v6_seed_000010),
        ("property_campaigns::tests::nc_precedence_v6_seed_000011", nc_precedence_v6_seed_000011),
        ("property_campaigns::tests::nc_precedence_v6_seed_000012", nc_precedence_v6_seed_000012),
        ("property_campaigns::tests::nc_precedence_v6_seed_000013", nc_precedence_v6_seed_000013),
        ("property_campaigns::tests::nc_precedence_v6_seed_000014", nc_precedence_v6_seed_000014),
        ("property_campaigns::tests::nc_precedence_v6_seed_000015", nc_precedence_v6_seed_000015),
        ("property_campaigns::tests::nc_precedence_v6_seed_000016", nc_precedence_v6_seed_000016),
        ("property_campaigns::tests::nc_precedence_v6_seed_000017", nc_precedence_v6_seed_000017),
        ("property_campaigns::tests::nc_precedence_v6_seed_000018", nc_precedence_v6_seed_000018),
        ("property_campaigns::tests::nc_precedence_v6_seed_000019", nc_precedence_v6_seed_000019),
        ("property_campaigns::tests::nc_precedence_v6_seed_000020", nc_precedence_v6_seed_000020),
        ("property_campaigns::tests::nc_precedence_v6_seed_000021", nc_precedence_v6_seed_000021),
        ("property_campaigns::tests::nc_precedence_v6_seed_000022", nc_precedence_v6_seed_000022),
        ("property_campaigns::tests::nc_precedence_v6_seed_000023", nc_precedence_v6_seed_000023),
        ("property_campaigns::tests::nc_precedence_v6_seed_000024", nc_precedence_v6_seed_000024),
        ("property_campaigns::tests::nc_precedence_v6_seed_000025", nc_precedence_v6_seed_000025),
        ("property_campaigns::tests::nc_precedence_v6_seed_000026", nc_precedence_v6_seed_000026),
        ("property_campaigns::tests::nc_precedence_v6_seed_000027", nc_precedence_v6_seed_000027),
        ("property_campaigns::tests::nc_precedence_v6_seed_000028", nc_precedence_v6_seed_000028),
        ("property_campaigns::tests::nc_precedence_v6_seed_000029", nc_precedence_v6_seed_000029),
        ("property_campaigns::tests::nc_precedence_v6_seed_000030", nc_precedence_v6_seed_000030),
        ("property_campaigns::tests::nc_precedence_v6_seed_000031", nc_precedence_v6_seed_000031),
        ("property_campaigns::tests::nc_precedence_v6_seed_000032", nc_precedence_v6_seed_000032),
        ("property_campaigns::tests::nc_precedence_v6_seed_000033", nc_precedence_v6_seed_000033),
        ("property_campaigns::tests::nc_precedence_v6_seed_000034", nc_precedence_v6_seed_000034),
        ("property_campaigns::tests::nc_precedence_v6_seed_000035", nc_precedence_v6_seed_000035),
        ("property_campaigns::tests::nc_precedence_v6_seed_000036", nc_precedence_v6_seed_000036),
        ("property_campaigns::tests::nc_precedence_v6_seed_000037", nc_precedence_v6_seed_000037),
        ("property_campaigns::tests::nc_precedence_v6_seed_000038", nc_precedence_v6_seed_000038),
        ("property_campaigns::tests::nc_precedence_v6_seed_000039", nc_precedence_v6_seed_000039),
        ("property_campaigns::tests::nc_precedence_v6_seed_000040", nc_precedence_v6_seed_000040),
        ("property_campaigns::tests::nc_precedence_v6_seed_000041", nc_precedence_v6_seed_000041),
        ("property_campaigns::tests::nc_precedence_v6_seed_000042", nc_precedence_v6_seed_000042),
        ("property_campaigns::tests::nc_precedence_v6_seed_000043", nc_precedence_v6_seed_000043),
        ("property_campaigns::tests::nc_precedence_v6_seed_000044", nc_precedence_v6_seed_000044),
        ("property_campaigns::tests::nc_precedence_v6_seed_000045", nc_precedence_v6_seed_000045),
        ("property_campaigns::tests::nc_precedence_v6_seed_000046", nc_precedence_v6_seed_000046),
        ("property_campaigns::tests::nc_precedence_v6_seed_000047", nc_precedence_v6_seed_000047),
        ("property_campaigns::tests::nc_precedence_v6_seed_000048", nc_precedence_v6_seed_000048),
        ("property_campaigns::tests::nc_precedence_v6_seed_000049", nc_precedence_v6_seed_000049),
        ("property_campaigns::tests::nc_precedence_v6_seed_000050", nc_precedence_v6_seed_000050),
        ("property_campaigns::tests::nc_precedence_v6_seed_000051", nc_precedence_v6_seed_000051),
        ("property_campaigns::tests::nc_precedence_v6_seed_000052", nc_precedence_v6_seed_000052),
        ("property_campaigns::tests::nc_precedence_v6_seed_000053", nc_precedence_v6_seed_000053),
        ("property_campaigns::tests::nc_precedence_v6_seed_000054", nc_precedence_v6_seed_000054),
        ("property_campaigns::tests::nc_precedence_v6_seed_000055", nc_precedence_v6_seed_000055),
        ("property_campaigns::tests::nc_precedence_v6_seed_000056", nc_precedence_v6_seed_000056),
        ("property_campaigns::tests::nc_precedence_v6_seed_000057", nc_precedence_v6_seed_000057),
        ("property_campaigns::tests::nc_precedence_v6_seed_000058", nc_precedence_v6_seed_000058),
        ("property_campaigns::tests::nc_precedence_v6_seed_000059", nc_precedence_v6_seed_000059),
        ("property_campaigns::tests::nc_precedence_v6_seed_000060", nc_precedence_v6_seed_000060),
        ("property_campaigns::tests::nc_precedence_v6_seed_000061", nc_precedence_v6_seed_000061),
        ("property_campaigns::tests::nc_precedence_v6_seed_000062", nc_precedence_v6_seed_000062),
        ("property_campaigns::tests::nc_precedence_v6_seed_000063", nc_precedence_v6_seed_000063),
        ("property_campaigns::tests::nc_precedence_v6_seed_000064", nc_precedence_v6_seed_000064),
        ("property_campaigns::tests::nc_precedence_v6_seed_000065", nc_precedence_v6_seed_000065),
        ("property_campaigns::tests::nc_precedence_v6_seed_000066", nc_precedence_v6_seed_000066),
        ("property_campaigns::tests::nc_precedence_v6_seed_000067", nc_precedence_v6_seed_000067),
        ("property_campaigns::tests::nc_precedence_v6_seed_000068", nc_precedence_v6_seed_000068),
        ("property_campaigns::tests::nc_precedence_v6_seed_000069", nc_precedence_v6_seed_000069),
        ("property_campaigns::tests::nc_precedence_v6_seed_000070", nc_precedence_v6_seed_000070),
        ("property_campaigns::tests::nc_precedence_v6_seed_000071", nc_precedence_v6_seed_000071),
        ("property_campaigns::tests::nc_precedence_v6_seed_000072", nc_precedence_v6_seed_000072),
        ("property_campaigns::tests::nc_precedence_v6_seed_000073", nc_precedence_v6_seed_000073),
        ("property_campaigns::tests::nc_precedence_v6_seed_000074", nc_precedence_v6_seed_000074),
        ("property_campaigns::tests::nc_precedence_v6_seed_000075", nc_precedence_v6_seed_000075),
        ("property_campaigns::tests::nc_precedence_v6_seed_000076", nc_precedence_v6_seed_000076),
        ("property_campaigns::tests::nc_precedence_v6_seed_000077", nc_precedence_v6_seed_000077),
        ("property_campaigns::tests::nc_precedence_v6_seed_000078", nc_precedence_v6_seed_000078),
        ("property_campaigns::tests::nc_precedence_v6_seed_000079", nc_precedence_v6_seed_000079),
        ("property_campaigns::tests::nc_precedence_v6_seed_000080", nc_precedence_v6_seed_000080),
        ("property_campaigns::tests::nc_precedence_v6_seed_000081", nc_precedence_v6_seed_000081),
        ("property_campaigns::tests::nc_precedence_v6_seed_000082", nc_precedence_v6_seed_000082),
        ("property_campaigns::tests::nc_precedence_v6_seed_000083", nc_precedence_v6_seed_000083),
        ("property_campaigns::tests::nc_precedence_v6_seed_000084", nc_precedence_v6_seed_000084),
        ("property_campaigns::tests::nc_precedence_v6_seed_000085", nc_precedence_v6_seed_000085),
        ("property_campaigns::tests::nc_precedence_v6_seed_000086", nc_precedence_v6_seed_000086),
        ("property_campaigns::tests::nc_precedence_v6_seed_000087", nc_precedence_v6_seed_000087),
        ("property_campaigns::tests::nc_precedence_v6_seed_000088", nc_precedence_v6_seed_000088),
        ("property_campaigns::tests::nc_precedence_v6_seed_000089", nc_precedence_v6_seed_000089),
        ("property_campaigns::tests::nc_precedence_v6_seed_000090", nc_precedence_v6_seed_000090),
        ("property_campaigns::tests::nc_precedence_v6_seed_000091", nc_precedence_v6_seed_000091),
        ("property_campaigns::tests::nc_precedence_v6_seed_000092", nc_precedence_v6_seed_000092),
        ("property_campaigns::tests::nc_precedence_v6_seed_000093", nc_precedence_v6_seed_000093),
        ("property_campaigns::tests::nc_precedence_v6_seed_000094", nc_precedence_v6_seed_000094),
        ("property_campaigns::tests::nc_precedence_v6_seed_000095", nc_precedence_v6_seed_000095),
        ("property_campaigns::tests::nc_precedence_v6_seed_000096", nc_precedence_v6_seed_000096),
        ("property_campaigns::tests::nc_precedence_v6_seed_000097", nc_precedence_v6_seed_000097),
        ("property_campaigns::tests::nc_precedence_v6_seed_000098", nc_precedence_v6_seed_000098),
        ("property_campaigns::tests::nc_precedence_v6_seed_000099", nc_precedence_v6_seed_000099),
        ("property_campaigns::tests::nc_precedence_v6_seed_000100", nc_precedence_v6_seed_000100),
        ("property_campaigns::tests::nc_precedence_v6_seed_000101", nc_precedence_v6_seed_000101),
        ("property_campaigns::tests::nc_precedence_v6_seed_000102", nc_precedence_v6_seed_000102),
        ("property_campaigns::tests::nc_precedence_v6_seed_000103", nc_precedence_v6_seed_000103),
        ("property_campaigns::tests::nc_precedence_v6_seed_000104", nc_precedence_v6_seed_000104),
        ("property_campaigns::tests::nc_precedence_v6_seed_000105", nc_precedence_v6_seed_000105),
        ("property_campaigns::tests::nc_precedence_v6_seed_000106", nc_precedence_v6_seed_000106),
        ("property_campaigns::tests::nc_precedence_v6_seed_000107", nc_precedence_v6_seed_000107),
        ("property_campaigns::tests::nc_precedence_v6_seed_000108", nc_precedence_v6_seed_000108),
        ("property_campaigns::tests::nc_precedence_v6_seed_000109", nc_precedence_v6_seed_000109),
        ("property_campaigns::tests::nc_precedence_v6_seed_000110", nc_precedence_v6_seed_000110),
        ("property_campaigns::tests::nc_precedence_v6_seed_000111", nc_precedence_v6_seed_000111),
        ("property_campaigns::tests::nc_precedence_v6_seed_000112", nc_precedence_v6_seed_000112),
        ("property_campaigns::tests::nc_precedence_v6_seed_000113", nc_precedence_v6_seed_000113),
        ("property_campaigns::tests::nc_precedence_v6_seed_000114", nc_precedence_v6_seed_000114),
        ("property_campaigns::tests::nc_precedence_v6_seed_000115", nc_precedence_v6_seed_000115),
        ("property_campaigns::tests::nc_precedence_v6_seed_000116", nc_precedence_v6_seed_000116),
        ("property_campaigns::tests::nc_precedence_v6_seed_000117", nc_precedence_v6_seed_000117),
        ("property_campaigns::tests::nc_precedence_v6_seed_000118", nc_precedence_v6_seed_000118),
        ("property_campaigns::tests::nc_precedence_v6_seed_000119", nc_precedence_v6_seed_000119),
        ("property_campaigns::tests::nc_precedence_v6_seed_000120", nc_precedence_v6_seed_000120),
        ("property_campaigns::tests::nc_precedence_v6_seed_000121", nc_precedence_v6_seed_000121),
        ("property_campaigns::tests::nc_precedence_v6_seed_000122", nc_precedence_v6_seed_000122),
        ("property_campaigns::tests::nc_precedence_v6_seed_000123", nc_precedence_v6_seed_000123),
        ("property_campaigns::tests::nc_precedence_v6_seed_000124", nc_precedence_v6_seed_000124),
        ("property_campaigns::tests::nc_precedence_v6_seed_000125", nc_precedence_v6_seed_000125),
        ("property_campaigns::tests::nc_precedence_v6_seed_000126", nc_precedence_v6_seed_000126),
        ("property_campaigns::tests::nc_precedence_v6_seed_000127", nc_precedence_v6_seed_000127),
        ("property_campaigns::tests::nc_precedence_v6_seed_000128", nc_precedence_v6_seed_000128),
        ("property_campaigns::tests::nc_precedence_v6_seed_000129", nc_precedence_v6_seed_000129),
        ("property_campaigns::tests::nc_precedence_v6_seed_000130", nc_precedence_v6_seed_000130),
        ("property_campaigns::tests::nc_precedence_v6_seed_000131", nc_precedence_v6_seed_000131),
        ("property_campaigns::tests::nc_precedence_v6_seed_000132", nc_precedence_v6_seed_000132),
        ("property_campaigns::tests::nc_precedence_v6_seed_000133", nc_precedence_v6_seed_000133),
        ("property_campaigns::tests::nc_precedence_v6_seed_000134", nc_precedence_v6_seed_000134),
        ("property_campaigns::tests::nc_precedence_v6_seed_000135", nc_precedence_v6_seed_000135),
        ("property_campaigns::tests::nc_precedence_v6_seed_000136", nc_precedence_v6_seed_000136),
        ("property_campaigns::tests::nc_precedence_v6_seed_000137", nc_precedence_v6_seed_000137),
        ("property_campaigns::tests::nc_precedence_v6_seed_000138", nc_precedence_v6_seed_000138),
        ("property_campaigns::tests::nc_precedence_v6_seed_000139", nc_precedence_v6_seed_000139),
        ("property_campaigns::tests::nc_precedence_v6_seed_000140", nc_precedence_v6_seed_000140),
        ("property_campaigns::tests::nc_precedence_v6_seed_000141", nc_precedence_v6_seed_000141),
        ("property_campaigns::tests::nc_precedence_v6_seed_000142", nc_precedence_v6_seed_000142),
        ("property_campaigns::tests::nc_precedence_v6_seed_000143", nc_precedence_v6_seed_000143),
        ("property_campaigns::tests::nc_precedence_v6_seed_000144", nc_precedence_v6_seed_000144),
        ("property_campaigns::tests::nc_precedence_v6_seed_000145", nc_precedence_v6_seed_000145),
        ("property_campaigns::tests::nc_precedence_v6_seed_000146", nc_precedence_v6_seed_000146),
        ("property_campaigns::tests::nc_precedence_v6_seed_000147", nc_precedence_v6_seed_000147),
        ("property_campaigns::tests::nc_precedence_v6_seed_000148", nc_precedence_v6_seed_000148),
        ("property_campaigns::tests::nc_precedence_v6_seed_000149", nc_precedence_v6_seed_000149),
        ("property_campaigns::tests::nc_precedence_v6_seed_000150", nc_precedence_v6_seed_000150),
        ("property_campaigns::tests::nc_precedence_v6_seed_000151", nc_precedence_v6_seed_000151),
        ("property_campaigns::tests::nc_precedence_v6_seed_000152", nc_precedence_v6_seed_000152),
        ("property_campaigns::tests::nc_precedence_v6_seed_000153", nc_precedence_v6_seed_000153),
        ("property_campaigns::tests::nc_precedence_v6_seed_000154", nc_precedence_v6_seed_000154),
        ("property_campaigns::tests::nc_precedence_v6_seed_000155", nc_precedence_v6_seed_000155),
        ("property_campaigns::tests::nc_precedence_v6_seed_000156", nc_precedence_v6_seed_000156),
        ("property_campaigns::tests::nc_precedence_v6_seed_000157", nc_precedence_v6_seed_000157),
        ("property_campaigns::tests::nc_precedence_v6_seed_000158", nc_precedence_v6_seed_000158),
        ("property_campaigns::tests::nc_precedence_v6_seed_000159", nc_precedence_v6_seed_000159),
        ("property_campaigns::tests::nc_precedence_v6_seed_000160", nc_precedence_v6_seed_000160),
        ("property_campaigns::tests::nc_precedence_v6_seed_000161", nc_precedence_v6_seed_000161),
        ("property_campaigns::tests::nc_precedence_v6_seed_000162", nc_precedence_v6_seed_000162),
        ("property_campaigns::tests::nc_precedence_v6_seed_000163", nc_precedence_v6_seed_000163),
        ("property_campaigns::tests::nc_precedence_v6_seed_000164", nc_precedence_v6_seed_000164),
        ("property_campaigns::tests::nc_precedence_v6_seed_000165", nc_precedence_v6_seed_000165),
        ("property_campaigns::tests::nc_precedence_v6_seed_000166", nc_precedence_v6_seed_000166),
        ("property_campaigns::tests::nc_precedence_v6_seed_000167", nc_precedence_v6_seed_000167),
        ("property_campaigns::tests::nc_precedence_v6_seed_000168", nc_precedence_v6_seed_000168),
        ("property_campaigns::tests::nc_precedence_v6_seed_000169", nc_precedence_v6_seed_000169),
        ("property_campaigns::tests::nc_precedence_v6_seed_000170", nc_precedence_v6_seed_000170),
        ("property_campaigns::tests::nc_precedence_v6_seed_000171", nc_precedence_v6_seed_000171),
        ("property_campaigns::tests::nc_precedence_v6_seed_000172", nc_precedence_v6_seed_000172),
        ("property_campaigns::tests::nc_precedence_v6_seed_000173", nc_precedence_v6_seed_000173),
        ("property_campaigns::tests::nc_precedence_v6_seed_000174", nc_precedence_v6_seed_000174),
        ("property_campaigns::tests::nc_precedence_v6_seed_000175", nc_precedence_v6_seed_000175),
        ("property_campaigns::tests::nc_precedence_v6_seed_000176", nc_precedence_v6_seed_000176),
        ("property_campaigns::tests::nc_precedence_v6_seed_000177", nc_precedence_v6_seed_000177),
        ("property_campaigns::tests::nc_precedence_v6_seed_000178", nc_precedence_v6_seed_000178),
        ("property_campaigns::tests::nc_precedence_v6_seed_000179", nc_precedence_v6_seed_000179),
        ("property_campaigns::tests::nc_precedence_v6_seed_000180", nc_precedence_v6_seed_000180),
        ("property_campaigns::tests::nc_precedence_v6_seed_000181", nc_precedence_v6_seed_000181),
        ("property_campaigns::tests::nc_precedence_v6_seed_000182", nc_precedence_v6_seed_000182),
        ("property_campaigns::tests::nc_precedence_v6_seed_000183", nc_precedence_v6_seed_000183),
        ("property_campaigns::tests::nc_precedence_v6_seed_000184", nc_precedence_v6_seed_000184),
        ("property_campaigns::tests::nc_precedence_v6_seed_000185", nc_precedence_v6_seed_000185),
        ("property_campaigns::tests::nc_precedence_v6_seed_000186", nc_precedence_v6_seed_000186),
        ("property_campaigns::tests::nc_precedence_v6_seed_000187", nc_precedence_v6_seed_000187),
        ("property_campaigns::tests::nc_precedence_v6_seed_000188", nc_precedence_v6_seed_000188),
        ("property_campaigns::tests::nc_precedence_v6_seed_000189", nc_precedence_v6_seed_000189),
        ("property_campaigns::tests::nc_precedence_v6_seed_000190", nc_precedence_v6_seed_000190),
        ("property_campaigns::tests::nc_precedence_v6_seed_000191", nc_precedence_v6_seed_000191),
        ("property_campaigns::tests::nc_precedence_v6_seed_000192", nc_precedence_v6_seed_000192),
        ("property_campaigns::tests::nc_precedence_v6_seed_000193", nc_precedence_v6_seed_000193),
        ("property_campaigns::tests::nc_precedence_v6_seed_000194", nc_precedence_v6_seed_000194),
        ("property_campaigns::tests::nc_precedence_v6_seed_000195", nc_precedence_v6_seed_000195),
        ("property_campaigns::tests::nc_precedence_v6_seed_000196", nc_precedence_v6_seed_000196),
        ("property_campaigns::tests::nc_precedence_v6_seed_000197", nc_precedence_v6_seed_000197),
        ("property_campaigns::tests::nc_precedence_v6_seed_000198", nc_precedence_v6_seed_000198),
        ("property_campaigns::tests::nc_precedence_v6_seed_000199", nc_precedence_v6_seed_000199),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000000", nc_case_invariance_core_seed_000000),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000001", nc_case_invariance_core_seed_000001),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000002", nc_case_invariance_core_seed_000002),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000003", nc_case_invariance_core_seed_000003),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000004", nc_case_invariance_core_seed_000004),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000005", nc_case_invariance_core_seed_000005),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000006", nc_case_invariance_core_seed_000006),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000007", nc_case_invariance_core_seed_000007),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000008", nc_case_invariance_core_seed_000008),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000009", nc_case_invariance_core_seed_000009),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000010", nc_case_invariance_core_seed_000010),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000011", nc_case_invariance_core_seed_000011),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000012", nc_case_invariance_core_seed_000012),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000013", nc_case_invariance_core_seed_000013),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000014", nc_case_invariance_core_seed_000014),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000015", nc_case_invariance_core_seed_000015),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000016", nc_case_invariance_core_seed_000016),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000017", nc_case_invariance_core_seed_000017),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000018", nc_case_invariance_core_seed_000018),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000019", nc_case_invariance_core_seed_000019),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000020", nc_case_invariance_core_seed_000020),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000021", nc_case_invariance_core_seed_000021),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000022", nc_case_invariance_core_seed_000022),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000023", nc_case_invariance_core_seed_000023),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000024", nc_case_invariance_core_seed_000024),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000025", nc_case_invariance_core_seed_000025),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000026", nc_case_invariance_core_seed_000026),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000027", nc_case_invariance_core_seed_000027),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000028", nc_case_invariance_core_seed_000028),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000029", nc_case_invariance_core_seed_000029),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000030", nc_case_invariance_core_seed_000030),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000031", nc_case_invariance_core_seed_000031),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000032", nc_case_invariance_core_seed_000032),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000033", nc_case_invariance_core_seed_000033),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000034", nc_case_invariance_core_seed_000034),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000035", nc_case_invariance_core_seed_000035),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000036", nc_case_invariance_core_seed_000036),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000037", nc_case_invariance_core_seed_000037),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000038", nc_case_invariance_core_seed_000038),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000039", nc_case_invariance_core_seed_000039),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000040", nc_case_invariance_core_seed_000040),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000041", nc_case_invariance_core_seed_000041),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000042", nc_case_invariance_core_seed_000042),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000043", nc_case_invariance_core_seed_000043),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000044", nc_case_invariance_core_seed_000044),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000045", nc_case_invariance_core_seed_000045),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000046", nc_case_invariance_core_seed_000046),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000047", nc_case_invariance_core_seed_000047),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000048", nc_case_invariance_core_seed_000048),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000049", nc_case_invariance_core_seed_000049),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000050", nc_case_invariance_core_seed_000050),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000051", nc_case_invariance_core_seed_000051),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000052", nc_case_invariance_core_seed_000052),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000053", nc_case_invariance_core_seed_000053),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000054", nc_case_invariance_core_seed_000054),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000055", nc_case_invariance_core_seed_000055),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000056", nc_case_invariance_core_seed_000056),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000057", nc_case_invariance_core_seed_000057),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000058", nc_case_invariance_core_seed_000058),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000059", nc_case_invariance_core_seed_000059),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000060", nc_case_invariance_core_seed_000060),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000061", nc_case_invariance_core_seed_000061),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000062", nc_case_invariance_core_seed_000062),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000063", nc_case_invariance_core_seed_000063),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000064", nc_case_invariance_core_seed_000064),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000065", nc_case_invariance_core_seed_000065),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000066", nc_case_invariance_core_seed_000066),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000067", nc_case_invariance_core_seed_000067),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000068", nc_case_invariance_core_seed_000068),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000069", nc_case_invariance_core_seed_000069),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000070", nc_case_invariance_core_seed_000070),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000071", nc_case_invariance_core_seed_000071),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000072", nc_case_invariance_core_seed_000072),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000073", nc_case_invariance_core_seed_000073),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000074", nc_case_invariance_core_seed_000074),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000075", nc_case_invariance_core_seed_000075),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000076", nc_case_invariance_core_seed_000076),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000077", nc_case_invariance_core_seed_000077),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000078", nc_case_invariance_core_seed_000078),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000079", nc_case_invariance_core_seed_000079),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000080", nc_case_invariance_core_seed_000080),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000081", nc_case_invariance_core_seed_000081),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000082", nc_case_invariance_core_seed_000082),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000083", nc_case_invariance_core_seed_000083),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000084", nc_case_invariance_core_seed_000084),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000085", nc_case_invariance_core_seed_000085),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000086", nc_case_invariance_core_seed_000086),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000087", nc_case_invariance_core_seed_000087),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000088", nc_case_invariance_core_seed_000088),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000089", nc_case_invariance_core_seed_000089),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000090", nc_case_invariance_core_seed_000090),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000091", nc_case_invariance_core_seed_000091),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000092", nc_case_invariance_core_seed_000092),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000093", nc_case_invariance_core_seed_000093),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000094", nc_case_invariance_core_seed_000094),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000095", nc_case_invariance_core_seed_000095),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000096", nc_case_invariance_core_seed_000096),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000097", nc_case_invariance_core_seed_000097),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000098", nc_case_invariance_core_seed_000098),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000099", nc_case_invariance_core_seed_000099),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000100", nc_case_invariance_core_seed_000100),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000101", nc_case_invariance_core_seed_000101),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000102", nc_case_invariance_core_seed_000102),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000103", nc_case_invariance_core_seed_000103),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000104", nc_case_invariance_core_seed_000104),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000105", nc_case_invariance_core_seed_000105),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000106", nc_case_invariance_core_seed_000106),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000107", nc_case_invariance_core_seed_000107),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000108", nc_case_invariance_core_seed_000108),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000109", nc_case_invariance_core_seed_000109),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000110", nc_case_invariance_core_seed_000110),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000111", nc_case_invariance_core_seed_000111),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000112", nc_case_invariance_core_seed_000112),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000113", nc_case_invariance_core_seed_000113),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000114", nc_case_invariance_core_seed_000114),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000115", nc_case_invariance_core_seed_000115),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000116", nc_case_invariance_core_seed_000116),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000117", nc_case_invariance_core_seed_000117),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000118", nc_case_invariance_core_seed_000118),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000119", nc_case_invariance_core_seed_000119),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000120", nc_case_invariance_core_seed_000120),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000121", nc_case_invariance_core_seed_000121),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000122", nc_case_invariance_core_seed_000122),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000123", nc_case_invariance_core_seed_000123),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000124", nc_case_invariance_core_seed_000124),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000125", nc_case_invariance_core_seed_000125),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000126", nc_case_invariance_core_seed_000126),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000127", nc_case_invariance_core_seed_000127),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000128", nc_case_invariance_core_seed_000128),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000129", nc_case_invariance_core_seed_000129),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000130", nc_case_invariance_core_seed_000130),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000131", nc_case_invariance_core_seed_000131),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000132", nc_case_invariance_core_seed_000132),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000133", nc_case_invariance_core_seed_000133),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000134", nc_case_invariance_core_seed_000134),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000135", nc_case_invariance_core_seed_000135),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000136", nc_case_invariance_core_seed_000136),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000137", nc_case_invariance_core_seed_000137),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000138", nc_case_invariance_core_seed_000138),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000139", nc_case_invariance_core_seed_000139),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000140", nc_case_invariance_core_seed_000140),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000141", nc_case_invariance_core_seed_000141),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000142", nc_case_invariance_core_seed_000142),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000143", nc_case_invariance_core_seed_000143),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000144", nc_case_invariance_core_seed_000144),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000145", nc_case_invariance_core_seed_000145),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000146", nc_case_invariance_core_seed_000146),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000147", nc_case_invariance_core_seed_000147),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000148", nc_case_invariance_core_seed_000148),
        ("property_campaigns::tests::nc_case_invariance_core_seed_000149", nc_case_invariance_core_seed_000149),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000000", nc_case_invariance_v6_seed_000000),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000001", nc_case_invariance_v6_seed_000001),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000002", nc_case_invariance_v6_seed_000002),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000003", nc_case_invariance_v6_seed_000003),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000004", nc_case_invariance_v6_seed_000004),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000005", nc_case_invariance_v6_seed_000005),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000006", nc_case_invariance_v6_seed_000006),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000007", nc_case_invariance_v6_seed_000007),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000008", nc_case_invariance_v6_seed_000008),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000009", nc_case_invariance_v6_seed_000009),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000010", nc_case_invariance_v6_seed_000010),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000011", nc_case_invariance_v6_seed_000011),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000012", nc_case_invariance_v6_seed_000012),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000013", nc_case_invariance_v6_seed_000013),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000014", nc_case_invariance_v6_seed_000014),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000015", nc_case_invariance_v6_seed_000015),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000016", nc_case_invariance_v6_seed_000016),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000017", nc_case_invariance_v6_seed_000017),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000018", nc_case_invariance_v6_seed_000018),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000019", nc_case_invariance_v6_seed_000019),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000020", nc_case_invariance_v6_seed_000020),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000021", nc_case_invariance_v6_seed_000021),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000022", nc_case_invariance_v6_seed_000022),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000023", nc_case_invariance_v6_seed_000023),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000024", nc_case_invariance_v6_seed_000024),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000025", nc_case_invariance_v6_seed_000025),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000026", nc_case_invariance_v6_seed_000026),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000027", nc_case_invariance_v6_seed_000027),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000028", nc_case_invariance_v6_seed_000028),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000029", nc_case_invariance_v6_seed_000029),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000030", nc_case_invariance_v6_seed_000030),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000031", nc_case_invariance_v6_seed_000031),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000032", nc_case_invariance_v6_seed_000032),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000033", nc_case_invariance_v6_seed_000033),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000034", nc_case_invariance_v6_seed_000034),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000035", nc_case_invariance_v6_seed_000035),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000036", nc_case_invariance_v6_seed_000036),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000037", nc_case_invariance_v6_seed_000037),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000038", nc_case_invariance_v6_seed_000038),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000039", nc_case_invariance_v6_seed_000039),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000040", nc_case_invariance_v6_seed_000040),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000041", nc_case_invariance_v6_seed_000041),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000042", nc_case_invariance_v6_seed_000042),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000043", nc_case_invariance_v6_seed_000043),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000044", nc_case_invariance_v6_seed_000044),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000045", nc_case_invariance_v6_seed_000045),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000046", nc_case_invariance_v6_seed_000046),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000047", nc_case_invariance_v6_seed_000047),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000048", nc_case_invariance_v6_seed_000048),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000049", nc_case_invariance_v6_seed_000049),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000050", nc_case_invariance_v6_seed_000050),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000051", nc_case_invariance_v6_seed_000051),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000052", nc_case_invariance_v6_seed_000052),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000053", nc_case_invariance_v6_seed_000053),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000054", nc_case_invariance_v6_seed_000054),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000055", nc_case_invariance_v6_seed_000055),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000056", nc_case_invariance_v6_seed_000056),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000057", nc_case_invariance_v6_seed_000057),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000058", nc_case_invariance_v6_seed_000058),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000059", nc_case_invariance_v6_seed_000059),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000060", nc_case_invariance_v6_seed_000060),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000061", nc_case_invariance_v6_seed_000061),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000062", nc_case_invariance_v6_seed_000062),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000063", nc_case_invariance_v6_seed_000063),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000064", nc_case_invariance_v6_seed_000064),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000065", nc_case_invariance_v6_seed_000065),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000066", nc_case_invariance_v6_seed_000066),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000067", nc_case_invariance_v6_seed_000067),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000068", nc_case_invariance_v6_seed_000068),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000069", nc_case_invariance_v6_seed_000069),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000070", nc_case_invariance_v6_seed_000070),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000071", nc_case_invariance_v6_seed_000071),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000072", nc_case_invariance_v6_seed_000072),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000073", nc_case_invariance_v6_seed_000073),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000074", nc_case_invariance_v6_seed_000074),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000075", nc_case_invariance_v6_seed_000075),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000076", nc_case_invariance_v6_seed_000076),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000077", nc_case_invariance_v6_seed_000077),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000078", nc_case_invariance_v6_seed_000078),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000079", nc_case_invariance_v6_seed_000079),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000080", nc_case_invariance_v6_seed_000080),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000081", nc_case_invariance_v6_seed_000081),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000082", nc_case_invariance_v6_seed_000082),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000083", nc_case_invariance_v6_seed_000083),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000084", nc_case_invariance_v6_seed_000084),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000085", nc_case_invariance_v6_seed_000085),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000086", nc_case_invariance_v6_seed_000086),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000087", nc_case_invariance_v6_seed_000087),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000088", nc_case_invariance_v6_seed_000088),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000089", nc_case_invariance_v6_seed_000089),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000090", nc_case_invariance_v6_seed_000090),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000091", nc_case_invariance_v6_seed_000091),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000092", nc_case_invariance_v6_seed_000092),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000093", nc_case_invariance_v6_seed_000093),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000094", nc_case_invariance_v6_seed_000094),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000095", nc_case_invariance_v6_seed_000095),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000096", nc_case_invariance_v6_seed_000096),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000097", nc_case_invariance_v6_seed_000097),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000098", nc_case_invariance_v6_seed_000098),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000099", nc_case_invariance_v6_seed_000099),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000100", nc_case_invariance_v6_seed_000100),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000101", nc_case_invariance_v6_seed_000101),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000102", nc_case_invariance_v6_seed_000102),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000103", nc_case_invariance_v6_seed_000103),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000104", nc_case_invariance_v6_seed_000104),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000105", nc_case_invariance_v6_seed_000105),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000106", nc_case_invariance_v6_seed_000106),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000107", nc_case_invariance_v6_seed_000107),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000108", nc_case_invariance_v6_seed_000108),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000109", nc_case_invariance_v6_seed_000109),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000110", nc_case_invariance_v6_seed_000110),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000111", nc_case_invariance_v6_seed_000111),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000112", nc_case_invariance_v6_seed_000112),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000113", nc_case_invariance_v6_seed_000113),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000114", nc_case_invariance_v6_seed_000114),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000115", nc_case_invariance_v6_seed_000115),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000116", nc_case_invariance_v6_seed_000116),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000117", nc_case_invariance_v6_seed_000117),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000118", nc_case_invariance_v6_seed_000118),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000119", nc_case_invariance_v6_seed_000119),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000120", nc_case_invariance_v6_seed_000120),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000121", nc_case_invariance_v6_seed_000121),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000122", nc_case_invariance_v6_seed_000122),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000123", nc_case_invariance_v6_seed_000123),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000124", nc_case_invariance_v6_seed_000124),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000125", nc_case_invariance_v6_seed_000125),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000126", nc_case_invariance_v6_seed_000126),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000127", nc_case_invariance_v6_seed_000127),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000128", nc_case_invariance_v6_seed_000128),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000129", nc_case_invariance_v6_seed_000129),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000130", nc_case_invariance_v6_seed_000130),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000131", nc_case_invariance_v6_seed_000131),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000132", nc_case_invariance_v6_seed_000132),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000133", nc_case_invariance_v6_seed_000133),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000134", nc_case_invariance_v6_seed_000134),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000135", nc_case_invariance_v6_seed_000135),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000136", nc_case_invariance_v6_seed_000136),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000137", nc_case_invariance_v6_seed_000137),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000138", nc_case_invariance_v6_seed_000138),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000139", nc_case_invariance_v6_seed_000139),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000140", nc_case_invariance_v6_seed_000140),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000141", nc_case_invariance_v6_seed_000141),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000142", nc_case_invariance_v6_seed_000142),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000143", nc_case_invariance_v6_seed_000143),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000144", nc_case_invariance_v6_seed_000144),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000145", nc_case_invariance_v6_seed_000145),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000146", nc_case_invariance_v6_seed_000146),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000147", nc_case_invariance_v6_seed_000147),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000148", nc_case_invariance_v6_seed_000148),
        ("property_campaigns::tests::nc_case_invariance_v6_seed_000149", nc_case_invariance_v6_seed_000149),
        ("property_campaigns::tests::adj_symmetry_seed_000000", adj_symmetry_seed_000000),
        ("property_campaigns::tests::adj_symmetry_seed_000001", adj_symmetry_seed_000001),
        ("property_campaigns::tests::adj_symmetry_seed_000002", adj_symmetry_seed_000002),
        ("property_campaigns::tests::adj_symmetry_seed_000003", adj_symmetry_seed_000003),
        ("property_campaigns::tests::adj_symmetry_seed_000004", adj_symmetry_seed_000004),
        ("property_campaigns::tests::adj_symmetry_seed_000005", adj_symmetry_seed_000005),
        ("property_campaigns::tests::adj_symmetry_seed_000006", adj_symmetry_seed_000006),
        ("property_campaigns::tests::adj_symmetry_seed_000007", adj_symmetry_seed_000007),
        ("property_campaigns::tests::adj_symmetry_seed_000008", adj_symmetry_seed_000008),
        ("property_campaigns::tests::adj_symmetry_seed_000009", adj_symmetry_seed_000009),
        ("property_campaigns::tests::adj_symmetry_seed_000010", adj_symmetry_seed_000010),
        ("property_campaigns::tests::adj_symmetry_seed_000011", adj_symmetry_seed_000011),
        ("property_campaigns::tests::adj_symmetry_seed_000012", adj_symmetry_seed_000012),
        ("property_campaigns::tests::adj_symmetry_seed_000013", adj_symmetry_seed_000013),
        ("property_campaigns::tests::adj_symmetry_seed_000014", adj_symmetry_seed_000014),
        ("property_campaigns::tests::adj_symmetry_seed_000015", adj_symmetry_seed_000015),
        ("property_campaigns::tests::adj_symmetry_seed_000016", adj_symmetry_seed_000016),
        ("property_campaigns::tests::adj_symmetry_seed_000017", adj_symmetry_seed_000017),
        ("property_campaigns::tests::adj_symmetry_seed_000018", adj_symmetry_seed_000018),
        ("property_campaigns::tests::adj_symmetry_seed_000019", adj_symmetry_seed_000019),
        ("property_campaigns::tests::adj_symmetry_seed_000020", adj_symmetry_seed_000020),
        ("property_campaigns::tests::adj_symmetry_seed_000021", adj_symmetry_seed_000021),
        ("property_campaigns::tests::adj_symmetry_seed_000022", adj_symmetry_seed_000022),
        ("property_campaigns::tests::adj_symmetry_seed_000023", adj_symmetry_seed_000023),
        ("property_campaigns::tests::adj_symmetry_seed_000024", adj_symmetry_seed_000024),
        ("property_campaigns::tests::adj_symmetry_seed_000025", adj_symmetry_seed_000025),
        ("property_campaigns::tests::adj_symmetry_seed_000026", adj_symmetry_seed_000026),
        ("property_campaigns::tests::adj_symmetry_seed_000027", adj_symmetry_seed_000027),
        ("property_campaigns::tests::adj_symmetry_seed_000028", adj_symmetry_seed_000028),
        ("property_campaigns::tests::adj_symmetry_seed_000029", adj_symmetry_seed_000029),
        ("property_campaigns::tests::adj_symmetry_seed_000030", adj_symmetry_seed_000030),
        ("property_campaigns::tests::adj_symmetry_seed_000031", adj_symmetry_seed_000031),
        ("property_campaigns::tests::adj_symmetry_seed_000032", adj_symmetry_seed_000032),
        ("property_campaigns::tests::adj_symmetry_seed_000033", adj_symmetry_seed_000033),
        ("property_campaigns::tests::adj_symmetry_seed_000034", adj_symmetry_seed_000034),
        ("property_campaigns::tests::adj_symmetry_seed_000035", adj_symmetry_seed_000035),
        ("property_campaigns::tests::adj_symmetry_seed_000036", adj_symmetry_seed_000036),
        ("property_campaigns::tests::adj_symmetry_seed_000037", adj_symmetry_seed_000037),
        ("property_campaigns::tests::adj_symmetry_seed_000038", adj_symmetry_seed_000038),
        ("property_campaigns::tests::adj_symmetry_seed_000039", adj_symmetry_seed_000039),
        ("property_campaigns::tests::adj_symmetry_seed_000040", adj_symmetry_seed_000040),
        ("property_campaigns::tests::adj_symmetry_seed_000041", adj_symmetry_seed_000041),
        ("property_campaigns::tests::adj_symmetry_seed_000042", adj_symmetry_seed_000042),
        ("property_campaigns::tests::adj_symmetry_seed_000043", adj_symmetry_seed_000043),
        ("property_campaigns::tests::adj_symmetry_seed_000044", adj_symmetry_seed_000044),
        ("property_campaigns::tests::adj_symmetry_seed_000045", adj_symmetry_seed_000045),
        ("property_campaigns::tests::adj_symmetry_seed_000046", adj_symmetry_seed_000046),
        ("property_campaigns::tests::adj_symmetry_seed_000047", adj_symmetry_seed_000047),
        ("property_campaigns::tests::adj_symmetry_seed_000048", adj_symmetry_seed_000048),
        ("property_campaigns::tests::adj_symmetry_seed_000049", adj_symmetry_seed_000049),
        ("property_campaigns::tests::adj_symmetry_seed_000050", adj_symmetry_seed_000050),
        ("property_campaigns::tests::adj_symmetry_seed_000051", adj_symmetry_seed_000051),
        ("property_campaigns::tests::adj_symmetry_seed_000052", adj_symmetry_seed_000052),
        ("property_campaigns::tests::adj_symmetry_seed_000053", adj_symmetry_seed_000053),
        ("property_campaigns::tests::adj_symmetry_seed_000054", adj_symmetry_seed_000054),
        ("property_campaigns::tests::adj_symmetry_seed_000055", adj_symmetry_seed_000055),
        ("property_campaigns::tests::adj_symmetry_seed_000056", adj_symmetry_seed_000056),
        ("property_campaigns::tests::adj_symmetry_seed_000057", adj_symmetry_seed_000057),
        ("property_campaigns::tests::adj_symmetry_seed_000058", adj_symmetry_seed_000058),
        ("property_campaigns::tests::adj_symmetry_seed_000059", adj_symmetry_seed_000059),
        ("property_campaigns::tests::adj_symmetry_seed_000060", adj_symmetry_seed_000060),
        ("property_campaigns::tests::adj_symmetry_seed_000061", adj_symmetry_seed_000061),
        ("property_campaigns::tests::adj_symmetry_seed_000062", adj_symmetry_seed_000062),
        ("property_campaigns::tests::adj_symmetry_seed_000063", adj_symmetry_seed_000063),
        ("property_campaigns::tests::adj_symmetry_seed_000064", adj_symmetry_seed_000064),
        ("property_campaigns::tests::adj_symmetry_seed_000065", adj_symmetry_seed_000065),
        ("property_campaigns::tests::adj_symmetry_seed_000066", adj_symmetry_seed_000066),
        ("property_campaigns::tests::adj_symmetry_seed_000067", adj_symmetry_seed_000067),
        ("property_campaigns::tests::adj_symmetry_seed_000068", adj_symmetry_seed_000068),
        ("property_campaigns::tests::adj_symmetry_seed_000069", adj_symmetry_seed_000069),
        ("property_campaigns::tests::adj_symmetry_seed_000070", adj_symmetry_seed_000070),
        ("property_campaigns::tests::adj_symmetry_seed_000071", adj_symmetry_seed_000071),
        ("property_campaigns::tests::adj_symmetry_seed_000072", adj_symmetry_seed_000072),
        ("property_campaigns::tests::adj_symmetry_seed_000073", adj_symmetry_seed_000073),
        ("property_campaigns::tests::adj_symmetry_seed_000074", adj_symmetry_seed_000074),
        ("property_campaigns::tests::adj_symmetry_seed_000075", adj_symmetry_seed_000075),
        ("property_campaigns::tests::adj_symmetry_seed_000076", adj_symmetry_seed_000076),
        ("property_campaigns::tests::adj_symmetry_seed_000077", adj_symmetry_seed_000077),
        ("property_campaigns::tests::adj_symmetry_seed_000078", adj_symmetry_seed_000078),
        ("property_campaigns::tests::adj_symmetry_seed_000079", adj_symmetry_seed_000079),
        ("property_campaigns::tests::adj_symmetry_seed_000080", adj_symmetry_seed_000080),
        ("property_campaigns::tests::adj_symmetry_seed_000081", adj_symmetry_seed_000081),
        ("property_campaigns::tests::adj_symmetry_seed_000082", adj_symmetry_seed_000082),
        ("property_campaigns::tests::adj_symmetry_seed_000083", adj_symmetry_seed_000083),
        ("property_campaigns::tests::adj_symmetry_seed_000084", adj_symmetry_seed_000084),
        ("property_campaigns::tests::adj_symmetry_seed_000085", adj_symmetry_seed_000085),
        ("property_campaigns::tests::adj_symmetry_seed_000086", adj_symmetry_seed_000086),
        ("property_campaigns::tests::adj_symmetry_seed_000087", adj_symmetry_seed_000087),
        ("property_campaigns::tests::adj_symmetry_seed_000088", adj_symmetry_seed_000088),
        ("property_campaigns::tests::adj_symmetry_seed_000089", adj_symmetry_seed_000089),
        ("property_campaigns::tests::adj_symmetry_seed_000090", adj_symmetry_seed_000090),
        ("property_campaigns::tests::adj_symmetry_seed_000091", adj_symmetry_seed_000091),
        ("property_campaigns::tests::adj_symmetry_seed_000092", adj_symmetry_seed_000092),
        ("property_campaigns::tests::adj_symmetry_seed_000093", adj_symmetry_seed_000093),
        ("property_campaigns::tests::adj_symmetry_seed_000094", adj_symmetry_seed_000094),
        ("property_campaigns::tests::adj_symmetry_seed_000095", adj_symmetry_seed_000095),
        ("property_campaigns::tests::adj_symmetry_seed_000096", adj_symmetry_seed_000096),
        ("property_campaigns::tests::adj_symmetry_seed_000097", adj_symmetry_seed_000097),
        ("property_campaigns::tests::adj_symmetry_seed_000098", adj_symmetry_seed_000098),
        ("property_campaigns::tests::adj_symmetry_seed_000099", adj_symmetry_seed_000099),
        ("property_campaigns::tests::adj_symmetry_seed_000100", adj_symmetry_seed_000100),
        ("property_campaigns::tests::adj_symmetry_seed_000101", adj_symmetry_seed_000101),
        ("property_campaigns::tests::adj_symmetry_seed_000102", adj_symmetry_seed_000102),
        ("property_campaigns::tests::adj_symmetry_seed_000103", adj_symmetry_seed_000103),
        ("property_campaigns::tests::adj_symmetry_seed_000104", adj_symmetry_seed_000104),
        ("property_campaigns::tests::adj_symmetry_seed_000105", adj_symmetry_seed_000105),
        ("property_campaigns::tests::adj_symmetry_seed_000106", adj_symmetry_seed_000106),
        ("property_campaigns::tests::adj_symmetry_seed_000107", adj_symmetry_seed_000107),
        ("property_campaigns::tests::adj_symmetry_seed_000108", adj_symmetry_seed_000108),
        ("property_campaigns::tests::adj_symmetry_seed_000109", adj_symmetry_seed_000109),
        ("property_campaigns::tests::adj_symmetry_seed_000110", adj_symmetry_seed_000110),
        ("property_campaigns::tests::adj_symmetry_seed_000111", adj_symmetry_seed_000111),
        ("property_campaigns::tests::adj_symmetry_seed_000112", adj_symmetry_seed_000112),
        ("property_campaigns::tests::adj_symmetry_seed_000113", adj_symmetry_seed_000113),
        ("property_campaigns::tests::adj_symmetry_seed_000114", adj_symmetry_seed_000114),
        ("property_campaigns::tests::adj_symmetry_seed_000115", adj_symmetry_seed_000115),
        ("property_campaigns::tests::adj_symmetry_seed_000116", adj_symmetry_seed_000116),
        ("property_campaigns::tests::adj_symmetry_seed_000117", adj_symmetry_seed_000117),
        ("property_campaigns::tests::adj_symmetry_seed_000118", adj_symmetry_seed_000118),
        ("property_campaigns::tests::adj_symmetry_seed_000119", adj_symmetry_seed_000119),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000000", adj_diagonal_zero_seed_000000),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000001", adj_diagonal_zero_seed_000001),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000002", adj_diagonal_zero_seed_000002),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000003", adj_diagonal_zero_seed_000003),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000004", adj_diagonal_zero_seed_000004),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000005", adj_diagonal_zero_seed_000005),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000006", adj_diagonal_zero_seed_000006),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000007", adj_diagonal_zero_seed_000007),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000008", adj_diagonal_zero_seed_000008),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000009", adj_diagonal_zero_seed_000009),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000010", adj_diagonal_zero_seed_000010),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000011", adj_diagonal_zero_seed_000011),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000012", adj_diagonal_zero_seed_000012),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000013", adj_diagonal_zero_seed_000013),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000014", adj_diagonal_zero_seed_000014),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000015", adj_diagonal_zero_seed_000015),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000016", adj_diagonal_zero_seed_000016),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000017", adj_diagonal_zero_seed_000017),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000018", adj_diagonal_zero_seed_000018),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000019", adj_diagonal_zero_seed_000019),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000020", adj_diagonal_zero_seed_000020),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000021", adj_diagonal_zero_seed_000021),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000022", adj_diagonal_zero_seed_000022),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000023", adj_diagonal_zero_seed_000023),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000024", adj_diagonal_zero_seed_000024),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000025", adj_diagonal_zero_seed_000025),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000026", adj_diagonal_zero_seed_000026),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000027", adj_diagonal_zero_seed_000027),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000028", adj_diagonal_zero_seed_000028),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000029", adj_diagonal_zero_seed_000029),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000030", adj_diagonal_zero_seed_000030),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000031", adj_diagonal_zero_seed_000031),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000032", adj_diagonal_zero_seed_000032),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000033", adj_diagonal_zero_seed_000033),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000034", adj_diagonal_zero_seed_000034),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000035", adj_diagonal_zero_seed_000035),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000036", adj_diagonal_zero_seed_000036),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000037", adj_diagonal_zero_seed_000037),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000038", adj_diagonal_zero_seed_000038),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000039", adj_diagonal_zero_seed_000039),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000040", adj_diagonal_zero_seed_000040),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000041", adj_diagonal_zero_seed_000041),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000042", adj_diagonal_zero_seed_000042),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000043", adj_diagonal_zero_seed_000043),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000044", adj_diagonal_zero_seed_000044),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000045", adj_diagonal_zero_seed_000045),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000046", adj_diagonal_zero_seed_000046),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000047", adj_diagonal_zero_seed_000047),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000048", adj_diagonal_zero_seed_000048),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000049", adj_diagonal_zero_seed_000049),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000050", adj_diagonal_zero_seed_000050),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000051", adj_diagonal_zero_seed_000051),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000052", adj_diagonal_zero_seed_000052),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000053", adj_diagonal_zero_seed_000053),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000054", adj_diagonal_zero_seed_000054),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000055", adj_diagonal_zero_seed_000055),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000056", adj_diagonal_zero_seed_000056),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000057", adj_diagonal_zero_seed_000057),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000058", adj_diagonal_zero_seed_000058),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000059", adj_diagonal_zero_seed_000059),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000060", adj_diagonal_zero_seed_000060),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000061", adj_diagonal_zero_seed_000061),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000062", adj_diagonal_zero_seed_000062),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000063", adj_diagonal_zero_seed_000063),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000064", adj_diagonal_zero_seed_000064),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000065", adj_diagonal_zero_seed_000065),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000066", adj_diagonal_zero_seed_000066),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000067", adj_diagonal_zero_seed_000067),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000068", adj_diagonal_zero_seed_000068),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000069", adj_diagonal_zero_seed_000069),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000070", adj_diagonal_zero_seed_000070),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000071", adj_diagonal_zero_seed_000071),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000072", adj_diagonal_zero_seed_000072),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000073", adj_diagonal_zero_seed_000073),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000074", adj_diagonal_zero_seed_000074),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000075", adj_diagonal_zero_seed_000075),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000076", adj_diagonal_zero_seed_000076),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000077", adj_diagonal_zero_seed_000077),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000078", adj_diagonal_zero_seed_000078),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000079", adj_diagonal_zero_seed_000079),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000080", adj_diagonal_zero_seed_000080),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000081", adj_diagonal_zero_seed_000081),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000082", adj_diagonal_zero_seed_000082),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000083", adj_diagonal_zero_seed_000083),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000084", adj_diagonal_zero_seed_000084),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000085", adj_diagonal_zero_seed_000085),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000086", adj_diagonal_zero_seed_000086),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000087", adj_diagonal_zero_seed_000087),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000088", adj_diagonal_zero_seed_000088),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000089", adj_diagonal_zero_seed_000089),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000090", adj_diagonal_zero_seed_000090),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000091", adj_diagonal_zero_seed_000091),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000092", adj_diagonal_zero_seed_000092),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000093", adj_diagonal_zero_seed_000093),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000094", adj_diagonal_zero_seed_000094),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000095", adj_diagonal_zero_seed_000095),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000096", adj_diagonal_zero_seed_000096),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000097", adj_diagonal_zero_seed_000097),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000098", adj_diagonal_zero_seed_000098),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000099", adj_diagonal_zero_seed_000099),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000100", adj_diagonal_zero_seed_000100),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000101", adj_diagonal_zero_seed_000101),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000102", adj_diagonal_zero_seed_000102),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000103", adj_diagonal_zero_seed_000103),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000104", adj_diagonal_zero_seed_000104),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000105", adj_diagonal_zero_seed_000105),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000106", adj_diagonal_zero_seed_000106),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000107", adj_diagonal_zero_seed_000107),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000108", adj_diagonal_zero_seed_000108),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000109", adj_diagonal_zero_seed_000109),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000110", adj_diagonal_zero_seed_000110),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000111", adj_diagonal_zero_seed_000111),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000112", adj_diagonal_zero_seed_000112),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000113", adj_diagonal_zero_seed_000113),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000114", adj_diagonal_zero_seed_000114),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000115", adj_diagonal_zero_seed_000115),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000116", adj_diagonal_zero_seed_000116),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000117", adj_diagonal_zero_seed_000117),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000118", adj_diagonal_zero_seed_000118),
        ("property_campaigns::tests::adj_diagonal_zero_seed_000119", adj_diagonal_zero_seed_000119),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000000", adj_pin_order_invariance_seed_000000),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000001", adj_pin_order_invariance_seed_000001),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000002", adj_pin_order_invariance_seed_000002),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000003", adj_pin_order_invariance_seed_000003),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000004", adj_pin_order_invariance_seed_000004),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000005", adj_pin_order_invariance_seed_000005),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000006", adj_pin_order_invariance_seed_000006),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000007", adj_pin_order_invariance_seed_000007),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000008", adj_pin_order_invariance_seed_000008),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000009", adj_pin_order_invariance_seed_000009),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000010", adj_pin_order_invariance_seed_000010),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000011", adj_pin_order_invariance_seed_000011),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000012", adj_pin_order_invariance_seed_000012),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000013", adj_pin_order_invariance_seed_000013),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000014", adj_pin_order_invariance_seed_000014),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000015", adj_pin_order_invariance_seed_000015),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000016", adj_pin_order_invariance_seed_000016),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000017", adj_pin_order_invariance_seed_000017),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000018", adj_pin_order_invariance_seed_000018),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000019", adj_pin_order_invariance_seed_000019),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000020", adj_pin_order_invariance_seed_000020),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000021", adj_pin_order_invariance_seed_000021),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000022", adj_pin_order_invariance_seed_000022),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000023", adj_pin_order_invariance_seed_000023),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000024", adj_pin_order_invariance_seed_000024),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000025", adj_pin_order_invariance_seed_000025),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000026", adj_pin_order_invariance_seed_000026),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000027", adj_pin_order_invariance_seed_000027),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000028", adj_pin_order_invariance_seed_000028),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000029", adj_pin_order_invariance_seed_000029),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000030", adj_pin_order_invariance_seed_000030),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000031", adj_pin_order_invariance_seed_000031),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000032", adj_pin_order_invariance_seed_000032),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000033", adj_pin_order_invariance_seed_000033),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000034", adj_pin_order_invariance_seed_000034),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000035", adj_pin_order_invariance_seed_000035),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000036", adj_pin_order_invariance_seed_000036),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000037", adj_pin_order_invariance_seed_000037),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000038", adj_pin_order_invariance_seed_000038),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000039", adj_pin_order_invariance_seed_000039),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000040", adj_pin_order_invariance_seed_000040),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000041", adj_pin_order_invariance_seed_000041),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000042", adj_pin_order_invariance_seed_000042),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000043", adj_pin_order_invariance_seed_000043),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000044", adj_pin_order_invariance_seed_000044),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000045", adj_pin_order_invariance_seed_000045),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000046", adj_pin_order_invariance_seed_000046),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000047", adj_pin_order_invariance_seed_000047),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000048", adj_pin_order_invariance_seed_000048),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000049", adj_pin_order_invariance_seed_000049),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000050", adj_pin_order_invariance_seed_000050),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000051", adj_pin_order_invariance_seed_000051),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000052", adj_pin_order_invariance_seed_000052),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000053", adj_pin_order_invariance_seed_000053),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000054", adj_pin_order_invariance_seed_000054),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000055", adj_pin_order_invariance_seed_000055),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000056", adj_pin_order_invariance_seed_000056),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000057", adj_pin_order_invariance_seed_000057),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000058", adj_pin_order_invariance_seed_000058),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000059", adj_pin_order_invariance_seed_000059),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000060", adj_pin_order_invariance_seed_000060),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000061", adj_pin_order_invariance_seed_000061),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000062", adj_pin_order_invariance_seed_000062),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000063", adj_pin_order_invariance_seed_000063),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000064", adj_pin_order_invariance_seed_000064),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000065", adj_pin_order_invariance_seed_000065),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000066", adj_pin_order_invariance_seed_000066),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000067", adj_pin_order_invariance_seed_000067),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000068", adj_pin_order_invariance_seed_000068),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000069", adj_pin_order_invariance_seed_000069),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000070", adj_pin_order_invariance_seed_000070),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000071", adj_pin_order_invariance_seed_000071),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000072", adj_pin_order_invariance_seed_000072),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000073", adj_pin_order_invariance_seed_000073),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000074", adj_pin_order_invariance_seed_000074),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000075", adj_pin_order_invariance_seed_000075),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000076", adj_pin_order_invariance_seed_000076),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000077", adj_pin_order_invariance_seed_000077),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000078", adj_pin_order_invariance_seed_000078),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000079", adj_pin_order_invariance_seed_000079),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000080", adj_pin_order_invariance_seed_000080),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000081", adj_pin_order_invariance_seed_000081),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000082", adj_pin_order_invariance_seed_000082),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000083", adj_pin_order_invariance_seed_000083),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000084", adj_pin_order_invariance_seed_000084),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000085", adj_pin_order_invariance_seed_000085),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000086", adj_pin_order_invariance_seed_000086),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000087", adj_pin_order_invariance_seed_000087),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000088", adj_pin_order_invariance_seed_000088),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000089", adj_pin_order_invariance_seed_000089),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000090", adj_pin_order_invariance_seed_000090),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000091", adj_pin_order_invariance_seed_000091),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000092", adj_pin_order_invariance_seed_000092),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000093", adj_pin_order_invariance_seed_000093),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000094", adj_pin_order_invariance_seed_000094),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000095", adj_pin_order_invariance_seed_000095),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000096", adj_pin_order_invariance_seed_000096),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000097", adj_pin_order_invariance_seed_000097),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000098", adj_pin_order_invariance_seed_000098),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000099", adj_pin_order_invariance_seed_000099),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000100", adj_pin_order_invariance_seed_000100),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000101", adj_pin_order_invariance_seed_000101),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000102", adj_pin_order_invariance_seed_000102),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000103", adj_pin_order_invariance_seed_000103),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000104", adj_pin_order_invariance_seed_000104),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000105", adj_pin_order_invariance_seed_000105),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000106", adj_pin_order_invariance_seed_000106),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000107", adj_pin_order_invariance_seed_000107),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000108", adj_pin_order_invariance_seed_000108),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000109", adj_pin_order_invariance_seed_000109),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000110", adj_pin_order_invariance_seed_000110),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000111", adj_pin_order_invariance_seed_000111),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000112", adj_pin_order_invariance_seed_000112),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000113", adj_pin_order_invariance_seed_000113),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000114", adj_pin_order_invariance_seed_000114),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000115", adj_pin_order_invariance_seed_000115),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000116", adj_pin_order_invariance_seed_000116),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000117", adj_pin_order_invariance_seed_000117),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000118", adj_pin_order_invariance_seed_000118),
        ("property_campaigns::tests::adj_pin_order_invariance_seed_000119", adj_pin_order_invariance_seed_000119),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000000", adj_relabeling_invariance_seed_000000),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000001", adj_relabeling_invariance_seed_000001),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000002", adj_relabeling_invariance_seed_000002),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000003", adj_relabeling_invariance_seed_000003),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000004", adj_relabeling_invariance_seed_000004),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000005", adj_relabeling_invariance_seed_000005),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000006", adj_relabeling_invariance_seed_000006),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000007", adj_relabeling_invariance_seed_000007),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000008", adj_relabeling_invariance_seed_000008),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000009", adj_relabeling_invariance_seed_000009),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000010", adj_relabeling_invariance_seed_000010),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000011", adj_relabeling_invariance_seed_000011),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000012", adj_relabeling_invariance_seed_000012),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000013", adj_relabeling_invariance_seed_000013),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000014", adj_relabeling_invariance_seed_000014),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000015", adj_relabeling_invariance_seed_000015),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000016", adj_relabeling_invariance_seed_000016),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000017", adj_relabeling_invariance_seed_000017),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000018", adj_relabeling_invariance_seed_000018),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000019", adj_relabeling_invariance_seed_000019),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000020", adj_relabeling_invariance_seed_000020),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000021", adj_relabeling_invariance_seed_000021),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000022", adj_relabeling_invariance_seed_000022),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000023", adj_relabeling_invariance_seed_000023),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000024", adj_relabeling_invariance_seed_000024),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000025", adj_relabeling_invariance_seed_000025),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000026", adj_relabeling_invariance_seed_000026),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000027", adj_relabeling_invariance_seed_000027),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000028", adj_relabeling_invariance_seed_000028),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000029", adj_relabeling_invariance_seed_000029),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000030", adj_relabeling_invariance_seed_000030),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000031", adj_relabeling_invariance_seed_000031),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000032", adj_relabeling_invariance_seed_000032),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000033", adj_relabeling_invariance_seed_000033),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000034", adj_relabeling_invariance_seed_000034),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000035", adj_relabeling_invariance_seed_000035),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000036", adj_relabeling_invariance_seed_000036),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000037", adj_relabeling_invariance_seed_000037),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000038", adj_relabeling_invariance_seed_000038),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000039", adj_relabeling_invariance_seed_000039),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000040", adj_relabeling_invariance_seed_000040),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000041", adj_relabeling_invariance_seed_000041),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000042", adj_relabeling_invariance_seed_000042),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000043", adj_relabeling_invariance_seed_000043),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000044", adj_relabeling_invariance_seed_000044),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000045", adj_relabeling_invariance_seed_000045),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000046", adj_relabeling_invariance_seed_000046),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000047", adj_relabeling_invariance_seed_000047),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000048", adj_relabeling_invariance_seed_000048),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000049", adj_relabeling_invariance_seed_000049),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000050", adj_relabeling_invariance_seed_000050),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000051", adj_relabeling_invariance_seed_000051),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000052", adj_relabeling_invariance_seed_000052),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000053", adj_relabeling_invariance_seed_000053),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000054", adj_relabeling_invariance_seed_000054),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000055", adj_relabeling_invariance_seed_000055),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000056", adj_relabeling_invariance_seed_000056),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000057", adj_relabeling_invariance_seed_000057),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000058", adj_relabeling_invariance_seed_000058),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000059", adj_relabeling_invariance_seed_000059),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000060", adj_relabeling_invariance_seed_000060),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000061", adj_relabeling_invariance_seed_000061),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000062", adj_relabeling_invariance_seed_000062),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000063", adj_relabeling_invariance_seed_000063),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000064", adj_relabeling_invariance_seed_000064),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000065", adj_relabeling_invariance_seed_000065),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000066", adj_relabeling_invariance_seed_000066),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000067", adj_relabeling_invariance_seed_000067),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000068", adj_relabeling_invariance_seed_000068),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000069", adj_relabeling_invariance_seed_000069),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000070", adj_relabeling_invariance_seed_000070),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000071", adj_relabeling_invariance_seed_000071),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000072", adj_relabeling_invariance_seed_000072),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000073", adj_relabeling_invariance_seed_000073),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000074", adj_relabeling_invariance_seed_000074),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000075", adj_relabeling_invariance_seed_000075),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000076", adj_relabeling_invariance_seed_000076),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000077", adj_relabeling_invariance_seed_000077),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000078", adj_relabeling_invariance_seed_000078),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000079", adj_relabeling_invariance_seed_000079),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000080", adj_relabeling_invariance_seed_000080),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000081", adj_relabeling_invariance_seed_000081),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000082", adj_relabeling_invariance_seed_000082),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000083", adj_relabeling_invariance_seed_000083),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000084", adj_relabeling_invariance_seed_000084),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000085", adj_relabeling_invariance_seed_000085),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000086", adj_relabeling_invariance_seed_000086),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000087", adj_relabeling_invariance_seed_000087),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000088", adj_relabeling_invariance_seed_000088),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000089", adj_relabeling_invariance_seed_000089),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000090", adj_relabeling_invariance_seed_000090),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000091", adj_relabeling_invariance_seed_000091),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000092", adj_relabeling_invariance_seed_000092),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000093", adj_relabeling_invariance_seed_000093),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000094", adj_relabeling_invariance_seed_000094),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000095", adj_relabeling_invariance_seed_000095),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000096", adj_relabeling_invariance_seed_000096),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000097", adj_relabeling_invariance_seed_000097),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000098", adj_relabeling_invariance_seed_000098),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000099", adj_relabeling_invariance_seed_000099),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000100", adj_relabeling_invariance_seed_000100),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000101", adj_relabeling_invariance_seed_000101),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000102", adj_relabeling_invariance_seed_000102),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000103", adj_relabeling_invariance_seed_000103),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000104", adj_relabeling_invariance_seed_000104),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000105", adj_relabeling_invariance_seed_000105),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000106", adj_relabeling_invariance_seed_000106),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000107", adj_relabeling_invariance_seed_000107),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000108", adj_relabeling_invariance_seed_000108),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000109", adj_relabeling_invariance_seed_000109),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000110", adj_relabeling_invariance_seed_000110),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000111", adj_relabeling_invariance_seed_000111),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000112", adj_relabeling_invariance_seed_000112),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000113", adj_relabeling_invariance_seed_000113),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000114", adj_relabeling_invariance_seed_000114),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000115", adj_relabeling_invariance_seed_000115),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000116", adj_relabeling_invariance_seed_000116),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000117", adj_relabeling_invariance_seed_000117),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000118", adj_relabeling_invariance_seed_000118),
        ("property_campaigns::tests::adj_relabeling_invariance_seed_000119", adj_relabeling_invariance_seed_000119),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000000", pyrepr_round_trip_seed_000000),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000001", pyrepr_round_trip_seed_000001),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000002", pyrepr_round_trip_seed_000002),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000003", pyrepr_round_trip_seed_000003),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000004", pyrepr_round_trip_seed_000004),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000005", pyrepr_round_trip_seed_000005),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000006", pyrepr_round_trip_seed_000006),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000007", pyrepr_round_trip_seed_000007),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000008", pyrepr_round_trip_seed_000008),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000009", pyrepr_round_trip_seed_000009),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000010", pyrepr_round_trip_seed_000010),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000011", pyrepr_round_trip_seed_000011),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000012", pyrepr_round_trip_seed_000012),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000013", pyrepr_round_trip_seed_000013),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000014", pyrepr_round_trip_seed_000014),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000015", pyrepr_round_trip_seed_000015),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000016", pyrepr_round_trip_seed_000016),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000017", pyrepr_round_trip_seed_000017),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000018", pyrepr_round_trip_seed_000018),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000019", pyrepr_round_trip_seed_000019),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000020", pyrepr_round_trip_seed_000020),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000021", pyrepr_round_trip_seed_000021),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000022", pyrepr_round_trip_seed_000022),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000023", pyrepr_round_trip_seed_000023),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000024", pyrepr_round_trip_seed_000024),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000025", pyrepr_round_trip_seed_000025),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000026", pyrepr_round_trip_seed_000026),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000027", pyrepr_round_trip_seed_000027),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000028", pyrepr_round_trip_seed_000028),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000029", pyrepr_round_trip_seed_000029),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000030", pyrepr_round_trip_seed_000030),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000031", pyrepr_round_trip_seed_000031),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000032", pyrepr_round_trip_seed_000032),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000033", pyrepr_round_trip_seed_000033),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000034", pyrepr_round_trip_seed_000034),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000035", pyrepr_round_trip_seed_000035),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000036", pyrepr_round_trip_seed_000036),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000037", pyrepr_round_trip_seed_000037),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000038", pyrepr_round_trip_seed_000038),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000039", pyrepr_round_trip_seed_000039),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000040", pyrepr_round_trip_seed_000040),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000041", pyrepr_round_trip_seed_000041),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000042", pyrepr_round_trip_seed_000042),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000043", pyrepr_round_trip_seed_000043),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000044", pyrepr_round_trip_seed_000044),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000045", pyrepr_round_trip_seed_000045),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000046", pyrepr_round_trip_seed_000046),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000047", pyrepr_round_trip_seed_000047),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000048", pyrepr_round_trip_seed_000048),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000049", pyrepr_round_trip_seed_000049),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000050", pyrepr_round_trip_seed_000050),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000051", pyrepr_round_trip_seed_000051),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000052", pyrepr_round_trip_seed_000052),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000053", pyrepr_round_trip_seed_000053),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000054", pyrepr_round_trip_seed_000054),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000055", pyrepr_round_trip_seed_000055),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000056", pyrepr_round_trip_seed_000056),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000057", pyrepr_round_trip_seed_000057),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000058", pyrepr_round_trip_seed_000058),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000059", pyrepr_round_trip_seed_000059),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000060", pyrepr_round_trip_seed_000060),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000061", pyrepr_round_trip_seed_000061),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000062", pyrepr_round_trip_seed_000062),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000063", pyrepr_round_trip_seed_000063),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000064", pyrepr_round_trip_seed_000064),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000065", pyrepr_round_trip_seed_000065),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000066", pyrepr_round_trip_seed_000066),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000067", pyrepr_round_trip_seed_000067),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000068", pyrepr_round_trip_seed_000068),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000069", pyrepr_round_trip_seed_000069),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000070", pyrepr_round_trip_seed_000070),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000071", pyrepr_round_trip_seed_000071),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000072", pyrepr_round_trip_seed_000072),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000073", pyrepr_round_trip_seed_000073),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000074", pyrepr_round_trip_seed_000074),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000075", pyrepr_round_trip_seed_000075),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000076", pyrepr_round_trip_seed_000076),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000077", pyrepr_round_trip_seed_000077),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000078", pyrepr_round_trip_seed_000078),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000079", pyrepr_round_trip_seed_000079),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000080", pyrepr_round_trip_seed_000080),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000081", pyrepr_round_trip_seed_000081),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000082", pyrepr_round_trip_seed_000082),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000083", pyrepr_round_trip_seed_000083),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000084", pyrepr_round_trip_seed_000084),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000085", pyrepr_round_trip_seed_000085),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000086", pyrepr_round_trip_seed_000086),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000087", pyrepr_round_trip_seed_000087),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000088", pyrepr_round_trip_seed_000088),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000089", pyrepr_round_trip_seed_000089),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000090", pyrepr_round_trip_seed_000090),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000091", pyrepr_round_trip_seed_000091),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000092", pyrepr_round_trip_seed_000092),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000093", pyrepr_round_trip_seed_000093),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000094", pyrepr_round_trip_seed_000094),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000095", pyrepr_round_trip_seed_000095),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000096", pyrepr_round_trip_seed_000096),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000097", pyrepr_round_trip_seed_000097),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000098", pyrepr_round_trip_seed_000098),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000099", pyrepr_round_trip_seed_000099),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000100", pyrepr_round_trip_seed_000100),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000101", pyrepr_round_trip_seed_000101),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000102", pyrepr_round_trip_seed_000102),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000103", pyrepr_round_trip_seed_000103),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000104", pyrepr_round_trip_seed_000104),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000105", pyrepr_round_trip_seed_000105),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000106", pyrepr_round_trip_seed_000106),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000107", pyrepr_round_trip_seed_000107),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000108", pyrepr_round_trip_seed_000108),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000109", pyrepr_round_trip_seed_000109),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000110", pyrepr_round_trip_seed_000110),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000111", pyrepr_round_trip_seed_000111),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000112", pyrepr_round_trip_seed_000112),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000113", pyrepr_round_trip_seed_000113),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000114", pyrepr_round_trip_seed_000114),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000115", pyrepr_round_trip_seed_000115),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000116", pyrepr_round_trip_seed_000116),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000117", pyrepr_round_trip_seed_000117),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000118", pyrepr_round_trip_seed_000118),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000119", pyrepr_round_trip_seed_000119),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000120", pyrepr_round_trip_seed_000120),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000121", pyrepr_round_trip_seed_000121),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000122", pyrepr_round_trip_seed_000122),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000123", pyrepr_round_trip_seed_000123),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000124", pyrepr_round_trip_seed_000124),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000125", pyrepr_round_trip_seed_000125),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000126", pyrepr_round_trip_seed_000126),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000127", pyrepr_round_trip_seed_000127),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000128", pyrepr_round_trip_seed_000128),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000129", pyrepr_round_trip_seed_000129),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000130", pyrepr_round_trip_seed_000130),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000131", pyrepr_round_trip_seed_000131),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000132", pyrepr_round_trip_seed_000132),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000133", pyrepr_round_trip_seed_000133),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000134", pyrepr_round_trip_seed_000134),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000135", pyrepr_round_trip_seed_000135),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000136", pyrepr_round_trip_seed_000136),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000137", pyrepr_round_trip_seed_000137),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000138", pyrepr_round_trip_seed_000138),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000139", pyrepr_round_trip_seed_000139),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000140", pyrepr_round_trip_seed_000140),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000141", pyrepr_round_trip_seed_000141),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000142", pyrepr_round_trip_seed_000142),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000143", pyrepr_round_trip_seed_000143),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000144", pyrepr_round_trip_seed_000144),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000145", pyrepr_round_trip_seed_000145),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000146", pyrepr_round_trip_seed_000146),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000147", pyrepr_round_trip_seed_000147),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000148", pyrepr_round_trip_seed_000148),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000149", pyrepr_round_trip_seed_000149),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000150", pyrepr_round_trip_seed_000150),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000151", pyrepr_round_trip_seed_000151),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000152", pyrepr_round_trip_seed_000152),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000153", pyrepr_round_trip_seed_000153),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000154", pyrepr_round_trip_seed_000154),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000155", pyrepr_round_trip_seed_000155),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000156", pyrepr_round_trip_seed_000156),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000157", pyrepr_round_trip_seed_000157),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000158", pyrepr_round_trip_seed_000158),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000159", pyrepr_round_trip_seed_000159),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000160", pyrepr_round_trip_seed_000160),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000161", pyrepr_round_trip_seed_000161),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000162", pyrepr_round_trip_seed_000162),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000163", pyrepr_round_trip_seed_000163),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000164", pyrepr_round_trip_seed_000164),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000165", pyrepr_round_trip_seed_000165),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000166", pyrepr_round_trip_seed_000166),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000167", pyrepr_round_trip_seed_000167),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000168", pyrepr_round_trip_seed_000168),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000169", pyrepr_round_trip_seed_000169),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000170", pyrepr_round_trip_seed_000170),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000171", pyrepr_round_trip_seed_000171),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000172", pyrepr_round_trip_seed_000172),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000173", pyrepr_round_trip_seed_000173),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000174", pyrepr_round_trip_seed_000174),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000175", pyrepr_round_trip_seed_000175),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000176", pyrepr_round_trip_seed_000176),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000177", pyrepr_round_trip_seed_000177),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000178", pyrepr_round_trip_seed_000178),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000179", pyrepr_round_trip_seed_000179),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000180", pyrepr_round_trip_seed_000180),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000181", pyrepr_round_trip_seed_000181),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000182", pyrepr_round_trip_seed_000182),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000183", pyrepr_round_trip_seed_000183),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000184", pyrepr_round_trip_seed_000184),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000185", pyrepr_round_trip_seed_000185),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000186", pyrepr_round_trip_seed_000186),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000187", pyrepr_round_trip_seed_000187),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000188", pyrepr_round_trip_seed_000188),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000189", pyrepr_round_trip_seed_000189),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000190", pyrepr_round_trip_seed_000190),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000191", pyrepr_round_trip_seed_000191),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000192", pyrepr_round_trip_seed_000192),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000193", pyrepr_round_trip_seed_000193),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000194", pyrepr_round_trip_seed_000194),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000195", pyrepr_round_trip_seed_000195),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000196", pyrepr_round_trip_seed_000196),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000197", pyrepr_round_trip_seed_000197),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000198", pyrepr_round_trip_seed_000198),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000199", pyrepr_round_trip_seed_000199),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000200", pyrepr_round_trip_seed_000200),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000201", pyrepr_round_trip_seed_000201),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000202", pyrepr_round_trip_seed_000202),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000203", pyrepr_round_trip_seed_000203),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000204", pyrepr_round_trip_seed_000204),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000205", pyrepr_round_trip_seed_000205),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000206", pyrepr_round_trip_seed_000206),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000207", pyrepr_round_trip_seed_000207),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000208", pyrepr_round_trip_seed_000208),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000209", pyrepr_round_trip_seed_000209),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000210", pyrepr_round_trip_seed_000210),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000211", pyrepr_round_trip_seed_000211),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000212", pyrepr_round_trip_seed_000212),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000213", pyrepr_round_trip_seed_000213),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000214", pyrepr_round_trip_seed_000214),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000215", pyrepr_round_trip_seed_000215),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000216", pyrepr_round_trip_seed_000216),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000217", pyrepr_round_trip_seed_000217),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000218", pyrepr_round_trip_seed_000218),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000219", pyrepr_round_trip_seed_000219),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000220", pyrepr_round_trip_seed_000220),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000221", pyrepr_round_trip_seed_000221),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000222", pyrepr_round_trip_seed_000222),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000223", pyrepr_round_trip_seed_000223),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000224", pyrepr_round_trip_seed_000224),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000225", pyrepr_round_trip_seed_000225),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000226", pyrepr_round_trip_seed_000226),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000227", pyrepr_round_trip_seed_000227),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000228", pyrepr_round_trip_seed_000228),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000229", pyrepr_round_trip_seed_000229),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000230", pyrepr_round_trip_seed_000230),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000231", pyrepr_round_trip_seed_000231),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000232", pyrepr_round_trip_seed_000232),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000233", pyrepr_round_trip_seed_000233),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000234", pyrepr_round_trip_seed_000234),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000235", pyrepr_round_trip_seed_000235),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000236", pyrepr_round_trip_seed_000236),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000237", pyrepr_round_trip_seed_000237),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000238", pyrepr_round_trip_seed_000238),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000239", pyrepr_round_trip_seed_000239),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000240", pyrepr_round_trip_seed_000240),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000241", pyrepr_round_trip_seed_000241),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000242", pyrepr_round_trip_seed_000242),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000243", pyrepr_round_trip_seed_000243),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000244", pyrepr_round_trip_seed_000244),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000245", pyrepr_round_trip_seed_000245),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000246", pyrepr_round_trip_seed_000246),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000247", pyrepr_round_trip_seed_000247),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000248", pyrepr_round_trip_seed_000248),
        ("property_campaigns::tests::pyrepr_round_trip_seed_000249", pyrepr_round_trip_seed_000249),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000000", pyrepr_format_fixed_rounding_seed_000000),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000001", pyrepr_format_fixed_rounding_seed_000001),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000002", pyrepr_format_fixed_rounding_seed_000002),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000003", pyrepr_format_fixed_rounding_seed_000003),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000004", pyrepr_format_fixed_rounding_seed_000004),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000005", pyrepr_format_fixed_rounding_seed_000005),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000006", pyrepr_format_fixed_rounding_seed_000006),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000007", pyrepr_format_fixed_rounding_seed_000007),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000008", pyrepr_format_fixed_rounding_seed_000008),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000009", pyrepr_format_fixed_rounding_seed_000009),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000010", pyrepr_format_fixed_rounding_seed_000010),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000011", pyrepr_format_fixed_rounding_seed_000011),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000012", pyrepr_format_fixed_rounding_seed_000012),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000013", pyrepr_format_fixed_rounding_seed_000013),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000014", pyrepr_format_fixed_rounding_seed_000014),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000015", pyrepr_format_fixed_rounding_seed_000015),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000016", pyrepr_format_fixed_rounding_seed_000016),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000017", pyrepr_format_fixed_rounding_seed_000017),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000018", pyrepr_format_fixed_rounding_seed_000018),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000019", pyrepr_format_fixed_rounding_seed_000019),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000020", pyrepr_format_fixed_rounding_seed_000020),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000021", pyrepr_format_fixed_rounding_seed_000021),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000022", pyrepr_format_fixed_rounding_seed_000022),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000023", pyrepr_format_fixed_rounding_seed_000023),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000024", pyrepr_format_fixed_rounding_seed_000024),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000025", pyrepr_format_fixed_rounding_seed_000025),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000026", pyrepr_format_fixed_rounding_seed_000026),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000027", pyrepr_format_fixed_rounding_seed_000027),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000028", pyrepr_format_fixed_rounding_seed_000028),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000029", pyrepr_format_fixed_rounding_seed_000029),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000030", pyrepr_format_fixed_rounding_seed_000030),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000031", pyrepr_format_fixed_rounding_seed_000031),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000032", pyrepr_format_fixed_rounding_seed_000032),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000033", pyrepr_format_fixed_rounding_seed_000033),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000034", pyrepr_format_fixed_rounding_seed_000034),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000035", pyrepr_format_fixed_rounding_seed_000035),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000036", pyrepr_format_fixed_rounding_seed_000036),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000037", pyrepr_format_fixed_rounding_seed_000037),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000038", pyrepr_format_fixed_rounding_seed_000038),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000039", pyrepr_format_fixed_rounding_seed_000039),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000040", pyrepr_format_fixed_rounding_seed_000040),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000041", pyrepr_format_fixed_rounding_seed_000041),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000042", pyrepr_format_fixed_rounding_seed_000042),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000043", pyrepr_format_fixed_rounding_seed_000043),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000044", pyrepr_format_fixed_rounding_seed_000044),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000045", pyrepr_format_fixed_rounding_seed_000045),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000046", pyrepr_format_fixed_rounding_seed_000046),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000047", pyrepr_format_fixed_rounding_seed_000047),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000048", pyrepr_format_fixed_rounding_seed_000048),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000049", pyrepr_format_fixed_rounding_seed_000049),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000050", pyrepr_format_fixed_rounding_seed_000050),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000051", pyrepr_format_fixed_rounding_seed_000051),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000052", pyrepr_format_fixed_rounding_seed_000052),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000053", pyrepr_format_fixed_rounding_seed_000053),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000054", pyrepr_format_fixed_rounding_seed_000054),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000055", pyrepr_format_fixed_rounding_seed_000055),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000056", pyrepr_format_fixed_rounding_seed_000056),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000057", pyrepr_format_fixed_rounding_seed_000057),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000058", pyrepr_format_fixed_rounding_seed_000058),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000059", pyrepr_format_fixed_rounding_seed_000059),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000060", pyrepr_format_fixed_rounding_seed_000060),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000061", pyrepr_format_fixed_rounding_seed_000061),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000062", pyrepr_format_fixed_rounding_seed_000062),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000063", pyrepr_format_fixed_rounding_seed_000063),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000064", pyrepr_format_fixed_rounding_seed_000064),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000065", pyrepr_format_fixed_rounding_seed_000065),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000066", pyrepr_format_fixed_rounding_seed_000066),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000067", pyrepr_format_fixed_rounding_seed_000067),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000068", pyrepr_format_fixed_rounding_seed_000068),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000069", pyrepr_format_fixed_rounding_seed_000069),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000070", pyrepr_format_fixed_rounding_seed_000070),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000071", pyrepr_format_fixed_rounding_seed_000071),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000072", pyrepr_format_fixed_rounding_seed_000072),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000073", pyrepr_format_fixed_rounding_seed_000073),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000074", pyrepr_format_fixed_rounding_seed_000074),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000075", pyrepr_format_fixed_rounding_seed_000075),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000076", pyrepr_format_fixed_rounding_seed_000076),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000077", pyrepr_format_fixed_rounding_seed_000077),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000078", pyrepr_format_fixed_rounding_seed_000078),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000079", pyrepr_format_fixed_rounding_seed_000079),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000080", pyrepr_format_fixed_rounding_seed_000080),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000081", pyrepr_format_fixed_rounding_seed_000081),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000082", pyrepr_format_fixed_rounding_seed_000082),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000083", pyrepr_format_fixed_rounding_seed_000083),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000084", pyrepr_format_fixed_rounding_seed_000084),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000085", pyrepr_format_fixed_rounding_seed_000085),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000086", pyrepr_format_fixed_rounding_seed_000086),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000087", pyrepr_format_fixed_rounding_seed_000087),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000088", pyrepr_format_fixed_rounding_seed_000088),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000089", pyrepr_format_fixed_rounding_seed_000089),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000090", pyrepr_format_fixed_rounding_seed_000090),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000091", pyrepr_format_fixed_rounding_seed_000091),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000092", pyrepr_format_fixed_rounding_seed_000092),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000093", pyrepr_format_fixed_rounding_seed_000093),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000094", pyrepr_format_fixed_rounding_seed_000094),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000095", pyrepr_format_fixed_rounding_seed_000095),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000096", pyrepr_format_fixed_rounding_seed_000096),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000097", pyrepr_format_fixed_rounding_seed_000097),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000098", pyrepr_format_fixed_rounding_seed_000098),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000099", pyrepr_format_fixed_rounding_seed_000099),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000100", pyrepr_format_fixed_rounding_seed_000100),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000101", pyrepr_format_fixed_rounding_seed_000101),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000102", pyrepr_format_fixed_rounding_seed_000102),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000103", pyrepr_format_fixed_rounding_seed_000103),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000104", pyrepr_format_fixed_rounding_seed_000104),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000105", pyrepr_format_fixed_rounding_seed_000105),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000106", pyrepr_format_fixed_rounding_seed_000106),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000107", pyrepr_format_fixed_rounding_seed_000107),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000108", pyrepr_format_fixed_rounding_seed_000108),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000109", pyrepr_format_fixed_rounding_seed_000109),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000110", pyrepr_format_fixed_rounding_seed_000110),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000111", pyrepr_format_fixed_rounding_seed_000111),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000112", pyrepr_format_fixed_rounding_seed_000112),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000113", pyrepr_format_fixed_rounding_seed_000113),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000114", pyrepr_format_fixed_rounding_seed_000114),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000115", pyrepr_format_fixed_rounding_seed_000115),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000116", pyrepr_format_fixed_rounding_seed_000116),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000117", pyrepr_format_fixed_rounding_seed_000117),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000118", pyrepr_format_fixed_rounding_seed_000118),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000119", pyrepr_format_fixed_rounding_seed_000119),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000120", pyrepr_format_fixed_rounding_seed_000120),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000121", pyrepr_format_fixed_rounding_seed_000121),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000122", pyrepr_format_fixed_rounding_seed_000122),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000123", pyrepr_format_fixed_rounding_seed_000123),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000124", pyrepr_format_fixed_rounding_seed_000124),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000125", pyrepr_format_fixed_rounding_seed_000125),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000126", pyrepr_format_fixed_rounding_seed_000126),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000127", pyrepr_format_fixed_rounding_seed_000127),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000128", pyrepr_format_fixed_rounding_seed_000128),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000129", pyrepr_format_fixed_rounding_seed_000129),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000130", pyrepr_format_fixed_rounding_seed_000130),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000131", pyrepr_format_fixed_rounding_seed_000131),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000132", pyrepr_format_fixed_rounding_seed_000132),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000133", pyrepr_format_fixed_rounding_seed_000133),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000134", pyrepr_format_fixed_rounding_seed_000134),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000135", pyrepr_format_fixed_rounding_seed_000135),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000136", pyrepr_format_fixed_rounding_seed_000136),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000137", pyrepr_format_fixed_rounding_seed_000137),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000138", pyrepr_format_fixed_rounding_seed_000138),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000139", pyrepr_format_fixed_rounding_seed_000139),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000140", pyrepr_format_fixed_rounding_seed_000140),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000141", pyrepr_format_fixed_rounding_seed_000141),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000142", pyrepr_format_fixed_rounding_seed_000142),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000143", pyrepr_format_fixed_rounding_seed_000143),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000144", pyrepr_format_fixed_rounding_seed_000144),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000145", pyrepr_format_fixed_rounding_seed_000145),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000146", pyrepr_format_fixed_rounding_seed_000146),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000147", pyrepr_format_fixed_rounding_seed_000147),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000148", pyrepr_format_fixed_rounding_seed_000148),
        ("property_campaigns::tests::pyrepr_format_fixed_rounding_seed_000149", pyrepr_format_fixed_rounding_seed_000149),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000000", pyrepr_sign_symmetry_seed_000000),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000001", pyrepr_sign_symmetry_seed_000001),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000002", pyrepr_sign_symmetry_seed_000002),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000003", pyrepr_sign_symmetry_seed_000003),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000004", pyrepr_sign_symmetry_seed_000004),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000005", pyrepr_sign_symmetry_seed_000005),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000006", pyrepr_sign_symmetry_seed_000006),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000007", pyrepr_sign_symmetry_seed_000007),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000008", pyrepr_sign_symmetry_seed_000008),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000009", pyrepr_sign_symmetry_seed_000009),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000010", pyrepr_sign_symmetry_seed_000010),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000011", pyrepr_sign_symmetry_seed_000011),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000012", pyrepr_sign_symmetry_seed_000012),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000013", pyrepr_sign_symmetry_seed_000013),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000014", pyrepr_sign_symmetry_seed_000014),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000015", pyrepr_sign_symmetry_seed_000015),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000016", pyrepr_sign_symmetry_seed_000016),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000017", pyrepr_sign_symmetry_seed_000017),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000018", pyrepr_sign_symmetry_seed_000018),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000019", pyrepr_sign_symmetry_seed_000019),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000020", pyrepr_sign_symmetry_seed_000020),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000021", pyrepr_sign_symmetry_seed_000021),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000022", pyrepr_sign_symmetry_seed_000022),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000023", pyrepr_sign_symmetry_seed_000023),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000024", pyrepr_sign_symmetry_seed_000024),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000025", pyrepr_sign_symmetry_seed_000025),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000026", pyrepr_sign_symmetry_seed_000026),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000027", pyrepr_sign_symmetry_seed_000027),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000028", pyrepr_sign_symmetry_seed_000028),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000029", pyrepr_sign_symmetry_seed_000029),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000030", pyrepr_sign_symmetry_seed_000030),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000031", pyrepr_sign_symmetry_seed_000031),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000032", pyrepr_sign_symmetry_seed_000032),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000033", pyrepr_sign_symmetry_seed_000033),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000034", pyrepr_sign_symmetry_seed_000034),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000035", pyrepr_sign_symmetry_seed_000035),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000036", pyrepr_sign_symmetry_seed_000036),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000037", pyrepr_sign_symmetry_seed_000037),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000038", pyrepr_sign_symmetry_seed_000038),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000039", pyrepr_sign_symmetry_seed_000039),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000040", pyrepr_sign_symmetry_seed_000040),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000041", pyrepr_sign_symmetry_seed_000041),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000042", pyrepr_sign_symmetry_seed_000042),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000043", pyrepr_sign_symmetry_seed_000043),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000044", pyrepr_sign_symmetry_seed_000044),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000045", pyrepr_sign_symmetry_seed_000045),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000046", pyrepr_sign_symmetry_seed_000046),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000047", pyrepr_sign_symmetry_seed_000047),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000048", pyrepr_sign_symmetry_seed_000048),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000049", pyrepr_sign_symmetry_seed_000049),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000050", pyrepr_sign_symmetry_seed_000050),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000051", pyrepr_sign_symmetry_seed_000051),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000052", pyrepr_sign_symmetry_seed_000052),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000053", pyrepr_sign_symmetry_seed_000053),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000054", pyrepr_sign_symmetry_seed_000054),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000055", pyrepr_sign_symmetry_seed_000055),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000056", pyrepr_sign_symmetry_seed_000056),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000057", pyrepr_sign_symmetry_seed_000057),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000058", pyrepr_sign_symmetry_seed_000058),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000059", pyrepr_sign_symmetry_seed_000059),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000060", pyrepr_sign_symmetry_seed_000060),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000061", pyrepr_sign_symmetry_seed_000061),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000062", pyrepr_sign_symmetry_seed_000062),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000063", pyrepr_sign_symmetry_seed_000063),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000064", pyrepr_sign_symmetry_seed_000064),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000065", pyrepr_sign_symmetry_seed_000065),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000066", pyrepr_sign_symmetry_seed_000066),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000067", pyrepr_sign_symmetry_seed_000067),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000068", pyrepr_sign_symmetry_seed_000068),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000069", pyrepr_sign_symmetry_seed_000069),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000070", pyrepr_sign_symmetry_seed_000070),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000071", pyrepr_sign_symmetry_seed_000071),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000072", pyrepr_sign_symmetry_seed_000072),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000073", pyrepr_sign_symmetry_seed_000073),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000074", pyrepr_sign_symmetry_seed_000074),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000075", pyrepr_sign_symmetry_seed_000075),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000076", pyrepr_sign_symmetry_seed_000076),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000077", pyrepr_sign_symmetry_seed_000077),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000078", pyrepr_sign_symmetry_seed_000078),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000079", pyrepr_sign_symmetry_seed_000079),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000080", pyrepr_sign_symmetry_seed_000080),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000081", pyrepr_sign_symmetry_seed_000081),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000082", pyrepr_sign_symmetry_seed_000082),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000083", pyrepr_sign_symmetry_seed_000083),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000084", pyrepr_sign_symmetry_seed_000084),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000085", pyrepr_sign_symmetry_seed_000085),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000086", pyrepr_sign_symmetry_seed_000086),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000087", pyrepr_sign_symmetry_seed_000087),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000088", pyrepr_sign_symmetry_seed_000088),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000089", pyrepr_sign_symmetry_seed_000089),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000090", pyrepr_sign_symmetry_seed_000090),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000091", pyrepr_sign_symmetry_seed_000091),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000092", pyrepr_sign_symmetry_seed_000092),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000093", pyrepr_sign_symmetry_seed_000093),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000094", pyrepr_sign_symmetry_seed_000094),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000095", pyrepr_sign_symmetry_seed_000095),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000096", pyrepr_sign_symmetry_seed_000096),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000097", pyrepr_sign_symmetry_seed_000097),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000098", pyrepr_sign_symmetry_seed_000098),
        ("property_campaigns::tests::pyrepr_sign_symmetry_seed_000099", pyrepr_sign_symmetry_seed_000099),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
