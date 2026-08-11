// Property campaigns over three independent, pure, deterministic
// `temper-rust-router-core` kernels: the geographic pruning predicate
// (`pruning::is_candidate_edge`), the constraint rewrite/simplification
// fixpoint (`combinator::rewrite::rewrite`), and the grid A* pathfinder
// (`astar::astar_kernel_3d`).
//
// Why this exists (R7 / the WASM-tier volume payload)
// -----------------------------------------------------------------------
// A fixed, hand-written unit-test fixture explores the same handful of
// inputs every time it runs. This module gives the wasm32 tier a payload
// where each registered test explores a *distinct* generated input: every
// property below is a pure function of a `u64` seed through the
// `SplitMix64` generator below, so `pr_monotonic_params_seed_000042` and
// `pr_monotonic_params_seed_000043` exercise different geometry, and a
// failure is reproducible from its seed alone.
//
// Each property is a metamorphic or invariant relation over the real
// kernel -- a relationship that must hold between two *related* calls --
// never a restatement of the implementation (i.e. never "recompute X, and
// assert X equals X"). Every one is picked so that a plausible bug in the
// kernel it covers flips it from green to red; see this crate's PR body
// (or `docs/evidence/` if this lands with one) for the mutation-testing
// evidence: each property was checked against a deliberately broken kernel
// and shown to fail on exactly the cases it should, then the kernel was
// reverted.
//
// A note on scope, since it is easy to conflate the two crates: the
// sibling `temper-rust-router` crate (no `-core`) reproduces CPython's
// `max`/`min`/`list.sort` iterable semantics for NaN-bearing wirelength
// keys (`net_ordering.rs`'s `py_max`/`py_min`/`py_list_sort`), where a
// clean total order cannot be assumed. None of that machinery exists in
// `temper-rust-router-core` -- this crate's three kernels here operate on
// ordinary finite f64 geometry (pruning), a discrete rewrite system
// (combinator), and f32 grid costs with no user-supplied NaN path (astar).
// No property below needs a NaN caveat; this note exists so a future
// reader does not go looking for one that would be a copy-paste of the
// sibling crate's concern rather than a real one here.
//
// No `proptest`: it is a dev-dependency, absent from the ordinary
// (non-test) build this crate's `wasm-registry` feature compiles into
// (see `scripts/gen_wasm_test_registry.py`'s `PROPTEST_USE` exclusion).
// Note `pruning.rs` already has an extensive proptest suite
// (`pruning::property_tests`, 11 properties) proving several of the same
// relations this module ports below (monotonicity, symmetry, EMST
// soundness) -- that suite is exactly what `--census` reports excluded as
// `proptest-dev-dependency`. The properties below are independent,
// deterministic re-implementations of that same reasoning using
// `SplitMix64` instead of `proptest::Strategy`, so they compile into a
// plain (non-dev-dependency) build and can run on `wasm32`. No RNG crate
// either: `SplitMix64` is a small, self-contained, portable PRNG --
// wasm32-unknown-unknown has no OS entropy source, and fixed seeds are
// what make a wasm32 trap reproducible from its seed by a human reading
// the failing test's name.
//
// This crate denies `clippy::unwrap_used` and `clippy::expect_used`
// crate-wide (see `Cargo.toml`'s `[lints.clippy]`); every function below
// (outside `mod tests`, which the wasm-registry generator allow-lists)
// uses `match`/`if let`/indexing instead.
//
// Every item below (down to `mod tests`) is reachable ONLY from that
// module's `#[test]` functions -- which `scripts/gen_wasm_test_registry.py`
// turns into `pub(crate)` and reaches indirectly through
// `tests::WASM_TESTS` once this module is registered. A build with neither
// `test` nor `wasm-registry` active therefore sees every item below as
// unused, hence the blanket allow.
#![allow(dead_code)]

// ---------------------------------------------------------------------------
// Deterministic PRNG (SplitMix64) -- pure, no external dependency, portable
// to wasm32-unknown-unknown without an entropy source. Shared by all three
// kernels' properties below; each property draws its own generated case
// from `seed` directly, and any extra randomized parameter from an
// independent `sub_rng(seed, salt)` stream so a property's own parameters
// never correlate with which base case `seed` produced.
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
/// same base seed (same pattern as `packages/temper-geometry/src/
/// property_campaigns.rs`'s `sub_rng`, which itself copies
/// `packages/temper-drc-rs/src/rules/drc/property_campaigns.rs`).
fn sub_rng(seed: u64, salt: u64) -> SplitMix64 {
    SplitMix64::new(seed.wrapping_mul(0x9E37_79B9_7F4A_7C15).wrapping_add(salt))
}

// ===========================================================================
// Kernel 1: pruning.rs -- `is_candidate_edge`, the geographic pruning
// predicate for the router's SAT encoding (candidate(n, e) = dist_min(e,
// P_n) <= max(K * S_n, M_min)).
// ===========================================================================

use crate::pruning::{
    dist_min_edge_to_pins, euclidean_dist, is_candidate_edge, Edge2D, NetPins, Point2D,
    PruningParams,
};

const PR_SALT_PARAMS: u64 = 0xE1;
const PR_SALT_ENDPOINTS: u64 = 0xE2;

/// A net of 1-6 pins in `[0, 200)^2` -- the same range `pruning::
/// property_tests`'s `point_2d`/`net_pins` proptest strategies use.
fn pr_gen_net_from(rng: &mut SplitMix64) -> NetPins {
    let n = 1 + rng.index(6); // 1..=6
    let positions = (0..n).map(|_| (rng.range(0.0, 200.0), rng.range(0.0, 200.0))).collect();
    NetPins { positions }
}

fn pr_gen_point_from(rng: &mut SplitMix64) -> Point2D {
    (rng.range(0.0, 200.0), rng.range(0.0, 200.0))
}

fn pr_gen_edge_from(rng: &mut SplitMix64) -> Edge2D {
    Edge2D { start: pr_gen_point_from(rng), end: pr_gen_point_from(rng) }
}

/// Loosening the pruning parameters (`k_factor` and/or `m_min`) never turns
/// a candidate edge into a non-candidate: `M_n = max(K * S_n, M_min)` is
/// monotonically non-decreasing in both K and M_min, and the predicate is
/// `dist <= M_n`, so a larger `M_n` can only keep or add candidates, never
/// remove one. Mirrors `pruning::property_tests::
/// property_monotonic_looser_params_include_more`, deterministically.
///
/// Bug this would catch: any change to `is_candidate_edge`'s formula that
/// breaks the `max(K*S_n, M_min)` monotonicity -- e.g. swapping the `max`
/// for a `min`, or using the *new* K to compute `S_n` from a stale margin --
/// would let a stricter combination of parameters admit an edge a looser
/// one excludes.
pub(crate) fn pr_monotonic_params_impl(seed: u64) {
    let mut rng = SplitMix64::new(seed);
    let net = pr_gen_net_from(&mut rng);
    let edge = pr_gen_edge_from(&mut rng);
    let mut prng = sub_rng(seed, PR_SALT_PARAMS);
    let k = prng.range(1.0, 5.0);
    let m = prng.range(0.1, 100.0);
    let tight = PruningParams { k_factor: k, m_min: m };
    let loose = PruningParams { k_factor: k + 1.0, m_min: m + 10.0 };

    let tight_result = is_candidate_edge(&net, &edge, &tight);
    let loose_result = is_candidate_edge(&net, &edge, &loose);

    assert!(
        !tight_result || loose_result,
        "monotonicity violated: seed={seed} tight=(K={k}, M_min={m}) says candidate=true \
         but loose=(K={}, M_min={}) says candidate=false",
        k + 1.0,
        m + 10.0
    );
}

/// `is_candidate_edge` must be symmetric under swapping an edge's
/// endpoints: a line segment is an unordered pair of points, and
/// `dist_min_edge_to_pins`/`point_to_segment_distance` project onto the
/// segment's line, which does not depend on traversal direction.
///
/// Bug this would catch: a refactor of `point_to_segment_distance` that
/// clamps the projection parameter `t` asymmetrically (e.g. `t.max(0.0)`
/// without the matching `.min(1.0)`, or a swapped `seg_a`/`seg_b` in only
/// one code path) would make the result depend on which endpoint is
/// `start` and which is `end`.
pub(crate) fn pr_symmetric_endpoints_impl(seed: u64) {
    let mut rng = SplitMix64::new(seed);
    let net = pr_gen_net_from(&mut rng);
    let mut erng = sub_rng(seed, PR_SALT_ENDPOINTS);
    let start = pr_gen_point_from(&mut erng);
    let end = pr_gen_point_from(&mut erng);
    let params = PruningParams::default();

    let forward = Edge2D { start, end };
    let backward = Edge2D { start: end, end: start };
    let r_forward = is_candidate_edge(&net, &forward, &params);
    let r_backward = is_candidate_edge(&net, &backward, &params);

    assert_eq!(
        r_forward, r_backward,
        "is_candidate_edge is not symmetric under edge-endpoint swap: seed={seed} \
         start={start:?} end={end:?} forward={r_forward} backward={r_backward}"
    );
}

/// Compute the Euclidean Minimum Spanning Tree of `points` via Prim's
/// algorithm on the complete graph. Ported from `pruning::property_tests::
/// euclidean_mst` -- an independent construction from `pruning.rs`'s own
/// logic (it only calls the crate's public `euclidean_dist`, never
/// `is_candidate_edge` or `pin_span`), so checking every MST edge against
/// the predicate below is a genuine soundness check, not a restatement.
fn pr_euclidean_mst(points: &[Point2D]) -> Vec<(usize, usize)> {
    let n = points.len();
    if n <= 1 {
        return Vec::new();
    }

    let mut in_tree = vec![false; n];
    let mut min_dist = vec![f64::INFINITY; n];
    let mut parent = vec![0usize; n];
    min_dist[0] = 0.0;

    for _ in 0..n {
        let mut u = n;
        let mut best = f64::INFINITY;
        for i in 0..n {
            if !in_tree[i] && min_dist[i] < best {
                best = min_dist[i];
                u = i;
            }
        }
        if u == n {
            break;
        }
        in_tree[u] = true;
        for v in 0..n {
            if !in_tree[v] {
                let d = euclidean_dist(points[u], points[v]);
                if d < min_dist[v] {
                    min_dist[v] = d;
                    parent[v] = u;
                }
            }
        }
    }

    let mut edges = Vec::with_capacity(n.saturating_sub(1));
    for v in 1..n {
        if min_dist[v].is_finite() {
            edges.push((parent[v], v));
        }
    }
    edges
}

/// Every edge of a net's own Euclidean MST must be a pruning candidate
/// under default parameters. This is the crate's own soundness argument
/// (`pruning.rs`'s module doc: "guarantees zero false negatives -- every
/// edge on any feasible route passes the test") applied to a concrete
/// lower-bound witness: any feasible routing of a net's pins connects them,
/// the EMST is the shortest such connection, and every EMST edge's
/// endpoints are pins of the net (so its distance to the pin set is 0,
/// trivially <= any non-negative margin).
///
/// Bug this would catch: a regression that tightens the default `K`/`M_min`
/// constants (or the formula combining them) enough to exclude a
/// legitimate short connecting edge -- exactly the over-pruning class
/// `pruning.rs`'s own `tight_margin_excludes_detour_edge` test demonstrates
/// deliberately with non-default parameters.
pub(crate) fn pr_emst_soundness_impl(seed: u64) {
    let mut rng = SplitMix64::new(seed);
    let n = 2 + rng.index(7); // 2..=8
    let pins: Vec<Point2D> = (0..n).map(|_| pr_gen_point_from(&mut rng)).collect();
    let net = NetPins { positions: pins.clone() };
    let params = PruningParams::default();
    let mst_edges = pr_euclidean_mst(&pins);

    for &(i, j) in &mst_edges {
        let edge = Edge2D { start: pins[i], end: pins[j] };
        let dist = dist_min_edge_to_pins(&edge, &net.positions);
        assert!(
            is_candidate_edge(&net, &edge, &params),
            "EMST soundness violated: seed={seed} edge=({i},{j}) dist_to_pins={dist:.3} \
             excluded by the default-parameter predicate"
        );
    }
}

// ===========================================================================
// Kernel 2: combinator/rewrite.rs -- `rewrite()`, the RW1-RW7 fixpoint
// simplifier over `InternalConstraintModel`.
// ===========================================================================

use crate::combinator::rewrite::{rewrite, RewriteError};
use crate::types::{InternalConstraint, InternalConstraintModel};

/// Fisher-Yates partial shuffle: `k` distinct indices from `0..n`, order
/// randomized. Used to pick a random subset of a channel's variables for a
/// `Capacity` constraint's `terms`, or a random pair for `DiffPair`.
fn rw_choose_subset(rng: &mut SplitMix64, n: usize, k: usize) -> Vec<usize> {
    let k = k.min(n);
    let mut idx: Vec<usize> = (0..n).collect();
    for i in 0..k {
        let j = i + rng.index(n - i);
        idx.swap(i, j);
    }
    idx.truncate(k);
    idx
}

/// A canonical, order-independent string key for one constraint. `f64`
/// fields are formatted to fixed precision (not `Debug`, which is stable
/// per-value but this keeps the format under this module's control) and
/// `terms` is sorted by variable name, so two constraint lists that agree
/// as *multisets* produce identical `canon_constraints` output regardless
/// of element order.
///
/// This matters because `rewrite()`'s `subsume_capacity` rebuilds its
/// output by iterating a `HashMap<BTreeSet<String>, (usize, usize)>`
/// (`dedup_map`) whenever more than one `Capacity` constraint is present --
/// and `std::collections::HashMap` iteration order is not guaranteed
/// stable even between two calls in the same process (`RandomState` draws
/// fresh keys per instantiation). Two correct, semantically-identical
/// `rewrite()` calls can therefore legitimately emit their `Capacity`
/// constraints in different relative order. Comparing raw `Vec` equality
/// for the idempotence/duplicate-invariance properties below would make
/// them flaky on a fully correct kernel; comparing the canonical
/// (sorted) form does not.
fn canon_constraint(c: &InternalConstraint) -> String {
    match c {
        InternalConstraint::Capacity { channel_id, capacity, slack_factor, terms } => {
            let mut t: Vec<String> = terms.iter().map(|(n, w)| format!("{n}:{w:.6}")).collect();
            t.sort();
            format!("Capacity({channel_id},{capacity:.6},{slack_factor:.6},[{}])", t.join(","))
        }
        InternalConstraint::DiffPair { channel_id, p_var_name, n_var_name } => {
            format!("DiffPair({channel_id},{p_var_name},{n_var_name})")
        }
        InternalConstraint::LayerRestriction { var_name, allowed } => {
            format!("LayerRestriction({var_name},{allowed})")
        }
        InternalConstraint::ChannelSeparation { group_a, group_b, min_slots, channel_id } => {
            format!("ChannelSeparation({channel_id},{min_slots},{group_a:?},{group_b:?})")
        }
    }
}

/// The canonical (sorted, order-independent) multiset representation of a
/// constraint list. See [`canon_constraint`] for why this, not `Vec`
/// equality, is the right comparison for `rewrite()`'s output.
fn canon_constraints(cs: &[InternalConstraint]) -> Vec<String> {
    let mut v: Vec<String> = cs.iter().map(canon_constraint).collect();
    v.sort();
    v
}

/// A random, RW7-conflict-free constraint model: 1-3 channels, each with
/// 2-5 variables scoped to that channel (`"ch{c}_v{v}"`, so no two channels
/// ever share a variable name and `subsume_capacity`'s `dedup_map` --
/// keyed only by variable-set, not channel -- cannot collide across
/// channels), 0-2 `Capacity` constraints per channel, an independent
/// per-variable `LayerRestriction` coin flip (each variable gets *one*
/// `allowed` value or none -- never both `true` and `false`, so this
/// generator never manufactures RW7's `UnsatPreSolve`; that path is
/// exercised deliberately by [`rw_gen_conflict_model`] instead), an
/// optional `DiffPair`, and an optional (semantically inert to `rewrite()`,
/// pure pass-through noise) `ChannelSeparation`.
fn rw_gen_model(seed: u64) -> InternalConstraintModel {
    let mut rng = SplitMix64::new(seed);
    let n_channels = 1 + rng.index(3); // 1..=3
    let mut constraints = Vec::new();

    for c in 0..n_channels {
        let channel = format!("ch{c}");
        let n_vars = 2 + rng.index(4); // 2..=5
        let vars: Vec<String> = (0..n_vars).map(|v| format!("{channel}_v{v}")).collect();

        let n_caps = rng.index(3); // 0..=2
        for _ in 0..n_caps {
            let k_terms = 1 + rng.index(n_vars.min(4));
            let sel = rw_choose_subset(&mut rng, n_vars, k_terms);
            let terms: Vec<(String, f64)> =
                sel.iter().map(|&i| (vars[i].clone(), rng.range(0.5, 5.0))).collect();
            constraints.push(InternalConstraint::Capacity {
                channel_id: channel.clone(),
                capacity: rng.range(1.0, 50.0),
                slack_factor: rng.range(0.5, 2.0),
                terms,
            });
        }

        for v in &vars {
            if rng.next_f64() < 0.4 {
                let allowed = rng.next_f64() < 0.5;
                constraints.push(InternalConstraint::LayerRestriction { var_name: v.clone(), allowed });
            }
        }

        if vars.len() >= 2 && rng.next_f64() < 0.5 {
            let sel = rw_choose_subset(&mut rng, vars.len(), 2);
            constraints.push(InternalConstraint::DiffPair {
                channel_id: channel.clone(),
                p_var_name: vars[sel[0]].clone(),
                n_var_name: vars[sel[1]].clone(),
            });
        }

        if rng.next_f64() < 0.3 {
            constraints.push(InternalConstraint::ChannelSeparation {
                group_a: vec![rng.index(5)],
                group_b: vec![rng.index(5)],
                min_slots: 1 + rng.index(3),
                channel_id: channel.clone(),
            });
        }
    }

    InternalConstraintModel { variables: Vec::new(), constraints }
}

/// `rewrite()` is a fixpoint simplifier (module doc: "Applies simplification
/// rules ... until fixpoint"): applying it to its own output must be a
/// no-op. This is the direct claim a fixpoint loop makes, and the sharpest
/// possible test of it -- a simplifier that only *partially* converges
/// within one call would still look done to a caller that never re-checks,
/// exactly the bug this catches.
///
/// Bug this would catch: replacing the `while changed && iteration <
/// max_iterations` loop with a single unconditional pass (`if` instead of
/// `while`) -- the model still gets non-trivially simpler on the *first*
/// call for any input needing two or more rule rounds to converge (e.g. a
/// `LayerPropagate` that unlocks a `CapEliminate`), but the *second* call
/// keeps simplifying what the first call left half-done, so the two
/// outputs disagree.
pub(crate) fn rw_idempotent_impl(seed: u64) {
    let model = rw_gen_model(seed);
    let r1 = rewrite(&model);
    match &r1 {
        Ok(m1) => {
            let r2 = rewrite(m1);
            match &r2 {
                Ok(m2) => {
                    let c1 = canon_constraints(&m1.constraints);
                    let c2 = canon_constraints(&m2.constraints);
                    assert_eq!(
                        c1, c2,
                        "rewrite() is not idempotent: seed={seed}\n\
                         fixed point:      {c1:?}\n\
                         applied again to: {c2:?}"
                    );
                }
                Err(e) => panic!(
                    "rewrite() succeeded once but errored when re-applied to its own \
                     output: seed={seed} error={e:?}"
                ),
            }
        }
        Err(e1) => {
            // The generator is RW7-conflict-free, so this branch should not
            // be reached in practice; if it ever is, a repeat call on the
            // *same* input is at minimum still required to be deterministic.
            let r1b = rewrite(&model);
            match &r1b {
                Err(e2) => assert_eq!(
                    e1, e2,
                    "rewrite() gave a different error on a repeat call with the same \
                     input: seed={seed}"
                ),
                Ok(_) => panic!(
                    "rewrite() errored once then succeeded on an identical repeat call: \
                     seed={seed} first_error={e1:?}"
                ),
            }
        }
    }
}

/// A random, RW7-conflict-free model with exactly one channel and a
/// *guaranteed* `LayerRestriction` and `DiffPair` pair to duplicate, so the
/// duplicate-invariance property below always has a real target instead of
/// depending on a generator coin flip landing right.
fn rw_gen_model_for_dup(seed: u64) -> (InternalConstraintModel, InternalConstraint) {
    let mut rng = SplitMix64::new(seed);
    let channel = "chDup".to_string();
    let n_vars = 2 + rng.index(4); // 2..=5
    let vars: Vec<String> = (0..n_vars).map(|v| format!("{channel}_v{v}")).collect();
    let mut constraints = Vec::new();

    let layer_restriction = InternalConstraint::LayerRestriction {
        var_name: vars[0].clone(),
        allowed: rng.next_f64() < 0.5,
    };
    constraints.push(layer_restriction.clone());

    let diff_pair = InternalConstraint::DiffPair {
        channel_id: channel.clone(),
        p_var_name: vars[0].clone(),
        n_var_name: vars[1].clone(),
    };
    constraints.push(diff_pair.clone());

    let n_caps = rng.index(3); // 0..=2, background noise
    for _ in 0..n_caps {
        let k_terms = 1 + rng.index(n_vars.min(4));
        let sel = rw_choose_subset(&mut rng, n_vars, k_terms);
        let terms: Vec<(String, f64)> =
            sel.iter().map(|&i| (vars[i].clone(), rng.range(0.5, 5.0))).collect();
        constraints.push(InternalConstraint::Capacity {
            channel_id: channel.clone(),
            capacity: rng.range(1.0, 50.0),
            slack_factor: rng.range(0.5, 2.0),
            terms,
        });
    }

    let model = InternalConstraintModel { variables: Vec::new(), constraints };
    let dup_target = if rng.next_f64() < 0.5 { layer_restriction } else { diff_pair };
    (model, dup_target)
}

/// Appending an exact duplicate of an existing `DiffPair` or
/// `LayerRestriction` constraint must not change `rewrite()`'s fixed point:
/// RW5 (`DiffPairDedup`) and RW6 (`LayerDedup`) are documented to "drop
/// duplicate ... constraints (keep first)", and a duplicate at the tail of
/// the list does not change any other constraint's relative processing
/// order, so the surviving set must be identical.
///
/// Bug this would catch: disabling or narrowing RW5/RW6 (e.g. keying
/// `LayerDedup` on `var_name` alone, ignoring `allowed`) would leave the
/// duplicate (or a related-but-distinct constraint it wrongly conflates
/// with) in the output, changing the canonical constraint multiset.
pub(crate) fn rw_duplicate_invariant_impl(seed: u64) {
    let (model, dup_target) = rw_gen_model_for_dup(seed);
    let mut dup_model = model.clone();
    dup_model.constraints.push(dup_target);

    let base = rewrite(&model);
    let dup = rewrite(&dup_model);

    match (&base, &dup) {
        (Ok(b), Ok(d)) => {
            let cb = canon_constraints(&b.constraints);
            let cd = canon_constraints(&d.constraints);
            assert_eq!(
                cb, cd,
                "appending an exact duplicate DiffPair/LayerRestriction changed \
                 rewrite()'s fixed point: seed={seed}\n\
                 base:           {cb:?}\n\
                 with duplicate: {cd:?}"
            );
        }
        (Err(eb), Err(ed)) => assert_eq!(
            eb, ed,
            "the duplicate-constraint model errored differently than the base model: \
             seed={seed}"
        ),
        _ => panic!(
            "appending a duplicate constraint changed rewrite() from Ok to Err (or vice \
             versa): seed={seed} base_is_ok={} dup_is_ok={}",
            base.is_ok(),
            dup.is_ok()
        ),
    }
}

/// A model containing exactly one RW7 conflict (`LayerRestriction
/// ("conflict_var", true)` and `LayerRestriction("conflict_var", false)`),
/// plus 0-5 unrelated filler constraints on disjoint variable/channel
/// names, all Fisher-Yates shuffled together -- so the conflicting pair
/// lands at an unpredictable position and in an unpredictable relative
/// order across seeds.
fn rw_gen_conflict_model(seed: u64) -> InternalConstraintModel {
    let mut rng = SplitMix64::new(seed);
    let mut constraints = vec![
        InternalConstraint::LayerRestriction { var_name: "conflict_var".into(), allowed: true },
        InternalConstraint::LayerRestriction { var_name: "conflict_var".into(), allowed: false },
    ];

    let n_filler = rng.index(6); // 0..=5
    for i in 0..n_filler {
        let var = format!("filler_v{i}");
        match rng.index(3) {
            0 => constraints.push(InternalConstraint::LayerRestriction {
                var_name: var,
                allowed: rng.next_f64() < 0.5,
            }),
            1 => constraints.push(InternalConstraint::DiffPair {
                channel_id: format!("filler_ch{i}"),
                p_var_name: format!("{var}_p"),
                n_var_name: format!("{var}_n"),
            }),
            _ => constraints.push(InternalConstraint::Capacity {
                channel_id: format!("filler_ch{i}"),
                capacity: rng.range(1.0, 20.0),
                slack_factor: rng.range(0.5, 2.0),
                terms: vec![(var, rng.range(0.5, 5.0))],
            }),
        }
    }

    let n = constraints.len();
    for i in (1..n).rev() {
        let j = rng.index(i + 1);
        constraints.swap(i, j);
    }

    InternalConstraintModel { variables: Vec::new(), constraints }
}

/// `rewrite()` must detect an RW7 `LayerRestriction` conflict regardless of
/// where the two conflicting constraints land after shuffling, or which
/// one appears first: `detect_layer_conflict` scans the whole list with two
/// `HashSet`s and reports as soon as either direction is seen, which is
/// order-independent by construction. This is the metamorphic pair to
/// `rw_idempotent_impl`/`rw_duplicate_invariant_impl` above: those two
/// establish that reordering *shouldn't* matter for the surviving
/// constraint set, this one establishes it *doesn't* matter for conflict
/// detection either.
///
/// Bug this would catch: this is the property purpose-built to catch an
/// order-*dependent* regression -- e.g. dropping the `false`-branch's
/// `true_vars.contains(var_name)` check (or its `true`-branch mirror) would
/// only catch the conflict when the constraints appear in one specific
/// relative order, and this property shuffles that order across seeds.
pub(crate) fn rw_conflict_order_independent_impl(seed: u64) {
    let model = rw_gen_conflict_model(seed);
    match rewrite(&model) {
        Err(RewriteError::UnsatPreSolve { var_name, .. }) => {
            assert_eq!(
                var_name, "conflict_var",
                "rewrite() reported a structural conflict on the wrong variable: seed={seed}"
            );
        }
        Ok(_) => panic!(
            "rewrite() did not detect the structural LayerRestriction(conflict_var, \
             true/false) conflict after shuffling: seed={seed}"
        ),
        Err(other) => panic!(
            "rewrite() returned an unexpected error variant instead of UnsatPreSolve: \
             seed={seed} error={other:?}"
        ),
    }
}

// ===========================================================================
// Kernel 3: astar.rs -- `astar_kernel_3d`, the 8-connected grid A* used for
// congestion/thermal-aware routing.
// ===========================================================================

