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

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn full_marks() {
        // completion 1.0 → 60, drc 0 → 20, 0 vias/net → 20 → 100
        assert_eq!(routing_quality_score(1.0, 0, 0, 10), 100.0);
    }

    #[test]
    fn drc_error_zeroes_drc_points() {
        // completion 0.5 → 30, drc 3 → 0, net 0 → 20 → 50
        assert_eq!(routing_quality_score(0.5, 10, 3, 0), 50.0);
    }

    #[test]
    fn via_penalty_clamp_upper() {
        // vias_per_net 10 → (10-2)/8 = 1.0 → penalty 1.0 → efficiency 0
        assert_eq!(routing_quality_score(0.0, 100, 0, 10), 20.0);
    }

    #[test]
    fn via_penalty_clamp_lower() {
        // vias_per_net 0 → (0-2)/8 = -0.25 → penalty 0 → efficiency 20
        assert_eq!(routing_quality_score(0.0, 0, 0, 10), 40.0);
    }

    #[test]
    fn zero_nets_full_efficiency() {
        // 0.25*60 = 15 completion + 20 drc + 20 zero-net efficiency == 55
        assert_eq!(routing_quality_score(0.25, 0, 0, 0), 55.0);
    }

    #[test]
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
}
