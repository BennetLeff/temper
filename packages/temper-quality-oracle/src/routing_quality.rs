//! Routing-quality composite score kernel (Wave 4, Phase A #1).
//!
//! Ports the pure scoring arithmetic of
//! `temper_placer/metrics/routing_quality.py::evaluate_routing_quality`
//! (the composite 0-100 score: 60% completion, 20% DRC, 20% via-density
//! efficiency) to Rust.
//!
//! ## Bit-exactness discipline
//!
//! The arithmetic mirrors the Python reference's exact f64 operation
//! order so outputs are bit-identical (pinned by the differential suite
//! in `packages/temper-placer/tests/metrics/`):
//!
//! - `completion * 60` (float × int → float) ⇔ `completion * 60.0`
//! - `vias / net_count` (int/int true division → float) ⇔
//!   `via_count as f64 / net_count as f64`
//! - `(vias_per_net - 2) / 8` (int literals promoted) ⇔
//!   `(vias_per_net - 2.0) / 8.0`
//! - `max(0.0, min(1.0, x))` ⇔ `x.min(1.0).max(0.0)` — Python's builtin
//!   `min`/`max` return the first non-NaN operand on a NaN comparison, and
//!   Rust's `f64::min`/`max` ignore NaN the same way, so the clamp agrees
//!   even on non-finite input.
//! - `20 * (1.0 - via_penalty)` (int × float) ⇔ `20.0 * (1.0 - via_penalty)`
//! - `completion_score + drc_score + efficiency_score` is evaluated
//!   left-to-right in Python (same as Rust's left-associative `+`), and
//!   the int `drc_score` (0 or 20) is promoted to f64 at the same point.

