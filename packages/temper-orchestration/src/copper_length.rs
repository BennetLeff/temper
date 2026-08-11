// The copper-length compute of
// `temper_workflow/routing/route_and_measure.py` (Wave 4, Phase 5).
//
// `measure_copper_length` parsed a KiCad PCB and accumulated per-trace
// Euclidean segment lengths per net. The parse stays Python (the
// `temper_placer.io.kicad_parser` Phase-3 surface is not this slice's); the
// shim flattens `result.traces` to `(net, sx, sy, ex, ey)` tuples and this
// function does the accumulation. The differential
// (`tests/test_route_and_measure_rust_differential.py`, oracle
// `tests/_route_and_measure_py_oracle.py`) extracts the oracle's loop body
// mechanically and pins bit-identical parity.
//
// Traps pinned (see the differential docstring for the measurement cites):
// - `dx ** 2` / `dy ** 2` are CPython `float ** float` — libm `pow` via
//   `dlsym`, NOT `x * x` (measured 389/300000 mismatches of `x*x` vs `**2`
//   in this slice's own environment). Resolved through `host_math::pow`.
// - `math.sqrt` is the correctly-rounded IEEE sqrt -> `f64::sqrt`.
// - `total_length += length` and `net_lengths.get(net, 0.0) + length` are
//   naive (non-compensated) accumulation; Rust uses plain f64 `+=` / add.
//   Segment order is therefore load-bearing and the differential permutes.
// - `if not trace.net` is a truthiness skip: empty string AND None both
//   skip (flattened as `Option<String>`).

#[cfg(feature = "python")]
use pyo3::prelude::*;

use crate::host_math;