use crate::astar::{astar_kernel_3d, AstarInput};

/// Generous relative to any grid this module generates (<=10x10=100 cells),
/// so no property below can be confounded by hitting the iteration cap --
/// that failure mode is `test_iteration_cap_respected`'s job, not this
/// module's.
const AS_MAX_ITERATIONS: u64 = 200_000;

/// An open (or mostly open) `rows`x`cols` grid, 4-10 per side, with 0..25%
/// of non-start/goal cells having their 8 *outgoing* validity bits cleared
/// (mirroring the hand-written `make_validity` test helper's blocking
/// convention: validity gates moves *out of* a cell, not moves *into* it).
/// Returns `(rows, cols, validity, start, goal, blocked)` so callers can
/// build a strict superset of `validity` by restoring some of `blocked`.
fn as_gen_base(seed: u64) -> (usize, usize, Vec<u8>, i64, i64, Vec<usize>) {
    let mut rng = SplitMix64::new(seed);
    let rows = 5 + rng.index(6); // 5..=10
    let cols = 5 + rng.index(6); // 5..=10
    let n_cells = rows * cols;

    let start = rng.index(n_cells);
    let goal = (start + 1 + rng.index(n_cells - 1)) % n_cells;

    let mut validity = vec![1u8; n_cells * 8];
    let max_blocked = (n_cells / 4).max(1);
    let n_blocked = rng.index(max_blocked + 1);
    let mut blocked = Vec::with_capacity(n_blocked);
    let mut tries = 0;
    while blocked.len() < n_blocked && tries < n_blocked * 8 + 32 {
        tries += 1;
        let b = rng.index(n_cells);
        if b != start && b != goal && !blocked.contains(&b) {
            blocked.push(b);
            for d in 0..8 {
                validity[b * 8 + d] = 0;
            }
        }
    }

    (rows, cols, validity, start as i64, goal as i64, blocked)
}

fn as_input<'a>(rows: usize, cols: usize, validity: &'a [u8], start: i64, goal: i64) -> AstarInput<'a> {
    AstarInput {
        start_idx: start,
        goal_idx: goal,
        rows,
        cols,
        validity,
        max_iterations: AS_MAX_ITERATIONS,
        congestion: None,
        congestion_weight: 0.0,
        max_congestion_cost: 100.0,
        thermal: None,
        thermal_weight: 0.0,
    }
}

/// `astar_kernel_3d`'s documented 8-connected neighbor order (module doc:
/// "E, SE, S, SW, W, NW, N, NE"), as a `(dcol, drow) -> direction index`
/// lookup independent of the kernel's own internal `match` -- this is the
/// crate's committed external contract (the module doc states the order
/// explicitly as a faithfulness requirement to the retired JIT kernel), not
/// an implementation accident, so re-stating it here to check the kernel's
/// *output* against is a legitimate independent oracle.
fn as_direction_index(dcol: i64, drow: i64) -> Option<usize> {
    match (dcol, drow) {
        (1, 0) => Some(0),
        (1, 1) => Some(1),
        (0, 1) => Some(2),
        (-1, 1) => Some(3),
        (-1, 0) => Some(4),
        (-1, -1) => Some(5),
        (0, -1) => Some(6),
        (1, -1) => Some(7),
        _ => None,
    }
}

/// `astar_kernel_3d` must be stable under re-running: calling it twice on
/// byte-identical input must produce a byte-identical `AstarOutput`. There
/// is no hidden state, clock, or entropy in its signature, so this is a
/// direct claim, not an assumption -- and it is the same "stable under
/// re-running" property this crate's `order_nets`-shaped sibling kernels
/// are asked for (see this PR's description), applied to the kernel that
/// actually exists in this crate.
///
/// Bug this would catch: any accidental read of non-deterministic state --
/// e.g. a future change that seeds the heap tie-break from something other
/// than pure insertion order -- would make two calls disagree whenever the
/// search visits a real tie.
pub(crate) fn as_determinism_impl(seed: u64) {
    let (rows, cols, validity, start, goal, _blocked) = as_gen_base(seed);
    let input = as_input(rows, cols, &validity, start, goal);
    let out1 = astar_kernel_3d(&input);
    let out2 = astar_kernel_3d(&input);
    assert_eq!(
        out1.path, out2.path,
        "astar_kernel_3d returned different paths for the same input: seed={seed}"
    );
    assert_eq!(
        out1.iterations, out2.iterations,
        "astar_kernel_3d returned different iteration counts for the same input: seed={seed}"
    );
}

/// A returned path must be a genuine walk through the *input* validity
/// tensor: it starts at `start`, ends at `goal`, every consecutive pair is
/// an 8-connected step whose direction bit is actually set in `validity`
/// (checked via the kernel's own documented, fixed direction table --
/// [`as_direction_index`] -- not by re-deriving costs or re-running the
/// search), stays in-bounds, and never revisits a cell. This is checked
/// independently of `astar_kernel_3d`'s own heap/cost machinery.
///
/// Bug this would catch: an off-by-one in the neighbor delta table (e.g.
/// swapping the SE/SW deltas), a validity index computed from the wrong
/// cell (neighbor's bit instead of the current cell's), or a path
/// reconstruction bug that revisits a `came_from` cycle.
pub(crate) fn as_path_validity_impl(seed: u64) {
    let (rows, cols, validity, start, goal, _blocked) = as_gen_base(seed);
    let input = as_input(rows, cols, &validity, start, goal);
    let out = astar_kernel_3d(&input);
    if out.path.is_empty() {
        return;
    }

    assert_eq!(out.path[0], start as i32, "path does not start at start_idx: seed={seed}");
    assert_eq!(
        out.path[out.path.len() - 1],
        goal as i32,
        "path does not end at goal_idx: seed={seed}"
    );

    let mut seen: std::collections::HashSet<i32> = std::collections::HashSet::new();
    for &cell in &out.path {
        assert!(
            cell >= 0 && (cell as usize) < rows * cols,
            "path cell {cell} out of bounds: seed={seed}"
        );
        assert!(seen.insert(cell), "path revisits cell {cell}: seed={seed}");
    }

    for w in out.path.windows(2) {
        let (a, b) = (w[0], w[1]);
        let (ar, ac) = (a as i64 / cols as i64, a as i64 % cols as i64);
        let (br, bc) = (b as i64 / cols as i64, b as i64 % cols as i64);
        let (dcol, drow) = (bc - ac, br - ar);
        match as_direction_index(dcol, drow) {
            Some(dir) => {
                let bit = validity.get(a as usize * 8 + dir).copied().unwrap_or(0);
                assert!(
                    bit != 0,
                    "path step {a}->{b} uses direction {dir} but the input validity bit \
                     is clear: seed={seed}"
                );
            }
            None => panic!(
                "path step {a}->{b} (dcol={dcol}, drow={drow}) is not an 8-connected \
                 move: seed={seed}"
            ),
        }
    }
}