/// Compute the composite routing-quality score (0-100).
///
/// Mirrors `evaluate_routing_quality`'s scoring math verbatim.
///
/// # Arguments
///
/// * `completion_rate` — fraction of nets routed (0.0-1.0); 60% of the score.
/// * `via_count` — total vias used.
/// * `drc_error_count` — DRC error count; 0 earns the full 20 DRC points,
///   any error earns 0.
/// * `net_count` — total nets (routed + failed); 0 nets ⇒ full 20
///   efficiency points (nothing to penalize).
///
/// # Returns
///
/// The composite score in [0, 100].
pub fn routing_quality_score(
    completion_rate: f64,
    via_count: i64,
    drc_error_count: i64,
    net_count: i64,
) -> f64 {
    let completion_score = completion_rate * 60.0;
    let drc_score: f64 = if drc_error_count == 0 { 20.0 } else { 0.0 };
    let efficiency_score: f64 = if net_count > 0 {
        let vias_per_net = via_count as f64 / net_count as f64;
        // 0-2 vias per net = full points, 10+ = 0 points (clamped).
        // `min(1.0).max(0.0)` is deliberate, NOT `clamp(0.0, 1.0)`: on a
        // NaN input, `f64::clamp` propagates NaN while `min`/`max` ignore
        // NaN — and the CPython reference (`max(0.0, min(1.0, x))`) keeps
        // the first non-NaN operand, so the `.min().max()` chain is the
        // bit-exact mirror. (Clippy's manual_clamp lint is suppressed for
        // this reason.)
        #[allow(clippy::manual_clamp)]
        let via_penalty = ((vias_per_net - 2.0) / 8.0).min(1.0).max(0.0);
        20.0 * (1.0 - via_penalty)
    } else {
        20.0
    };
    (completion_score + drc_score) + efficiency_score
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn full_marks() {
        // completion 1.0 → 60, drc 0 → 20, 0 vias/net → 20 → 100
        assert_eq!(routing_quality_score(1.0, 0, 0, 10), 100.0);
    }

    #[cfg_attr(test, test)]
    fn drc_error_zeroes_drc_points() {
        // completion 0.5 → 30, drc 3 → 0, net 0 → 20 → 50
        assert_eq!(routing_quality_score(0.5, 10, 3, 0), 50.0);
    }

    #[cfg_attr(test, test)]
    fn via_penalty_clamp_upper() {
        // vias_per_net 10 → (10-2)/8 = 1.0 → penalty 1.0 → efficiency 0
        assert_eq!(routing_quality_score(0.0, 100, 0, 10), 20.0);
    }

    #[cfg_attr(test, test)]
    fn via_penalty_clamp_lower() {
        // vias_per_net 0 → (0-2)/8 = -0.25 → penalty 0 → efficiency 20
        assert_eq!(routing_quality_score(0.0, 0, 0, 10), 40.0);
    }

    #[cfg_attr(test, test)]
    fn zero_nets_full_efficiency() {
        // 0.25*60 = 15 completion + 20 drc + 20 zero-net efficiency == 55
        assert_eq!(routing_quality_score(0.25, 0, 0, 0), 55.0);
    }

    #[cfg_attr(test, test)]
    fn score_never_exceeds_100() {
        let mut max = f64::MIN;
        for completion in (0..=100).map(|c| c as f64 / 100.0) {
            for via_count in 0..=200 {
                for net_count in 1..=50 {
                    max = max.max(routing_quality_score(completion, via_count, 0, net_count));
                }
            }
        }
        assert!(max <= 100.0);
    }

    // --- proptest: routing_quality structural properties ---

    // Carries its own `#[cfg(test)]`, redundant under `cargo test` (the parent
    // `tests` module already has one) but load-bearing for the wasm32 tier: it
    // makes `scripts/gen_wasm_test_registry.py` census this module separately,
    // so the `proptest` dev-dependency -- absent from the non-test build the
    // registry compiles into -- excludes only these properties and not the
    // parent module's plain `#[test]`s.  Same shape as `temper-thermal`'s.
    #[cfg(test)]
    #[allow(clippy::items_after_test_module, clippy::expect_used, clippy::unwrap_used)]
    mod proptests {

        use super::*;
        use proptest::prelude::*;

        proptest! {
            // --------------------------------------------------------------
            // Property R1: Score is always in [0, 100] for valid inputs.
            // --------------------------------------------------------------
            #[test]
            fn prop_score_in_0_100(
                completion in 0.0f64..1.0f64,
                via_count in 0i64..1000i64,
                drc_errors in 0i64..100i64,
                net_count in 0i64..100i64,
            ) {
                let score = routing_quality_score(completion, via_count, drc_errors, net_count);
                prop_assert!(score.is_finite());
                prop_assert!(score >= 0.0);
                prop_assert!(score <= 100.0);
            }

            // --------------------------------------------------------------
            // Property R2: With zero DRC errors, the score is at least
            // the drc component (20.0). The maximum is 100 (60+20+20).
            // --------------------------------------------------------------
            #[test]
            fn prop_drc_clean_score_in_20_100(
                completion in 0.0f64..1.0f64,
                via_count in 0i64..1000i64,
                net_count in 1i64..100i64,
            ) {
                let score = routing_quality_score(completion, via_count, 0, net_count);
                prop_assert!(score >= 20.0);
                prop_assert!(score <= 100.0);
            }

            // --------------------------------------------------------------
            // Property R3: Monotonic in completion_rate: higher completion
            // should yield higher score for fixed other parameters.
            // --------------------------------------------------------------
            #[test]
            fn prop_monotonic_in_completion(
                c1 in 0.0f64..1.0f64,
                c2 in 0.0f64..1.0f64,
                via_count in 0i64..500i64,
                drc in 0i64..10i64,
                net_count in 1i64..50i64,
            ) {
                let (c1, c2) = if c1 <= c2 { (c1, c2) } else { (c2, c1) };
                let s1 = routing_quality_score(c1, via_count, drc, net_count);
                let s2 = routing_quality_score(c2, via_count, drc, net_count);
                prop_assert!(s2 >= s1,
                    "score not monotonic: completion {c1}->{s1}, {c2}->{s2}");
            }

            // --------------------------------------------------------------
            // Property R4: Zero nets yield full efficiency points (20).
            // --------------------------------------------------------------
            #[test]
            fn prop_zero_nets_full_efficiency(
                completion in 0.0f64..1.0f64,
                drc in 0i64..10i64,
            ) {
                let score = routing_quality_score(completion, 100, drc, 0);
                let drc_part: f64 = if drc == 0 { 20.0 } else { 0.0 };
                let expected = completion * 60.0 + drc_part + 20.0;
                prop_assert!((score - expected).abs() < 1e-12,
                    "score {score} != expected {expected}");
            }

            // --------------------------------------------------------------
            // Property R5: DRC errors flip the drc_score from 20 to 0.
            // --------------------------------------------------------------
            #[test]
            fn prop_drc_errors_zero_drc_points(
                completion in 0.0f64..1.0f64,
                via_count in 0i64..500i64,
                net_count in 1i64..50i64,
            ) {
                let clean = routing_quality_score(completion, via_count, 0, net_count);
                let dirty = routing_quality_score(completion, via_count, 1, net_count);
                prop_assert!(clean > dirty || (clean - dirty).abs() < 1e-12,
                    "clean score {clean} should be >= dirty score {dirty}");
            }

            // --------------------------------------------------------------
            // Property R6: Score is deterministic (same inputs, same output).
            // --------------------------------------------------------------
            #[test]
            fn prop_routing_deterministic(
                completion in 0.0f64..1.0f64,
                via_count in 0i64..1000i64,
                drc in 0i64..100i64,
                net_count in 0i64..100i64,
            ) {
                let a = routing_quality_score(completion, via_count, drc, net_count);
                let b = routing_quality_score(completion, via_count, drc, net_count);
                prop_assert_eq!(a.to_bits(), b.to_bits());
            }
        }
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("routing_quality::tests::full_marks", full_marks),
        ("routing_quality::tests::drc_error_zeroes_drc_points", drc_error_zeroes_drc_points),
        ("routing_quality::tests::via_penalty_clamp_upper", via_penalty_clamp_upper),
        ("routing_quality::tests::via_penalty_clamp_lower", via_penalty_clamp_lower),
        ("routing_quality::tests::zero_nets_full_efficiency", zero_nets_full_efficiency),
        ("routing_quality::tests::score_never_exceeds_100", score_never_exceeds_100),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