/// Accumulate per-net Euclidean copper length over flattened trace segments
/// `(net, start_x, start_y, end_x, end_y)`.
///
/// Returns `(total_wirelength_mm, [(net, length), ...])` where the pair
/// list is in FIRST-SEEN net order — the shim assembles the Python dict
/// from it, and dict insertion order is part of the contract.
#[cfg_attr(feature = "python", pyfunction)]
pub fn measure_copper_length(
    traces: Vec<(Option<String>, f64, f64, f64, f64)>,
) -> (f64, Vec<(String, f64)>) {
    let mut net_lengths: Vec<(String, f64)> = Vec::new();
    let mut total_length = 0.0_f64;
    for (net, sx, sy, ex, ey) in traces {
        // Python: `if not trace.net: continue` — None and "" are falsy.
        let Some(net) = net else { continue };
        if net.is_empty() {
            continue;
        }
        let dx = ex - sx;
        let dy = ey - sy;
        // Python: math.sqrt(dx ** 2 + dy ** 2)
        let length = (host_math::pow(dx, 2.0) + host_math::pow(dy, 2.0)).sqrt();
        match net_lengths.iter_mut().find(|(n, _)| *n == net) {
            Some((_, acc)) => *acc += length,
            None => net_lengths.push((net, length)),
        }
        total_length += length;
    }
    (total_length, net_lengths)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn three_four_five_triangle() {
        let (total, pairs) = measure_copper_length(vec![(Some("GND".into()), 0.0, 0.0, 3.0, 4.0)]);
        assert_eq!(total, 5.0);
        assert_eq!(pairs, vec![("GND".to_string(), 5.0)]);
    }

    #[cfg_attr(test, test)]
    fn falsy_nets_skipped() {
        let (total, pairs) = measure_copper_length(vec![
            (Some("GND".into()), 0.0, 0.0, 3.0, 4.0),
            (Some(String::new()), 0.0, 0.0, 100.0, 100.0),
            (None, 0.0, 0.0, 100.0, 100.0),
        ]);
        assert_eq!(total, 5.0);
        assert_eq!(pairs.len(), 1);
    }

    #[cfg_attr(test, test)]
    fn first_seen_order_preserved() {
        let (_, pairs) = measure_copper_length(vec![
            (Some("A".into()), 0.0, 0.0, 1.0, 0.0),
            (Some("B".into()), 0.0, 0.0, 2.0, 0.0),
            (Some("A".into()), 1.0, 0.0, 3.0, 0.0),
        ]);
        assert_eq!(pairs[0].0, "A");
        assert_eq!(pairs[1].0, "B");
        assert_eq!(pairs.len(), 2);
    }

    #[cfg_attr(test, test)]
    fn empty_input() {
        let (total, pairs) = measure_copper_length(vec![]);
        assert_eq!(total, 0.0);
        assert!(pairs.is_empty());
    }

    // -----------------------------------------------------------------------
    // Deterministic mirrors of `proptests`' seven properties (P1-P7) below.
    // `proptest` is a dev-dependency (the `proptest-dev-dependency`
    // exclusion class), so its macro bodies cannot be registered directly;
    // each property here reproduces the SAME assertion over a fixed, seeded
    // `SplitMix64` corpus. The native, randomized proptest module is
    // UNCHANGED and keeps exploring randomly.
    //
    // `measure_copper_length` calls `host_math::pow` internally (`dx**2 +
    // dy**2`), but none of P1-P7 compares its result against a captured
    // host-CPython reference value -- each is structural (non-negativity,
    // additivity within a numerical tolerance, order preservation), so the
    // mirror holds under either the dlsym'd host libm (native) or the
    // `f64::powf` fallback (wasm32). See `host_math.rs`'s own tests module
    // doc for the same check made there.
    //
    // A SMALL, FIXED net-name pool (`NET_POOL`, 4 entries) is used instead
    // of drawing arbitrary names, so that with more than 4 traces a
    // collision (two traces on the same net) is guaranteed by the pigeonhole
    // principle on every seed -- not a matter of luck. This is deliberate:
    // a wide/unique-name domain would make P3 (accumulation across multiple
    // segments on one net) and P7 (first-seen-order dedup) exercise their
    // real logic only occasionally, which is exactly the uniform-sampling
    // trap this task's own brief warns about (the geometry keepout /
    // thermal overlap-area precedents). `campaign_trap_check` below asserts
    // a minimum collision rate across the whole seed corpus as a standing
    // guard against that trap regressing silently.
    use crate::wasm_campaign_prng::SplitMix64;

    const NET_POOL: &[&str] = &["NA", "NB", "NC", "ND"];

    /// `(net, sx, sy, ex, ey)`: ~20% None, ~20% falsy empty string, ~60% a
    /// real name drawn from the small `NET_POOL` (collisions likely).
    fn campaign_trace(rng: &mut SplitMix64) -> (Option<String>, f64, f64, f64, f64) {
        let net = match rng.index(5) {
            0 => None,
            1 => Some(String::new()),
            _ => Some(NET_POOL[rng.index(NET_POOL.len())].to_string()),
        };
        let sx = rng.range(-1e3, 1e3);
        let sy = rng.range(-1e3, 1e3);
        let ex = rng.range(-1e3, 1e3);
        let ey = rng.range(-1e3, 1e3);
        (net, sx, sy, ex, ey)
    }

    fn campaign_traces(rng: &mut SplitMix64, n: i64) -> Vec<(Option<String>, f64, f64, f64, f64)> {
        (0..n).map(|_| campaign_trace(rng)).collect()
    }

    /// P1. Total length is always non-negative.
    fn p1_total_length_non_negative_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let n = rng.range_i64(0, 30);
        let traces = campaign_traces(&mut rng, n);
        let (total, _) = measure_copper_length(traces);
        assert!(total >= 0.0, "total length should be >= 0, got {total} (seed={seed})");
    }

    /// P2. Per-net lengths are all non-negative.
    fn p2_net_lengths_non_negative_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let n = rng.range_i64(0, 30);
        let traces = campaign_traces(&mut rng, n);
        let (_, pairs) = measure_copper_length(traces);
        for (net, len) in &pairs {
            assert!(*len >= 0.0, "net '{net}' has negative length {len} (seed={seed})");
        }
    }

    /// P3. Total length equals the sum of per-net lengths. `n` is drawn from
    /// 5..20 traces over the 4-entry `NET_POOL`, so multiple traces share a
    /// net (pigeonhole) and the accumulator's real behavior -- not just the
    /// trivial one-trace-per-net case -- is what gets checked.
    fn p3_total_equals_sum_of_nets_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let n = rng.range_i64(5, 20);
        let traces = campaign_traces(&mut rng, n);
        let (total, pairs) = measure_copper_length(traces);
        let sum: f64 = pairs.iter().map(|(_, l)| *l).sum();
        let diff = (total - sum).abs();
        assert!(diff < 1e-12 * total.max(1.0), "total={total} != sum of nets={sum}, diff={diff} (seed={seed})");
    }

    /// P4. Adding segments additively: measure(t1) + measure(t2) total ~=
    /// measure(t1 ++ t2) total.
    fn p4_additive_over_concatenation_impl(seed: u64) {
        let mut rng1 = SplitMix64::new(seed);
        let n1 = rng1.range_i64(0, 20);
        let t1 = campaign_traces(&mut rng1, n1);
        let mut rng2 = crate::wasm_campaign_prng::sub_rng(seed, 0xC0FFEE);
        let n2 = rng2.range_i64(0, 20);
        let t2 = campaign_traces(&mut rng2, n2);

        let (total1, _) = measure_copper_length(t1.clone());
        let (total2, _) = measure_copper_length(t2.clone());
        let mut combined = t1;
        combined.extend(t2);
        let (total_combined, _) = measure_copper_length(combined);

        let diff = (total_combined - (total1 + total2)).abs();
        assert!(
            diff < 1e-12 * total_combined.max(1.0),
            "not additive: {total1} + {total2} != {total_combined}, diff={diff} (seed={seed})"
        );
    }

    /// P5. A single non-degenerate segment yields positive total length.
    fn p5_non_degenerate_segment_positive_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let net = NET_POOL[rng.index(NET_POOL.len())].to_string();
        let sx = rng.range(-1e3, 1e3);
        let sy = rng.range(-1e3, 1e3);
        let dx_delta = rng.range(0.1, 100.0);
        let dy_delta = rng.range(0.1, 100.0);
        let ex = sx + dx_delta;
        let ey = sy + dy_delta;
        let (total, _) = measure_copper_length(vec![(Some(net), sx, sy, ex, ey)]);
        assert!(total > 0.0, "non-degenerate segment should have positive length, got {total} (seed={seed})");
    }

    /// P6. Falsy nets (None or empty string) are skipped and contribute zero
    /// to total length -- fixed falsy-ness by construction (that is the
    /// property under test), varying coordinates by seed.
    fn p6_falsy_nets_contribute_zero_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        let a = rng.range(-1e3, 1e3);
        let b = rng.range(-1e3, 1e3);
        let falsy_traces: Vec<_> = vec![
            (Some(String::new()), 0.0, 0.0, a, b),
            (None, 0.0, 0.0, b, a),
        ];
        let (total, pairs) = measure_copper_length(falsy_traces);
        assert_eq!(total, 0.0, "seed={seed}");
        assert!(pairs.is_empty(), "seed={seed}");
    }

    /// P7. Per-net lengths preserve first-seen net name order. Names are
    /// drawn from a 3-entry pool with 4..10 draws, so a duplicate is
    /// guaranteed (pigeonhole) and the dedup logic -- not just the
    /// all-unique pass-through case -- is what gets checked.
    fn p7_first_seen_order_impl(seed: u64) {
        let mut rng = SplitMix64::new(seed);
        const SMALL_POOL: &[&str] = &["X", "Y", "Z"];
        let count = rng.range_i64(4, 10);
        let names: Vec<String> = (0..count).map(|_| SMALL_POOL[rng.index(SMALL_POOL.len())].to_string()).collect();
        let sx = rng.range(-1e3, 1e3);
        let sy = rng.range(-1e3, 1e3);
        let delta = rng.range(1.0, 10.0);
        let traces: Vec<_> = names.iter().map(|n| (Some(n.clone()), sx, sy, sx + delta, sy + delta)).collect();
        let (_, pairs) = measure_copper_length(traces);

        let mut seen = std::collections::HashSet::new();
        let mut expected_order = Vec::new();
        for n in &names {
            if seen.insert(n.clone()) {
                expected_order.push(n.clone());
            }
        }
        assert_eq!(pairs.len(), expected_order.len(), "seed={seed}");
        for (i, (net, _)) in pairs.iter().enumerate() {
            assert_eq!(net, &expected_order[i], "order mismatch at position {i}: {net} != {} (seed={seed})", expected_order[i]);
        }
    }

    /// Standing guard against the uniform-sampling trap (task brief:
    /// "verify the interesting branch is actually exercised"): across the
    /// whole 20-seed corpus P3 draws from, at least some seeds must produce
    /// a real net-name collision (two traces sharing a net), or P3/P7's
    /// dedup/accumulation logic is never actually tested by this campaign.
    #[cfg_attr(test, test)]
    fn campaign_trap_check_collisions_occur() {
        let mut collision_seeds = 0;
        for seed in 0..20u64 {
            let mut rng = SplitMix64::new(seed);
            let n = rng.range_i64(5, 20);
            let traces = campaign_traces(&mut rng, n);
            let mut seen = std::collections::HashSet::new();
            let mut collided = false;
            for (net, ..) in &traces {
                if let Some(n) = net
                    && !n.is_empty()
                    && !seen.insert(n.clone())
                {
                    collided = true;
                }
            }
            if collided {
                collision_seeds += 1;
            }
        }
        assert!(
            collision_seeds >= 15,
            "only {collision_seeds}/20 seeds produced a net-name collision -- \
             the corpus is not reliably exercising the accumulation/dedup branch"
        );
    }

    // --- BEGIN generated seeded property-mirror wrappers (deterministic proptest mirrors, R19/U6) ---
    // 7 properties x 20 seeds = 140 distinct-input wasm tests.
    #[cfg_attr(test, test)]
    fn p1_total_length_non_negative_seed_000() { p1_total_length_non_negative_impl(0); }
    #[cfg_attr(test, test)]
    fn p1_total_length_non_negative_seed_001() { p1_total_length_non_negative_impl(1); }
    #[cfg_attr(test, test)]
    fn p1_total_length_non_negative_seed_002() { p1_total_length_non_negative_impl(2); }
    #[cfg_attr(test, test)]
    fn p1_total_length_non_negative_seed_003() { p1_total_length_non_negative_impl(3); }
    #[cfg_attr(test, test)]
    fn p1_total_length_non_negative_seed_004() { p1_total_length_non_negative_impl(4); }
    #[cfg_attr(test, test)]
    fn p1_total_length_non_negative_seed_005() { p1_total_length_non_negative_impl(5); }
    #[cfg_attr(test, test)]
    fn p1_total_length_non_negative_seed_006() { p1_total_length_non_negative_impl(6); }
    #[cfg_attr(test, test)]
    fn p1_total_length_non_negative_seed_007() { p1_total_length_non_negative_impl(7); }
    #[cfg_attr(test, test)]
    fn p1_total_length_non_negative_seed_008() { p1_total_length_non_negative_impl(8); }
    #[cfg_attr(test, test)]
    fn p1_total_length_non_negative_seed_009() { p1_total_length_non_negative_impl(9); }
    #[cfg_attr(test, test)]
    fn p1_total_length_non_negative_seed_010() { p1_total_length_non_negative_impl(10); }
    #[cfg_attr(test, test)]
    fn p1_total_length_non_negative_seed_011() { p1_total_length_non_negative_impl(11); }
    #[cfg_attr(test, test)]
    fn p1_total_length_non_negative_seed_012() { p1_total_length_non_negative_impl(12); }
    #[cfg_attr(test, test)]
    fn p1_total_length_non_negative_seed_013() { p1_total_length_non_negative_impl(13); }
    #[cfg_attr(test, test)]
    fn p1_total_length_non_negative_seed_014() { p1_total_length_non_negative_impl(14); }
    #[cfg_attr(test, test)]
    fn p1_total_length_non_negative_seed_015() { p1_total_length_non_negative_impl(15); }
    #[cfg_attr(test, test)]
    fn p1_total_length_non_negative_seed_016() { p1_total_length_non_negative_impl(16); }
    #[cfg_attr(test, test)]
    fn p1_total_length_non_negative_seed_017() { p1_total_length_non_negative_impl(17); }
    #[cfg_attr(test, test)]
    fn p1_total_length_non_negative_seed_018() { p1_total_length_non_negative_impl(18); }
    #[cfg_attr(test, test)]
    fn p1_total_length_non_negative_seed_019() { p1_total_length_non_negative_impl(19); }
    #[cfg_attr(test, test)]
    fn p2_net_lengths_non_negative_seed_000() { p2_net_lengths_non_negative_impl(0); }
    #[cfg_attr(test, test)]
    fn p2_net_lengths_non_negative_seed_001() { p2_net_lengths_non_negative_impl(1); }
    #[cfg_attr(test, test)]
    fn p2_net_lengths_non_negative_seed_002() { p2_net_lengths_non_negative_impl(2); }
    #[cfg_attr(test, test)]
    fn p2_net_lengths_non_negative_seed_003() { p2_net_lengths_non_negative_impl(3); }
    #[cfg_attr(test, test)]
    fn p2_net_lengths_non_negative_seed_004() { p2_net_lengths_non_negative_impl(4); }
    #[cfg_attr(test, test)]
    fn p2_net_lengths_non_negative_seed_005() { p2_net_lengths_non_negative_impl(5); }
    #[cfg_attr(test, test)]
    fn p2_net_lengths_non_negative_seed_006() { p2_net_lengths_non_negative_impl(6); }
    #[cfg_attr(test, test)]
    fn p2_net_lengths_non_negative_seed_007() { p2_net_lengths_non_negative_impl(7); }
    #[cfg_attr(test, test)]
    fn p2_net_lengths_non_negative_seed_008() { p2_net_lengths_non_negative_impl(8); }
    #[cfg_attr(test, test)]
    fn p2_net_lengths_non_negative_seed_009() { p2_net_lengths_non_negative_impl(9); }
    #[cfg_attr(test, test)]
    fn p2_net_lengths_non_negative_seed_010() { p2_net_lengths_non_negative_impl(10); }
    #[cfg_attr(test, test)]
    fn p2_net_lengths_non_negative_seed_011() { p2_net_lengths_non_negative_impl(11); }
    #[cfg_attr(test, test)]
    fn p2_net_lengths_non_negative_seed_012() { p2_net_lengths_non_negative_impl(12); }
    #[cfg_attr(test, test)]
    fn p2_net_lengths_non_negative_seed_013() { p2_net_lengths_non_negative_impl(13); }
    #[cfg_attr(test, test)]
    fn p2_net_lengths_non_negative_seed_014() { p2_net_lengths_non_negative_impl(14); }
    #[cfg_attr(test, test)]
    fn p2_net_lengths_non_negative_seed_015() { p2_net_lengths_non_negative_impl(15); }
    #[cfg_attr(test, test)]
    fn p2_net_lengths_non_negative_seed_016() { p2_net_lengths_non_negative_impl(16); }
    #[cfg_attr(test, test)]
    fn p2_net_lengths_non_negative_seed_017() { p2_net_lengths_non_negative_impl(17); }
    #[cfg_attr(test, test)]
    fn p2_net_lengths_non_negative_seed_018() { p2_net_lengths_non_negative_impl(18); }
    #[cfg_attr(test, test)]
    fn p2_net_lengths_non_negative_seed_019() { p2_net_lengths_non_negative_impl(19); }
    #[cfg_attr(test, test)]
    fn p3_total_equals_sum_of_nets_seed_000() { p3_total_equals_sum_of_nets_impl(0); }
    #[cfg_attr(test, test)]
    fn p3_total_equals_sum_of_nets_seed_001() { p3_total_equals_sum_of_nets_impl(1); }
    #[cfg_attr(test, test)]
    fn p3_total_equals_sum_of_nets_seed_002() { p3_total_equals_sum_of_nets_impl(2); }
    #[cfg_attr(test, test)]
    fn p3_total_equals_sum_of_nets_seed_003() { p3_total_equals_sum_of_nets_impl(3); }
    #[cfg_attr(test, test)]
    fn p3_total_equals_sum_of_nets_seed_004() { p3_total_equals_sum_of_nets_impl(4); }
    #[cfg_attr(test, test)]
    fn p3_total_equals_sum_of_nets_seed_005() { p3_total_equals_sum_of_nets_impl(5); }
    #[cfg_attr(test, test)]
    fn p3_total_equals_sum_of_nets_seed_006() { p3_total_equals_sum_of_nets_impl(6); }
    #[cfg_attr(test, test)]
    fn p3_total_equals_sum_of_nets_seed_007() { p3_total_equals_sum_of_nets_impl(7); }
    #[cfg_attr(test, test)]
    fn p3_total_equals_sum_of_nets_seed_008() { p3_total_equals_sum_of_nets_impl(8); }
    #[cfg_attr(test, test)]
    fn p3_total_equals_sum_of_nets_seed_009() { p3_total_equals_sum_of_nets_impl(9); }
    #[cfg_attr(test, test)]
    fn p3_total_equals_sum_of_nets_seed_010() { p3_total_equals_sum_of_nets_impl(10); }
    #[cfg_attr(test, test)]
    fn p3_total_equals_sum_of_nets_seed_011() { p3_total_equals_sum_of_nets_impl(11); }
    #[cfg_attr(test, test)]
    fn p3_total_equals_sum_of_nets_seed_012() { p3_total_equals_sum_of_nets_impl(12); }
    #[cfg_attr(test, test)]
    fn p3_total_equals_sum_of_nets_seed_013() { p3_total_equals_sum_of_nets_impl(13); }
    #[cfg_attr(test, test)]
    fn p3_total_equals_sum_of_nets_seed_014() { p3_total_equals_sum_of_nets_impl(14); }
    #[cfg_attr(test, test)]
    fn p3_total_equals_sum_of_nets_seed_015() { p3_total_equals_sum_of_nets_impl(15); }
    #[cfg_attr(test, test)]
    fn p3_total_equals_sum_of_nets_seed_016() { p3_total_equals_sum_of_nets_impl(16); }
    #[cfg_attr(test, test)]
    fn p3_total_equals_sum_of_nets_seed_017() { p3_total_equals_sum_of_nets_impl(17); }
    #[cfg_attr(test, test)]
    fn p3_total_equals_sum_of_nets_seed_018() { p3_total_equals_sum_of_nets_impl(18); }
    #[cfg_attr(test, test)]
    fn p3_total_equals_sum_of_nets_seed_019() { p3_total_equals_sum_of_nets_impl(19); }
    #[cfg_attr(test, test)]
    fn p4_additive_over_concatenation_seed_000() { p4_additive_over_concatenation_impl(0); }
    #[cfg_attr(test, test)]
    fn p4_additive_over_concatenation_seed_001() { p4_additive_over_concatenation_impl(1); }
    #[cfg_attr(test, test)]
    fn p4_additive_over_concatenation_seed_002() { p4_additive_over_concatenation_impl(2); }
    #[cfg_attr(test, test)]
    fn p4_additive_over_concatenation_seed_003() { p4_additive_over_concatenation_impl(3); }
    #[cfg_attr(test, test)]
    fn p4_additive_over_concatenation_seed_004() { p4_additive_over_concatenation_impl(4); }
    #[cfg_attr(test, test)]
    fn p4_additive_over_concatenation_seed_005() { p4_additive_over_concatenation_impl(5); }
    #[cfg_attr(test, test)]
    fn p4_additive_over_concatenation_seed_006() { p4_additive_over_concatenation_impl(6); }
    #[cfg_attr(test, test)]
    fn p4_additive_over_concatenation_seed_007() { p4_additive_over_concatenation_impl(7); }
    #[cfg_attr(test, test)]
    fn p4_additive_over_concatenation_seed_008() { p4_additive_over_concatenation_impl(8); }
    #[cfg_attr(test, test)]
    fn p4_additive_over_concatenation_seed_009() { p4_additive_over_concatenation_impl(9); }
    #[cfg_attr(test, test)]
    fn p4_additive_over_concatenation_seed_010() { p4_additive_over_concatenation_impl(10); }
    #[cfg_attr(test, test)]
    fn p4_additive_over_concatenation_seed_011() { p4_additive_over_concatenation_impl(11); }
    #[cfg_attr(test, test)]
    fn p4_additive_over_concatenation_seed_012() { p4_additive_over_concatenation_impl(12); }
    #[cfg_attr(test, test)]
    fn p4_additive_over_concatenation_seed_013() { p4_additive_over_concatenation_impl(13); }
    #[cfg_attr(test, test)]
    fn p4_additive_over_concatenation_seed_014() { p4_additive_over_concatenation_impl(14); }
    #[cfg_attr(test, test)]
    fn p4_additive_over_concatenation_seed_015() { p4_additive_over_concatenation_impl(15); }
    #[cfg_attr(test, test)]
    fn p4_additive_over_concatenation_seed_016() { p4_additive_over_concatenation_impl(16); }
    #[cfg_attr(test, test)]
    fn p4_additive_over_concatenation_seed_017() { p4_additive_over_concatenation_impl(17); }
    #[cfg_attr(test, test)]
    fn p4_additive_over_concatenation_seed_018() { p4_additive_over_concatenation_impl(18); }
    #[cfg_attr(test, test)]
    fn p4_additive_over_concatenation_seed_019() { p4_additive_over_concatenation_impl(19); }
    #[cfg_attr(test, test)]
    fn p5_non_degenerate_segment_positive_seed_000() { p5_non_degenerate_segment_positive_impl(0); }
    #[cfg_attr(test, test)]
    fn p5_non_degenerate_segment_positive_seed_001() { p5_non_degenerate_segment_positive_impl(1); }
    #[cfg_attr(test, test)]
    fn p5_non_degenerate_segment_positive_seed_002() { p5_non_degenerate_segment_positive_impl(2); }
    #[cfg_attr(test, test)]
    fn p5_non_degenerate_segment_positive_seed_003() { p5_non_degenerate_segment_positive_impl(3); }
    #[cfg_attr(test, test)]
    fn p5_non_degenerate_segment_positive_seed_004() { p5_non_degenerate_segment_positive_impl(4); }
    #[cfg_attr(test, test)]
    fn p5_non_degenerate_segment_positive_seed_005() { p5_non_degenerate_segment_positive_impl(5); }
    #[cfg_attr(test, test)]
    fn p5_non_degenerate_segment_positive_seed_006() { p5_non_degenerate_segment_positive_impl(6); }
    #[cfg_attr(test, test)]
    fn p5_non_degenerate_segment_positive_seed_007() { p5_non_degenerate_segment_positive_impl(7); }
    #[cfg_attr(test, test)]
    fn p5_non_degenerate_segment_positive_seed_008() { p5_non_degenerate_segment_positive_impl(8); }
    #[cfg_attr(test, test)]
    fn p5_non_degenerate_segment_positive_seed_009() { p5_non_degenerate_segment_positive_impl(9); }
    #[cfg_attr(test, test)]
    fn p5_non_degenerate_segment_positive_seed_010() { p5_non_degenerate_segment_positive_impl(10); }
    #[cfg_attr(test, test)]
    fn p5_non_degenerate_segment_positive_seed_011() { p5_non_degenerate_segment_positive_impl(11); }
    #[cfg_attr(test, test)]
    fn p5_non_degenerate_segment_positive_seed_012() { p5_non_degenerate_segment_positive_impl(12); }
    #[cfg_attr(test, test)]
    fn p5_non_degenerate_segment_positive_seed_013() { p5_non_degenerate_segment_positive_impl(13); }
    #[cfg_attr(test, test)]
    fn p5_non_degenerate_segment_positive_seed_014() { p5_non_degenerate_segment_positive_impl(14); }
    #[cfg_attr(test, test)]
    fn p5_non_degenerate_segment_positive_seed_015() { p5_non_degenerate_segment_positive_impl(15); }
    #[cfg_attr(test, test)]
    fn p5_non_degenerate_segment_positive_seed_016() { p5_non_degenerate_segment_positive_impl(16); }
    #[cfg_attr(test, test)]
    fn p5_non_degenerate_segment_positive_seed_017() { p5_non_degenerate_segment_positive_impl(17); }
    #[cfg_attr(test, test)]
    fn p5_non_degenerate_segment_positive_seed_018() { p5_non_degenerate_segment_positive_impl(18); }
    #[cfg_attr(test, test)]
    fn p5_non_degenerate_segment_positive_seed_019() { p5_non_degenerate_segment_positive_impl(19); }
    #[cfg_attr(test, test)]
    fn p6_falsy_nets_contribute_zero_seed_000() { p6_falsy_nets_contribute_zero_impl(0); }
    #[cfg_attr(test, test)]
    fn p6_falsy_nets_contribute_zero_seed_001() { p6_falsy_nets_contribute_zero_impl(1); }
    #[cfg_attr(test, test)]
    fn p6_falsy_nets_contribute_zero_seed_002() { p6_falsy_nets_contribute_zero_impl(2); }
    #[cfg_attr(test, test)]
    fn p6_falsy_nets_contribute_zero_seed_003() { p6_falsy_nets_contribute_zero_impl(3); }
    #[cfg_attr(test, test)]
    fn p6_falsy_nets_contribute_zero_seed_004() { p6_falsy_nets_contribute_zero_impl(4); }
    #[cfg_attr(test, test)]
    fn p6_falsy_nets_contribute_zero_seed_005() { p6_falsy_nets_contribute_zero_impl(5); }
    #[cfg_attr(test, test)]
    fn p6_falsy_nets_contribute_zero_seed_006() { p6_falsy_nets_contribute_zero_impl(6); }
    #[cfg_attr(test, test)]
    fn p6_falsy_nets_contribute_zero_seed_007() { p6_falsy_nets_contribute_zero_impl(7); }
    #[cfg_attr(test, test)]
    fn p6_falsy_nets_contribute_zero_seed_008() { p6_falsy_nets_contribute_zero_impl(8); }
    #[cfg_attr(test, test)]
    fn p6_falsy_nets_contribute_zero_seed_009() { p6_falsy_nets_contribute_zero_impl(9); }
    #[cfg_attr(test, test)]
    fn p6_falsy_nets_contribute_zero_seed_010() { p6_falsy_nets_contribute_zero_impl(10); }
    #[cfg_attr(test, test)]
    fn p6_falsy_nets_contribute_zero_seed_011() { p6_falsy_nets_contribute_zero_impl(11); }
    #[cfg_attr(test, test)]
    fn p6_falsy_nets_contribute_zero_seed_012() { p6_falsy_nets_contribute_zero_impl(12); }
    #[cfg_attr(test, test)]
    fn p6_falsy_nets_contribute_zero_seed_013() { p6_falsy_nets_contribute_zero_impl(13); }
    #[cfg_attr(test, test)]
    fn p6_falsy_nets_contribute_zero_seed_014() { p6_falsy_nets_contribute_zero_impl(14); }
    #[cfg_attr(test, test)]
    fn p6_falsy_nets_contribute_zero_seed_015() { p6_falsy_nets_contribute_zero_impl(15); }
    #[cfg_attr(test, test)]
    fn p6_falsy_nets_contribute_zero_seed_016() { p6_falsy_nets_contribute_zero_impl(16); }
    #[cfg_attr(test, test)]
    fn p6_falsy_nets_contribute_zero_seed_017() { p6_falsy_nets_contribute_zero_impl(17); }
    #[cfg_attr(test, test)]
    fn p6_falsy_nets_contribute_zero_seed_018() { p6_falsy_nets_contribute_zero_impl(18); }
    #[cfg_attr(test, test)]
    fn p6_falsy_nets_contribute_zero_seed_019() { p6_falsy_nets_contribute_zero_impl(19); }
    #[cfg_attr(test, test)]
    fn p7_first_seen_order_seed_000() { p7_first_seen_order_impl(0); }
    #[cfg_attr(test, test)]
    fn p7_first_seen_order_seed_001() { p7_first_seen_order_impl(1); }
    #[cfg_attr(test, test)]
    fn p7_first_seen_order_seed_002() { p7_first_seen_order_impl(2); }
    #[cfg_attr(test, test)]
    fn p7_first_seen_order_seed_003() { p7_first_seen_order_impl(3); }
    #[cfg_attr(test, test)]
    fn p7_first_seen_order_seed_004() { p7_first_seen_order_impl(4); }
    #[cfg_attr(test, test)]
    fn p7_first_seen_order_seed_005() { p7_first_seen_order_impl(5); }
    #[cfg_attr(test, test)]
    fn p7_first_seen_order_seed_006() { p7_first_seen_order_impl(6); }
    #[cfg_attr(test, test)]
    fn p7_first_seen_order_seed_007() { p7_first_seen_order_impl(7); }
    #[cfg_attr(test, test)]
    fn p7_first_seen_order_seed_008() { p7_first_seen_order_impl(8); }
    #[cfg_attr(test, test)]
    fn p7_first_seen_order_seed_009() { p7_first_seen_order_impl(9); }
    #[cfg_attr(test, test)]
    fn p7_first_seen_order_seed_010() { p7_first_seen_order_impl(10); }
    #[cfg_attr(test, test)]
    fn p7_first_seen_order_seed_011() { p7_first_seen_order_impl(11); }
    #[cfg_attr(test, test)]
    fn p7_first_seen_order_seed_012() { p7_first_seen_order_impl(12); }
    #[cfg_attr(test, test)]
    fn p7_first_seen_order_seed_013() { p7_first_seen_order_impl(13); }
    #[cfg_attr(test, test)]
    fn p7_first_seen_order_seed_014() { p7_first_seen_order_impl(14); }
    #[cfg_attr(test, test)]
    fn p7_first_seen_order_seed_015() { p7_first_seen_order_impl(15); }
    #[cfg_attr(test, test)]
    fn p7_first_seen_order_seed_016() { p7_first_seen_order_impl(16); }
    #[cfg_attr(test, test)]
    fn p7_first_seen_order_seed_017() { p7_first_seen_order_impl(17); }
    #[cfg_attr(test, test)]
    fn p7_first_seen_order_seed_018() { p7_first_seen_order_impl(18); }
    #[cfg_attr(test, test)]
    fn p7_first_seen_order_seed_019() { p7_first_seen_order_impl(19); }
    // --- END generated seeded property-mirror wrappers ---

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("copper_length::tests::three_four_five_triangle", three_four_five_triangle),
        ("copper_length::tests::falsy_nets_skipped", falsy_nets_skipped),
        ("copper_length::tests::first_seen_order_preserved", first_seen_order_preserved),
        ("copper_length::tests::empty_input", empty_input),
        ("copper_length::tests::campaign_trap_check_collisions_occur", campaign_trap_check_collisions_occur),
        ("copper_length::tests::p1_total_length_non_negative_seed_000", p1_total_length_non_negative_seed_000),
        ("copper_length::tests::p1_total_length_non_negative_seed_001", p1_total_length_non_negative_seed_001),
        ("copper_length::tests::p1_total_length_non_negative_seed_002", p1_total_length_non_negative_seed_002),
        ("copper_length::tests::p1_total_length_non_negative_seed_003", p1_total_length_non_negative_seed_003),
        ("copper_length::tests::p1_total_length_non_negative_seed_004", p1_total_length_non_negative_seed_004),
        ("copper_length::tests::p1_total_length_non_negative_seed_005", p1_total_length_non_negative_seed_005),
        ("copper_length::tests::p1_total_length_non_negative_seed_006", p1_total_length_non_negative_seed_006),
        ("copper_length::tests::p1_total_length_non_negative_seed_007", p1_total_length_non_negative_seed_007),
        ("copper_length::tests::p1_total_length_non_negative_seed_008", p1_total_length_non_negative_seed_008),
        ("copper_length::tests::p1_total_length_non_negative_seed_009", p1_total_length_non_negative_seed_009),
        ("copper_length::tests::p1_total_length_non_negative_seed_010", p1_total_length_non_negative_seed_010),
        ("copper_length::tests::p1_total_length_non_negative_seed_011", p1_total_length_non_negative_seed_011),
        ("copper_length::tests::p1_total_length_non_negative_seed_012", p1_total_length_non_negative_seed_012),
        ("copper_length::tests::p1_total_length_non_negative_seed_013", p1_total_length_non_negative_seed_013),
        ("copper_length::tests::p1_total_length_non_negative_seed_014", p1_total_length_non_negative_seed_014),
        ("copper_length::tests::p1_total_length_non_negative_seed_015", p1_total_length_non_negative_seed_015),
        ("copper_length::tests::p1_total_length_non_negative_seed_016", p1_total_length_non_negative_seed_016),
        ("copper_length::tests::p1_total_length_non_negative_seed_017", p1_total_length_non_negative_seed_017),
        ("copper_length::tests::p1_total_length_non_negative_seed_018", p1_total_length_non_negative_seed_018),
        ("copper_length::tests::p1_total_length_non_negative_seed_019", p1_total_length_non_negative_seed_019),
        ("copper_length::tests::p2_net_lengths_non_negative_seed_000", p2_net_lengths_non_negative_seed_000),
        ("copper_length::tests::p2_net_lengths_non_negative_seed_001", p2_net_lengths_non_negative_seed_001),
        ("copper_length::tests::p2_net_lengths_non_negative_seed_002", p2_net_lengths_non_negative_seed_002),
        ("copper_length::tests::p2_net_lengths_non_negative_seed_003", p2_net_lengths_non_negative_seed_003),
        ("copper_length::tests::p2_net_lengths_non_negative_seed_004", p2_net_lengths_non_negative_seed_004),
        ("copper_length::tests::p2_net_lengths_non_negative_seed_005", p2_net_lengths_non_negative_seed_005),
        ("copper_length::tests::p2_net_lengths_non_negative_seed_006", p2_net_lengths_non_negative_seed_006),
        ("copper_length::tests::p2_net_lengths_non_negative_seed_007", p2_net_lengths_non_negative_seed_007),
        ("copper_length::tests::p2_net_lengths_non_negative_seed_008", p2_net_lengths_non_negative_seed_008),
        ("copper_length::tests::p2_net_lengths_non_negative_seed_009", p2_net_lengths_non_negative_seed_009),
        ("copper_length::tests::p2_net_lengths_non_negative_seed_010", p2_net_lengths_non_negative_seed_010),
        ("copper_length::tests::p2_net_lengths_non_negative_seed_011", p2_net_lengths_non_negative_seed_011),
        ("copper_length::tests::p2_net_lengths_non_negative_seed_012", p2_net_lengths_non_negative_seed_012),
        ("copper_length::tests::p2_net_lengths_non_negative_seed_013", p2_net_lengths_non_negative_seed_013),
        ("copper_length::tests::p2_net_lengths_non_negative_seed_014", p2_net_lengths_non_negative_seed_014),
        ("copper_length::tests::p2_net_lengths_non_negative_seed_015", p2_net_lengths_non_negative_seed_015),
        ("copper_length::tests::p2_net_lengths_non_negative_seed_016", p2_net_lengths_non_negative_seed_016),
        ("copper_length::tests::p2_net_lengths_non_negative_seed_017", p2_net_lengths_non_negative_seed_017),
        ("copper_length::tests::p2_net_lengths_non_negative_seed_018", p2_net_lengths_non_negative_seed_018),
        ("copper_length::tests::p2_net_lengths_non_negative_seed_019", p2_net_lengths_non_negative_seed_019),
        ("copper_length::tests::p3_total_equals_sum_of_nets_seed_000", p3_total_equals_sum_of_nets_seed_000),
        ("copper_length::tests::p3_total_equals_sum_of_nets_seed_001", p3_total_equals_sum_of_nets_seed_001),
        ("copper_length::tests::p3_total_equals_sum_of_nets_seed_002", p3_total_equals_sum_of_nets_seed_002),
        ("copper_length::tests::p3_total_equals_sum_of_nets_seed_003", p3_total_equals_sum_of_nets_seed_003),
        ("copper_length::tests::p3_total_equals_sum_of_nets_seed_004", p3_total_equals_sum_of_nets_seed_004),
        ("copper_length::tests::p3_total_equals_sum_of_nets_seed_005", p3_total_equals_sum_of_nets_seed_005),
        ("copper_length::tests::p3_total_equals_sum_of_nets_seed_006", p3_total_equals_sum_of_nets_seed_006),
        ("copper_length::tests::p3_total_equals_sum_of_nets_seed_007", p3_total_equals_sum_of_nets_seed_007),
        ("copper_length::tests::p3_total_equals_sum_of_nets_seed_008", p3_total_equals_sum_of_nets_seed_008),
        ("copper_length::tests::p3_total_equals_sum_of_nets_seed_009", p3_total_equals_sum_of_nets_seed_009),
        ("copper_length::tests::p3_total_equals_sum_of_nets_seed_010", p3_total_equals_sum_of_nets_seed_010),
        ("copper_length::tests::p3_total_equals_sum_of_nets_seed_011", p3_total_equals_sum_of_nets_seed_011),
        ("copper_length::tests::p3_total_equals_sum_of_nets_seed_012", p3_total_equals_sum_of_nets_seed_012),
        ("copper_length::tests::p3_total_equals_sum_of_nets_seed_013", p3_total_equals_sum_of_nets_seed_013),
        ("copper_length::tests::p3_total_equals_sum_of_nets_seed_014", p3_total_equals_sum_of_nets_seed_014),
        ("copper_length::tests::p3_total_equals_sum_of_nets_seed_015", p3_total_equals_sum_of_nets_seed_015),
        ("copper_length::tests::p3_total_equals_sum_of_nets_seed_016", p3_total_equals_sum_of_nets_seed_016),
        ("copper_length::tests::p3_total_equals_sum_of_nets_seed_017", p3_total_equals_sum_of_nets_seed_017),
        ("copper_length::tests::p3_total_equals_sum_of_nets_seed_018", p3_total_equals_sum_of_nets_seed_018),
        ("copper_length::tests::p3_total_equals_sum_of_nets_seed_019", p3_total_equals_sum_of_nets_seed_019),
        ("copper_length::tests::p4_additive_over_concatenation_seed_000", p4_additive_over_concatenation_seed_000),
        ("copper_length::tests::p4_additive_over_concatenation_seed_001", p4_additive_over_concatenation_seed_001),
        ("copper_length::tests::p4_additive_over_concatenation_seed_002", p4_additive_over_concatenation_seed_002),
        ("copper_length::tests::p4_additive_over_concatenation_seed_003", p4_additive_over_concatenation_seed_003),
        ("copper_length::tests::p4_additive_over_concatenation_seed_004", p4_additive_over_concatenation_seed_004),
        ("copper_length::tests::p4_additive_over_concatenation_seed_005", p4_additive_over_concatenation_seed_005),
        ("copper_length::tests::p4_additive_over_concatenation_seed_006", p4_additive_over_concatenation_seed_006),
        ("copper_length::tests::p4_additive_over_concatenation_seed_007", p4_additive_over_concatenation_seed_007),
        ("copper_length::tests::p4_additive_over_concatenation_seed_008", p4_additive_over_concatenation_seed_008),
        ("copper_length::tests::p4_additive_over_concatenation_seed_009", p4_additive_over_concatenation_seed_009),
        ("copper_length::tests::p4_additive_over_concatenation_seed_010", p4_additive_over_concatenation_seed_010),
        ("copper_length::tests::p4_additive_over_concatenation_seed_011", p4_additive_over_concatenation_seed_011),
        ("copper_length::tests::p4_additive_over_concatenation_seed_012", p4_additive_over_concatenation_seed_012),
        ("copper_length::tests::p4_additive_over_concatenation_seed_013", p4_additive_over_concatenation_seed_013),
        ("copper_length::tests::p4_additive_over_concatenation_seed_014", p4_additive_over_concatenation_seed_014),
        ("copper_length::tests::p4_additive_over_concatenation_seed_015", p4_additive_over_concatenation_seed_015),
        ("copper_length::tests::p4_additive_over_concatenation_seed_016", p4_additive_over_concatenation_seed_016),
        ("copper_length::tests::p4_additive_over_concatenation_seed_017", p4_additive_over_concatenation_seed_017),
        ("copper_length::tests::p4_additive_over_concatenation_seed_018", p4_additive_over_concatenation_seed_018),
        ("copper_length::tests::p4_additive_over_concatenation_seed_019", p4_additive_over_concatenation_seed_019),
        ("copper_length::tests::p5_non_degenerate_segment_positive_seed_000", p5_non_degenerate_segment_positive_seed_000),
        ("copper_length::tests::p5_non_degenerate_segment_positive_seed_001", p5_non_degenerate_segment_positive_seed_001),
        ("copper_length::tests::p5_non_degenerate_segment_positive_seed_002", p5_non_degenerate_segment_positive_seed_002),
        ("copper_length::tests::p5_non_degenerate_segment_positive_seed_003", p5_non_degenerate_segment_positive_seed_003),
        ("copper_length::tests::p5_non_degenerate_segment_positive_seed_004", p5_non_degenerate_segment_positive_seed_004),
        ("copper_length::tests::p5_non_degenerate_segment_positive_seed_005", p5_non_degenerate_segment_positive_seed_005),
        ("copper_length::tests::p5_non_degenerate_segment_positive_seed_006", p5_non_degenerate_segment_positive_seed_006),
        ("copper_length::tests::p5_non_degenerate_segment_positive_seed_007", p5_non_degenerate_segment_positive_seed_007),
        ("copper_length::tests::p5_non_degenerate_segment_positive_seed_008", p5_non_degenerate_segment_positive_seed_008),
        ("copper_length::tests::p5_non_degenerate_segment_positive_seed_009", p5_non_degenerate_segment_positive_seed_009),
        ("copper_length::tests::p5_non_degenerate_segment_positive_seed_010", p5_non_degenerate_segment_positive_seed_010),
        ("copper_length::tests::p5_non_degenerate_segment_positive_seed_011", p5_non_degenerate_segment_positive_seed_011),
        ("copper_length::tests::p5_non_degenerate_segment_positive_seed_012", p5_non_degenerate_segment_positive_seed_012),
        ("copper_length::tests::p5_non_degenerate_segment_positive_seed_013", p5_non_degenerate_segment_positive_seed_013),
        ("copper_length::tests::p5_non_degenerate_segment_positive_seed_014", p5_non_degenerate_segment_positive_seed_014),
        ("copper_length::tests::p5_non_degenerate_segment_positive_seed_015", p5_non_degenerate_segment_positive_seed_015),
        ("copper_length::tests::p5_non_degenerate_segment_positive_seed_016", p5_non_degenerate_segment_positive_seed_016),
        ("copper_length::tests::p5_non_degenerate_segment_positive_seed_017", p5_non_degenerate_segment_positive_seed_017),
        ("copper_length::tests::p5_non_degenerate_segment_positive_seed_018", p5_non_degenerate_segment_positive_seed_018),
        ("copper_length::tests::p5_non_degenerate_segment_positive_seed_019", p5_non_degenerate_segment_positive_seed_019),
        ("copper_length::tests::p6_falsy_nets_contribute_zero_seed_000", p6_falsy_nets_contribute_zero_seed_000),
        ("copper_length::tests::p6_falsy_nets_contribute_zero_seed_001", p6_falsy_nets_contribute_zero_seed_001),
        ("copper_length::tests::p6_falsy_nets_contribute_zero_seed_002", p6_falsy_nets_contribute_zero_seed_002),
        ("copper_length::tests::p6_falsy_nets_contribute_zero_seed_003", p6_falsy_nets_contribute_zero_seed_003),
        ("copper_length::tests::p6_falsy_nets_contribute_zero_seed_004", p6_falsy_nets_contribute_zero_seed_004),
        ("copper_length::tests::p6_falsy_nets_contribute_zero_seed_005", p6_falsy_nets_contribute_zero_seed_005),
        ("copper_length::tests::p6_falsy_nets_contribute_zero_seed_006", p6_falsy_nets_contribute_zero_seed_006),
        ("copper_length::tests::p6_falsy_nets_contribute_zero_seed_007", p6_falsy_nets_contribute_zero_seed_007),
        ("copper_length::tests::p6_falsy_nets_contribute_zero_seed_008", p6_falsy_nets_contribute_zero_seed_008),
        ("copper_length::tests::p6_falsy_nets_contribute_zero_seed_009", p6_falsy_nets_contribute_zero_seed_009),
        ("copper_length::tests::p6_falsy_nets_contribute_zero_seed_010", p6_falsy_nets_contribute_zero_seed_010),
        ("copper_length::tests::p6_falsy_nets_contribute_zero_seed_011", p6_falsy_nets_contribute_zero_seed_011),
        ("copper_length::tests::p6_falsy_nets_contribute_zero_seed_012", p6_falsy_nets_contribute_zero_seed_012),
        ("copper_length::tests::p6_falsy_nets_contribute_zero_seed_013", p6_falsy_nets_contribute_zero_seed_013),
        ("copper_length::tests::p6_falsy_nets_contribute_zero_seed_014", p6_falsy_nets_contribute_zero_seed_014),
        ("copper_length::tests::p6_falsy_nets_contribute_zero_seed_015", p6_falsy_nets_contribute_zero_seed_015),
        ("copper_length::tests::p6_falsy_nets_contribute_zero_seed_016", p6_falsy_nets_contribute_zero_seed_016),
        ("copper_length::tests::p6_falsy_nets_contribute_zero_seed_017", p6_falsy_nets_contribute_zero_seed_017),
        ("copper_length::tests::p6_falsy_nets_contribute_zero_seed_018", p6_falsy_nets_contribute_zero_seed_018),
        ("copper_length::tests::p6_falsy_nets_contribute_zero_seed_019", p6_falsy_nets_contribute_zero_seed_019),
        ("copper_length::tests::p7_first_seen_order_seed_000", p7_first_seen_order_seed_000),
        ("copper_length::tests::p7_first_seen_order_seed_001", p7_first_seen_order_seed_001),
        ("copper_length::tests::p7_first_seen_order_seed_002", p7_first_seen_order_seed_002),
        ("copper_length::tests::p7_first_seen_order_seed_003", p7_first_seen_order_seed_003),
        ("copper_length::tests::p7_first_seen_order_seed_004", p7_first_seen_order_seed_004),
        ("copper_length::tests::p7_first_seen_order_seed_005", p7_first_seen_order_seed_005),
        ("copper_length::tests::p7_first_seen_order_seed_006", p7_first_seen_order_seed_006),
        ("copper_length::tests::p7_first_seen_order_seed_007", p7_first_seen_order_seed_007),
        ("copper_length::tests::p7_first_seen_order_seed_008", p7_first_seen_order_seed_008),
        ("copper_length::tests::p7_first_seen_order_seed_009", p7_first_seen_order_seed_009),
        ("copper_length::tests::p7_first_seen_order_seed_010", p7_first_seen_order_seed_010),
        ("copper_length::tests::p7_first_seen_order_seed_011", p7_first_seen_order_seed_011),
        ("copper_length::tests::p7_first_seen_order_seed_012", p7_first_seen_order_seed_012),
        ("copper_length::tests::p7_first_seen_order_seed_013", p7_first_seen_order_seed_013),
        ("copper_length::tests::p7_first_seen_order_seed_014", p7_first_seen_order_seed_014),
        ("copper_length::tests::p7_first_seen_order_seed_015", p7_first_seen_order_seed_015),
        ("copper_length::tests::p7_first_seen_order_seed_016", p7_first_seen_order_seed_016),
        ("copper_length::tests::p7_first_seen_order_seed_017", p7_first_seen_order_seed_017),
        ("copper_length::tests::p7_first_seen_order_seed_018", p7_first_seen_order_seed_018),
        ("copper_length::tests::p7_first_seen_order_seed_019", p7_first_seen_order_seed_019),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}