/// Reachability is monotonic in the validity tensor: if a path exists under
/// `validity`, one must still exist under any strict superset `validity'`
/// (every bit set in `validity` also set in `validity'`) with the same
/// grid/start/goal, because the graph `astar_kernel_3d` searches is a
/// literal subgraph of the one it searches under `validity'` -- the exact
/// same path is still available, so a complete search (generous
/// `max_iterations`, see [`AS_MAX_ITERATIONS`]) cannot fail to find *a*
/// path.
///
/// Bug this would catch: any search-completeness regression -- e.g. an
/// incorrect `closed` re-visit check that permanently locks out a cell
/// needed only once obstacles are removed, or a heap comparison bug that
/// starves a branch of the search space -- independent of whether the
/// *specific* path found changes.
pub(crate) fn as_monotonic_reachability_impl(seed: u64) {
    let (rows, cols, validity, start, goal, blocked) = as_gen_base(seed);
    let base_input = as_input(rows, cols, &validity, start, goal);
    let base_out = astar_kernel_3d(&base_input);
    if base_out.path.is_empty() {
        return;
    }

    let mut wider_rng = sub_rng(seed, 0xF1);
    let mut wider_validity = validity.clone();
    if !blocked.is_empty() {
        let n_unblock = 1 + wider_rng.index(blocked.len());
        for &b in blocked.iter().take(n_unblock) {
            for d in 0..8 {
                wider_validity[b * 8 + d] = 1;
            }
        }
    }

    let wider_input = as_input(rows, cols, &wider_validity, start, goal);
    let wider_out = astar_kernel_3d(&wider_input);
    assert!(
        !wider_out.path.is_empty(),
        "astar_kernel_3d lost reachability after obstacles were only REMOVED (a strict \
         superset of valid moves): seed={seed} start={start} goal={goal} rows={rows} \
         cols={cols}"
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
        let mut a = SplitMix64::new(42);
        let mut b = SplitMix64::new(42);
        for _ in 0..8 {
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
    fn pr_gen_net_length_in_expected_range() {
        for seed in [0u64, 7, 999_999] {
            let mut rng = SplitMix64::new(seed);
            let net = pr_gen_net_from(&mut rng);
            assert!((1..=6).contains(&net.positions.len()), "seed={seed}");
            for &(x, y) in &net.positions {
                assert!((0.0..200.0).contains(&x), "seed={seed} x={x}");
                assert!((0.0..200.0).contains(&y), "seed={seed} y={y}");
            }
        }
    }

    #[cfg_attr(test, test)]
    fn pr_euclidean_mst_has_n_minus_one_edges() {
        let pts = vec![(0.0, 0.0), (10.0, 0.0), (10.0, 10.0), (0.0, 10.0), (5.0, 5.0)];
        let edges = pr_euclidean_mst(&pts);
        assert_eq!(edges.len(), pts.len() - 1);
    }

    #[cfg_attr(test, test)]
    fn rw_choose_subset_returns_distinct_in_range_indices() {
        let mut rng = SplitMix64::new(123);
        let sel = rw_choose_subset(&mut rng, 5, 3);
        assert_eq!(sel.len(), 3);
        let mut sorted = sel.clone();
        sorted.sort_unstable();
        sorted.dedup();
        assert_eq!(sorted.len(), 3, "expected distinct indices, got {sel:?}");
        assert!(sel.iter().all(|&i| i < 5));
    }

    #[cfg_attr(test, test)]
    fn canon_constraints_is_order_independent() {
        let a = vec![
            InternalConstraint::LayerRestriction { var_name: "x".into(), allowed: true },
            InternalConstraint::DiffPair {
                channel_id: "ch0".into(),
                p_var_name: "x".into(),
                n_var_name: "y".into(),
            },
        ];
        let mut b = a.clone();
        b.reverse();
        assert_eq!(canon_constraints(&a), canon_constraints(&b));
    }

    #[cfg_attr(test, test)]
    fn rw_gen_model_never_produces_a_layer_conflict() {
        for seed in [0u64, 11, 5000, 999_999] {
            let model = rw_gen_model(seed);
            assert!(
                rewrite(&model).is_ok(),
                "seed={seed} unexpectedly produced an RW7 conflict"
            );
        }
    }

    #[cfg_attr(test, test)]
    fn rw_gen_conflict_model_always_conflicts() {
        for seed in [0u64, 11, 5000, 999_999] {
            let model = rw_gen_conflict_model(seed);
            match rewrite(&model) {
                Err(RewriteError::UnsatPreSolve { var_name, .. }) => {
                    assert_eq!(var_name, "conflict_var", "seed={seed}");
                }
                other => panic!("seed={seed} expected UnsatPreSolve, got {other:?}"),
            }
        }
    }

    #[cfg_attr(test, test)]
    fn as_gen_base_dims_and_endpoints_in_range() {
        for seed in [0u64, 3, 12345] {
            let (rows, cols, validity, start, goal, _blocked) = as_gen_base(seed);
            assert_eq!(validity.len(), rows * cols * 8);
            assert!((5..=10).contains(&rows), "seed={seed} rows={rows}");
            assert!((5..=10).contains(&cols), "seed={seed} cols={cols}");
            assert_ne!(start, goal, "seed={seed}");
            assert!(start >= 0 && (start as usize) < rows * cols, "seed={seed}");
            assert!(goal >= 0 && (goal as usize) < rows * cols, "seed={seed}");
        }
    }

    #[cfg_attr(test, test)]
    fn as_direction_index_matches_the_documented_table() {
        assert_eq!(as_direction_index(1, 0), Some(0));
        assert_eq!(as_direction_index(1, 1), Some(1));
        assert_eq!(as_direction_index(0, 1), Some(2));
        assert_eq!(as_direction_index(-1, 1), Some(3));
        assert_eq!(as_direction_index(-1, 0), Some(4));
        assert_eq!(as_direction_index(-1, -1), Some(5));
        assert_eq!(as_direction_index(0, -1), Some(6));
        assert_eq!(as_direction_index(1, -1), Some(7));
        assert_eq!(as_direction_index(0, 0), None);
        assert_eq!(as_direction_index(2, 0), None);
    }

    // --- pr_monotonic_params: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000000() { pr_monotonic_params_impl(0); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000001() { pr_monotonic_params_impl(1); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000002() { pr_monotonic_params_impl(2); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000003() { pr_monotonic_params_impl(3); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000004() { pr_monotonic_params_impl(4); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000005() { pr_monotonic_params_impl(5); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000006() { pr_monotonic_params_impl(6); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000007() { pr_monotonic_params_impl(7); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000008() { pr_monotonic_params_impl(8); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000009() { pr_monotonic_params_impl(9); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000010() { pr_monotonic_params_impl(10); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000011() { pr_monotonic_params_impl(11); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000012() { pr_monotonic_params_impl(12); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000013() { pr_monotonic_params_impl(13); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000014() { pr_monotonic_params_impl(14); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000015() { pr_monotonic_params_impl(15); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000016() { pr_monotonic_params_impl(16); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000017() { pr_monotonic_params_impl(17); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000018() { pr_monotonic_params_impl(18); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000019() { pr_monotonic_params_impl(19); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000020() { pr_monotonic_params_impl(20); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000021() { pr_monotonic_params_impl(21); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000022() { pr_monotonic_params_impl(22); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000023() { pr_monotonic_params_impl(23); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000024() { pr_monotonic_params_impl(24); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000025() { pr_monotonic_params_impl(25); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000026() { pr_monotonic_params_impl(26); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000027() { pr_monotonic_params_impl(27); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000028() { pr_monotonic_params_impl(28); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000029() { pr_monotonic_params_impl(29); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000030() { pr_monotonic_params_impl(30); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000031() { pr_monotonic_params_impl(31); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000032() { pr_monotonic_params_impl(32); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000033() { pr_monotonic_params_impl(33); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000034() { pr_monotonic_params_impl(34); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000035() { pr_monotonic_params_impl(35); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000036() { pr_monotonic_params_impl(36); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000037() { pr_monotonic_params_impl(37); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000038() { pr_monotonic_params_impl(38); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000039() { pr_monotonic_params_impl(39); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000040() { pr_monotonic_params_impl(40); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000041() { pr_monotonic_params_impl(41); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000042() { pr_monotonic_params_impl(42); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000043() { pr_monotonic_params_impl(43); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000044() { pr_monotonic_params_impl(44); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000045() { pr_monotonic_params_impl(45); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000046() { pr_monotonic_params_impl(46); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000047() { pr_monotonic_params_impl(47); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000048() { pr_monotonic_params_impl(48); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000049() { pr_monotonic_params_impl(49); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000050() { pr_monotonic_params_impl(50); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000051() { pr_monotonic_params_impl(51); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000052() { pr_monotonic_params_impl(52); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000053() { pr_monotonic_params_impl(53); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000054() { pr_monotonic_params_impl(54); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000055() { pr_monotonic_params_impl(55); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000056() { pr_monotonic_params_impl(56); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000057() { pr_monotonic_params_impl(57); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000058() { pr_monotonic_params_impl(58); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000059() { pr_monotonic_params_impl(59); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000060() { pr_monotonic_params_impl(60); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000061() { pr_monotonic_params_impl(61); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000062() { pr_monotonic_params_impl(62); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000063() { pr_monotonic_params_impl(63); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000064() { pr_monotonic_params_impl(64); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000065() { pr_monotonic_params_impl(65); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000066() { pr_monotonic_params_impl(66); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000067() { pr_monotonic_params_impl(67); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000068() { pr_monotonic_params_impl(68); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000069() { pr_monotonic_params_impl(69); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000070() { pr_monotonic_params_impl(70); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000071() { pr_monotonic_params_impl(71); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000072() { pr_monotonic_params_impl(72); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000073() { pr_monotonic_params_impl(73); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000074() { pr_monotonic_params_impl(74); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000075() { pr_monotonic_params_impl(75); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000076() { pr_monotonic_params_impl(76); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000077() { pr_monotonic_params_impl(77); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000078() { pr_monotonic_params_impl(78); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000079() { pr_monotonic_params_impl(79); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000080() { pr_monotonic_params_impl(80); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000081() { pr_monotonic_params_impl(81); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000082() { pr_monotonic_params_impl(82); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000083() { pr_monotonic_params_impl(83); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000084() { pr_monotonic_params_impl(84); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000085() { pr_monotonic_params_impl(85); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000086() { pr_monotonic_params_impl(86); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000087() { pr_monotonic_params_impl(87); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000088() { pr_monotonic_params_impl(88); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000089() { pr_monotonic_params_impl(89); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000090() { pr_monotonic_params_impl(90); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000091() { pr_monotonic_params_impl(91); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000092() { pr_monotonic_params_impl(92); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000093() { pr_monotonic_params_impl(93); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000094() { pr_monotonic_params_impl(94); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000095() { pr_monotonic_params_impl(95); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000096() { pr_monotonic_params_impl(96); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000097() { pr_monotonic_params_impl(97); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000098() { pr_monotonic_params_impl(98); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000099() { pr_monotonic_params_impl(99); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000100() { pr_monotonic_params_impl(100); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000101() { pr_monotonic_params_impl(101); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000102() { pr_monotonic_params_impl(102); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000103() { pr_monotonic_params_impl(103); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000104() { pr_monotonic_params_impl(104); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000105() { pr_monotonic_params_impl(105); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000106() { pr_monotonic_params_impl(106); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000107() { pr_monotonic_params_impl(107); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000108() { pr_monotonic_params_impl(108); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000109() { pr_monotonic_params_impl(109); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000110() { pr_monotonic_params_impl(110); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000111() { pr_monotonic_params_impl(111); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000112() { pr_monotonic_params_impl(112); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000113() { pr_monotonic_params_impl(113); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000114() { pr_monotonic_params_impl(114); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000115() { pr_monotonic_params_impl(115); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000116() { pr_monotonic_params_impl(116); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000117() { pr_monotonic_params_impl(117); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000118() { pr_monotonic_params_impl(118); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000119() { pr_monotonic_params_impl(119); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000120() { pr_monotonic_params_impl(120); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000121() { pr_monotonic_params_impl(121); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000122() { pr_monotonic_params_impl(122); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000123() { pr_monotonic_params_impl(123); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000124() { pr_monotonic_params_impl(124); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000125() { pr_monotonic_params_impl(125); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000126() { pr_monotonic_params_impl(126); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000127() { pr_monotonic_params_impl(127); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000128() { pr_monotonic_params_impl(128); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000129() { pr_monotonic_params_impl(129); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000130() { pr_monotonic_params_impl(130); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000131() { pr_monotonic_params_impl(131); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000132() { pr_monotonic_params_impl(132); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000133() { pr_monotonic_params_impl(133); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000134() { pr_monotonic_params_impl(134); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000135() { pr_monotonic_params_impl(135); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000136() { pr_monotonic_params_impl(136); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000137() { pr_monotonic_params_impl(137); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000138() { pr_monotonic_params_impl(138); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000139() { pr_monotonic_params_impl(139); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000140() { pr_monotonic_params_impl(140); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000141() { pr_monotonic_params_impl(141); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000142() { pr_monotonic_params_impl(142); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000143() { pr_monotonic_params_impl(143); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000144() { pr_monotonic_params_impl(144); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000145() { pr_monotonic_params_impl(145); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000146() { pr_monotonic_params_impl(146); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000147() { pr_monotonic_params_impl(147); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000148() { pr_monotonic_params_impl(148); }
    #[cfg_attr(test, test)]
    fn pr_monotonic_params_seed_000149() { pr_monotonic_params_impl(149); }

    // --- pr_symmetric_endpoints: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000000() { pr_symmetric_endpoints_impl(0); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000001() { pr_symmetric_endpoints_impl(1); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000002() { pr_symmetric_endpoints_impl(2); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000003() { pr_symmetric_endpoints_impl(3); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000004() { pr_symmetric_endpoints_impl(4); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000005() { pr_symmetric_endpoints_impl(5); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000006() { pr_symmetric_endpoints_impl(6); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000007() { pr_symmetric_endpoints_impl(7); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000008() { pr_symmetric_endpoints_impl(8); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000009() { pr_symmetric_endpoints_impl(9); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000010() { pr_symmetric_endpoints_impl(10); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000011() { pr_symmetric_endpoints_impl(11); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000012() { pr_symmetric_endpoints_impl(12); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000013() { pr_symmetric_endpoints_impl(13); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000014() { pr_symmetric_endpoints_impl(14); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000015() { pr_symmetric_endpoints_impl(15); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000016() { pr_symmetric_endpoints_impl(16); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000017() { pr_symmetric_endpoints_impl(17); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000018() { pr_symmetric_endpoints_impl(18); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000019() { pr_symmetric_endpoints_impl(19); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000020() { pr_symmetric_endpoints_impl(20); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000021() { pr_symmetric_endpoints_impl(21); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000022() { pr_symmetric_endpoints_impl(22); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000023() { pr_symmetric_endpoints_impl(23); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000024() { pr_symmetric_endpoints_impl(24); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000025() { pr_symmetric_endpoints_impl(25); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000026() { pr_symmetric_endpoints_impl(26); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000027() { pr_symmetric_endpoints_impl(27); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000028() { pr_symmetric_endpoints_impl(28); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000029() { pr_symmetric_endpoints_impl(29); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000030() { pr_symmetric_endpoints_impl(30); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000031() { pr_symmetric_endpoints_impl(31); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000032() { pr_symmetric_endpoints_impl(32); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000033() { pr_symmetric_endpoints_impl(33); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000034() { pr_symmetric_endpoints_impl(34); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000035() { pr_symmetric_endpoints_impl(35); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000036() { pr_symmetric_endpoints_impl(36); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000037() { pr_symmetric_endpoints_impl(37); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000038() { pr_symmetric_endpoints_impl(38); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000039() { pr_symmetric_endpoints_impl(39); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000040() { pr_symmetric_endpoints_impl(40); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000041() { pr_symmetric_endpoints_impl(41); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000042() { pr_symmetric_endpoints_impl(42); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000043() { pr_symmetric_endpoints_impl(43); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000044() { pr_symmetric_endpoints_impl(44); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000045() { pr_symmetric_endpoints_impl(45); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000046() { pr_symmetric_endpoints_impl(46); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000047() { pr_symmetric_endpoints_impl(47); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000048() { pr_symmetric_endpoints_impl(48); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000049() { pr_symmetric_endpoints_impl(49); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000050() { pr_symmetric_endpoints_impl(50); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000051() { pr_symmetric_endpoints_impl(51); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000052() { pr_symmetric_endpoints_impl(52); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000053() { pr_symmetric_endpoints_impl(53); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000054() { pr_symmetric_endpoints_impl(54); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000055() { pr_symmetric_endpoints_impl(55); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000056() { pr_symmetric_endpoints_impl(56); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000057() { pr_symmetric_endpoints_impl(57); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000058() { pr_symmetric_endpoints_impl(58); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000059() { pr_symmetric_endpoints_impl(59); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000060() { pr_symmetric_endpoints_impl(60); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000061() { pr_symmetric_endpoints_impl(61); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000062() { pr_symmetric_endpoints_impl(62); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000063() { pr_symmetric_endpoints_impl(63); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000064() { pr_symmetric_endpoints_impl(64); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000065() { pr_symmetric_endpoints_impl(65); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000066() { pr_symmetric_endpoints_impl(66); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000067() { pr_symmetric_endpoints_impl(67); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000068() { pr_symmetric_endpoints_impl(68); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000069() { pr_symmetric_endpoints_impl(69); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000070() { pr_symmetric_endpoints_impl(70); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000071() { pr_symmetric_endpoints_impl(71); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000072() { pr_symmetric_endpoints_impl(72); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000073() { pr_symmetric_endpoints_impl(73); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000074() { pr_symmetric_endpoints_impl(74); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000075() { pr_symmetric_endpoints_impl(75); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000076() { pr_symmetric_endpoints_impl(76); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000077() { pr_symmetric_endpoints_impl(77); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000078() { pr_symmetric_endpoints_impl(78); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000079() { pr_symmetric_endpoints_impl(79); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000080() { pr_symmetric_endpoints_impl(80); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000081() { pr_symmetric_endpoints_impl(81); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000082() { pr_symmetric_endpoints_impl(82); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000083() { pr_symmetric_endpoints_impl(83); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000084() { pr_symmetric_endpoints_impl(84); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000085() { pr_symmetric_endpoints_impl(85); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000086() { pr_symmetric_endpoints_impl(86); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000087() { pr_symmetric_endpoints_impl(87); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000088() { pr_symmetric_endpoints_impl(88); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000089() { pr_symmetric_endpoints_impl(89); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000090() { pr_symmetric_endpoints_impl(90); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000091() { pr_symmetric_endpoints_impl(91); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000092() { pr_symmetric_endpoints_impl(92); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000093() { pr_symmetric_endpoints_impl(93); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000094() { pr_symmetric_endpoints_impl(94); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000095() { pr_symmetric_endpoints_impl(95); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000096() { pr_symmetric_endpoints_impl(96); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000097() { pr_symmetric_endpoints_impl(97); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000098() { pr_symmetric_endpoints_impl(98); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000099() { pr_symmetric_endpoints_impl(99); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000100() { pr_symmetric_endpoints_impl(100); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000101() { pr_symmetric_endpoints_impl(101); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000102() { pr_symmetric_endpoints_impl(102); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000103() { pr_symmetric_endpoints_impl(103); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000104() { pr_symmetric_endpoints_impl(104); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000105() { pr_symmetric_endpoints_impl(105); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000106() { pr_symmetric_endpoints_impl(106); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000107() { pr_symmetric_endpoints_impl(107); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000108() { pr_symmetric_endpoints_impl(108); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000109() { pr_symmetric_endpoints_impl(109); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000110() { pr_symmetric_endpoints_impl(110); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000111() { pr_symmetric_endpoints_impl(111); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000112() { pr_symmetric_endpoints_impl(112); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000113() { pr_symmetric_endpoints_impl(113); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000114() { pr_symmetric_endpoints_impl(114); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000115() { pr_symmetric_endpoints_impl(115); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000116() { pr_symmetric_endpoints_impl(116); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000117() { pr_symmetric_endpoints_impl(117); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000118() { pr_symmetric_endpoints_impl(118); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000119() { pr_symmetric_endpoints_impl(119); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000120() { pr_symmetric_endpoints_impl(120); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000121() { pr_symmetric_endpoints_impl(121); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000122() { pr_symmetric_endpoints_impl(122); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000123() { pr_symmetric_endpoints_impl(123); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000124() { pr_symmetric_endpoints_impl(124); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000125() { pr_symmetric_endpoints_impl(125); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000126() { pr_symmetric_endpoints_impl(126); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000127() { pr_symmetric_endpoints_impl(127); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000128() { pr_symmetric_endpoints_impl(128); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000129() { pr_symmetric_endpoints_impl(129); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000130() { pr_symmetric_endpoints_impl(130); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000131() { pr_symmetric_endpoints_impl(131); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000132() { pr_symmetric_endpoints_impl(132); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000133() { pr_symmetric_endpoints_impl(133); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000134() { pr_symmetric_endpoints_impl(134); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000135() { pr_symmetric_endpoints_impl(135); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000136() { pr_symmetric_endpoints_impl(136); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000137() { pr_symmetric_endpoints_impl(137); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000138() { pr_symmetric_endpoints_impl(138); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000139() { pr_symmetric_endpoints_impl(139); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000140() { pr_symmetric_endpoints_impl(140); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000141() { pr_symmetric_endpoints_impl(141); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000142() { pr_symmetric_endpoints_impl(142); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000143() { pr_symmetric_endpoints_impl(143); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000144() { pr_symmetric_endpoints_impl(144); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000145() { pr_symmetric_endpoints_impl(145); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000146() { pr_symmetric_endpoints_impl(146); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000147() { pr_symmetric_endpoints_impl(147); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000148() { pr_symmetric_endpoints_impl(148); }
    #[cfg_attr(test, test)]
    fn pr_symmetric_endpoints_seed_000149() { pr_symmetric_endpoints_impl(149); }

    // --- pr_emst_soundness: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000000() { pr_emst_soundness_impl(0); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000001() { pr_emst_soundness_impl(1); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000002() { pr_emst_soundness_impl(2); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000003() { pr_emst_soundness_impl(3); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000004() { pr_emst_soundness_impl(4); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000005() { pr_emst_soundness_impl(5); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000006() { pr_emst_soundness_impl(6); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000007() { pr_emst_soundness_impl(7); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000008() { pr_emst_soundness_impl(8); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000009() { pr_emst_soundness_impl(9); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000010() { pr_emst_soundness_impl(10); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000011() { pr_emst_soundness_impl(11); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000012() { pr_emst_soundness_impl(12); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000013() { pr_emst_soundness_impl(13); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000014() { pr_emst_soundness_impl(14); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000015() { pr_emst_soundness_impl(15); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000016() { pr_emst_soundness_impl(16); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000017() { pr_emst_soundness_impl(17); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000018() { pr_emst_soundness_impl(18); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000019() { pr_emst_soundness_impl(19); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000020() { pr_emst_soundness_impl(20); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000021() { pr_emst_soundness_impl(21); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000022() { pr_emst_soundness_impl(22); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000023() { pr_emst_soundness_impl(23); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000024() { pr_emst_soundness_impl(24); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000025() { pr_emst_soundness_impl(25); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000026() { pr_emst_soundness_impl(26); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000027() { pr_emst_soundness_impl(27); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000028() { pr_emst_soundness_impl(28); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000029() { pr_emst_soundness_impl(29); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000030() { pr_emst_soundness_impl(30); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000031() { pr_emst_soundness_impl(31); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000032() { pr_emst_soundness_impl(32); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000033() { pr_emst_soundness_impl(33); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000034() { pr_emst_soundness_impl(34); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000035() { pr_emst_soundness_impl(35); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000036() { pr_emst_soundness_impl(36); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000037() { pr_emst_soundness_impl(37); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000038() { pr_emst_soundness_impl(38); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000039() { pr_emst_soundness_impl(39); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000040() { pr_emst_soundness_impl(40); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000041() { pr_emst_soundness_impl(41); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000042() { pr_emst_soundness_impl(42); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000043() { pr_emst_soundness_impl(43); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000044() { pr_emst_soundness_impl(44); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000045() { pr_emst_soundness_impl(45); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000046() { pr_emst_soundness_impl(46); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000047() { pr_emst_soundness_impl(47); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000048() { pr_emst_soundness_impl(48); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000049() { pr_emst_soundness_impl(49); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000050() { pr_emst_soundness_impl(50); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000051() { pr_emst_soundness_impl(51); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000052() { pr_emst_soundness_impl(52); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000053() { pr_emst_soundness_impl(53); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000054() { pr_emst_soundness_impl(54); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000055() { pr_emst_soundness_impl(55); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000056() { pr_emst_soundness_impl(56); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000057() { pr_emst_soundness_impl(57); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000058() { pr_emst_soundness_impl(58); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000059() { pr_emst_soundness_impl(59); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000060() { pr_emst_soundness_impl(60); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000061() { pr_emst_soundness_impl(61); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000062() { pr_emst_soundness_impl(62); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000063() { pr_emst_soundness_impl(63); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000064() { pr_emst_soundness_impl(64); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000065() { pr_emst_soundness_impl(65); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000066() { pr_emst_soundness_impl(66); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000067() { pr_emst_soundness_impl(67); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000068() { pr_emst_soundness_impl(68); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000069() { pr_emst_soundness_impl(69); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000070() { pr_emst_soundness_impl(70); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000071() { pr_emst_soundness_impl(71); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000072() { pr_emst_soundness_impl(72); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000073() { pr_emst_soundness_impl(73); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000074() { pr_emst_soundness_impl(74); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000075() { pr_emst_soundness_impl(75); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000076() { pr_emst_soundness_impl(76); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000077() { pr_emst_soundness_impl(77); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000078() { pr_emst_soundness_impl(78); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000079() { pr_emst_soundness_impl(79); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000080() { pr_emst_soundness_impl(80); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000081() { pr_emst_soundness_impl(81); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000082() { pr_emst_soundness_impl(82); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000083() { pr_emst_soundness_impl(83); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000084() { pr_emst_soundness_impl(84); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000085() { pr_emst_soundness_impl(85); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000086() { pr_emst_soundness_impl(86); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000087() { pr_emst_soundness_impl(87); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000088() { pr_emst_soundness_impl(88); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000089() { pr_emst_soundness_impl(89); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000090() { pr_emst_soundness_impl(90); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000091() { pr_emst_soundness_impl(91); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000092() { pr_emst_soundness_impl(92); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000093() { pr_emst_soundness_impl(93); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000094() { pr_emst_soundness_impl(94); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000095() { pr_emst_soundness_impl(95); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000096() { pr_emst_soundness_impl(96); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000097() { pr_emst_soundness_impl(97); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000098() { pr_emst_soundness_impl(98); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000099() { pr_emst_soundness_impl(99); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000100() { pr_emst_soundness_impl(100); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000101() { pr_emst_soundness_impl(101); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000102() { pr_emst_soundness_impl(102); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000103() { pr_emst_soundness_impl(103); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000104() { pr_emst_soundness_impl(104); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000105() { pr_emst_soundness_impl(105); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000106() { pr_emst_soundness_impl(106); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000107() { pr_emst_soundness_impl(107); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000108() { pr_emst_soundness_impl(108); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000109() { pr_emst_soundness_impl(109); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000110() { pr_emst_soundness_impl(110); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000111() { pr_emst_soundness_impl(111); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000112() { pr_emst_soundness_impl(112); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000113() { pr_emst_soundness_impl(113); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000114() { pr_emst_soundness_impl(114); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000115() { pr_emst_soundness_impl(115); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000116() { pr_emst_soundness_impl(116); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000117() { pr_emst_soundness_impl(117); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000118() { pr_emst_soundness_impl(118); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000119() { pr_emst_soundness_impl(119); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000120() { pr_emst_soundness_impl(120); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000121() { pr_emst_soundness_impl(121); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000122() { pr_emst_soundness_impl(122); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000123() { pr_emst_soundness_impl(123); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000124() { pr_emst_soundness_impl(124); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000125() { pr_emst_soundness_impl(125); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000126() { pr_emst_soundness_impl(126); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000127() { pr_emst_soundness_impl(127); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000128() { pr_emst_soundness_impl(128); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000129() { pr_emst_soundness_impl(129); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000130() { pr_emst_soundness_impl(130); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000131() { pr_emst_soundness_impl(131); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000132() { pr_emst_soundness_impl(132); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000133() { pr_emst_soundness_impl(133); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000134() { pr_emst_soundness_impl(134); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000135() { pr_emst_soundness_impl(135); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000136() { pr_emst_soundness_impl(136); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000137() { pr_emst_soundness_impl(137); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000138() { pr_emst_soundness_impl(138); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000139() { pr_emst_soundness_impl(139); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000140() { pr_emst_soundness_impl(140); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000141() { pr_emst_soundness_impl(141); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000142() { pr_emst_soundness_impl(142); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000143() { pr_emst_soundness_impl(143); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000144() { pr_emst_soundness_impl(144); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000145() { pr_emst_soundness_impl(145); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000146() { pr_emst_soundness_impl(146); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000147() { pr_emst_soundness_impl(147); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000148() { pr_emst_soundness_impl(148); }
    #[cfg_attr(test, test)]
    fn pr_emst_soundness_seed_000149() { pr_emst_soundness_impl(149); }

    // --- rw_idempotent: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000000() { rw_idempotent_impl(0); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000001() { rw_idempotent_impl(1); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000002() { rw_idempotent_impl(2); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000003() { rw_idempotent_impl(3); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000004() { rw_idempotent_impl(4); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000005() { rw_idempotent_impl(5); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000006() { rw_idempotent_impl(6); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000007() { rw_idempotent_impl(7); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000008() { rw_idempotent_impl(8); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000009() { rw_idempotent_impl(9); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000010() { rw_idempotent_impl(10); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000011() { rw_idempotent_impl(11); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000012() { rw_idempotent_impl(12); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000013() { rw_idempotent_impl(13); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000014() { rw_idempotent_impl(14); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000015() { rw_idempotent_impl(15); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000016() { rw_idempotent_impl(16); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000017() { rw_idempotent_impl(17); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000018() { rw_idempotent_impl(18); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000019() { rw_idempotent_impl(19); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000020() { rw_idempotent_impl(20); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000021() { rw_idempotent_impl(21); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000022() { rw_idempotent_impl(22); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000023() { rw_idempotent_impl(23); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000024() { rw_idempotent_impl(24); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000025() { rw_idempotent_impl(25); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000026() { rw_idempotent_impl(26); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000027() { rw_idempotent_impl(27); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000028() { rw_idempotent_impl(28); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000029() { rw_idempotent_impl(29); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000030() { rw_idempotent_impl(30); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000031() { rw_idempotent_impl(31); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000032() { rw_idempotent_impl(32); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000033() { rw_idempotent_impl(33); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000034() { rw_idempotent_impl(34); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000035() { rw_idempotent_impl(35); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000036() { rw_idempotent_impl(36); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000037() { rw_idempotent_impl(37); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000038() { rw_idempotent_impl(38); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000039() { rw_idempotent_impl(39); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000040() { rw_idempotent_impl(40); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000041() { rw_idempotent_impl(41); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000042() { rw_idempotent_impl(42); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000043() { rw_idempotent_impl(43); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000044() { rw_idempotent_impl(44); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000045() { rw_idempotent_impl(45); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000046() { rw_idempotent_impl(46); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000047() { rw_idempotent_impl(47); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000048() { rw_idempotent_impl(48); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000049() { rw_idempotent_impl(49); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000050() { rw_idempotent_impl(50); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000051() { rw_idempotent_impl(51); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000052() { rw_idempotent_impl(52); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000053() { rw_idempotent_impl(53); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000054() { rw_idempotent_impl(54); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000055() { rw_idempotent_impl(55); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000056() { rw_idempotent_impl(56); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000057() { rw_idempotent_impl(57); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000058() { rw_idempotent_impl(58); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000059() { rw_idempotent_impl(59); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000060() { rw_idempotent_impl(60); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000061() { rw_idempotent_impl(61); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000062() { rw_idempotent_impl(62); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000063() { rw_idempotent_impl(63); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000064() { rw_idempotent_impl(64); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000065() { rw_idempotent_impl(65); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000066() { rw_idempotent_impl(66); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000067() { rw_idempotent_impl(67); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000068() { rw_idempotent_impl(68); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000069() { rw_idempotent_impl(69); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000070() { rw_idempotent_impl(70); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000071() { rw_idempotent_impl(71); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000072() { rw_idempotent_impl(72); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000073() { rw_idempotent_impl(73); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000074() { rw_idempotent_impl(74); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000075() { rw_idempotent_impl(75); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000076() { rw_idempotent_impl(76); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000077() { rw_idempotent_impl(77); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000078() { rw_idempotent_impl(78); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000079() { rw_idempotent_impl(79); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000080() { rw_idempotent_impl(80); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000081() { rw_idempotent_impl(81); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000082() { rw_idempotent_impl(82); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000083() { rw_idempotent_impl(83); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000084() { rw_idempotent_impl(84); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000085() { rw_idempotent_impl(85); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000086() { rw_idempotent_impl(86); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000087() { rw_idempotent_impl(87); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000088() { rw_idempotent_impl(88); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000089() { rw_idempotent_impl(89); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000090() { rw_idempotent_impl(90); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000091() { rw_idempotent_impl(91); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000092() { rw_idempotent_impl(92); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000093() { rw_idempotent_impl(93); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000094() { rw_idempotent_impl(94); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000095() { rw_idempotent_impl(95); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000096() { rw_idempotent_impl(96); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000097() { rw_idempotent_impl(97); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000098() { rw_idempotent_impl(98); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000099() { rw_idempotent_impl(99); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000100() { rw_idempotent_impl(100); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000101() { rw_idempotent_impl(101); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000102() { rw_idempotent_impl(102); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000103() { rw_idempotent_impl(103); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000104() { rw_idempotent_impl(104); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000105() { rw_idempotent_impl(105); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000106() { rw_idempotent_impl(106); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000107() { rw_idempotent_impl(107); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000108() { rw_idempotent_impl(108); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000109() { rw_idempotent_impl(109); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000110() { rw_idempotent_impl(110); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000111() { rw_idempotent_impl(111); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000112() { rw_idempotent_impl(112); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000113() { rw_idempotent_impl(113); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000114() { rw_idempotent_impl(114); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000115() { rw_idempotent_impl(115); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000116() { rw_idempotent_impl(116); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000117() { rw_idempotent_impl(117); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000118() { rw_idempotent_impl(118); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000119() { rw_idempotent_impl(119); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000120() { rw_idempotent_impl(120); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000121() { rw_idempotent_impl(121); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000122() { rw_idempotent_impl(122); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000123() { rw_idempotent_impl(123); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000124() { rw_idempotent_impl(124); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000125() { rw_idempotent_impl(125); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000126() { rw_idempotent_impl(126); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000127() { rw_idempotent_impl(127); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000128() { rw_idempotent_impl(128); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000129() { rw_idempotent_impl(129); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000130() { rw_idempotent_impl(130); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000131() { rw_idempotent_impl(131); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000132() { rw_idempotent_impl(132); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000133() { rw_idempotent_impl(133); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000134() { rw_idempotent_impl(134); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000135() { rw_idempotent_impl(135); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000136() { rw_idempotent_impl(136); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000137() { rw_idempotent_impl(137); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000138() { rw_idempotent_impl(138); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000139() { rw_idempotent_impl(139); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000140() { rw_idempotent_impl(140); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000141() { rw_idempotent_impl(141); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000142() { rw_idempotent_impl(142); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000143() { rw_idempotent_impl(143); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000144() { rw_idempotent_impl(144); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000145() { rw_idempotent_impl(145); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000146() { rw_idempotent_impl(146); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000147() { rw_idempotent_impl(147); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000148() { rw_idempotent_impl(148); }
    #[cfg_attr(test, test)]
    fn rw_idempotent_seed_000149() { rw_idempotent_impl(149); }

    // --- rw_duplicate_invariant: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000000() { rw_duplicate_invariant_impl(0); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000001() { rw_duplicate_invariant_impl(1); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000002() { rw_duplicate_invariant_impl(2); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000003() { rw_duplicate_invariant_impl(3); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000004() { rw_duplicate_invariant_impl(4); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000005() { rw_duplicate_invariant_impl(5); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000006() { rw_duplicate_invariant_impl(6); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000007() { rw_duplicate_invariant_impl(7); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000008() { rw_duplicate_invariant_impl(8); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000009() { rw_duplicate_invariant_impl(9); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000010() { rw_duplicate_invariant_impl(10); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000011() { rw_duplicate_invariant_impl(11); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000012() { rw_duplicate_invariant_impl(12); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000013() { rw_duplicate_invariant_impl(13); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000014() { rw_duplicate_invariant_impl(14); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000015() { rw_duplicate_invariant_impl(15); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000016() { rw_duplicate_invariant_impl(16); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000017() { rw_duplicate_invariant_impl(17); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000018() { rw_duplicate_invariant_impl(18); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000019() { rw_duplicate_invariant_impl(19); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000020() { rw_duplicate_invariant_impl(20); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000021() { rw_duplicate_invariant_impl(21); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000022() { rw_duplicate_invariant_impl(22); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000023() { rw_duplicate_invariant_impl(23); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000024() { rw_duplicate_invariant_impl(24); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000025() { rw_duplicate_invariant_impl(25); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000026() { rw_duplicate_invariant_impl(26); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000027() { rw_duplicate_invariant_impl(27); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000028() { rw_duplicate_invariant_impl(28); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000029() { rw_duplicate_invariant_impl(29); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000030() { rw_duplicate_invariant_impl(30); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000031() { rw_duplicate_invariant_impl(31); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000032() { rw_duplicate_invariant_impl(32); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000033() { rw_duplicate_invariant_impl(33); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000034() { rw_duplicate_invariant_impl(34); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000035() { rw_duplicate_invariant_impl(35); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000036() { rw_duplicate_invariant_impl(36); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000037() { rw_duplicate_invariant_impl(37); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000038() { rw_duplicate_invariant_impl(38); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000039() { rw_duplicate_invariant_impl(39); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000040() { rw_duplicate_invariant_impl(40); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000041() { rw_duplicate_invariant_impl(41); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000042() { rw_duplicate_invariant_impl(42); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000043() { rw_duplicate_invariant_impl(43); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000044() { rw_duplicate_invariant_impl(44); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000045() { rw_duplicate_invariant_impl(45); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000046() { rw_duplicate_invariant_impl(46); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000047() { rw_duplicate_invariant_impl(47); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000048() { rw_duplicate_invariant_impl(48); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000049() { rw_duplicate_invariant_impl(49); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000050() { rw_duplicate_invariant_impl(50); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000051() { rw_duplicate_invariant_impl(51); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000052() { rw_duplicate_invariant_impl(52); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000053() { rw_duplicate_invariant_impl(53); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000054() { rw_duplicate_invariant_impl(54); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000055() { rw_duplicate_invariant_impl(55); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000056() { rw_duplicate_invariant_impl(56); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000057() { rw_duplicate_invariant_impl(57); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000058() { rw_duplicate_invariant_impl(58); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000059() { rw_duplicate_invariant_impl(59); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000060() { rw_duplicate_invariant_impl(60); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000061() { rw_duplicate_invariant_impl(61); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000062() { rw_duplicate_invariant_impl(62); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000063() { rw_duplicate_invariant_impl(63); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000064() { rw_duplicate_invariant_impl(64); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000065() { rw_duplicate_invariant_impl(65); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000066() { rw_duplicate_invariant_impl(66); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000067() { rw_duplicate_invariant_impl(67); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000068() { rw_duplicate_invariant_impl(68); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000069() { rw_duplicate_invariant_impl(69); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000070() { rw_duplicate_invariant_impl(70); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000071() { rw_duplicate_invariant_impl(71); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000072() { rw_duplicate_invariant_impl(72); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000073() { rw_duplicate_invariant_impl(73); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000074() { rw_duplicate_invariant_impl(74); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000075() { rw_duplicate_invariant_impl(75); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000076() { rw_duplicate_invariant_impl(76); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000077() { rw_duplicate_invariant_impl(77); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000078() { rw_duplicate_invariant_impl(78); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000079() { rw_duplicate_invariant_impl(79); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000080() { rw_duplicate_invariant_impl(80); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000081() { rw_duplicate_invariant_impl(81); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000082() { rw_duplicate_invariant_impl(82); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000083() { rw_duplicate_invariant_impl(83); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000084() { rw_duplicate_invariant_impl(84); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000085() { rw_duplicate_invariant_impl(85); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000086() { rw_duplicate_invariant_impl(86); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000087() { rw_duplicate_invariant_impl(87); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000088() { rw_duplicate_invariant_impl(88); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000089() { rw_duplicate_invariant_impl(89); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000090() { rw_duplicate_invariant_impl(90); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000091() { rw_duplicate_invariant_impl(91); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000092() { rw_duplicate_invariant_impl(92); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000093() { rw_duplicate_invariant_impl(93); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000094() { rw_duplicate_invariant_impl(94); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000095() { rw_duplicate_invariant_impl(95); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000096() { rw_duplicate_invariant_impl(96); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000097() { rw_duplicate_invariant_impl(97); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000098() { rw_duplicate_invariant_impl(98); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000099() { rw_duplicate_invariant_impl(99); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000100() { rw_duplicate_invariant_impl(100); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000101() { rw_duplicate_invariant_impl(101); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000102() { rw_duplicate_invariant_impl(102); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000103() { rw_duplicate_invariant_impl(103); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000104() { rw_duplicate_invariant_impl(104); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000105() { rw_duplicate_invariant_impl(105); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000106() { rw_duplicate_invariant_impl(106); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000107() { rw_duplicate_invariant_impl(107); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000108() { rw_duplicate_invariant_impl(108); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000109() { rw_duplicate_invariant_impl(109); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000110() { rw_duplicate_invariant_impl(110); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000111() { rw_duplicate_invariant_impl(111); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000112() { rw_duplicate_invariant_impl(112); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000113() { rw_duplicate_invariant_impl(113); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000114() { rw_duplicate_invariant_impl(114); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000115() { rw_duplicate_invariant_impl(115); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000116() { rw_duplicate_invariant_impl(116); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000117() { rw_duplicate_invariant_impl(117); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000118() { rw_duplicate_invariant_impl(118); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000119() { rw_duplicate_invariant_impl(119); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000120() { rw_duplicate_invariant_impl(120); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000121() { rw_duplicate_invariant_impl(121); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000122() { rw_duplicate_invariant_impl(122); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000123() { rw_duplicate_invariant_impl(123); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000124() { rw_duplicate_invariant_impl(124); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000125() { rw_duplicate_invariant_impl(125); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000126() { rw_duplicate_invariant_impl(126); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000127() { rw_duplicate_invariant_impl(127); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000128() { rw_duplicate_invariant_impl(128); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000129() { rw_duplicate_invariant_impl(129); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000130() { rw_duplicate_invariant_impl(130); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000131() { rw_duplicate_invariant_impl(131); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000132() { rw_duplicate_invariant_impl(132); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000133() { rw_duplicate_invariant_impl(133); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000134() { rw_duplicate_invariant_impl(134); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000135() { rw_duplicate_invariant_impl(135); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000136() { rw_duplicate_invariant_impl(136); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000137() { rw_duplicate_invariant_impl(137); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000138() { rw_duplicate_invariant_impl(138); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000139() { rw_duplicate_invariant_impl(139); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000140() { rw_duplicate_invariant_impl(140); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000141() { rw_duplicate_invariant_impl(141); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000142() { rw_duplicate_invariant_impl(142); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000143() { rw_duplicate_invariant_impl(143); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000144() { rw_duplicate_invariant_impl(144); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000145() { rw_duplicate_invariant_impl(145); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000146() { rw_duplicate_invariant_impl(146); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000147() { rw_duplicate_invariant_impl(147); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000148() { rw_duplicate_invariant_impl(148); }
    #[cfg_attr(test, test)]
    fn rw_duplicate_invariant_seed_000149() { rw_duplicate_invariant_impl(149); }

    // --- rw_conflict_order_independent: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000000() { rw_conflict_order_independent_impl(0); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000001() { rw_conflict_order_independent_impl(1); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000002() { rw_conflict_order_independent_impl(2); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000003() { rw_conflict_order_independent_impl(3); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000004() { rw_conflict_order_independent_impl(4); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000005() { rw_conflict_order_independent_impl(5); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000006() { rw_conflict_order_independent_impl(6); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000007() { rw_conflict_order_independent_impl(7); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000008() { rw_conflict_order_independent_impl(8); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000009() { rw_conflict_order_independent_impl(9); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000010() { rw_conflict_order_independent_impl(10); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000011() { rw_conflict_order_independent_impl(11); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000012() { rw_conflict_order_independent_impl(12); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000013() { rw_conflict_order_independent_impl(13); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000014() { rw_conflict_order_independent_impl(14); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000015() { rw_conflict_order_independent_impl(15); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000016() { rw_conflict_order_independent_impl(16); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000017() { rw_conflict_order_independent_impl(17); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000018() { rw_conflict_order_independent_impl(18); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000019() { rw_conflict_order_independent_impl(19); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000020() { rw_conflict_order_independent_impl(20); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000021() { rw_conflict_order_independent_impl(21); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000022() { rw_conflict_order_independent_impl(22); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000023() { rw_conflict_order_independent_impl(23); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000024() { rw_conflict_order_independent_impl(24); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000025() { rw_conflict_order_independent_impl(25); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000026() { rw_conflict_order_independent_impl(26); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000027() { rw_conflict_order_independent_impl(27); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000028() { rw_conflict_order_independent_impl(28); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000029() { rw_conflict_order_independent_impl(29); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000030() { rw_conflict_order_independent_impl(30); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000031() { rw_conflict_order_independent_impl(31); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000032() { rw_conflict_order_independent_impl(32); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000033() { rw_conflict_order_independent_impl(33); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000034() { rw_conflict_order_independent_impl(34); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000035() { rw_conflict_order_independent_impl(35); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000036() { rw_conflict_order_independent_impl(36); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000037() { rw_conflict_order_independent_impl(37); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000038() { rw_conflict_order_independent_impl(38); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000039() { rw_conflict_order_independent_impl(39); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000040() { rw_conflict_order_independent_impl(40); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000041() { rw_conflict_order_independent_impl(41); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000042() { rw_conflict_order_independent_impl(42); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000043() { rw_conflict_order_independent_impl(43); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000044() { rw_conflict_order_independent_impl(44); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000045() { rw_conflict_order_independent_impl(45); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000046() { rw_conflict_order_independent_impl(46); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000047() { rw_conflict_order_independent_impl(47); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000048() { rw_conflict_order_independent_impl(48); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000049() { rw_conflict_order_independent_impl(49); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000050() { rw_conflict_order_independent_impl(50); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000051() { rw_conflict_order_independent_impl(51); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000052() { rw_conflict_order_independent_impl(52); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000053() { rw_conflict_order_independent_impl(53); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000054() { rw_conflict_order_independent_impl(54); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000055() { rw_conflict_order_independent_impl(55); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000056() { rw_conflict_order_independent_impl(56); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000057() { rw_conflict_order_independent_impl(57); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000058() { rw_conflict_order_independent_impl(58); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000059() { rw_conflict_order_independent_impl(59); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000060() { rw_conflict_order_independent_impl(60); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000061() { rw_conflict_order_independent_impl(61); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000062() { rw_conflict_order_independent_impl(62); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000063() { rw_conflict_order_independent_impl(63); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000064() { rw_conflict_order_independent_impl(64); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000065() { rw_conflict_order_independent_impl(65); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000066() { rw_conflict_order_independent_impl(66); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000067() { rw_conflict_order_independent_impl(67); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000068() { rw_conflict_order_independent_impl(68); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000069() { rw_conflict_order_independent_impl(69); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000070() { rw_conflict_order_independent_impl(70); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000071() { rw_conflict_order_independent_impl(71); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000072() { rw_conflict_order_independent_impl(72); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000073() { rw_conflict_order_independent_impl(73); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000074() { rw_conflict_order_independent_impl(74); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000075() { rw_conflict_order_independent_impl(75); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000076() { rw_conflict_order_independent_impl(76); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000077() { rw_conflict_order_independent_impl(77); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000078() { rw_conflict_order_independent_impl(78); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000079() { rw_conflict_order_independent_impl(79); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000080() { rw_conflict_order_independent_impl(80); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000081() { rw_conflict_order_independent_impl(81); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000082() { rw_conflict_order_independent_impl(82); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000083() { rw_conflict_order_independent_impl(83); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000084() { rw_conflict_order_independent_impl(84); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000085() { rw_conflict_order_independent_impl(85); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000086() { rw_conflict_order_independent_impl(86); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000087() { rw_conflict_order_independent_impl(87); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000088() { rw_conflict_order_independent_impl(88); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000089() { rw_conflict_order_independent_impl(89); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000090() { rw_conflict_order_independent_impl(90); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000091() { rw_conflict_order_independent_impl(91); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000092() { rw_conflict_order_independent_impl(92); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000093() { rw_conflict_order_independent_impl(93); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000094() { rw_conflict_order_independent_impl(94); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000095() { rw_conflict_order_independent_impl(95); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000096() { rw_conflict_order_independent_impl(96); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000097() { rw_conflict_order_independent_impl(97); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000098() { rw_conflict_order_independent_impl(98); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000099() { rw_conflict_order_independent_impl(99); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000100() { rw_conflict_order_independent_impl(100); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000101() { rw_conflict_order_independent_impl(101); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000102() { rw_conflict_order_independent_impl(102); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000103() { rw_conflict_order_independent_impl(103); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000104() { rw_conflict_order_independent_impl(104); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000105() { rw_conflict_order_independent_impl(105); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000106() { rw_conflict_order_independent_impl(106); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000107() { rw_conflict_order_independent_impl(107); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000108() { rw_conflict_order_independent_impl(108); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000109() { rw_conflict_order_independent_impl(109); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000110() { rw_conflict_order_independent_impl(110); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000111() { rw_conflict_order_independent_impl(111); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000112() { rw_conflict_order_independent_impl(112); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000113() { rw_conflict_order_independent_impl(113); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000114() { rw_conflict_order_independent_impl(114); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000115() { rw_conflict_order_independent_impl(115); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000116() { rw_conflict_order_independent_impl(116); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000117() { rw_conflict_order_independent_impl(117); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000118() { rw_conflict_order_independent_impl(118); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000119() { rw_conflict_order_independent_impl(119); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000120() { rw_conflict_order_independent_impl(120); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000121() { rw_conflict_order_independent_impl(121); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000122() { rw_conflict_order_independent_impl(122); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000123() { rw_conflict_order_independent_impl(123); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000124() { rw_conflict_order_independent_impl(124); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000125() { rw_conflict_order_independent_impl(125); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000126() { rw_conflict_order_independent_impl(126); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000127() { rw_conflict_order_independent_impl(127); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000128() { rw_conflict_order_independent_impl(128); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000129() { rw_conflict_order_independent_impl(129); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000130() { rw_conflict_order_independent_impl(130); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000131() { rw_conflict_order_independent_impl(131); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000132() { rw_conflict_order_independent_impl(132); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000133() { rw_conflict_order_independent_impl(133); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000134() { rw_conflict_order_independent_impl(134); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000135() { rw_conflict_order_independent_impl(135); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000136() { rw_conflict_order_independent_impl(136); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000137() { rw_conflict_order_independent_impl(137); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000138() { rw_conflict_order_independent_impl(138); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000139() { rw_conflict_order_independent_impl(139); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000140() { rw_conflict_order_independent_impl(140); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000141() { rw_conflict_order_independent_impl(141); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000142() { rw_conflict_order_independent_impl(142); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000143() { rw_conflict_order_independent_impl(143); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000144() { rw_conflict_order_independent_impl(144); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000145() { rw_conflict_order_independent_impl(145); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000146() { rw_conflict_order_independent_impl(146); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000147() { rw_conflict_order_independent_impl(147); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000148() { rw_conflict_order_independent_impl(148); }
    #[cfg_attr(test, test)]
    fn rw_conflict_order_independent_seed_000149() { rw_conflict_order_independent_impl(149); }

    // --- as_determinism: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000000() { as_determinism_impl(0); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000001() { as_determinism_impl(1); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000002() { as_determinism_impl(2); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000003() { as_determinism_impl(3); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000004() { as_determinism_impl(4); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000005() { as_determinism_impl(5); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000006() { as_determinism_impl(6); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000007() { as_determinism_impl(7); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000008() { as_determinism_impl(8); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000009() { as_determinism_impl(9); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000010() { as_determinism_impl(10); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000011() { as_determinism_impl(11); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000012() { as_determinism_impl(12); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000013() { as_determinism_impl(13); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000014() { as_determinism_impl(14); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000015() { as_determinism_impl(15); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000016() { as_determinism_impl(16); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000017() { as_determinism_impl(17); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000018() { as_determinism_impl(18); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000019() { as_determinism_impl(19); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000020() { as_determinism_impl(20); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000021() { as_determinism_impl(21); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000022() { as_determinism_impl(22); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000023() { as_determinism_impl(23); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000024() { as_determinism_impl(24); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000025() { as_determinism_impl(25); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000026() { as_determinism_impl(26); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000027() { as_determinism_impl(27); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000028() { as_determinism_impl(28); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000029() { as_determinism_impl(29); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000030() { as_determinism_impl(30); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000031() { as_determinism_impl(31); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000032() { as_determinism_impl(32); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000033() { as_determinism_impl(33); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000034() { as_determinism_impl(34); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000035() { as_determinism_impl(35); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000036() { as_determinism_impl(36); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000037() { as_determinism_impl(37); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000038() { as_determinism_impl(38); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000039() { as_determinism_impl(39); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000040() { as_determinism_impl(40); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000041() { as_determinism_impl(41); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000042() { as_determinism_impl(42); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000043() { as_determinism_impl(43); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000044() { as_determinism_impl(44); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000045() { as_determinism_impl(45); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000046() { as_determinism_impl(46); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000047() { as_determinism_impl(47); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000048() { as_determinism_impl(48); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000049() { as_determinism_impl(49); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000050() { as_determinism_impl(50); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000051() { as_determinism_impl(51); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000052() { as_determinism_impl(52); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000053() { as_determinism_impl(53); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000054() { as_determinism_impl(54); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000055() { as_determinism_impl(55); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000056() { as_determinism_impl(56); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000057() { as_determinism_impl(57); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000058() { as_determinism_impl(58); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000059() { as_determinism_impl(59); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000060() { as_determinism_impl(60); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000061() { as_determinism_impl(61); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000062() { as_determinism_impl(62); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000063() { as_determinism_impl(63); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000064() { as_determinism_impl(64); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000065() { as_determinism_impl(65); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000066() { as_determinism_impl(66); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000067() { as_determinism_impl(67); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000068() { as_determinism_impl(68); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000069() { as_determinism_impl(69); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000070() { as_determinism_impl(70); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000071() { as_determinism_impl(71); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000072() { as_determinism_impl(72); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000073() { as_determinism_impl(73); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000074() { as_determinism_impl(74); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000075() { as_determinism_impl(75); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000076() { as_determinism_impl(76); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000077() { as_determinism_impl(77); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000078() { as_determinism_impl(78); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000079() { as_determinism_impl(79); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000080() { as_determinism_impl(80); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000081() { as_determinism_impl(81); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000082() { as_determinism_impl(82); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000083() { as_determinism_impl(83); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000084() { as_determinism_impl(84); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000085() { as_determinism_impl(85); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000086() { as_determinism_impl(86); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000087() { as_determinism_impl(87); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000088() { as_determinism_impl(88); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000089() { as_determinism_impl(89); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000090() { as_determinism_impl(90); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000091() { as_determinism_impl(91); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000092() { as_determinism_impl(92); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000093() { as_determinism_impl(93); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000094() { as_determinism_impl(94); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000095() { as_determinism_impl(95); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000096() { as_determinism_impl(96); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000097() { as_determinism_impl(97); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000098() { as_determinism_impl(98); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000099() { as_determinism_impl(99); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000100() { as_determinism_impl(100); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000101() { as_determinism_impl(101); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000102() { as_determinism_impl(102); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000103() { as_determinism_impl(103); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000104() { as_determinism_impl(104); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000105() { as_determinism_impl(105); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000106() { as_determinism_impl(106); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000107() { as_determinism_impl(107); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000108() { as_determinism_impl(108); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000109() { as_determinism_impl(109); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000110() { as_determinism_impl(110); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000111() { as_determinism_impl(111); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000112() { as_determinism_impl(112); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000113() { as_determinism_impl(113); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000114() { as_determinism_impl(114); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000115() { as_determinism_impl(115); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000116() { as_determinism_impl(116); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000117() { as_determinism_impl(117); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000118() { as_determinism_impl(118); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000119() { as_determinism_impl(119); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000120() { as_determinism_impl(120); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000121() { as_determinism_impl(121); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000122() { as_determinism_impl(122); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000123() { as_determinism_impl(123); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000124() { as_determinism_impl(124); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000125() { as_determinism_impl(125); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000126() { as_determinism_impl(126); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000127() { as_determinism_impl(127); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000128() { as_determinism_impl(128); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000129() { as_determinism_impl(129); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000130() { as_determinism_impl(130); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000131() { as_determinism_impl(131); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000132() { as_determinism_impl(132); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000133() { as_determinism_impl(133); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000134() { as_determinism_impl(134); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000135() { as_determinism_impl(135); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000136() { as_determinism_impl(136); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000137() { as_determinism_impl(137); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000138() { as_determinism_impl(138); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000139() { as_determinism_impl(139); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000140() { as_determinism_impl(140); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000141() { as_determinism_impl(141); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000142() { as_determinism_impl(142); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000143() { as_determinism_impl(143); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000144() { as_determinism_impl(144); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000145() { as_determinism_impl(145); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000146() { as_determinism_impl(146); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000147() { as_determinism_impl(147); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000148() { as_determinism_impl(148); }
    #[cfg_attr(test, test)]
    fn as_determinism_seed_000149() { as_determinism_impl(149); }

    // --- as_path_validity: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000000() { as_path_validity_impl(0); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000001() { as_path_validity_impl(1); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000002() { as_path_validity_impl(2); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000003() { as_path_validity_impl(3); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000004() { as_path_validity_impl(4); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000005() { as_path_validity_impl(5); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000006() { as_path_validity_impl(6); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000007() { as_path_validity_impl(7); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000008() { as_path_validity_impl(8); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000009() { as_path_validity_impl(9); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000010() { as_path_validity_impl(10); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000011() { as_path_validity_impl(11); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000012() { as_path_validity_impl(12); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000013() { as_path_validity_impl(13); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000014() { as_path_validity_impl(14); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000015() { as_path_validity_impl(15); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000016() { as_path_validity_impl(16); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000017() { as_path_validity_impl(17); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000018() { as_path_validity_impl(18); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000019() { as_path_validity_impl(19); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000020() { as_path_validity_impl(20); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000021() { as_path_validity_impl(21); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000022() { as_path_validity_impl(22); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000023() { as_path_validity_impl(23); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000024() { as_path_validity_impl(24); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000025() { as_path_validity_impl(25); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000026() { as_path_validity_impl(26); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000027() { as_path_validity_impl(27); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000028() { as_path_validity_impl(28); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000029() { as_path_validity_impl(29); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000030() { as_path_validity_impl(30); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000031() { as_path_validity_impl(31); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000032() { as_path_validity_impl(32); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000033() { as_path_validity_impl(33); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000034() { as_path_validity_impl(34); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000035() { as_path_validity_impl(35); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000036() { as_path_validity_impl(36); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000037() { as_path_validity_impl(37); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000038() { as_path_validity_impl(38); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000039() { as_path_validity_impl(39); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000040() { as_path_validity_impl(40); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000041() { as_path_validity_impl(41); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000042() { as_path_validity_impl(42); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000043() { as_path_validity_impl(43); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000044() { as_path_validity_impl(44); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000045() { as_path_validity_impl(45); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000046() { as_path_validity_impl(46); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000047() { as_path_validity_impl(47); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000048() { as_path_validity_impl(48); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000049() { as_path_validity_impl(49); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000050() { as_path_validity_impl(50); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000051() { as_path_validity_impl(51); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000052() { as_path_validity_impl(52); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000053() { as_path_validity_impl(53); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000054() { as_path_validity_impl(54); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000055() { as_path_validity_impl(55); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000056() { as_path_validity_impl(56); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000057() { as_path_validity_impl(57); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000058() { as_path_validity_impl(58); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000059() { as_path_validity_impl(59); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000060() { as_path_validity_impl(60); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000061() { as_path_validity_impl(61); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000062() { as_path_validity_impl(62); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000063() { as_path_validity_impl(63); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000064() { as_path_validity_impl(64); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000065() { as_path_validity_impl(65); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000066() { as_path_validity_impl(66); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000067() { as_path_validity_impl(67); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000068() { as_path_validity_impl(68); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000069() { as_path_validity_impl(69); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000070() { as_path_validity_impl(70); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000071() { as_path_validity_impl(71); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000072() { as_path_validity_impl(72); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000073() { as_path_validity_impl(73); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000074() { as_path_validity_impl(74); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000075() { as_path_validity_impl(75); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000076() { as_path_validity_impl(76); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000077() { as_path_validity_impl(77); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000078() { as_path_validity_impl(78); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000079() { as_path_validity_impl(79); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000080() { as_path_validity_impl(80); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000081() { as_path_validity_impl(81); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000082() { as_path_validity_impl(82); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000083() { as_path_validity_impl(83); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000084() { as_path_validity_impl(84); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000085() { as_path_validity_impl(85); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000086() { as_path_validity_impl(86); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000087() { as_path_validity_impl(87); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000088() { as_path_validity_impl(88); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000089() { as_path_validity_impl(89); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000090() { as_path_validity_impl(90); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000091() { as_path_validity_impl(91); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000092() { as_path_validity_impl(92); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000093() { as_path_validity_impl(93); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000094() { as_path_validity_impl(94); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000095() { as_path_validity_impl(95); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000096() { as_path_validity_impl(96); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000097() { as_path_validity_impl(97); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000098() { as_path_validity_impl(98); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000099() { as_path_validity_impl(99); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000100() { as_path_validity_impl(100); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000101() { as_path_validity_impl(101); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000102() { as_path_validity_impl(102); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000103() { as_path_validity_impl(103); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000104() { as_path_validity_impl(104); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000105() { as_path_validity_impl(105); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000106() { as_path_validity_impl(106); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000107() { as_path_validity_impl(107); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000108() { as_path_validity_impl(108); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000109() { as_path_validity_impl(109); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000110() { as_path_validity_impl(110); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000111() { as_path_validity_impl(111); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000112() { as_path_validity_impl(112); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000113() { as_path_validity_impl(113); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000114() { as_path_validity_impl(114); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000115() { as_path_validity_impl(115); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000116() { as_path_validity_impl(116); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000117() { as_path_validity_impl(117); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000118() { as_path_validity_impl(118); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000119() { as_path_validity_impl(119); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000120() { as_path_validity_impl(120); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000121() { as_path_validity_impl(121); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000122() { as_path_validity_impl(122); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000123() { as_path_validity_impl(123); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000124() { as_path_validity_impl(124); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000125() { as_path_validity_impl(125); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000126() { as_path_validity_impl(126); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000127() { as_path_validity_impl(127); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000128() { as_path_validity_impl(128); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000129() { as_path_validity_impl(129); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000130() { as_path_validity_impl(130); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000131() { as_path_validity_impl(131); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000132() { as_path_validity_impl(132); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000133() { as_path_validity_impl(133); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000134() { as_path_validity_impl(134); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000135() { as_path_validity_impl(135); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000136() { as_path_validity_impl(136); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000137() { as_path_validity_impl(137); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000138() { as_path_validity_impl(138); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000139() { as_path_validity_impl(139); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000140() { as_path_validity_impl(140); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000141() { as_path_validity_impl(141); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000142() { as_path_validity_impl(142); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000143() { as_path_validity_impl(143); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000144() { as_path_validity_impl(144); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000145() { as_path_validity_impl(145); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000146() { as_path_validity_impl(146); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000147() { as_path_validity_impl(147); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000148() { as_path_validity_impl(148); }
    #[cfg_attr(test, test)]
    fn as_path_validity_seed_000149() { as_path_validity_impl(149); }

    // --- as_monotonic_reachability: 150 generated seeds ---
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000000() { as_monotonic_reachability_impl(0); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000001() { as_monotonic_reachability_impl(1); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000002() { as_monotonic_reachability_impl(2); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000003() { as_monotonic_reachability_impl(3); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000004() { as_monotonic_reachability_impl(4); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000005() { as_monotonic_reachability_impl(5); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000006() { as_monotonic_reachability_impl(6); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000007() { as_monotonic_reachability_impl(7); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000008() { as_monotonic_reachability_impl(8); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000009() { as_monotonic_reachability_impl(9); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000010() { as_monotonic_reachability_impl(10); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000011() { as_monotonic_reachability_impl(11); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000012() { as_monotonic_reachability_impl(12); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000013() { as_monotonic_reachability_impl(13); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000014() { as_monotonic_reachability_impl(14); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000015() { as_monotonic_reachability_impl(15); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000016() { as_monotonic_reachability_impl(16); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000017() { as_monotonic_reachability_impl(17); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000018() { as_monotonic_reachability_impl(18); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000019() { as_monotonic_reachability_impl(19); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000020() { as_monotonic_reachability_impl(20); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000021() { as_monotonic_reachability_impl(21); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000022() { as_monotonic_reachability_impl(22); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000023() { as_monotonic_reachability_impl(23); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000024() { as_monotonic_reachability_impl(24); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000025() { as_monotonic_reachability_impl(25); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000026() { as_monotonic_reachability_impl(26); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000027() { as_monotonic_reachability_impl(27); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000028() { as_monotonic_reachability_impl(28); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000029() { as_monotonic_reachability_impl(29); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000030() { as_monotonic_reachability_impl(30); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000031() { as_monotonic_reachability_impl(31); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000032() { as_monotonic_reachability_impl(32); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000033() { as_monotonic_reachability_impl(33); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000034() { as_monotonic_reachability_impl(34); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000035() { as_monotonic_reachability_impl(35); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000036() { as_monotonic_reachability_impl(36); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000037() { as_monotonic_reachability_impl(37); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000038() { as_monotonic_reachability_impl(38); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000039() { as_monotonic_reachability_impl(39); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000040() { as_monotonic_reachability_impl(40); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000041() { as_monotonic_reachability_impl(41); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000042() { as_monotonic_reachability_impl(42); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000043() { as_monotonic_reachability_impl(43); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000044() { as_monotonic_reachability_impl(44); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000045() { as_monotonic_reachability_impl(45); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000046() { as_monotonic_reachability_impl(46); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000047() { as_monotonic_reachability_impl(47); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000048() { as_monotonic_reachability_impl(48); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000049() { as_monotonic_reachability_impl(49); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000050() { as_monotonic_reachability_impl(50); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000051() { as_monotonic_reachability_impl(51); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000052() { as_monotonic_reachability_impl(52); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000053() { as_monotonic_reachability_impl(53); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000054() { as_monotonic_reachability_impl(54); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000055() { as_monotonic_reachability_impl(55); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000056() { as_monotonic_reachability_impl(56); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000057() { as_monotonic_reachability_impl(57); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000058() { as_monotonic_reachability_impl(58); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000059() { as_monotonic_reachability_impl(59); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000060() { as_monotonic_reachability_impl(60); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000061() { as_monotonic_reachability_impl(61); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000062() { as_monotonic_reachability_impl(62); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000063() { as_monotonic_reachability_impl(63); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000064() { as_monotonic_reachability_impl(64); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000065() { as_monotonic_reachability_impl(65); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000066() { as_monotonic_reachability_impl(66); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000067() { as_monotonic_reachability_impl(67); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000068() { as_monotonic_reachability_impl(68); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000069() { as_monotonic_reachability_impl(69); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000070() { as_monotonic_reachability_impl(70); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000071() { as_monotonic_reachability_impl(71); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000072() { as_monotonic_reachability_impl(72); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000073() { as_monotonic_reachability_impl(73); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000074() { as_monotonic_reachability_impl(74); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000075() { as_monotonic_reachability_impl(75); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000076() { as_monotonic_reachability_impl(76); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000077() { as_monotonic_reachability_impl(77); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000078() { as_monotonic_reachability_impl(78); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000079() { as_monotonic_reachability_impl(79); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000080() { as_monotonic_reachability_impl(80); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000081() { as_monotonic_reachability_impl(81); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000082() { as_monotonic_reachability_impl(82); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000083() { as_monotonic_reachability_impl(83); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000084() { as_monotonic_reachability_impl(84); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000085() { as_monotonic_reachability_impl(85); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000086() { as_monotonic_reachability_impl(86); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000087() { as_monotonic_reachability_impl(87); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000088() { as_monotonic_reachability_impl(88); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000089() { as_monotonic_reachability_impl(89); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000090() { as_monotonic_reachability_impl(90); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000091() { as_monotonic_reachability_impl(91); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000092() { as_monotonic_reachability_impl(92); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000093() { as_monotonic_reachability_impl(93); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000094() { as_monotonic_reachability_impl(94); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000095() { as_monotonic_reachability_impl(95); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000096() { as_monotonic_reachability_impl(96); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000097() { as_monotonic_reachability_impl(97); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000098() { as_monotonic_reachability_impl(98); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000099() { as_monotonic_reachability_impl(99); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000100() { as_monotonic_reachability_impl(100); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000101() { as_monotonic_reachability_impl(101); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000102() { as_monotonic_reachability_impl(102); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000103() { as_monotonic_reachability_impl(103); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000104() { as_monotonic_reachability_impl(104); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000105() { as_monotonic_reachability_impl(105); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000106() { as_monotonic_reachability_impl(106); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000107() { as_monotonic_reachability_impl(107); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000108() { as_monotonic_reachability_impl(108); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000109() { as_monotonic_reachability_impl(109); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000110() { as_monotonic_reachability_impl(110); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000111() { as_monotonic_reachability_impl(111); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000112() { as_monotonic_reachability_impl(112); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000113() { as_monotonic_reachability_impl(113); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000114() { as_monotonic_reachability_impl(114); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000115() { as_monotonic_reachability_impl(115); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000116() { as_monotonic_reachability_impl(116); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000117() { as_monotonic_reachability_impl(117); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000118() { as_monotonic_reachability_impl(118); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000119() { as_monotonic_reachability_impl(119); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000120() { as_monotonic_reachability_impl(120); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000121() { as_monotonic_reachability_impl(121); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000122() { as_monotonic_reachability_impl(122); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000123() { as_monotonic_reachability_impl(123); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000124() { as_monotonic_reachability_impl(124); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000125() { as_monotonic_reachability_impl(125); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000126() { as_monotonic_reachability_impl(126); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000127() { as_monotonic_reachability_impl(127); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000128() { as_monotonic_reachability_impl(128); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000129() { as_monotonic_reachability_impl(129); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000130() { as_monotonic_reachability_impl(130); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000131() { as_monotonic_reachability_impl(131); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000132() { as_monotonic_reachability_impl(132); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000133() { as_monotonic_reachability_impl(133); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000134() { as_monotonic_reachability_impl(134); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000135() { as_monotonic_reachability_impl(135); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000136() { as_monotonic_reachability_impl(136); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000137() { as_monotonic_reachability_impl(137); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000138() { as_monotonic_reachability_impl(138); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000139() { as_monotonic_reachability_impl(139); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000140() { as_monotonic_reachability_impl(140); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000141() { as_monotonic_reachability_impl(141); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000142() { as_monotonic_reachability_impl(142); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000143() { as_monotonic_reachability_impl(143); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000144() { as_monotonic_reachability_impl(144); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000145() { as_monotonic_reachability_impl(145); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000146() { as_monotonic_reachability_impl(146); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000147() { as_monotonic_reachability_impl(147); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000148() { as_monotonic_reachability_impl(148); }
    #[cfg_attr(test, test)]
    fn as_monotonic_reachability_seed_000149() { as_monotonic_reachability_impl(149); }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("property_campaigns::tests::splitmix64_is_deterministic_in_seed", splitmix64_is_deterministic_in_seed),
        ("property_campaigns::tests::splitmix64_varies_with_seed", splitmix64_varies_with_seed),
        ("property_campaigns::tests::pr_gen_net_length_in_expected_range", pr_gen_net_length_in_expected_range),
        ("property_campaigns::tests::pr_euclidean_mst_has_n_minus_one_edges", pr_euclidean_mst_has_n_minus_one_edges),
        ("property_campaigns::tests::rw_choose_subset_returns_distinct_in_range_indices", rw_choose_subset_returns_distinct_in_range_indices),
        ("property_campaigns::tests::canon_constraints_is_order_independent", canon_constraints_is_order_independent),
        ("property_campaigns::tests::rw_gen_model_never_produces_a_layer_conflict", rw_gen_model_never_produces_a_layer_conflict),
        ("property_campaigns::tests::rw_gen_conflict_model_always_conflicts", rw_gen_conflict_model_always_conflicts),
        ("property_campaigns::tests::as_gen_base_dims_and_endpoints_in_range", as_gen_base_dims_and_endpoints_in_range),
        ("property_campaigns::tests::as_direction_index_matches_the_documented_table", as_direction_index_matches_the_documented_table),
        ("property_campaigns::tests::pr_monotonic_params_seed_000000", pr_monotonic_params_seed_000000),
        ("property_campaigns::tests::pr_monotonic_params_seed_000001", pr_monotonic_params_seed_000001),
        ("property_campaigns::tests::pr_monotonic_params_seed_000002", pr_monotonic_params_seed_000002),
        ("property_campaigns::tests::pr_monotonic_params_seed_000003", pr_monotonic_params_seed_000003),
        ("property_campaigns::tests::pr_monotonic_params_seed_000004", pr_monotonic_params_seed_000004),
        ("property_campaigns::tests::pr_monotonic_params_seed_000005", pr_monotonic_params_seed_000005),
        ("property_campaigns::tests::pr_monotonic_params_seed_000006", pr_monotonic_params_seed_000006),
        ("property_campaigns::tests::pr_monotonic_params_seed_000007", pr_monotonic_params_seed_000007),
        ("property_campaigns::tests::pr_monotonic_params_seed_000008", pr_monotonic_params_seed_000008),
        ("property_campaigns::tests::pr_monotonic_params_seed_000009", pr_monotonic_params_seed_000009),
        ("property_campaigns::tests::pr_monotonic_params_seed_000010", pr_monotonic_params_seed_000010),
        ("property_campaigns::tests::pr_monotonic_params_seed_000011", pr_monotonic_params_seed_000011),
        ("property_campaigns::tests::pr_monotonic_params_seed_000012", pr_monotonic_params_seed_000012),
        ("property_campaigns::tests::pr_monotonic_params_seed_000013", pr_monotonic_params_seed_000013),
        ("property_campaigns::tests::pr_monotonic_params_seed_000014", pr_monotonic_params_seed_000014),
        ("property_campaigns::tests::pr_monotonic_params_seed_000015", pr_monotonic_params_seed_000015),
        ("property_campaigns::tests::pr_monotonic_params_seed_000016", pr_monotonic_params_seed_000016),
        ("property_campaigns::tests::pr_monotonic_params_seed_000017", pr_monotonic_params_seed_000017),
        ("property_campaigns::tests::pr_monotonic_params_seed_000018", pr_monotonic_params_seed_000018),
        ("property_campaigns::tests::pr_monotonic_params_seed_000019", pr_monotonic_params_seed_000019),
        ("property_campaigns::tests::pr_monotonic_params_seed_000020", pr_monotonic_params_seed_000020),
        ("property_campaigns::tests::pr_monotonic_params_seed_000021", pr_monotonic_params_seed_000021),
        ("property_campaigns::tests::pr_monotonic_params_seed_000022", pr_monotonic_params_seed_000022),
        ("property_campaigns::tests::pr_monotonic_params_seed_000023", pr_monotonic_params_seed_000023),
        ("property_campaigns::tests::pr_monotonic_params_seed_000024", pr_monotonic_params_seed_000024),
        ("property_campaigns::tests::pr_monotonic_params_seed_000025", pr_monotonic_params_seed_000025),
        ("property_campaigns::tests::pr_monotonic_params_seed_000026", pr_monotonic_params_seed_000026),
        ("property_campaigns::tests::pr_monotonic_params_seed_000027", pr_monotonic_params_seed_000027),
        ("property_campaigns::tests::pr_monotonic_params_seed_000028", pr_monotonic_params_seed_000028),
        ("property_campaigns::tests::pr_monotonic_params_seed_000029", pr_monotonic_params_seed_000029),
        ("property_campaigns::tests::pr_monotonic_params_seed_000030", pr_monotonic_params_seed_000030),
        ("property_campaigns::tests::pr_monotonic_params_seed_000031", pr_monotonic_params_seed_000031),
        ("property_campaigns::tests::pr_monotonic_params_seed_000032", pr_monotonic_params_seed_000032),
        ("property_campaigns::tests::pr_monotonic_params_seed_000033", pr_monotonic_params_seed_000033),
        ("property_campaigns::tests::pr_monotonic_params_seed_000034", pr_monotonic_params_seed_000034),
        ("property_campaigns::tests::pr_monotonic_params_seed_000035", pr_monotonic_params_seed_000035),
        ("property_campaigns::tests::pr_monotonic_params_seed_000036", pr_monotonic_params_seed_000036),
        ("property_campaigns::tests::pr_monotonic_params_seed_000037", pr_monotonic_params_seed_000037),
        ("property_campaigns::tests::pr_monotonic_params_seed_000038", pr_monotonic_params_seed_000038),
        ("property_campaigns::tests::pr_monotonic_params_seed_000039", pr_monotonic_params_seed_000039),
        ("property_campaigns::tests::pr_monotonic_params_seed_000040", pr_monotonic_params_seed_000040),
        ("property_campaigns::tests::pr_monotonic_params_seed_000041", pr_monotonic_params_seed_000041),
        ("property_campaigns::tests::pr_monotonic_params_seed_000042", pr_monotonic_params_seed_000042),
        ("property_campaigns::tests::pr_monotonic_params_seed_000043", pr_monotonic_params_seed_000043),
        ("property_campaigns::tests::pr_monotonic_params_seed_000044", pr_monotonic_params_seed_000044),
        ("property_campaigns::tests::pr_monotonic_params_seed_000045", pr_monotonic_params_seed_000045),
        ("property_campaigns::tests::pr_monotonic_params_seed_000046", pr_monotonic_params_seed_000046),
        ("property_campaigns::tests::pr_monotonic_params_seed_000047", pr_monotonic_params_seed_000047),
        ("property_campaigns::tests::pr_monotonic_params_seed_000048", pr_monotonic_params_seed_000048),
        ("property_campaigns::tests::pr_monotonic_params_seed_000049", pr_monotonic_params_seed_000049),
        ("property_campaigns::tests::pr_monotonic_params_seed_000050", pr_monotonic_params_seed_000050),
        ("property_campaigns::tests::pr_monotonic_params_seed_000051", pr_monotonic_params_seed_000051),
        ("property_campaigns::tests::pr_monotonic_params_seed_000052", pr_monotonic_params_seed_000052),
        ("property_campaigns::tests::pr_monotonic_params_seed_000053", pr_monotonic_params_seed_000053),
        ("property_campaigns::tests::pr_monotonic_params_seed_000054", pr_monotonic_params_seed_000054),
        ("property_campaigns::tests::pr_monotonic_params_seed_000055", pr_monotonic_params_seed_000055),
        ("property_campaigns::tests::pr_monotonic_params_seed_000056", pr_monotonic_params_seed_000056),
        ("property_campaigns::tests::pr_monotonic_params_seed_000057", pr_monotonic_params_seed_000057),
        ("property_campaigns::tests::pr_monotonic_params_seed_000058", pr_monotonic_params_seed_000058),
        ("property_campaigns::tests::pr_monotonic_params_seed_000059", pr_monotonic_params_seed_000059),
        ("property_campaigns::tests::pr_monotonic_params_seed_000060", pr_monotonic_params_seed_000060),
        ("property_campaigns::tests::pr_monotonic_params_seed_000061", pr_monotonic_params_seed_000061),
        ("property_campaigns::tests::pr_monotonic_params_seed_000062", pr_monotonic_params_seed_000062),
        ("property_campaigns::tests::pr_monotonic_params_seed_000063", pr_monotonic_params_seed_000063),
        ("property_campaigns::tests::pr_monotonic_params_seed_000064", pr_monotonic_params_seed_000064),
        ("property_campaigns::tests::pr_monotonic_params_seed_000065", pr_monotonic_params_seed_000065),
        ("property_campaigns::tests::pr_monotonic_params_seed_000066", pr_monotonic_params_seed_000066),
        ("property_campaigns::tests::pr_monotonic_params_seed_000067", pr_monotonic_params_seed_000067),
        ("property_campaigns::tests::pr_monotonic_params_seed_000068", pr_monotonic_params_seed_000068),
        ("property_campaigns::tests::pr_monotonic_params_seed_000069", pr_monotonic_params_seed_000069),
        ("property_campaigns::tests::pr_monotonic_params_seed_000070", pr_monotonic_params_seed_000070),
        ("property_campaigns::tests::pr_monotonic_params_seed_000071", pr_monotonic_params_seed_000071),
        ("property_campaigns::tests::pr_monotonic_params_seed_000072", pr_monotonic_params_seed_000072),
        ("property_campaigns::tests::pr_monotonic_params_seed_000073", pr_monotonic_params_seed_000073),
        ("property_campaigns::tests::pr_monotonic_params_seed_000074", pr_monotonic_params_seed_000074),
        ("property_campaigns::tests::pr_monotonic_params_seed_000075", pr_monotonic_params_seed_000075),
        ("property_campaigns::tests::pr_monotonic_params_seed_000076", pr_monotonic_params_seed_000076),
        ("property_campaigns::tests::pr_monotonic_params_seed_000077", pr_monotonic_params_seed_000077),
        ("property_campaigns::tests::pr_monotonic_params_seed_000078", pr_monotonic_params_seed_000078),
        ("property_campaigns::tests::pr_monotonic_params_seed_000079", pr_monotonic_params_seed_000079),
        ("property_campaigns::tests::pr_monotonic_params_seed_000080", pr_monotonic_params_seed_000080),
        ("property_campaigns::tests::pr_monotonic_params_seed_000081", pr_monotonic_params_seed_000081),
        ("property_campaigns::tests::pr_monotonic_params_seed_000082", pr_monotonic_params_seed_000082),
        ("property_campaigns::tests::pr_monotonic_params_seed_000083", pr_monotonic_params_seed_000083),
        ("property_campaigns::tests::pr_monotonic_params_seed_000084", pr_monotonic_params_seed_000084),
        ("property_campaigns::tests::pr_monotonic_params_seed_000085", pr_monotonic_params_seed_000085),
        ("property_campaigns::tests::pr_monotonic_params_seed_000086", pr_monotonic_params_seed_000086),
        ("property_campaigns::tests::pr_monotonic_params_seed_000087", pr_monotonic_params_seed_000087),
        ("property_campaigns::tests::pr_monotonic_params_seed_000088", pr_monotonic_params_seed_000088),
        ("property_campaigns::tests::pr_monotonic_params_seed_000089", pr_monotonic_params_seed_000089),
        ("property_campaigns::tests::pr_monotonic_params_seed_000090", pr_monotonic_params_seed_000090),
        ("property_campaigns::tests::pr_monotonic_params_seed_000091", pr_monotonic_params_seed_000091),
        ("property_campaigns::tests::pr_monotonic_params_seed_000092", pr_monotonic_params_seed_000092),
        ("property_campaigns::tests::pr_monotonic_params_seed_000093", pr_monotonic_params_seed_000093),
        ("property_campaigns::tests::pr_monotonic_params_seed_000094", pr_monotonic_params_seed_000094),
        ("property_campaigns::tests::pr_monotonic_params_seed_000095", pr_monotonic_params_seed_000095),
        ("property_campaigns::tests::pr_monotonic_params_seed_000096", pr_monotonic_params_seed_000096),
        ("property_campaigns::tests::pr_monotonic_params_seed_000097", pr_monotonic_params_seed_000097),
        ("property_campaigns::tests::pr_monotonic_params_seed_000098", pr_monotonic_params_seed_000098),
        ("property_campaigns::tests::pr_monotonic_params_seed_000099", pr_monotonic_params_seed_000099),
        ("property_campaigns::tests::pr_monotonic_params_seed_000100", pr_monotonic_params_seed_000100),
        ("property_campaigns::tests::pr_monotonic_params_seed_000101", pr_monotonic_params_seed_000101),
        ("property_campaigns::tests::pr_monotonic_params_seed_000102", pr_monotonic_params_seed_000102),
        ("property_campaigns::tests::pr_monotonic_params_seed_000103", pr_monotonic_params_seed_000103),
        ("property_campaigns::tests::pr_monotonic_params_seed_000104", pr_monotonic_params_seed_000104),
        ("property_campaigns::tests::pr_monotonic_params_seed_000105", pr_monotonic_params_seed_000105),
        ("property_campaigns::tests::pr_monotonic_params_seed_000106", pr_monotonic_params_seed_000106),
        ("property_campaigns::tests::pr_monotonic_params_seed_000107", pr_monotonic_params_seed_000107),
        ("property_campaigns::tests::pr_monotonic_params_seed_000108", pr_monotonic_params_seed_000108),
        ("property_campaigns::tests::pr_monotonic_params_seed_000109", pr_monotonic_params_seed_000109),
        ("property_campaigns::tests::pr_monotonic_params_seed_000110", pr_monotonic_params_seed_000110),
        ("property_campaigns::tests::pr_monotonic_params_seed_000111", pr_monotonic_params_seed_000111),
        ("property_campaigns::tests::pr_monotonic_params_seed_000112", pr_monotonic_params_seed_000112),
        ("property_campaigns::tests::pr_monotonic_params_seed_000113", pr_monotonic_params_seed_000113),
        ("property_campaigns::tests::pr_monotonic_params_seed_000114", pr_monotonic_params_seed_000114),
        ("property_campaigns::tests::pr_monotonic_params_seed_000115", pr_monotonic_params_seed_000115),
        ("property_campaigns::tests::pr_monotonic_params_seed_000116", pr_monotonic_params_seed_000116),
        ("property_campaigns::tests::pr_monotonic_params_seed_000117", pr_monotonic_params_seed_000117),
        ("property_campaigns::tests::pr_monotonic_params_seed_000118", pr_monotonic_params_seed_000118),
        ("property_campaigns::tests::pr_monotonic_params_seed_000119", pr_monotonic_params_seed_000119),
        ("property_campaigns::tests::pr_monotonic_params_seed_000120", pr_monotonic_params_seed_000120),
        ("property_campaigns::tests::pr_monotonic_params_seed_000121", pr_monotonic_params_seed_000121),
        ("property_campaigns::tests::pr_monotonic_params_seed_000122", pr_monotonic_params_seed_000122),
        ("property_campaigns::tests::pr_monotonic_params_seed_000123", pr_monotonic_params_seed_000123),
        ("property_campaigns::tests::pr_monotonic_params_seed_000124", pr_monotonic_params_seed_000124),
        ("property_campaigns::tests::pr_monotonic_params_seed_000125", pr_monotonic_params_seed_000125),
        ("property_campaigns::tests::pr_monotonic_params_seed_000126", pr_monotonic_params_seed_000126),
        ("property_campaigns::tests::pr_monotonic_params_seed_000127", pr_monotonic_params_seed_000127),
        ("property_campaigns::tests::pr_monotonic_params_seed_000128", pr_monotonic_params_seed_000128),
        ("property_campaigns::tests::pr_monotonic_params_seed_000129", pr_monotonic_params_seed_000129),
        ("property_campaigns::tests::pr_monotonic_params_seed_000130", pr_monotonic_params_seed_000130),
        ("property_campaigns::tests::pr_monotonic_params_seed_000131", pr_monotonic_params_seed_000131),
        ("property_campaigns::tests::pr_monotonic_params_seed_000132", pr_monotonic_params_seed_000132),
        ("property_campaigns::tests::pr_monotonic_params_seed_000133", pr_monotonic_params_seed_000133),
        ("property_campaigns::tests::pr_monotonic_params_seed_000134", pr_monotonic_params_seed_000134),
        ("property_campaigns::tests::pr_monotonic_params_seed_000135", pr_monotonic_params_seed_000135),
        ("property_campaigns::tests::pr_monotonic_params_seed_000136", pr_monotonic_params_seed_000136),
        ("property_campaigns::tests::pr_monotonic_params_seed_000137", pr_monotonic_params_seed_000137),
        ("property_campaigns::tests::pr_monotonic_params_seed_000138", pr_monotonic_params_seed_000138),
        ("property_campaigns::tests::pr_monotonic_params_seed_000139", pr_monotonic_params_seed_000139),
        ("property_campaigns::tests::pr_monotonic_params_seed_000140", pr_monotonic_params_seed_000140),
        ("property_campaigns::tests::pr_monotonic_params_seed_000141", pr_monotonic_params_seed_000141),
        ("property_campaigns::tests::pr_monotonic_params_seed_000142", pr_monotonic_params_seed_000142),
        ("property_campaigns::tests::pr_monotonic_params_seed_000143", pr_monotonic_params_seed_000143),
        ("property_campaigns::tests::pr_monotonic_params_seed_000144", pr_monotonic_params_seed_000144),
        ("property_campaigns::tests::pr_monotonic_params_seed_000145", pr_monotonic_params_seed_000145),
        ("property_campaigns::tests::pr_monotonic_params_seed_000146", pr_monotonic_params_seed_000146),
        ("property_campaigns::tests::pr_monotonic_params_seed_000147", pr_monotonic_params_seed_000147),
        ("property_campaigns::tests::pr_monotonic_params_seed_000148", pr_monotonic_params_seed_000148),
        ("property_campaigns::tests::pr_monotonic_params_seed_000149", pr_monotonic_params_seed_000149),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000000", pr_symmetric_endpoints_seed_000000),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000001", pr_symmetric_endpoints_seed_000001),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000002", pr_symmetric_endpoints_seed_000002),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000003", pr_symmetric_endpoints_seed_000003),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000004", pr_symmetric_endpoints_seed_000004),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000005", pr_symmetric_endpoints_seed_000005),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000006", pr_symmetric_endpoints_seed_000006),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000007", pr_symmetric_endpoints_seed_000007),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000008", pr_symmetric_endpoints_seed_000008),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000009", pr_symmetric_endpoints_seed_000009),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000010", pr_symmetric_endpoints_seed_000010),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000011", pr_symmetric_endpoints_seed_000011),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000012", pr_symmetric_endpoints_seed_000012),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000013", pr_symmetric_endpoints_seed_000013),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000014", pr_symmetric_endpoints_seed_000014),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000015", pr_symmetric_endpoints_seed_000015),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000016", pr_symmetric_endpoints_seed_000016),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000017", pr_symmetric_endpoints_seed_000017),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000018", pr_symmetric_endpoints_seed_000018),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000019", pr_symmetric_endpoints_seed_000019),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000020", pr_symmetric_endpoints_seed_000020),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000021", pr_symmetric_endpoints_seed_000021),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000022", pr_symmetric_endpoints_seed_000022),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000023", pr_symmetric_endpoints_seed_000023),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000024", pr_symmetric_endpoints_seed_000024),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000025", pr_symmetric_endpoints_seed_000025),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000026", pr_symmetric_endpoints_seed_000026),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000027", pr_symmetric_endpoints_seed_000027),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000028", pr_symmetric_endpoints_seed_000028),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000029", pr_symmetric_endpoints_seed_000029),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000030", pr_symmetric_endpoints_seed_000030),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000031", pr_symmetric_endpoints_seed_000031),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000032", pr_symmetric_endpoints_seed_000032),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000033", pr_symmetric_endpoints_seed_000033),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000034", pr_symmetric_endpoints_seed_000034),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000035", pr_symmetric_endpoints_seed_000035),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000036", pr_symmetric_endpoints_seed_000036),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000037", pr_symmetric_endpoints_seed_000037),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000038", pr_symmetric_endpoints_seed_000038),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000039", pr_symmetric_endpoints_seed_000039),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000040", pr_symmetric_endpoints_seed_000040),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000041", pr_symmetric_endpoints_seed_000041),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000042", pr_symmetric_endpoints_seed_000042),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000043", pr_symmetric_endpoints_seed_000043),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000044", pr_symmetric_endpoints_seed_000044),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000045", pr_symmetric_endpoints_seed_000045),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000046", pr_symmetric_endpoints_seed_000046),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000047", pr_symmetric_endpoints_seed_000047),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000048", pr_symmetric_endpoints_seed_000048),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000049", pr_symmetric_endpoints_seed_000049),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000050", pr_symmetric_endpoints_seed_000050),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000051", pr_symmetric_endpoints_seed_000051),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000052", pr_symmetric_endpoints_seed_000052),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000053", pr_symmetric_endpoints_seed_000053),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000054", pr_symmetric_endpoints_seed_000054),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000055", pr_symmetric_endpoints_seed_000055),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000056", pr_symmetric_endpoints_seed_000056),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000057", pr_symmetric_endpoints_seed_000057),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000058", pr_symmetric_endpoints_seed_000058),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000059", pr_symmetric_endpoints_seed_000059),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000060", pr_symmetric_endpoints_seed_000060),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000061", pr_symmetric_endpoints_seed_000061),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000062", pr_symmetric_endpoints_seed_000062),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000063", pr_symmetric_endpoints_seed_000063),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000064", pr_symmetric_endpoints_seed_000064),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000065", pr_symmetric_endpoints_seed_000065),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000066", pr_symmetric_endpoints_seed_000066),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000067", pr_symmetric_endpoints_seed_000067),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000068", pr_symmetric_endpoints_seed_000068),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000069", pr_symmetric_endpoints_seed_000069),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000070", pr_symmetric_endpoints_seed_000070),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000071", pr_symmetric_endpoints_seed_000071),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000072", pr_symmetric_endpoints_seed_000072),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000073", pr_symmetric_endpoints_seed_000073),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000074", pr_symmetric_endpoints_seed_000074),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000075", pr_symmetric_endpoints_seed_000075),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000076", pr_symmetric_endpoints_seed_000076),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000077", pr_symmetric_endpoints_seed_000077),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000078", pr_symmetric_endpoints_seed_000078),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000079", pr_symmetric_endpoints_seed_000079),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000080", pr_symmetric_endpoints_seed_000080),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000081", pr_symmetric_endpoints_seed_000081),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000082", pr_symmetric_endpoints_seed_000082),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000083", pr_symmetric_endpoints_seed_000083),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000084", pr_symmetric_endpoints_seed_000084),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000085", pr_symmetric_endpoints_seed_000085),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000086", pr_symmetric_endpoints_seed_000086),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000087", pr_symmetric_endpoints_seed_000087),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000088", pr_symmetric_endpoints_seed_000088),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000089", pr_symmetric_endpoints_seed_000089),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000090", pr_symmetric_endpoints_seed_000090),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000091", pr_symmetric_endpoints_seed_000091),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000092", pr_symmetric_endpoints_seed_000092),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000093", pr_symmetric_endpoints_seed_000093),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000094", pr_symmetric_endpoints_seed_000094),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000095", pr_symmetric_endpoints_seed_000095),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000096", pr_symmetric_endpoints_seed_000096),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000097", pr_symmetric_endpoints_seed_000097),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000098", pr_symmetric_endpoints_seed_000098),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000099", pr_symmetric_endpoints_seed_000099),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000100", pr_symmetric_endpoints_seed_000100),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000101", pr_symmetric_endpoints_seed_000101),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000102", pr_symmetric_endpoints_seed_000102),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000103", pr_symmetric_endpoints_seed_000103),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000104", pr_symmetric_endpoints_seed_000104),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000105", pr_symmetric_endpoints_seed_000105),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000106", pr_symmetric_endpoints_seed_000106),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000107", pr_symmetric_endpoints_seed_000107),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000108", pr_symmetric_endpoints_seed_000108),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000109", pr_symmetric_endpoints_seed_000109),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000110", pr_symmetric_endpoints_seed_000110),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000111", pr_symmetric_endpoints_seed_000111),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000112", pr_symmetric_endpoints_seed_000112),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000113", pr_symmetric_endpoints_seed_000113),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000114", pr_symmetric_endpoints_seed_000114),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000115", pr_symmetric_endpoints_seed_000115),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000116", pr_symmetric_endpoints_seed_000116),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000117", pr_symmetric_endpoints_seed_000117),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000118", pr_symmetric_endpoints_seed_000118),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000119", pr_symmetric_endpoints_seed_000119),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000120", pr_symmetric_endpoints_seed_000120),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000121", pr_symmetric_endpoints_seed_000121),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000122", pr_symmetric_endpoints_seed_000122),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000123", pr_symmetric_endpoints_seed_000123),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000124", pr_symmetric_endpoints_seed_000124),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000125", pr_symmetric_endpoints_seed_000125),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000126", pr_symmetric_endpoints_seed_000126),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000127", pr_symmetric_endpoints_seed_000127),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000128", pr_symmetric_endpoints_seed_000128),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000129", pr_symmetric_endpoints_seed_000129),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000130", pr_symmetric_endpoints_seed_000130),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000131", pr_symmetric_endpoints_seed_000131),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000132", pr_symmetric_endpoints_seed_000132),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000133", pr_symmetric_endpoints_seed_000133),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000134", pr_symmetric_endpoints_seed_000134),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000135", pr_symmetric_endpoints_seed_000135),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000136", pr_symmetric_endpoints_seed_000136),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000137", pr_symmetric_endpoints_seed_000137),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000138", pr_symmetric_endpoints_seed_000138),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000139", pr_symmetric_endpoints_seed_000139),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000140", pr_symmetric_endpoints_seed_000140),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000141", pr_symmetric_endpoints_seed_000141),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000142", pr_symmetric_endpoints_seed_000142),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000143", pr_symmetric_endpoints_seed_000143),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000144", pr_symmetric_endpoints_seed_000144),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000145", pr_symmetric_endpoints_seed_000145),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000146", pr_symmetric_endpoints_seed_000146),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000147", pr_symmetric_endpoints_seed_000147),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000148", pr_symmetric_endpoints_seed_000148),
        ("property_campaigns::tests::pr_symmetric_endpoints_seed_000149", pr_symmetric_endpoints_seed_000149),
        ("property_campaigns::tests::pr_emst_soundness_seed_000000", pr_emst_soundness_seed_000000),
        ("property_campaigns::tests::pr_emst_soundness_seed_000001", pr_emst_soundness_seed_000001),
        ("property_campaigns::tests::pr_emst_soundness_seed_000002", pr_emst_soundness_seed_000002),
        ("property_campaigns::tests::pr_emst_soundness_seed_000003", pr_emst_soundness_seed_000003),
        ("property_campaigns::tests::pr_emst_soundness_seed_000004", pr_emst_soundness_seed_000004),
        ("property_campaigns::tests::pr_emst_soundness_seed_000005", pr_emst_soundness_seed_000005),
        ("property_campaigns::tests::pr_emst_soundness_seed_000006", pr_emst_soundness_seed_000006),
        ("property_campaigns::tests::pr_emst_soundness_seed_000007", pr_emst_soundness_seed_000007),
        ("property_campaigns::tests::pr_emst_soundness_seed_000008", pr_emst_soundness_seed_000008),
        ("property_campaigns::tests::pr_emst_soundness_seed_000009", pr_emst_soundness_seed_000009),
        ("property_campaigns::tests::pr_emst_soundness_seed_000010", pr_emst_soundness_seed_000010),
        ("property_campaigns::tests::pr_emst_soundness_seed_000011", pr_emst_soundness_seed_000011),
        ("property_campaigns::tests::pr_emst_soundness_seed_000012", pr_emst_soundness_seed_000012),
        ("property_campaigns::tests::pr_emst_soundness_seed_000013", pr_emst_soundness_seed_000013),
        ("property_campaigns::tests::pr_emst_soundness_seed_000014", pr_emst_soundness_seed_000014),
        ("property_campaigns::tests::pr_emst_soundness_seed_000015", pr_emst_soundness_seed_000015),
        ("property_campaigns::tests::pr_emst_soundness_seed_000016", pr_emst_soundness_seed_000016),
        ("property_campaigns::tests::pr_emst_soundness_seed_000017", pr_emst_soundness_seed_000017),
        ("property_campaigns::tests::pr_emst_soundness_seed_000018", pr_emst_soundness_seed_000018),
        ("property_campaigns::tests::pr_emst_soundness_seed_000019", pr_emst_soundness_seed_000019),
        ("property_campaigns::tests::pr_emst_soundness_seed_000020", pr_emst_soundness_seed_000020),
        ("property_campaigns::tests::pr_emst_soundness_seed_000021", pr_emst_soundness_seed_000021),
        ("property_campaigns::tests::pr_emst_soundness_seed_000022", pr_emst_soundness_seed_000022),
        ("property_campaigns::tests::pr_emst_soundness_seed_000023", pr_emst_soundness_seed_000023),
        ("property_campaigns::tests::pr_emst_soundness_seed_000024", pr_emst_soundness_seed_000024),
        ("property_campaigns::tests::pr_emst_soundness_seed_000025", pr_emst_soundness_seed_000025),
        ("property_campaigns::tests::pr_emst_soundness_seed_000026", pr_emst_soundness_seed_000026),
        ("property_campaigns::tests::pr_emst_soundness_seed_000027", pr_emst_soundness_seed_000027),
        ("property_campaigns::tests::pr_emst_soundness_seed_000028", pr_emst_soundness_seed_000028),
        ("property_campaigns::tests::pr_emst_soundness_seed_000029", pr_emst_soundness_seed_000029),
        ("property_campaigns::tests::pr_emst_soundness_seed_000030", pr_emst_soundness_seed_000030),
        ("property_campaigns::tests::pr_emst_soundness_seed_000031", pr_emst_soundness_seed_000031),
        ("property_campaigns::tests::pr_emst_soundness_seed_000032", pr_emst_soundness_seed_000032),
        ("property_campaigns::tests::pr_emst_soundness_seed_000033", pr_emst_soundness_seed_000033),
        ("property_campaigns::tests::pr_emst_soundness_seed_000034", pr_emst_soundness_seed_000034),
        ("property_campaigns::tests::pr_emst_soundness_seed_000035", pr_emst_soundness_seed_000035),
        ("property_campaigns::tests::pr_emst_soundness_seed_000036", pr_emst_soundness_seed_000036),
        ("property_campaigns::tests::pr_emst_soundness_seed_000037", pr_emst_soundness_seed_000037),
        ("property_campaigns::tests::pr_emst_soundness_seed_000038", pr_emst_soundness_seed_000038),
        ("property_campaigns::tests::pr_emst_soundness_seed_000039", pr_emst_soundness_seed_000039),
        ("property_campaigns::tests::pr_emst_soundness_seed_000040", pr_emst_soundness_seed_000040),
        ("property_campaigns::tests::pr_emst_soundness_seed_000041", pr_emst_soundness_seed_000041),
        ("property_campaigns::tests::pr_emst_soundness_seed_000042", pr_emst_soundness_seed_000042),
        ("property_campaigns::tests::pr_emst_soundness_seed_000043", pr_emst_soundness_seed_000043),
        ("property_campaigns::tests::pr_emst_soundness_seed_000044", pr_emst_soundness_seed_000044),
        ("property_campaigns::tests::pr_emst_soundness_seed_000045", pr_emst_soundness_seed_000045),
        ("property_campaigns::tests::pr_emst_soundness_seed_000046", pr_emst_soundness_seed_000046),
        ("property_campaigns::tests::pr_emst_soundness_seed_000047", pr_emst_soundness_seed_000047),
        ("property_campaigns::tests::pr_emst_soundness_seed_000048", pr_emst_soundness_seed_000048),
        ("property_campaigns::tests::pr_emst_soundness_seed_000049", pr_emst_soundness_seed_000049),
        ("property_campaigns::tests::pr_emst_soundness_seed_000050", pr_emst_soundness_seed_000050),
        ("property_campaigns::tests::pr_emst_soundness_seed_000051", pr_emst_soundness_seed_000051),
        ("property_campaigns::tests::pr_emst_soundness_seed_000052", pr_emst_soundness_seed_000052),
        ("property_campaigns::tests::pr_emst_soundness_seed_000053", pr_emst_soundness_seed_000053),
        ("property_campaigns::tests::pr_emst_soundness_seed_000054", pr_emst_soundness_seed_000054),
        ("property_campaigns::tests::pr_emst_soundness_seed_000055", pr_emst_soundness_seed_000055),
        ("property_campaigns::tests::pr_emst_soundness_seed_000056", pr_emst_soundness_seed_000056),
        ("property_campaigns::tests::pr_emst_soundness_seed_000057", pr_emst_soundness_seed_000057),
        ("property_campaigns::tests::pr_emst_soundness_seed_000058", pr_emst_soundness_seed_000058),
        ("property_campaigns::tests::pr_emst_soundness_seed_000059", pr_emst_soundness_seed_000059),
        ("property_campaigns::tests::pr_emst_soundness_seed_000060", pr_emst_soundness_seed_000060),
        ("property_campaigns::tests::pr_emst_soundness_seed_000061", pr_emst_soundness_seed_000061),
        ("property_campaigns::tests::pr_emst_soundness_seed_000062", pr_emst_soundness_seed_000062),
        ("property_campaigns::tests::pr_emst_soundness_seed_000063", pr_emst_soundness_seed_000063),
        ("property_campaigns::tests::pr_emst_soundness_seed_000064", pr_emst_soundness_seed_000064),
        ("property_campaigns::tests::pr_emst_soundness_seed_000065", pr_emst_soundness_seed_000065),
        ("property_campaigns::tests::pr_emst_soundness_seed_000066", pr_emst_soundness_seed_000066),
        ("property_campaigns::tests::pr_emst_soundness_seed_000067", pr_emst_soundness_seed_000067),
        ("property_campaigns::tests::pr_emst_soundness_seed_000068", pr_emst_soundness_seed_000068),
        ("property_campaigns::tests::pr_emst_soundness_seed_000069", pr_emst_soundness_seed_000069),
        ("property_campaigns::tests::pr_emst_soundness_seed_000070", pr_emst_soundness_seed_000070),
        ("property_campaigns::tests::pr_emst_soundness_seed_000071", pr_emst_soundness_seed_000071),
        ("property_campaigns::tests::pr_emst_soundness_seed_000072", pr_emst_soundness_seed_000072),
        ("property_campaigns::tests::pr_emst_soundness_seed_000073", pr_emst_soundness_seed_000073),
        ("property_campaigns::tests::pr_emst_soundness_seed_000074", pr_emst_soundness_seed_000074),
        ("property_campaigns::tests::pr_emst_soundness_seed_000075", pr_emst_soundness_seed_000075),
        ("property_campaigns::tests::pr_emst_soundness_seed_000076", pr_emst_soundness_seed_000076),
        ("property_campaigns::tests::pr_emst_soundness_seed_000077", pr_emst_soundness_seed_000077),
        ("property_campaigns::tests::pr_emst_soundness_seed_000078", pr_emst_soundness_seed_000078),
        ("property_campaigns::tests::pr_emst_soundness_seed_000079", pr_emst_soundness_seed_000079),
        ("property_campaigns::tests::pr_emst_soundness_seed_000080", pr_emst_soundness_seed_000080),
        ("property_campaigns::tests::pr_emst_soundness_seed_000081", pr_emst_soundness_seed_000081),
        ("property_campaigns::tests::pr_emst_soundness_seed_000082", pr_emst_soundness_seed_000082),
        ("property_campaigns::tests::pr_emst_soundness_seed_000083", pr_emst_soundness_seed_000083),
        ("property_campaigns::tests::pr_emst_soundness_seed_000084", pr_emst_soundness_seed_000084),
        ("property_campaigns::tests::pr_emst_soundness_seed_000085", pr_emst_soundness_seed_000085),
        ("property_campaigns::tests::pr_emst_soundness_seed_000086", pr_emst_soundness_seed_000086),
        ("property_campaigns::tests::pr_emst_soundness_seed_000087", pr_emst_soundness_seed_000087),
        ("property_campaigns::tests::pr_emst_soundness_seed_000088", pr_emst_soundness_seed_000088),
        ("property_campaigns::tests::pr_emst_soundness_seed_000089", pr_emst_soundness_seed_000089),
        ("property_campaigns::tests::pr_emst_soundness_seed_000090", pr_emst_soundness_seed_000090),
        ("property_campaigns::tests::pr_emst_soundness_seed_000091", pr_emst_soundness_seed_000091),
        ("property_campaigns::tests::pr_emst_soundness_seed_000092", pr_emst_soundness_seed_000092),
        ("property_campaigns::tests::pr_emst_soundness_seed_000093", pr_emst_soundness_seed_000093),
        ("property_campaigns::tests::pr_emst_soundness_seed_000094", pr_emst_soundness_seed_000094),
        ("property_campaigns::tests::pr_emst_soundness_seed_000095", pr_emst_soundness_seed_000095),
        ("property_campaigns::tests::pr_emst_soundness_seed_000096", pr_emst_soundness_seed_000096),
        ("property_campaigns::tests::pr_emst_soundness_seed_000097", pr_emst_soundness_seed_000097),
        ("property_campaigns::tests::pr_emst_soundness_seed_000098", pr_emst_soundness_seed_000098),
        ("property_campaigns::tests::pr_emst_soundness_seed_000099", pr_emst_soundness_seed_000099),
        ("property_campaigns::tests::pr_emst_soundness_seed_000100", pr_emst_soundness_seed_000100),
        ("property_campaigns::tests::pr_emst_soundness_seed_000101", pr_emst_soundness_seed_000101),
        ("property_campaigns::tests::pr_emst_soundness_seed_000102", pr_emst_soundness_seed_000102),
        ("property_campaigns::tests::pr_emst_soundness_seed_000103", pr_emst_soundness_seed_000103),
        ("property_campaigns::tests::pr_emst_soundness_seed_000104", pr_emst_soundness_seed_000104),
        ("property_campaigns::tests::pr_emst_soundness_seed_000105", pr_emst_soundness_seed_000105),
        ("property_campaigns::tests::pr_emst_soundness_seed_000106", pr_emst_soundness_seed_000106),
        ("property_campaigns::tests::pr_emst_soundness_seed_000107", pr_emst_soundness_seed_000107),
        ("property_campaigns::tests::pr_emst_soundness_seed_000108", pr_emst_soundness_seed_000108),
        ("property_campaigns::tests::pr_emst_soundness_seed_000109", pr_emst_soundness_seed_000109),
        ("property_campaigns::tests::pr_emst_soundness_seed_000110", pr_emst_soundness_seed_000110),
        ("property_campaigns::tests::pr_emst_soundness_seed_000111", pr_emst_soundness_seed_000111),
        ("property_campaigns::tests::pr_emst_soundness_seed_000112", pr_emst_soundness_seed_000112),
        ("property_campaigns::tests::pr_emst_soundness_seed_000113", pr_emst_soundness_seed_000113),
        ("property_campaigns::tests::pr_emst_soundness_seed_000114", pr_emst_soundness_seed_000114),
        ("property_campaigns::tests::pr_emst_soundness_seed_000115", pr_emst_soundness_seed_000115),
        ("property_campaigns::tests::pr_emst_soundness_seed_000116", pr_emst_soundness_seed_000116),
        ("property_campaigns::tests::pr_emst_soundness_seed_000117", pr_emst_soundness_seed_000117),
        ("property_campaigns::tests::pr_emst_soundness_seed_000118", pr_emst_soundness_seed_000118),
        ("property_campaigns::tests::pr_emst_soundness_seed_000119", pr_emst_soundness_seed_000119),
        ("property_campaigns::tests::pr_emst_soundness_seed_000120", pr_emst_soundness_seed_000120),
        ("property_campaigns::tests::pr_emst_soundness_seed_000121", pr_emst_soundness_seed_000121),
        ("property_campaigns::tests::pr_emst_soundness_seed_000122", pr_emst_soundness_seed_000122),
        ("property_campaigns::tests::pr_emst_soundness_seed_000123", pr_emst_soundness_seed_000123),
        ("property_campaigns::tests::pr_emst_soundness_seed_000124", pr_emst_soundness_seed_000124),
        ("property_campaigns::tests::pr_emst_soundness_seed_000125", pr_emst_soundness_seed_000125),
        ("property_campaigns::tests::pr_emst_soundness_seed_000126", pr_emst_soundness_seed_000126),
        ("property_campaigns::tests::pr_emst_soundness_seed_000127", pr_emst_soundness_seed_000127),
        ("property_campaigns::tests::pr_emst_soundness_seed_000128", pr_emst_soundness_seed_000128),
        ("property_campaigns::tests::pr_emst_soundness_seed_000129", pr_emst_soundness_seed_000129),
        ("property_campaigns::tests::pr_emst_soundness_seed_000130", pr_emst_soundness_seed_000130),
        ("property_campaigns::tests::pr_emst_soundness_seed_000131", pr_emst_soundness_seed_000131),
        ("property_campaigns::tests::pr_emst_soundness_seed_000132", pr_emst_soundness_seed_000132),
        ("property_campaigns::tests::pr_emst_soundness_seed_000133", pr_emst_soundness_seed_000133),
        ("property_campaigns::tests::pr_emst_soundness_seed_000134", pr_emst_soundness_seed_000134),
        ("property_campaigns::tests::pr_emst_soundness_seed_000135", pr_emst_soundness_seed_000135),
        ("property_campaigns::tests::pr_emst_soundness_seed_000136", pr_emst_soundness_seed_000136),
        ("property_campaigns::tests::pr_emst_soundness_seed_000137", pr_emst_soundness_seed_000137),
        ("property_campaigns::tests::pr_emst_soundness_seed_000138", pr_emst_soundness_seed_000138),
        ("property_campaigns::tests::pr_emst_soundness_seed_000139", pr_emst_soundness_seed_000139),
        ("property_campaigns::tests::pr_emst_soundness_seed_000140", pr_emst_soundness_seed_000140),
        ("property_campaigns::tests::pr_emst_soundness_seed_000141", pr_emst_soundness_seed_000141),
        ("property_campaigns::tests::pr_emst_soundness_seed_000142", pr_emst_soundness_seed_000142),
        ("property_campaigns::tests::pr_emst_soundness_seed_000143", pr_emst_soundness_seed_000143),
        ("property_campaigns::tests::pr_emst_soundness_seed_000144", pr_emst_soundness_seed_000144),
        ("property_campaigns::tests::pr_emst_soundness_seed_000145", pr_emst_soundness_seed_000145),
        ("property_campaigns::tests::pr_emst_soundness_seed_000146", pr_emst_soundness_seed_000146),
        ("property_campaigns::tests::pr_emst_soundness_seed_000147", pr_emst_soundness_seed_000147),
        ("property_campaigns::tests::pr_emst_soundness_seed_000148", pr_emst_soundness_seed_000148),
        ("property_campaigns::tests::pr_emst_soundness_seed_000149", pr_emst_soundness_seed_000149),
        ("property_campaigns::tests::rw_idempotent_seed_000000", rw_idempotent_seed_000000),
        ("property_campaigns::tests::rw_idempotent_seed_000001", rw_idempotent_seed_000001),
        ("property_campaigns::tests::rw_idempotent_seed_000002", rw_idempotent_seed_000002),
        ("property_campaigns::tests::rw_idempotent_seed_000003", rw_idempotent_seed_000003),
        ("property_campaigns::tests::rw_idempotent_seed_000004", rw_idempotent_seed_000004),
        ("property_campaigns::tests::rw_idempotent_seed_000005", rw_idempotent_seed_000005),
        ("property_campaigns::tests::rw_idempotent_seed_000006", rw_idempotent_seed_000006),
        ("property_campaigns::tests::rw_idempotent_seed_000007", rw_idempotent_seed_000007),
        ("property_campaigns::tests::rw_idempotent_seed_000008", rw_idempotent_seed_000008),
        ("property_campaigns::tests::rw_idempotent_seed_000009", rw_idempotent_seed_000009),
        ("property_campaigns::tests::rw_idempotent_seed_000010", rw_idempotent_seed_000010),
        ("property_campaigns::tests::rw_idempotent_seed_000011", rw_idempotent_seed_000011),
        ("property_campaigns::tests::rw_idempotent_seed_000012", rw_idempotent_seed_000012),
        ("property_campaigns::tests::rw_idempotent_seed_000013", rw_idempotent_seed_000013),
        ("property_campaigns::tests::rw_idempotent_seed_000014", rw_idempotent_seed_000014),
        ("property_campaigns::tests::rw_idempotent_seed_000015", rw_idempotent_seed_000015),
        ("property_campaigns::tests::rw_idempotent_seed_000016", rw_idempotent_seed_000016),
        ("property_campaigns::tests::rw_idempotent_seed_000017", rw_idempotent_seed_000017),
        ("property_campaigns::tests::rw_idempotent_seed_000018", rw_idempotent_seed_000018),
        ("property_campaigns::tests::rw_idempotent_seed_000019", rw_idempotent_seed_000019),
        ("property_campaigns::tests::rw_idempotent_seed_000020", rw_idempotent_seed_000020),
        ("property_campaigns::tests::rw_idempotent_seed_000021", rw_idempotent_seed_000021),
        ("property_campaigns::tests::rw_idempotent_seed_000022", rw_idempotent_seed_000022),
        ("property_campaigns::tests::rw_idempotent_seed_000023", rw_idempotent_seed_000023),
        ("property_campaigns::tests::rw_idempotent_seed_000024", rw_idempotent_seed_000024),
        ("property_campaigns::tests::rw_idempotent_seed_000025", rw_idempotent_seed_000025),
        ("property_campaigns::tests::rw_idempotent_seed_000026", rw_idempotent_seed_000026),
        ("property_campaigns::tests::rw_idempotent_seed_000027", rw_idempotent_seed_000027),
        ("property_campaigns::tests::rw_idempotent_seed_000028", rw_idempotent_seed_000028),
        ("property_campaigns::tests::rw_idempotent_seed_000029", rw_idempotent_seed_000029),
        ("property_campaigns::tests::rw_idempotent_seed_000030", rw_idempotent_seed_000030),
        ("property_campaigns::tests::rw_idempotent_seed_000031", rw_idempotent_seed_000031),
        ("property_campaigns::tests::rw_idempotent_seed_000032", rw_idempotent_seed_000032),
        ("property_campaigns::tests::rw_idempotent_seed_000033", rw_idempotent_seed_000033),
        ("property_campaigns::tests::rw_idempotent_seed_000034", rw_idempotent_seed_000034),
        ("property_campaigns::tests::rw_idempotent_seed_000035", rw_idempotent_seed_000035),
        ("property_campaigns::tests::rw_idempotent_seed_000036", rw_idempotent_seed_000036),
        ("property_campaigns::tests::rw_idempotent_seed_000037", rw_idempotent_seed_000037),
        ("property_campaigns::tests::rw_idempotent_seed_000038", rw_idempotent_seed_000038),
        ("property_campaigns::tests::rw_idempotent_seed_000039", rw_idempotent_seed_000039),
        ("property_campaigns::tests::rw_idempotent_seed_000040", rw_idempotent_seed_000040),
        ("property_campaigns::tests::rw_idempotent_seed_000041", rw_idempotent_seed_000041),
        ("property_campaigns::tests::rw_idempotent_seed_000042", rw_idempotent_seed_000042),
        ("property_campaigns::tests::rw_idempotent_seed_000043", rw_idempotent_seed_000043),
        ("property_campaigns::tests::rw_idempotent_seed_000044", rw_idempotent_seed_000044),
        ("property_campaigns::tests::rw_idempotent_seed_000045", rw_idempotent_seed_000045),
        ("property_campaigns::tests::rw_idempotent_seed_000046", rw_idempotent_seed_000046),
        ("property_campaigns::tests::rw_idempotent_seed_000047", rw_idempotent_seed_000047),
        ("property_campaigns::tests::rw_idempotent_seed_000048", rw_idempotent_seed_000048),
        ("property_campaigns::tests::rw_idempotent_seed_000049", rw_idempotent_seed_000049),
        ("property_campaigns::tests::rw_idempotent_seed_000050", rw_idempotent_seed_000050),
        ("property_campaigns::tests::rw_idempotent_seed_000051", rw_idempotent_seed_000051),
        ("property_campaigns::tests::rw_idempotent_seed_000052", rw_idempotent_seed_000052),
        ("property_campaigns::tests::rw_idempotent_seed_000053", rw_idempotent_seed_000053),
        ("property_campaigns::tests::rw_idempotent_seed_000054", rw_idempotent_seed_000054),
        ("property_campaigns::tests::rw_idempotent_seed_000055", rw_idempotent_seed_000055),
        ("property_campaigns::tests::rw_idempotent_seed_000056", rw_idempotent_seed_000056),
        ("property_campaigns::tests::rw_idempotent_seed_000057", rw_idempotent_seed_000057),
        ("property_campaigns::tests::rw_idempotent_seed_000058", rw_idempotent_seed_000058),
        ("property_campaigns::tests::rw_idempotent_seed_000059", rw_idempotent_seed_000059),
        ("property_campaigns::tests::rw_idempotent_seed_000060", rw_idempotent_seed_000060),
        ("property_campaigns::tests::rw_idempotent_seed_000061", rw_idempotent_seed_000061),
        ("property_campaigns::tests::rw_idempotent_seed_000062", rw_idempotent_seed_000062),
        ("property_campaigns::tests::rw_idempotent_seed_000063", rw_idempotent_seed_000063),
        ("property_campaigns::tests::rw_idempotent_seed_000064", rw_idempotent_seed_000064),
        ("property_campaigns::tests::rw_idempotent_seed_000065", rw_idempotent_seed_000065),
        ("property_campaigns::tests::rw_idempotent_seed_000066", rw_idempotent_seed_000066),
        ("property_campaigns::tests::rw_idempotent_seed_000067", rw_idempotent_seed_000067),
        ("property_campaigns::tests::rw_idempotent_seed_000068", rw_idempotent_seed_000068),
        ("property_campaigns::tests::rw_idempotent_seed_000069", rw_idempotent_seed_000069),
        ("property_campaigns::tests::rw_idempotent_seed_000070", rw_idempotent_seed_000070),
        ("property_campaigns::tests::rw_idempotent_seed_000071", rw_idempotent_seed_000071),
        ("property_campaigns::tests::rw_idempotent_seed_000072", rw_idempotent_seed_000072),
        ("property_campaigns::tests::rw_idempotent_seed_000073", rw_idempotent_seed_000073),
        ("property_campaigns::tests::rw_idempotent_seed_000074", rw_idempotent_seed_000074),
        ("property_campaigns::tests::rw_idempotent_seed_000075", rw_idempotent_seed_000075),
        ("property_campaigns::tests::rw_idempotent_seed_000076", rw_idempotent_seed_000076),
        ("property_campaigns::tests::rw_idempotent_seed_000077", rw_idempotent_seed_000077),
        ("property_campaigns::tests::rw_idempotent_seed_000078", rw_idempotent_seed_000078),
        ("property_campaigns::tests::rw_idempotent_seed_000079", rw_idempotent_seed_000079),
        ("property_campaigns::tests::rw_idempotent_seed_000080", rw_idempotent_seed_000080),
        ("property_campaigns::tests::rw_idempotent_seed_000081", rw_idempotent_seed_000081),
        ("property_campaigns::tests::rw_idempotent_seed_000082", rw_idempotent_seed_000082),
        ("property_campaigns::tests::rw_idempotent_seed_000083", rw_idempotent_seed_000083),
        ("property_campaigns::tests::rw_idempotent_seed_000084", rw_idempotent_seed_000084),
        ("property_campaigns::tests::rw_idempotent_seed_000085", rw_idempotent_seed_000085),
        ("property_campaigns::tests::rw_idempotent_seed_000086", rw_idempotent_seed_000086),
        ("property_campaigns::tests::rw_idempotent_seed_000087", rw_idempotent_seed_000087),
        ("property_campaigns::tests::rw_idempotent_seed_000088", rw_idempotent_seed_000088),
        ("property_campaigns::tests::rw_idempotent_seed_000089", rw_idempotent_seed_000089),
        ("property_campaigns::tests::rw_idempotent_seed_000090", rw_idempotent_seed_000090),
        ("property_campaigns::tests::rw_idempotent_seed_000091", rw_idempotent_seed_000091),
        ("property_campaigns::tests::rw_idempotent_seed_000092", rw_idempotent_seed_000092),
        ("property_campaigns::tests::rw_idempotent_seed_000093", rw_idempotent_seed_000093),
        ("property_campaigns::tests::rw_idempotent_seed_000094", rw_idempotent_seed_000094),
        ("property_campaigns::tests::rw_idempotent_seed_000095", rw_idempotent_seed_000095),
        ("property_campaigns::tests::rw_idempotent_seed_000096", rw_idempotent_seed_000096),
        ("property_campaigns::tests::rw_idempotent_seed_000097", rw_idempotent_seed_000097),
        ("property_campaigns::tests::rw_idempotent_seed_000098", rw_idempotent_seed_000098),
        ("property_campaigns::tests::rw_idempotent_seed_000099", rw_idempotent_seed_000099),
        ("property_campaigns::tests::rw_idempotent_seed_000100", rw_idempotent_seed_000100),
        ("property_campaigns::tests::rw_idempotent_seed_000101", rw_idempotent_seed_000101),
        ("property_campaigns::tests::rw_idempotent_seed_000102", rw_idempotent_seed_000102),
        ("property_campaigns::tests::rw_idempotent_seed_000103", rw_idempotent_seed_000103),
        ("property_campaigns::tests::rw_idempotent_seed_000104", rw_idempotent_seed_000104),
        ("property_campaigns::tests::rw_idempotent_seed_000105", rw_idempotent_seed_000105),
        ("property_campaigns::tests::rw_idempotent_seed_000106", rw_idempotent_seed_000106),
        ("property_campaigns::tests::rw_idempotent_seed_000107", rw_idempotent_seed_000107),
        ("property_campaigns::tests::rw_idempotent_seed_000108", rw_idempotent_seed_000108),
        ("property_campaigns::tests::rw_idempotent_seed_000109", rw_idempotent_seed_000109),
        ("property_campaigns::tests::rw_idempotent_seed_000110", rw_idempotent_seed_000110),
        ("property_campaigns::tests::rw_idempotent_seed_000111", rw_idempotent_seed_000111),
        ("property_campaigns::tests::rw_idempotent_seed_000112", rw_idempotent_seed_000112),
        ("property_campaigns::tests::rw_idempotent_seed_000113", rw_idempotent_seed_000113),
        ("property_campaigns::tests::rw_idempotent_seed_000114", rw_idempotent_seed_000114),
        ("property_campaigns::tests::rw_idempotent_seed_000115", rw_idempotent_seed_000115),
        ("property_campaigns::tests::rw_idempotent_seed_000116", rw_idempotent_seed_000116),
        ("property_campaigns::tests::rw_idempotent_seed_000117", rw_idempotent_seed_000117),
        ("property_campaigns::tests::rw_idempotent_seed_000118", rw_idempotent_seed_000118),
        ("property_campaigns::tests::rw_idempotent_seed_000119", rw_idempotent_seed_000119),
        ("property_campaigns::tests::rw_idempotent_seed_000120", rw_idempotent_seed_000120),
        ("property_campaigns::tests::rw_idempotent_seed_000121", rw_idempotent_seed_000121),
        ("property_campaigns::tests::rw_idempotent_seed_000122", rw_idempotent_seed_000122),
        ("property_campaigns::tests::rw_idempotent_seed_000123", rw_idempotent_seed_000123),
        ("property_campaigns::tests::rw_idempotent_seed_000124", rw_idempotent_seed_000124),
        ("property_campaigns::tests::rw_idempotent_seed_000125", rw_idempotent_seed_000125),
        ("property_campaigns::tests::rw_idempotent_seed_000126", rw_idempotent_seed_000126),
        ("property_campaigns::tests::rw_idempotent_seed_000127", rw_idempotent_seed_000127),
        ("property_campaigns::tests::rw_idempotent_seed_000128", rw_idempotent_seed_000128),
        ("property_campaigns::tests::rw_idempotent_seed_000129", rw_idempotent_seed_000129),
        ("property_campaigns::tests::rw_idempotent_seed_000130", rw_idempotent_seed_000130),
        ("property_campaigns::tests::rw_idempotent_seed_000131", rw_idempotent_seed_000131),
        ("property_campaigns::tests::rw_idempotent_seed_000132", rw_idempotent_seed_000132),
        ("property_campaigns::tests::rw_idempotent_seed_000133", rw_idempotent_seed_000133),
        ("property_campaigns::tests::rw_idempotent_seed_000134", rw_idempotent_seed_000134),
        ("property_campaigns::tests::rw_idempotent_seed_000135", rw_idempotent_seed_000135),
        ("property_campaigns::tests::rw_idempotent_seed_000136", rw_idempotent_seed_000136),
        ("property_campaigns::tests::rw_idempotent_seed_000137", rw_idempotent_seed_000137),
        ("property_campaigns::tests::rw_idempotent_seed_000138", rw_idempotent_seed_000138),
        ("property_campaigns::tests::rw_idempotent_seed_000139", rw_idempotent_seed_000139),
        ("property_campaigns::tests::rw_idempotent_seed_000140", rw_idempotent_seed_000140),
        ("property_campaigns::tests::rw_idempotent_seed_000141", rw_idempotent_seed_000141),
        ("property_campaigns::tests::rw_idempotent_seed_000142", rw_idempotent_seed_000142),
        ("property_campaigns::tests::rw_idempotent_seed_000143", rw_idempotent_seed_000143),
        ("property_campaigns::tests::rw_idempotent_seed_000144", rw_idempotent_seed_000144),
        ("property_campaigns::tests::rw_idempotent_seed_000145", rw_idempotent_seed_000145),
        ("property_campaigns::tests::rw_idempotent_seed_000146", rw_idempotent_seed_000146),
        ("property_campaigns::tests::rw_idempotent_seed_000147", rw_idempotent_seed_000147),
        ("property_campaigns::tests::rw_idempotent_seed_000148", rw_idempotent_seed_000148),
        ("property_campaigns::tests::rw_idempotent_seed_000149", rw_idempotent_seed_000149),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000000", rw_duplicate_invariant_seed_000000),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000001", rw_duplicate_invariant_seed_000001),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000002", rw_duplicate_invariant_seed_000002),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000003", rw_duplicate_invariant_seed_000003),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000004", rw_duplicate_invariant_seed_000004),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000005", rw_duplicate_invariant_seed_000005),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000006", rw_duplicate_invariant_seed_000006),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000007", rw_duplicate_invariant_seed_000007),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000008", rw_duplicate_invariant_seed_000008),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000009", rw_duplicate_invariant_seed_000009),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000010", rw_duplicate_invariant_seed_000010),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000011", rw_duplicate_invariant_seed_000011),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000012", rw_duplicate_invariant_seed_000012),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000013", rw_duplicate_invariant_seed_000013),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000014", rw_duplicate_invariant_seed_000014),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000015", rw_duplicate_invariant_seed_000015),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000016", rw_duplicate_invariant_seed_000016),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000017", rw_duplicate_invariant_seed_000017),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000018", rw_duplicate_invariant_seed_000018),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000019", rw_duplicate_invariant_seed_000019),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000020", rw_duplicate_invariant_seed_000020),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000021", rw_duplicate_invariant_seed_000021),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000022", rw_duplicate_invariant_seed_000022),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000023", rw_duplicate_invariant_seed_000023),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000024", rw_duplicate_invariant_seed_000024),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000025", rw_duplicate_invariant_seed_000025),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000026", rw_duplicate_invariant_seed_000026),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000027", rw_duplicate_invariant_seed_000027),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000028", rw_duplicate_invariant_seed_000028),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000029", rw_duplicate_invariant_seed_000029),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000030", rw_duplicate_invariant_seed_000030),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000031", rw_duplicate_invariant_seed_000031),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000032", rw_duplicate_invariant_seed_000032),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000033", rw_duplicate_invariant_seed_000033),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000034", rw_duplicate_invariant_seed_000034),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000035", rw_duplicate_invariant_seed_000035),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000036", rw_duplicate_invariant_seed_000036),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000037", rw_duplicate_invariant_seed_000037),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000038", rw_duplicate_invariant_seed_000038),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000039", rw_duplicate_invariant_seed_000039),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000040", rw_duplicate_invariant_seed_000040),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000041", rw_duplicate_invariant_seed_000041),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000042", rw_duplicate_invariant_seed_000042),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000043", rw_duplicate_invariant_seed_000043),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000044", rw_duplicate_invariant_seed_000044),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000045", rw_duplicate_invariant_seed_000045),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000046", rw_duplicate_invariant_seed_000046),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000047", rw_duplicate_invariant_seed_000047),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000048", rw_duplicate_invariant_seed_000048),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000049", rw_duplicate_invariant_seed_000049),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000050", rw_duplicate_invariant_seed_000050),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000051", rw_duplicate_invariant_seed_000051),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000052", rw_duplicate_invariant_seed_000052),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000053", rw_duplicate_invariant_seed_000053),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000054", rw_duplicate_invariant_seed_000054),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000055", rw_duplicate_invariant_seed_000055),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000056", rw_duplicate_invariant_seed_000056),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000057", rw_duplicate_invariant_seed_000057),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000058", rw_duplicate_invariant_seed_000058),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000059", rw_duplicate_invariant_seed_000059),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000060", rw_duplicate_invariant_seed_000060),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000061", rw_duplicate_invariant_seed_000061),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000062", rw_duplicate_invariant_seed_000062),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000063", rw_duplicate_invariant_seed_000063),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000064", rw_duplicate_invariant_seed_000064),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000065", rw_duplicate_invariant_seed_000065),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000066", rw_duplicate_invariant_seed_000066),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000067", rw_duplicate_invariant_seed_000067),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000068", rw_duplicate_invariant_seed_000068),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000069", rw_duplicate_invariant_seed_000069),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000070", rw_duplicate_invariant_seed_000070),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000071", rw_duplicate_invariant_seed_000071),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000072", rw_duplicate_invariant_seed_000072),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000073", rw_duplicate_invariant_seed_000073),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000074", rw_duplicate_invariant_seed_000074),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000075", rw_duplicate_invariant_seed_000075),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000076", rw_duplicate_invariant_seed_000076),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000077", rw_duplicate_invariant_seed_000077),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000078", rw_duplicate_invariant_seed_000078),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000079", rw_duplicate_invariant_seed_000079),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000080", rw_duplicate_invariant_seed_000080),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000081", rw_duplicate_invariant_seed_000081),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000082", rw_duplicate_invariant_seed_000082),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000083", rw_duplicate_invariant_seed_000083),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000084", rw_duplicate_invariant_seed_000084),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000085", rw_duplicate_invariant_seed_000085),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000086", rw_duplicate_invariant_seed_000086),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000087", rw_duplicate_invariant_seed_000087),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000088", rw_duplicate_invariant_seed_000088),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000089", rw_duplicate_invariant_seed_000089),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000090", rw_duplicate_invariant_seed_000090),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000091", rw_duplicate_invariant_seed_000091),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000092", rw_duplicate_invariant_seed_000092),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000093", rw_duplicate_invariant_seed_000093),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000094", rw_duplicate_invariant_seed_000094),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000095", rw_duplicate_invariant_seed_000095),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000096", rw_duplicate_invariant_seed_000096),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000097", rw_duplicate_invariant_seed_000097),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000098", rw_duplicate_invariant_seed_000098),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000099", rw_duplicate_invariant_seed_000099),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000100", rw_duplicate_invariant_seed_000100),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000101", rw_duplicate_invariant_seed_000101),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000102", rw_duplicate_invariant_seed_000102),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000103", rw_duplicate_invariant_seed_000103),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000104", rw_duplicate_invariant_seed_000104),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000105", rw_duplicate_invariant_seed_000105),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000106", rw_duplicate_invariant_seed_000106),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000107", rw_duplicate_invariant_seed_000107),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000108", rw_duplicate_invariant_seed_000108),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000109", rw_duplicate_invariant_seed_000109),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000110", rw_duplicate_invariant_seed_000110),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000111", rw_duplicate_invariant_seed_000111),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000112", rw_duplicate_invariant_seed_000112),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000113", rw_duplicate_invariant_seed_000113),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000114", rw_duplicate_invariant_seed_000114),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000115", rw_duplicate_invariant_seed_000115),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000116", rw_duplicate_invariant_seed_000116),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000117", rw_duplicate_invariant_seed_000117),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000118", rw_duplicate_invariant_seed_000118),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000119", rw_duplicate_invariant_seed_000119),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000120", rw_duplicate_invariant_seed_000120),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000121", rw_duplicate_invariant_seed_000121),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000122", rw_duplicate_invariant_seed_000122),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000123", rw_duplicate_invariant_seed_000123),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000124", rw_duplicate_invariant_seed_000124),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000125", rw_duplicate_invariant_seed_000125),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000126", rw_duplicate_invariant_seed_000126),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000127", rw_duplicate_invariant_seed_000127),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000128", rw_duplicate_invariant_seed_000128),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000129", rw_duplicate_invariant_seed_000129),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000130", rw_duplicate_invariant_seed_000130),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000131", rw_duplicate_invariant_seed_000131),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000132", rw_duplicate_invariant_seed_000132),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000133", rw_duplicate_invariant_seed_000133),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000134", rw_duplicate_invariant_seed_000134),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000135", rw_duplicate_invariant_seed_000135),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000136", rw_duplicate_invariant_seed_000136),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000137", rw_duplicate_invariant_seed_000137),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000138", rw_duplicate_invariant_seed_000138),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000139", rw_duplicate_invariant_seed_000139),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000140", rw_duplicate_invariant_seed_000140),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000141", rw_duplicate_invariant_seed_000141),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000142", rw_duplicate_invariant_seed_000142),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000143", rw_duplicate_invariant_seed_000143),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000144", rw_duplicate_invariant_seed_000144),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000145", rw_duplicate_invariant_seed_000145),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000146", rw_duplicate_invariant_seed_000146),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000147", rw_duplicate_invariant_seed_000147),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000148", rw_duplicate_invariant_seed_000148),
        ("property_campaigns::tests::rw_duplicate_invariant_seed_000149", rw_duplicate_invariant_seed_000149),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000000", rw_conflict_order_independent_seed_000000),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000001", rw_conflict_order_independent_seed_000001),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000002", rw_conflict_order_independent_seed_000002),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000003", rw_conflict_order_independent_seed_000003),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000004", rw_conflict_order_independent_seed_000004),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000005", rw_conflict_order_independent_seed_000005),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000006", rw_conflict_order_independent_seed_000006),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000007", rw_conflict_order_independent_seed_000007),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000008", rw_conflict_order_independent_seed_000008),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000009", rw_conflict_order_independent_seed_000009),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000010", rw_conflict_order_independent_seed_000010),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000011", rw_conflict_order_independent_seed_000011),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000012", rw_conflict_order_independent_seed_000012),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000013", rw_conflict_order_independent_seed_000013),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000014", rw_conflict_order_independent_seed_000014),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000015", rw_conflict_order_independent_seed_000015),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000016", rw_conflict_order_independent_seed_000016),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000017", rw_conflict_order_independent_seed_000017),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000018", rw_conflict_order_independent_seed_000018),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000019", rw_conflict_order_independent_seed_000019),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000020", rw_conflict_order_independent_seed_000020),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000021", rw_conflict_order_independent_seed_000021),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000022", rw_conflict_order_independent_seed_000022),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000023", rw_conflict_order_independent_seed_000023),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000024", rw_conflict_order_independent_seed_000024),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000025", rw_conflict_order_independent_seed_000025),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000026", rw_conflict_order_independent_seed_000026),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000027", rw_conflict_order_independent_seed_000027),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000028", rw_conflict_order_independent_seed_000028),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000029", rw_conflict_order_independent_seed_000029),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000030", rw_conflict_order_independent_seed_000030),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000031", rw_conflict_order_independent_seed_000031),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000032", rw_conflict_order_independent_seed_000032),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000033", rw_conflict_order_independent_seed_000033),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000034", rw_conflict_order_independent_seed_000034),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000035", rw_conflict_order_independent_seed_000035),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000036", rw_conflict_order_independent_seed_000036),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000037", rw_conflict_order_independent_seed_000037),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000038", rw_conflict_order_independent_seed_000038),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000039", rw_conflict_order_independent_seed_000039),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000040", rw_conflict_order_independent_seed_000040),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000041", rw_conflict_order_independent_seed_000041),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000042", rw_conflict_order_independent_seed_000042),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000043", rw_conflict_order_independent_seed_000043),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000044", rw_conflict_order_independent_seed_000044),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000045", rw_conflict_order_independent_seed_000045),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000046", rw_conflict_order_independent_seed_000046),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000047", rw_conflict_order_independent_seed_000047),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000048", rw_conflict_order_independent_seed_000048),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000049", rw_conflict_order_independent_seed_000049),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000050", rw_conflict_order_independent_seed_000050),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000051", rw_conflict_order_independent_seed_000051),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000052", rw_conflict_order_independent_seed_000052),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000053", rw_conflict_order_independent_seed_000053),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000054", rw_conflict_order_independent_seed_000054),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000055", rw_conflict_order_independent_seed_000055),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000056", rw_conflict_order_independent_seed_000056),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000057", rw_conflict_order_independent_seed_000057),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000058", rw_conflict_order_independent_seed_000058),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000059", rw_conflict_order_independent_seed_000059),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000060", rw_conflict_order_independent_seed_000060),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000061", rw_conflict_order_independent_seed_000061),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000062", rw_conflict_order_independent_seed_000062),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000063", rw_conflict_order_independent_seed_000063),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000064", rw_conflict_order_independent_seed_000064),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000065", rw_conflict_order_independent_seed_000065),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000066", rw_conflict_order_independent_seed_000066),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000067", rw_conflict_order_independent_seed_000067),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000068", rw_conflict_order_independent_seed_000068),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000069", rw_conflict_order_independent_seed_000069),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000070", rw_conflict_order_independent_seed_000070),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000071", rw_conflict_order_independent_seed_000071),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000072", rw_conflict_order_independent_seed_000072),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000073", rw_conflict_order_independent_seed_000073),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000074", rw_conflict_order_independent_seed_000074),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000075", rw_conflict_order_independent_seed_000075),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000076", rw_conflict_order_independent_seed_000076),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000077", rw_conflict_order_independent_seed_000077),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000078", rw_conflict_order_independent_seed_000078),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000079", rw_conflict_order_independent_seed_000079),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000080", rw_conflict_order_independent_seed_000080),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000081", rw_conflict_order_independent_seed_000081),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000082", rw_conflict_order_independent_seed_000082),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000083", rw_conflict_order_independent_seed_000083),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000084", rw_conflict_order_independent_seed_000084),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000085", rw_conflict_order_independent_seed_000085),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000086", rw_conflict_order_independent_seed_000086),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000087", rw_conflict_order_independent_seed_000087),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000088", rw_conflict_order_independent_seed_000088),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000089", rw_conflict_order_independent_seed_000089),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000090", rw_conflict_order_independent_seed_000090),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000091", rw_conflict_order_independent_seed_000091),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000092", rw_conflict_order_independent_seed_000092),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000093", rw_conflict_order_independent_seed_000093),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000094", rw_conflict_order_independent_seed_000094),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000095", rw_conflict_order_independent_seed_000095),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000096", rw_conflict_order_independent_seed_000096),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000097", rw_conflict_order_independent_seed_000097),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000098", rw_conflict_order_independent_seed_000098),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000099", rw_conflict_order_independent_seed_000099),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000100", rw_conflict_order_independent_seed_000100),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000101", rw_conflict_order_independent_seed_000101),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000102", rw_conflict_order_independent_seed_000102),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000103", rw_conflict_order_independent_seed_000103),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000104", rw_conflict_order_independent_seed_000104),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000105", rw_conflict_order_independent_seed_000105),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000106", rw_conflict_order_independent_seed_000106),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000107", rw_conflict_order_independent_seed_000107),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000108", rw_conflict_order_independent_seed_000108),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000109", rw_conflict_order_independent_seed_000109),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000110", rw_conflict_order_independent_seed_000110),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000111", rw_conflict_order_independent_seed_000111),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000112", rw_conflict_order_independent_seed_000112),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000113", rw_conflict_order_independent_seed_000113),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000114", rw_conflict_order_independent_seed_000114),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000115", rw_conflict_order_independent_seed_000115),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000116", rw_conflict_order_independent_seed_000116),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000117", rw_conflict_order_independent_seed_000117),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000118", rw_conflict_order_independent_seed_000118),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000119", rw_conflict_order_independent_seed_000119),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000120", rw_conflict_order_independent_seed_000120),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000121", rw_conflict_order_independent_seed_000121),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000122", rw_conflict_order_independent_seed_000122),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000123", rw_conflict_order_independent_seed_000123),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000124", rw_conflict_order_independent_seed_000124),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000125", rw_conflict_order_independent_seed_000125),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000126", rw_conflict_order_independent_seed_000126),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000127", rw_conflict_order_independent_seed_000127),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000128", rw_conflict_order_independent_seed_000128),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000129", rw_conflict_order_independent_seed_000129),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000130", rw_conflict_order_independent_seed_000130),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000131", rw_conflict_order_independent_seed_000131),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000132", rw_conflict_order_independent_seed_000132),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000133", rw_conflict_order_independent_seed_000133),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000134", rw_conflict_order_independent_seed_000134),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000135", rw_conflict_order_independent_seed_000135),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000136", rw_conflict_order_independent_seed_000136),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000137", rw_conflict_order_independent_seed_000137),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000138", rw_conflict_order_independent_seed_000138),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000139", rw_conflict_order_independent_seed_000139),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000140", rw_conflict_order_independent_seed_000140),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000141", rw_conflict_order_independent_seed_000141),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000142", rw_conflict_order_independent_seed_000142),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000143", rw_conflict_order_independent_seed_000143),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000144", rw_conflict_order_independent_seed_000144),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000145", rw_conflict_order_independent_seed_000145),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000146", rw_conflict_order_independent_seed_000146),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000147", rw_conflict_order_independent_seed_000147),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000148", rw_conflict_order_independent_seed_000148),
        ("property_campaigns::tests::rw_conflict_order_independent_seed_000149", rw_conflict_order_independent_seed_000149),
        ("property_campaigns::tests::as_determinism_seed_000000", as_determinism_seed_000000),
        ("property_campaigns::tests::as_determinism_seed_000001", as_determinism_seed_000001),
        ("property_campaigns::tests::as_determinism_seed_000002", as_determinism_seed_000002),
        ("property_campaigns::tests::as_determinism_seed_000003", as_determinism_seed_000003),
        ("property_campaigns::tests::as_determinism_seed_000004", as_determinism_seed_000004),
        ("property_campaigns::tests::as_determinism_seed_000005", as_determinism_seed_000005),
        ("property_campaigns::tests::as_determinism_seed_000006", as_determinism_seed_000006),
        ("property_campaigns::tests::as_determinism_seed_000007", as_determinism_seed_000007),
        ("property_campaigns::tests::as_determinism_seed_000008", as_determinism_seed_000008),
        ("property_campaigns::tests::as_determinism_seed_000009", as_determinism_seed_000009),
        ("property_campaigns::tests::as_determinism_seed_000010", as_determinism_seed_000010),
        ("property_campaigns::tests::as_determinism_seed_000011", as_determinism_seed_000011),
        ("property_campaigns::tests::as_determinism_seed_000012", as_determinism_seed_000012),
        ("property_campaigns::tests::as_determinism_seed_000013", as_determinism_seed_000013),
        ("property_campaigns::tests::as_determinism_seed_000014", as_determinism_seed_000014),
        ("property_campaigns::tests::as_determinism_seed_000015", as_determinism_seed_000015),
        ("property_campaigns::tests::as_determinism_seed_000016", as_determinism_seed_000016),
        ("property_campaigns::tests::as_determinism_seed_000017", as_determinism_seed_000017),
        ("property_campaigns::tests::as_determinism_seed_000018", as_determinism_seed_000018),
        ("property_campaigns::tests::as_determinism_seed_000019", as_determinism_seed_000019),
        ("property_campaigns::tests::as_determinism_seed_000020", as_determinism_seed_000020),
        ("property_campaigns::tests::as_determinism_seed_000021", as_determinism_seed_000021),
        ("property_campaigns::tests::as_determinism_seed_000022", as_determinism_seed_000022),
        ("property_campaigns::tests::as_determinism_seed_000023", as_determinism_seed_000023),
        ("property_campaigns::tests::as_determinism_seed_000024", as_determinism_seed_000024),
        ("property_campaigns::tests::as_determinism_seed_000025", as_determinism_seed_000025),
        ("property_campaigns::tests::as_determinism_seed_000026", as_determinism_seed_000026),
        ("property_campaigns::tests::as_determinism_seed_000027", as_determinism_seed_000027),
        ("property_campaigns::tests::as_determinism_seed_000028", as_determinism_seed_000028),
        ("property_campaigns::tests::as_determinism_seed_000029", as_determinism_seed_000029),
        ("property_campaigns::tests::as_determinism_seed_000030", as_determinism_seed_000030),
        ("property_campaigns::tests::as_determinism_seed_000031", as_determinism_seed_000031),
        ("property_campaigns::tests::as_determinism_seed_000032", as_determinism_seed_000032),
        ("property_campaigns::tests::as_determinism_seed_000033", as_determinism_seed_000033),
        ("property_campaigns::tests::as_determinism_seed_000034", as_determinism_seed_000034),
        ("property_campaigns::tests::as_determinism_seed_000035", as_determinism_seed_000035),
        ("property_campaigns::tests::as_determinism_seed_000036", as_determinism_seed_000036),
        ("property_campaigns::tests::as_determinism_seed_000037", as_determinism_seed_000037),
        ("property_campaigns::tests::as_determinism_seed_000038", as_determinism_seed_000038),
        ("property_campaigns::tests::as_determinism_seed_000039", as_determinism_seed_000039),
        ("property_campaigns::tests::as_determinism_seed_000040", as_determinism_seed_000040),
        ("property_campaigns::tests::as_determinism_seed_000041", as_determinism_seed_000041),
        ("property_campaigns::tests::as_determinism_seed_000042", as_determinism_seed_000042),
        ("property_campaigns::tests::as_determinism_seed_000043", as_determinism_seed_000043),
        ("property_campaigns::tests::as_determinism_seed_000044", as_determinism_seed_000044),
        ("property_campaigns::tests::as_determinism_seed_000045", as_determinism_seed_000045),
        ("property_campaigns::tests::as_determinism_seed_000046", as_determinism_seed_000046),
        ("property_campaigns::tests::as_determinism_seed_000047", as_determinism_seed_000047),
        ("property_campaigns::tests::as_determinism_seed_000048", as_determinism_seed_000048),
        ("property_campaigns::tests::as_determinism_seed_000049", as_determinism_seed_000049),
        ("property_campaigns::tests::as_determinism_seed_000050", as_determinism_seed_000050),
        ("property_campaigns::tests::as_determinism_seed_000051", as_determinism_seed_000051),
        ("property_campaigns::tests::as_determinism_seed_000052", as_determinism_seed_000052),
        ("property_campaigns::tests::as_determinism_seed_000053", as_determinism_seed_000053),
        ("property_campaigns::tests::as_determinism_seed_000054", as_determinism_seed_000054),
        ("property_campaigns::tests::as_determinism_seed_000055", as_determinism_seed_000055),
        ("property_campaigns::tests::as_determinism_seed_000056", as_determinism_seed_000056),
        ("property_campaigns::tests::as_determinism_seed_000057", as_determinism_seed_000057),
        ("property_campaigns::tests::as_determinism_seed_000058", as_determinism_seed_000058),
        ("property_campaigns::tests::as_determinism_seed_000059", as_determinism_seed_000059),
        ("property_campaigns::tests::as_determinism_seed_000060", as_determinism_seed_000060),
        ("property_campaigns::tests::as_determinism_seed_000061", as_determinism_seed_000061),
        ("property_campaigns::tests::as_determinism_seed_000062", as_determinism_seed_000062),
        ("property_campaigns::tests::as_determinism_seed_000063", as_determinism_seed_000063),
        ("property_campaigns::tests::as_determinism_seed_000064", as_determinism_seed_000064),
        ("property_campaigns::tests::as_determinism_seed_000065", as_determinism_seed_000065),
        ("property_campaigns::tests::as_determinism_seed_000066", as_determinism_seed_000066),
        ("property_campaigns::tests::as_determinism_seed_000067", as_determinism_seed_000067),
        ("property_campaigns::tests::as_determinism_seed_000068", as_determinism_seed_000068),
        ("property_campaigns::tests::as_determinism_seed_000069", as_determinism_seed_000069),
        ("property_campaigns::tests::as_determinism_seed_000070", as_determinism_seed_000070),
        ("property_campaigns::tests::as_determinism_seed_000071", as_determinism_seed_000071),
        ("property_campaigns::tests::as_determinism_seed_000072", as_determinism_seed_000072),
        ("property_campaigns::tests::as_determinism_seed_000073", as_determinism_seed_000073),
        ("property_campaigns::tests::as_determinism_seed_000074", as_determinism_seed_000074),
        ("property_campaigns::tests::as_determinism_seed_000075", as_determinism_seed_000075),
        ("property_campaigns::tests::as_determinism_seed_000076", as_determinism_seed_000076),
        ("property_campaigns::tests::as_determinism_seed_000077", as_determinism_seed_000077),
        ("property_campaigns::tests::as_determinism_seed_000078", as_determinism_seed_000078),
        ("property_campaigns::tests::as_determinism_seed_000079", as_determinism_seed_000079),
        ("property_campaigns::tests::as_determinism_seed_000080", as_determinism_seed_000080),
        ("property_campaigns::tests::as_determinism_seed_000081", as_determinism_seed_000081),
        ("property_campaigns::tests::as_determinism_seed_000082", as_determinism_seed_000082),
        ("property_campaigns::tests::as_determinism_seed_000083", as_determinism_seed_000083),
        ("property_campaigns::tests::as_determinism_seed_000084", as_determinism_seed_000084),
        ("property_campaigns::tests::as_determinism_seed_000085", as_determinism_seed_000085),
        ("property_campaigns::tests::as_determinism_seed_000086", as_determinism_seed_000086),
        ("property_campaigns::tests::as_determinism_seed_000087", as_determinism_seed_000087),
        ("property_campaigns::tests::as_determinism_seed_000088", as_determinism_seed_000088),
        ("property_campaigns::tests::as_determinism_seed_000089", as_determinism_seed_000089),
        ("property_campaigns::tests::as_determinism_seed_000090", as_determinism_seed_000090),
        ("property_campaigns::tests::as_determinism_seed_000091", as_determinism_seed_000091),
        ("property_campaigns::tests::as_determinism_seed_000092", as_determinism_seed_000092),
        ("property_campaigns::tests::as_determinism_seed_000093", as_determinism_seed_000093),
        ("property_campaigns::tests::as_determinism_seed_000094", as_determinism_seed_000094),
        ("property_campaigns::tests::as_determinism_seed_000095", as_determinism_seed_000095),
        ("property_campaigns::tests::as_determinism_seed_000096", as_determinism_seed_000096),
        ("property_campaigns::tests::as_determinism_seed_000097", as_determinism_seed_000097),
        ("property_campaigns::tests::as_determinism_seed_000098", as_determinism_seed_000098),
        ("property_campaigns::tests::as_determinism_seed_000099", as_determinism_seed_000099),
        ("property_campaigns::tests::as_determinism_seed_000100", as_determinism_seed_000100),
        ("property_campaigns::tests::as_determinism_seed_000101", as_determinism_seed_000101),
        ("property_campaigns::tests::as_determinism_seed_000102", as_determinism_seed_000102),
        ("property_campaigns::tests::as_determinism_seed_000103", as_determinism_seed_000103),
        ("property_campaigns::tests::as_determinism_seed_000104", as_determinism_seed_000104),
        ("property_campaigns::tests::as_determinism_seed_000105", as_determinism_seed_000105),
        ("property_campaigns::tests::as_determinism_seed_000106", as_determinism_seed_000106),
        ("property_campaigns::tests::as_determinism_seed_000107", as_determinism_seed_000107),
        ("property_campaigns::tests::as_determinism_seed_000108", as_determinism_seed_000108),
        ("property_campaigns::tests::as_determinism_seed_000109", as_determinism_seed_000109),
        ("property_campaigns::tests::as_determinism_seed_000110", as_determinism_seed_000110),
        ("property_campaigns::tests::as_determinism_seed_000111", as_determinism_seed_000111),
        ("property_campaigns::tests::as_determinism_seed_000112", as_determinism_seed_000112),
        ("property_campaigns::tests::as_determinism_seed_000113", as_determinism_seed_000113),
        ("property_campaigns::tests::as_determinism_seed_000114", as_determinism_seed_000114),
        ("property_campaigns::tests::as_determinism_seed_000115", as_determinism_seed_000115),
        ("property_campaigns::tests::as_determinism_seed_000116", as_determinism_seed_000116),
        ("property_campaigns::tests::as_determinism_seed_000117", as_determinism_seed_000117),
        ("property_campaigns::tests::as_determinism_seed_000118", as_determinism_seed_000118),
        ("property_campaigns::tests::as_determinism_seed_000119", as_determinism_seed_000119),
        ("property_campaigns::tests::as_determinism_seed_000120", as_determinism_seed_000120),
        ("property_campaigns::tests::as_determinism_seed_000121", as_determinism_seed_000121),
        ("property_campaigns::tests::as_determinism_seed_000122", as_determinism_seed_000122),
        ("property_campaigns::tests::as_determinism_seed_000123", as_determinism_seed_000123),
        ("property_campaigns::tests::as_determinism_seed_000124", as_determinism_seed_000124),
        ("property_campaigns::tests::as_determinism_seed_000125", as_determinism_seed_000125),
        ("property_campaigns::tests::as_determinism_seed_000126", as_determinism_seed_000126),
        ("property_campaigns::tests::as_determinism_seed_000127", as_determinism_seed_000127),
        ("property_campaigns::tests::as_determinism_seed_000128", as_determinism_seed_000128),
        ("property_campaigns::tests::as_determinism_seed_000129", as_determinism_seed_000129),
        ("property_campaigns::tests::as_determinism_seed_000130", as_determinism_seed_000130),
        ("property_campaigns::tests::as_determinism_seed_000131", as_determinism_seed_000131),
        ("property_campaigns::tests::as_determinism_seed_000132", as_determinism_seed_000132),
        ("property_campaigns::tests::as_determinism_seed_000133", as_determinism_seed_000133),
        ("property_campaigns::tests::as_determinism_seed_000134", as_determinism_seed_000134),
        ("property_campaigns::tests::as_determinism_seed_000135", as_determinism_seed_000135),
        ("property_campaigns::tests::as_determinism_seed_000136", as_determinism_seed_000136),
        ("property_campaigns::tests::as_determinism_seed_000137", as_determinism_seed_000137),
        ("property_campaigns::tests::as_determinism_seed_000138", as_determinism_seed_000138),
        ("property_campaigns::tests::as_determinism_seed_000139", as_determinism_seed_000139),
        ("property_campaigns::tests::as_determinism_seed_000140", as_determinism_seed_000140),
        ("property_campaigns::tests::as_determinism_seed_000141", as_determinism_seed_000141),
        ("property_campaigns::tests::as_determinism_seed_000142", as_determinism_seed_000142),
        ("property_campaigns::tests::as_determinism_seed_000143", as_determinism_seed_000143),
        ("property_campaigns::tests::as_determinism_seed_000144", as_determinism_seed_000144),
        ("property_campaigns::tests::as_determinism_seed_000145", as_determinism_seed_000145),
        ("property_campaigns::tests::as_determinism_seed_000146", as_determinism_seed_000146),
        ("property_campaigns::tests::as_determinism_seed_000147", as_determinism_seed_000147),
        ("property_campaigns::tests::as_determinism_seed_000148", as_determinism_seed_000148),
        ("property_campaigns::tests::as_determinism_seed_000149", as_determinism_seed_000149),
        ("property_campaigns::tests::as_path_validity_seed_000000", as_path_validity_seed_000000),
        ("property_campaigns::tests::as_path_validity_seed_000001", as_path_validity_seed_000001),
        ("property_campaigns::tests::as_path_validity_seed_000002", as_path_validity_seed_000002),
        ("property_campaigns::tests::as_path_validity_seed_000003", as_path_validity_seed_000003),
        ("property_campaigns::tests::as_path_validity_seed_000004", as_path_validity_seed_000004),
        ("property_campaigns::tests::as_path_validity_seed_000005", as_path_validity_seed_000005),
        ("property_campaigns::tests::as_path_validity_seed_000006", as_path_validity_seed_000006),
        ("property_campaigns::tests::as_path_validity_seed_000007", as_path_validity_seed_000007),
        ("property_campaigns::tests::as_path_validity_seed_000008", as_path_validity_seed_000008),
        ("property_campaigns::tests::as_path_validity_seed_000009", as_path_validity_seed_000009),
        ("property_campaigns::tests::as_path_validity_seed_000010", as_path_validity_seed_000010),
        ("property_campaigns::tests::as_path_validity_seed_000011", as_path_validity_seed_000011),
        ("property_campaigns::tests::as_path_validity_seed_000012", as_path_validity_seed_000012),
        ("property_campaigns::tests::as_path_validity_seed_000013", as_path_validity_seed_000013),
        ("property_campaigns::tests::as_path_validity_seed_000014", as_path_validity_seed_000014),
        ("property_campaigns::tests::as_path_validity_seed_000015", as_path_validity_seed_000015),
        ("property_campaigns::tests::as_path_validity_seed_000016", as_path_validity_seed_000016),
        ("property_campaigns::tests::as_path_validity_seed_000017", as_path_validity_seed_000017),
        ("property_campaigns::tests::as_path_validity_seed_000018", as_path_validity_seed_000018),
        ("property_campaigns::tests::as_path_validity_seed_000019", as_path_validity_seed_000019),
        ("property_campaigns::tests::as_path_validity_seed_000020", as_path_validity_seed_000020),
        ("property_campaigns::tests::as_path_validity_seed_000021", as_path_validity_seed_000021),
        ("property_campaigns::tests::as_path_validity_seed_000022", as_path_validity_seed_000022),
        ("property_campaigns::tests::as_path_validity_seed_000023", as_path_validity_seed_000023),
        ("property_campaigns::tests::as_path_validity_seed_000024", as_path_validity_seed_000024),
        ("property_campaigns::tests::as_path_validity_seed_000025", as_path_validity_seed_000025),
        ("property_campaigns::tests::as_path_validity_seed_000026", as_path_validity_seed_000026),
        ("property_campaigns::tests::as_path_validity_seed_000027", as_path_validity_seed_000027),
        ("property_campaigns::tests::as_path_validity_seed_000028", as_path_validity_seed_000028),
        ("property_campaigns::tests::as_path_validity_seed_000029", as_path_validity_seed_000029),
        ("property_campaigns::tests::as_path_validity_seed_000030", as_path_validity_seed_000030),
        ("property_campaigns::tests::as_path_validity_seed_000031", as_path_validity_seed_000031),
        ("property_campaigns::tests::as_path_validity_seed_000032", as_path_validity_seed_000032),
        ("property_campaigns::tests::as_path_validity_seed_000033", as_path_validity_seed_000033),
        ("property_campaigns::tests::as_path_validity_seed_000034", as_path_validity_seed_000034),
        ("property_campaigns::tests::as_path_validity_seed_000035", as_path_validity_seed_000035),
        ("property_campaigns::tests::as_path_validity_seed_000036", as_path_validity_seed_000036),
        ("property_campaigns::tests::as_path_validity_seed_000037", as_path_validity_seed_000037),
        ("property_campaigns::tests::as_path_validity_seed_000038", as_path_validity_seed_000038),
        ("property_campaigns::tests::as_path_validity_seed_000039", as_path_validity_seed_000039),
        ("property_campaigns::tests::as_path_validity_seed_000040", as_path_validity_seed_000040),
        ("property_campaigns::tests::as_path_validity_seed_000041", as_path_validity_seed_000041),
        ("property_campaigns::tests::as_path_validity_seed_000042", as_path_validity_seed_000042),
        ("property_campaigns::tests::as_path_validity_seed_000043", as_path_validity_seed_000043),
        ("property_campaigns::tests::as_path_validity_seed_000044", as_path_validity_seed_000044),
        ("property_campaigns::tests::as_path_validity_seed_000045", as_path_validity_seed_000045),
        ("property_campaigns::tests::as_path_validity_seed_000046", as_path_validity_seed_000046),
        ("property_campaigns::tests::as_path_validity_seed_000047", as_path_validity_seed_000047),
        ("property_campaigns::tests::as_path_validity_seed_000048", as_path_validity_seed_000048),
        ("property_campaigns::tests::as_path_validity_seed_000049", as_path_validity_seed_000049),
        ("property_campaigns::tests::as_path_validity_seed_000050", as_path_validity_seed_000050),
        ("property_campaigns::tests::as_path_validity_seed_000051", as_path_validity_seed_000051),
        ("property_campaigns::tests::as_path_validity_seed_000052", as_path_validity_seed_000052),
        ("property_campaigns::tests::as_path_validity_seed_000053", as_path_validity_seed_000053),
        ("property_campaigns::tests::as_path_validity_seed_000054", as_path_validity_seed_000054),
        ("property_campaigns::tests::as_path_validity_seed_000055", as_path_validity_seed_000055),
        ("property_campaigns::tests::as_path_validity_seed_000056", as_path_validity_seed_000056),
        ("property_campaigns::tests::as_path_validity_seed_000057", as_path_validity_seed_000057),
        ("property_campaigns::tests::as_path_validity_seed_000058", as_path_validity_seed_000058),
        ("property_campaigns::tests::as_path_validity_seed_000059", as_path_validity_seed_000059),
        ("property_campaigns::tests::as_path_validity_seed_000060", as_path_validity_seed_000060),
        ("property_campaigns::tests::as_path_validity_seed_000061", as_path_validity_seed_000061),
        ("property_campaigns::tests::as_path_validity_seed_000062", as_path_validity_seed_000062),
        ("property_campaigns::tests::as_path_validity_seed_000063", as_path_validity_seed_000063),
        ("property_campaigns::tests::as_path_validity_seed_000064", as_path_validity_seed_000064),
        ("property_campaigns::tests::as_path_validity_seed_000065", as_path_validity_seed_000065),
        ("property_campaigns::tests::as_path_validity_seed_000066", as_path_validity_seed_000066),
        ("property_campaigns::tests::as_path_validity_seed_000067", as_path_validity_seed_000067),
        ("property_campaigns::tests::as_path_validity_seed_000068", as_path_validity_seed_000068),
        ("property_campaigns::tests::as_path_validity_seed_000069", as_path_validity_seed_000069),
        ("property_campaigns::tests::as_path_validity_seed_000070", as_path_validity_seed_000070),
        ("property_campaigns::tests::as_path_validity_seed_000071", as_path_validity_seed_000071),
        ("property_campaigns::tests::as_path_validity_seed_000072", as_path_validity_seed_000072),
        ("property_campaigns::tests::as_path_validity_seed_000073", as_path_validity_seed_000073),
        ("property_campaigns::tests::as_path_validity_seed_000074", as_path_validity_seed_000074),
        ("property_campaigns::tests::as_path_validity_seed_000075", as_path_validity_seed_000075),
        ("property_campaigns::tests::as_path_validity_seed_000076", as_path_validity_seed_000076),
        ("property_campaigns::tests::as_path_validity_seed_000077", as_path_validity_seed_000077),
        ("property_campaigns::tests::as_path_validity_seed_000078", as_path_validity_seed_000078),
        ("property_campaigns::tests::as_path_validity_seed_000079", as_path_validity_seed_000079),
        ("property_campaigns::tests::as_path_validity_seed_000080", as_path_validity_seed_000080),
        ("property_campaigns::tests::as_path_validity_seed_000081", as_path_validity_seed_000081),
        ("property_campaigns::tests::as_path_validity_seed_000082", as_path_validity_seed_000082),
        ("property_campaigns::tests::as_path_validity_seed_000083", as_path_validity_seed_000083),
        ("property_campaigns::tests::as_path_validity_seed_000084", as_path_validity_seed_000084),
        ("property_campaigns::tests::as_path_validity_seed_000085", as_path_validity_seed_000085),
        ("property_campaigns::tests::as_path_validity_seed_000086", as_path_validity_seed_000086),
        ("property_campaigns::tests::as_path_validity_seed_000087", as_path_validity_seed_000087),
        ("property_campaigns::tests::as_path_validity_seed_000088", as_path_validity_seed_000088),
        ("property_campaigns::tests::as_path_validity_seed_000089", as_path_validity_seed_000089),
        ("property_campaigns::tests::as_path_validity_seed_000090", as_path_validity_seed_000090),
        ("property_campaigns::tests::as_path_validity_seed_000091", as_path_validity_seed_000091),
        ("property_campaigns::tests::as_path_validity_seed_000092", as_path_validity_seed_000092),
        ("property_campaigns::tests::as_path_validity_seed_000093", as_path_validity_seed_000093),
        ("property_campaigns::tests::as_path_validity_seed_000094", as_path_validity_seed_000094),
        ("property_campaigns::tests::as_path_validity_seed_000095", as_path_validity_seed_000095),
        ("property_campaigns::tests::as_path_validity_seed_000096", as_path_validity_seed_000096),
        ("property_campaigns::tests::as_path_validity_seed_000097", as_path_validity_seed_000097),
        ("property_campaigns::tests::as_path_validity_seed_000098", as_path_validity_seed_000098),
        ("property_campaigns::tests::as_path_validity_seed_000099", as_path_validity_seed_000099),
        ("property_campaigns::tests::as_path_validity_seed_000100", as_path_validity_seed_000100),
        ("property_campaigns::tests::as_path_validity_seed_000101", as_path_validity_seed_000101),
        ("property_campaigns::tests::as_path_validity_seed_000102", as_path_validity_seed_000102),
        ("property_campaigns::tests::as_path_validity_seed_000103", as_path_validity_seed_000103),
        ("property_campaigns::tests::as_path_validity_seed_000104", as_path_validity_seed_000104),
        ("property_campaigns::tests::as_path_validity_seed_000105", as_path_validity_seed_000105),
        ("property_campaigns::tests::as_path_validity_seed_000106", as_path_validity_seed_000106),
        ("property_campaigns::tests::as_path_validity_seed_000107", as_path_validity_seed_000107),
        ("property_campaigns::tests::as_path_validity_seed_000108", as_path_validity_seed_000108),
        ("property_campaigns::tests::as_path_validity_seed_000109", as_path_validity_seed_000109),
        ("property_campaigns::tests::as_path_validity_seed_000110", as_path_validity_seed_000110),
        ("property_campaigns::tests::as_path_validity_seed_000111", as_path_validity_seed_000111),
        ("property_campaigns::tests::as_path_validity_seed_000112", as_path_validity_seed_000112),
        ("property_campaigns::tests::as_path_validity_seed_000113", as_path_validity_seed_000113),
        ("property_campaigns::tests::as_path_validity_seed_000114", as_path_validity_seed_000114),
        ("property_campaigns::tests::as_path_validity_seed_000115", as_path_validity_seed_000115),
        ("property_campaigns::tests::as_path_validity_seed_000116", as_path_validity_seed_000116),
        ("property_campaigns::tests::as_path_validity_seed_000117", as_path_validity_seed_000117),
        ("property_campaigns::tests::as_path_validity_seed_000118", as_path_validity_seed_000118),
        ("property_campaigns::tests::as_path_validity_seed_000119", as_path_validity_seed_000119),
        ("property_campaigns::tests::as_path_validity_seed_000120", as_path_validity_seed_000120),
        ("property_campaigns::tests::as_path_validity_seed_000121", as_path_validity_seed_000121),
        ("property_campaigns::tests::as_path_validity_seed_000122", as_path_validity_seed_000122),
        ("property_campaigns::tests::as_path_validity_seed_000123", as_path_validity_seed_000123),
        ("property_campaigns::tests::as_path_validity_seed_000124", as_path_validity_seed_000124),
        ("property_campaigns::tests::as_path_validity_seed_000125", as_path_validity_seed_000125),
        ("property_campaigns::tests::as_path_validity_seed_000126", as_path_validity_seed_000126),
        ("property_campaigns::tests::as_path_validity_seed_000127", as_path_validity_seed_000127),
        ("property_campaigns::tests::as_path_validity_seed_000128", as_path_validity_seed_000128),
        ("property_campaigns::tests::as_path_validity_seed_000129", as_path_validity_seed_000129),
        ("property_campaigns::tests::as_path_validity_seed_000130", as_path_validity_seed_000130),
        ("property_campaigns::tests::as_path_validity_seed_000131", as_path_validity_seed_000131),
        ("property_campaigns::tests::as_path_validity_seed_000132", as_path_validity_seed_000132),
        ("property_campaigns::tests::as_path_validity_seed_000133", as_path_validity_seed_000133),
        ("property_campaigns::tests::as_path_validity_seed_000134", as_path_validity_seed_000134),
        ("property_campaigns::tests::as_path_validity_seed_000135", as_path_validity_seed_000135),
        ("property_campaigns::tests::as_path_validity_seed_000136", as_path_validity_seed_000136),
        ("property_campaigns::tests::as_path_validity_seed_000137", as_path_validity_seed_000137),
        ("property_campaigns::tests::as_path_validity_seed_000138", as_path_validity_seed_000138),
        ("property_campaigns::tests::as_path_validity_seed_000139", as_path_validity_seed_000139),
        ("property_campaigns::tests::as_path_validity_seed_000140", as_path_validity_seed_000140),
        ("property_campaigns::tests::as_path_validity_seed_000141", as_path_validity_seed_000141),
        ("property_campaigns::tests::as_path_validity_seed_000142", as_path_validity_seed_000142),
        ("property_campaigns::tests::as_path_validity_seed_000143", as_path_validity_seed_000143),
        ("property_campaigns::tests::as_path_validity_seed_000144", as_path_validity_seed_000144),
        ("property_campaigns::tests::as_path_validity_seed_000145", as_path_validity_seed_000145),
        ("property_campaigns::tests::as_path_validity_seed_000146", as_path_validity_seed_000146),
        ("property_campaigns::tests::as_path_validity_seed_000147", as_path_validity_seed_000147),
        ("property_campaigns::tests::as_path_validity_seed_000148", as_path_validity_seed_000148),
        ("property_campaigns::tests::as_path_validity_seed_000149", as_path_validity_seed_000149),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000000", as_monotonic_reachability_seed_000000),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000001", as_monotonic_reachability_seed_000001),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000002", as_monotonic_reachability_seed_000002),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000003", as_monotonic_reachability_seed_000003),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000004", as_monotonic_reachability_seed_000004),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000005", as_monotonic_reachability_seed_000005),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000006", as_monotonic_reachability_seed_000006),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000007", as_monotonic_reachability_seed_000007),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000008", as_monotonic_reachability_seed_000008),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000009", as_monotonic_reachability_seed_000009),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000010", as_monotonic_reachability_seed_000010),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000011", as_monotonic_reachability_seed_000011),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000012", as_monotonic_reachability_seed_000012),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000013", as_monotonic_reachability_seed_000013),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000014", as_monotonic_reachability_seed_000014),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000015", as_monotonic_reachability_seed_000015),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000016", as_monotonic_reachability_seed_000016),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000017", as_monotonic_reachability_seed_000017),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000018", as_monotonic_reachability_seed_000018),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000019", as_monotonic_reachability_seed_000019),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000020", as_monotonic_reachability_seed_000020),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000021", as_monotonic_reachability_seed_000021),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000022", as_monotonic_reachability_seed_000022),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000023", as_monotonic_reachability_seed_000023),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000024", as_monotonic_reachability_seed_000024),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000025", as_monotonic_reachability_seed_000025),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000026", as_monotonic_reachability_seed_000026),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000027", as_monotonic_reachability_seed_000027),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000028", as_monotonic_reachability_seed_000028),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000029", as_monotonic_reachability_seed_000029),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000030", as_monotonic_reachability_seed_000030),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000031", as_monotonic_reachability_seed_000031),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000032", as_monotonic_reachability_seed_000032),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000033", as_monotonic_reachability_seed_000033),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000034", as_monotonic_reachability_seed_000034),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000035", as_monotonic_reachability_seed_000035),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000036", as_monotonic_reachability_seed_000036),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000037", as_monotonic_reachability_seed_000037),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000038", as_monotonic_reachability_seed_000038),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000039", as_monotonic_reachability_seed_000039),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000040", as_monotonic_reachability_seed_000040),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000041", as_monotonic_reachability_seed_000041),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000042", as_monotonic_reachability_seed_000042),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000043", as_monotonic_reachability_seed_000043),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000044", as_monotonic_reachability_seed_000044),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000045", as_monotonic_reachability_seed_000045),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000046", as_monotonic_reachability_seed_000046),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000047", as_monotonic_reachability_seed_000047),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000048", as_monotonic_reachability_seed_000048),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000049", as_monotonic_reachability_seed_000049),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000050", as_monotonic_reachability_seed_000050),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000051", as_monotonic_reachability_seed_000051),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000052", as_monotonic_reachability_seed_000052),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000053", as_monotonic_reachability_seed_000053),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000054", as_monotonic_reachability_seed_000054),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000055", as_monotonic_reachability_seed_000055),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000056", as_monotonic_reachability_seed_000056),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000057", as_monotonic_reachability_seed_000057),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000058", as_monotonic_reachability_seed_000058),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000059", as_monotonic_reachability_seed_000059),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000060", as_monotonic_reachability_seed_000060),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000061", as_monotonic_reachability_seed_000061),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000062", as_monotonic_reachability_seed_000062),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000063", as_monotonic_reachability_seed_000063),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000064", as_monotonic_reachability_seed_000064),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000065", as_monotonic_reachability_seed_000065),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000066", as_monotonic_reachability_seed_000066),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000067", as_monotonic_reachability_seed_000067),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000068", as_monotonic_reachability_seed_000068),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000069", as_monotonic_reachability_seed_000069),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000070", as_monotonic_reachability_seed_000070),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000071", as_monotonic_reachability_seed_000071),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000072", as_monotonic_reachability_seed_000072),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000073", as_monotonic_reachability_seed_000073),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000074", as_monotonic_reachability_seed_000074),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000075", as_monotonic_reachability_seed_000075),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000076", as_monotonic_reachability_seed_000076),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000077", as_monotonic_reachability_seed_000077),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000078", as_monotonic_reachability_seed_000078),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000079", as_monotonic_reachability_seed_000079),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000080", as_monotonic_reachability_seed_000080),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000081", as_monotonic_reachability_seed_000081),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000082", as_monotonic_reachability_seed_000082),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000083", as_monotonic_reachability_seed_000083),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000084", as_monotonic_reachability_seed_000084),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000085", as_monotonic_reachability_seed_000085),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000086", as_monotonic_reachability_seed_000086),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000087", as_monotonic_reachability_seed_000087),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000088", as_monotonic_reachability_seed_000088),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000089", as_monotonic_reachability_seed_000089),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000090", as_monotonic_reachability_seed_000090),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000091", as_monotonic_reachability_seed_000091),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000092", as_monotonic_reachability_seed_000092),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000093", as_monotonic_reachability_seed_000093),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000094", as_monotonic_reachability_seed_000094),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000095", as_monotonic_reachability_seed_000095),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000096", as_monotonic_reachability_seed_000096),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000097", as_monotonic_reachability_seed_000097),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000098", as_monotonic_reachability_seed_000098),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000099", as_monotonic_reachability_seed_000099),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000100", as_monotonic_reachability_seed_000100),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000101", as_monotonic_reachability_seed_000101),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000102", as_monotonic_reachability_seed_000102),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000103", as_monotonic_reachability_seed_000103),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000104", as_monotonic_reachability_seed_000104),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000105", as_monotonic_reachability_seed_000105),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000106", as_monotonic_reachability_seed_000106),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000107", as_monotonic_reachability_seed_000107),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000108", as_monotonic_reachability_seed_000108),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000109", as_monotonic_reachability_seed_000109),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000110", as_monotonic_reachability_seed_000110),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000111", as_monotonic_reachability_seed_000111),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000112", as_monotonic_reachability_seed_000112),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000113", as_monotonic_reachability_seed_000113),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000114", as_monotonic_reachability_seed_000114),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000115", as_monotonic_reachability_seed_000115),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000116", as_monotonic_reachability_seed_000116),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000117", as_monotonic_reachability_seed_000117),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000118", as_monotonic_reachability_seed_000118),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000119", as_monotonic_reachability_seed_000119),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000120", as_monotonic_reachability_seed_000120),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000121", as_monotonic_reachability_seed_000121),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000122", as_monotonic_reachability_seed_000122),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000123", as_monotonic_reachability_seed_000123),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000124", as_monotonic_reachability_seed_000124),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000125", as_monotonic_reachability_seed_000125),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000126", as_monotonic_reachability_seed_000126),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000127", as_monotonic_reachability_seed_000127),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000128", as_monotonic_reachability_seed_000128),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000129", as_monotonic_reachability_seed_000129),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000130", as_monotonic_reachability_seed_000130),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000131", as_monotonic_reachability_seed_000131),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000132", as_monotonic_reachability_seed_000132),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000133", as_monotonic_reachability_seed_000133),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000134", as_monotonic_reachability_seed_000134),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000135", as_monotonic_reachability_seed_000135),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000136", as_monotonic_reachability_seed_000136),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000137", as_monotonic_reachability_seed_000137),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000138", as_monotonic_reachability_seed_000138),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000139", as_monotonic_reachability_seed_000139),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000140", as_monotonic_reachability_seed_000140),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000141", as_monotonic_reachability_seed_000141),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000142", as_monotonic_reachability_seed_000142),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000143", as_monotonic_reachability_seed_000143),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000144", as_monotonic_reachability_seed_000144),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000145", as_monotonic_reachability_seed_000145),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000146", as_monotonic_reachability_seed_000146),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000147", as_monotonic_reachability_seed_000147),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000148", as_monotonic_reachability_seed_000148),
        ("property_campaigns::tests::as_monotonic_reachability_seed_000149", as_monotonic_reachability_seed_000149),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