#[cfg(test)]
mod proptests {
    use super::*;
    use proptest::prelude::*;

    fn normal_coord() -> impl Strategy<Value = f64> {
        // Bounded to keep Euclidean distances finite and avoid inf/NaN
        // in the additivity and non-negativity properties.
        (-1e6f64..1e6).prop_filter("avoid subnormals", |x| x.is_normal() || *x == 0.0)
    }

    fn net_name() -> impl Strategy<Value = String> {
        "[A-Z][A-Za-z0-9_]{0,15}"
    }

    fn trace_segment() -> impl Strategy<
        Value = (Option<String>, f64, f64, f64, f64),
    > {
        (
            prop::option::of(net_name()),
            normal_coord(),
            normal_coord(),
            normal_coord(),
            normal_coord(),
        )
    }

    proptest! {
        // -----------------------------------------------------------------
        // measure_copper_length — properties
        // -----------------------------------------------------------------

        /// P1. Total length is always non-negative.
        #[test]
        fn p1_total_length_non_negative(
            traces in prop::collection::vec(trace_segment(), 0..=50),
        ) {
            let (total, _) = measure_copper_length(traces);
            prop_assert!(total >= 0.0,
                "total length should be >= 0, got {total}");
        }

        /// P2. Per-net lengths are all non-negative.
        #[test]
        fn p2_net_lengths_non_negative(
            traces in prop::collection::vec(trace_segment(), 0..=50),
        ) {
            let (_, pairs) = measure_copper_length(traces);
            for (net, len) in &pairs {
                prop_assert!(*len >= 0.0,
                    "net '{net}' has negative length {len}");
            }
        }

        /// P3. Total length equals the sum of per-net lengths.
        #[test]
        fn p3_total_equals_sum_of_nets(
            traces in prop::collection::vec(trace_segment(), 0..=50),
        ) {
            let (total, pairs) = measure_copper_length(traces);
            let sum: f64 = pairs.iter().map(|(_, l)| *l).sum();
            // f64 addition is not exactly associative, so use a small
            // tolerance here — the per-net accumulator and the total
            // accumulator may differ by a handful of ulps.
            let diff = (total - sum).abs();
            prop_assert!(diff < 1e-12 * total.max(1.0),
                "total={total} != sum of nets={sum}, diff={diff}");
        }

        /// P4. Adding segments additively: measure(traces1) + measure(traces2)
        /// total ≈ measure(traces1 ++ traces2) total.
        #[test]
        fn p4_additive_over_concatenation(
            t1 in prop::collection::vec(trace_segment(), 0..=20),
            t2 in prop::collection::vec(trace_segment(), 0..=20),
        ) {
            let (total1, _) = measure_copper_length(t1.clone());
            let (total2, _) = measure_copper_length(t2.clone());
            let mut combined = t1;
            combined.extend(t2);
            let (total_combined, _) = measure_copper_length(combined);

            let diff = (total_combined - (total1 + total2)).abs();
            prop_assert!(diff < 1e-12 * total_combined.max(1.0),
                "not additive: {} + {} != {}, diff={}", total1, total2, total_combined, diff);
        }

        /// P5. A single non-degenerate segment yields positive total length.
        #[test]
        fn p5_non_degenerate_segment_positive(
            net in net_name(),
            sx in normal_coord(),
            sy in normal_coord(),
            dx_delta in 0.1f64..100.0,
            dy_delta in 0.1f64..100.0,
        ) {
            prop_assume!(dx_delta.abs() > 0.0 && dy_delta.abs() > 0.0);
            let ex = sx + dx_delta;
            let ey = sy + dy_delta;
            let (total, _) = measure_copper_length(vec![
                (Some(net), sx, sy, ex, ey)
            ]);
            prop_assert!(total > 0.0,
                "non-degenerate segment should have positive length, got {total}");
        }

        /// P6. Falsy nets (None or empty string) are skipped and contribute
        /// zero to total length.
        #[test]
        fn p6_falsy_nets_contribute_zero(
            _real_nets in prop::collection::vec(
                (net_name(), normal_coord(), normal_coord(), normal_coord(), normal_coord()),
                0..=10,
            ),
        ) {
            // Build a trace list with only falsy nets (None / empty string)
            // and check that the total is zero.
            let falsy_traces: Vec<_> = vec![
                (Some(String::new()), 0.0, 0.0, 10.0, 10.0),
                (None, 0.0, 0.0, 5.0, 5.0),
            ];
            let (total, pairs) = measure_copper_length(falsy_traces);
            prop_assert_eq!(total, 0.0);
            prop_assert!(pairs.is_empty());
        }

        /// P7. Per-net lengths preserve first-seen net name order.
        #[test]
        fn p7_first_seen_order(
            names in prop::collection::vec(net_name(), 1..=10),
            sx in normal_coord(),
            sy in normal_coord(),
            delta in 1.0f64..10.0,
        ) {
            // One segment per net, all same geometry but different net names.
            let traces: Vec<_> = names.iter().map(|n| {
                (Some(n.clone()), sx, sy, sx + delta, sy + delta)
            }).collect();
            let (_, pairs) = measure_copper_length(traces);
            // The pair list should match the first-seen order of unique nets.
            let mut seen = std::collections::HashSet::new();
            let mut expected_order = Vec::new();
            for n in &names {
                if seen.insert(n.clone()) {
                    expected_order.push(n.clone());
                }
            }
            prop_assert_eq!(pairs.len(), expected_order.len());
            for (i, (net, _)) in pairs.iter().enumerate() {
                prop_assert_eq!(net, &expected_order[i],
                    "order mismatch at position {}: {} != {}", i, net, expected_order[i]);
            }
        }
    }
}
