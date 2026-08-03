//! Composite placement/DRC/routing quality-score kernels (Wave 4, Phase A #5).
//!
//! Ports the pure scalar scoring arithmetic of
//! `temper_placer/metrics/quality_score.py` (the composite 0-100 quality
//! score: placement subscore, DRC subscore, the 50/50 or 40/40/20 weighted
//! overall, and the ``excellent/good/ok/poor`` interpretation) to Rust.
//! The Python module keeps its public API (`compute_quality_score`,
//! `interpret_score`, the `QualityInputs`/`QualityScore` dataclasses, the
//! `PlacementMetrics`/`DrcResult` input plumbing) and delegates the
//! arithmetic here.
//!
//! ## Bit-exactness discipline (Wave 4 catalog entries)
//!
//! The arithmetic mirrors the Python reference's exact f64 operation
//! order so outputs are bit-identical (pinned by the differential suite
//! in `packages/temper-placer/tests/metrics/`):
//!
//! - **B5 (Python `max`/`min` first-argument NaN semantics):** the oracle
//!   writes `max(0.0, min(100.0, score))` — the CONSTANT is the first
//!   argument, and CPython's builtin keeps the first argument on a NaN
//!   comparison (`min(100.0, NaN) == 100.0`).  The Rust side mirrors the
//!   nesting and argument order (`(100.0_f64.min(score)).max(0.0)`), so
//!   the constants are the receivers.  The wirelength cap is
//!   `min(10, (avg_len - 50) / 10)` ⇔ `10.0_f64.min((avg_len - 50.0) / 10.0)`.
//! - **B7 (f64 operation order):** every int penalty is exact integer
//!   arithmetic in Python (`overlap_count * 20`), converted to f64 exactly
//!   at the subtraction — Rust's `overlap_count as f64 * 20.0` is the same
//!   correctly-rounded product for magnitudes below 2^53.  The wirelength
//!   penalty keeps the parenthesized `(avg_len - 50) / 10` division before
//!   the `min`.  The overall is the left-to-right
//!   `0.5 * ps + 0.5 * ds` / `0.4 * ps + 0.4 * ds + 0.2 * rs` chain — no
//!   reassociation, no fusing.
//!
//! B1/B2/B3/B4/B6/B8/B9/B10 are **not applicable** here: the kernel calls
//! no libm functions (no sqrt/pow/log/hypot), divides no named constants,
//! rounds nothing, cannot produce denormal-range intermediates (every
//! intermediate is a bounded [0,100]-range sum; `avg_len - 50` for any
//! representable adjacent float is ≥ ulp(50) ≈ 7.1e-15, normal), and
//! renders no floats or dataclass reprs (the interpretation is a fixed
//! vocabulary of plain strings).

use pyo3::prelude::*;
use temper_py_bridge;

/// Compute the composite placement subscore (0-100).
///
/// Mirrors `_compute_placement_score`'s arithmetic verbatim:
/// start at 100.0, subtract per-violation penalties (overlap −20,
/// boundary −15, HV/LV −25, keepout −10, clearance-beyond-HV/LV −5,
/// zone −10), then the wirelength penalty
/// `min(10, (avg_net_length - 50) / 10)` when the average net length
/// exceeds 50 mm (and total wirelength is positive), clamped to
/// `[0, 100]` with the constant-first `max(0.0, min(100.0, score))`.
///
/// # Arguments
///
/// * `overlap_count`, `boundary_violations`, `hv_lv_violations`,
///   `keepout_violations`, `clearance_violations`, `zone_violations` —
///   violation counts.
/// * `total_wirelength` — total routed wirelength (mm); `> 0` gates the
///   wirelength penalty branch (IEEE comparison, false for NaN).
/// * `avg_net_length` — average net length (mm); the penalty is skipped
///   unless `> 50` (also an IEEE comparison).
///
/// # Returns
///
/// The placement subscore in `[0, 100]`.
#[allow(clippy::too_many_arguments)]
pub fn placement_score(
    overlap_count: i64,
    boundary_violations: i64,
    hv_lv_violations: i64,
    keepout_violations: i64,
    clearance_violations: i64,
    zone_violations: i64,
    total_wirelength: f64,
    avg_net_length: f64,
) -> f64 {
    let mut score = 100.0;

    // Critical violations (block routing or violate safety).
    score -= overlap_count as f64 * 20.0;
    score -= boundary_violations as f64 * 15.0;
    score -= hv_lv_violations as f64 * 25.0;
    score -= keepout_violations as f64 * 10.0;

    // Medium violations (sub-optimal but not critical).
    score -= (clearance_violations - hv_lv_violations) as f64 * 5.0;
    score -= zone_violations as f64 * 10.0;

    // Wirelength penalty: only when total wirelength is positive and the
    // average net length exceeds 50 mm.  `min(10, x)` keeps the constant
    // 10.0 on a NaN quotient (B5) — mirroring the oracle's argument order.
    if total_wirelength > 0.0 && avg_net_length > 50.0 {
        score -= 10.0_f64.min((avg_net_length - 50.0) / 10.0);
    }

    // Constant-first clamp: min(100.0, score) then max(0.0, ...) (B5).
    (100.0_f64.min(score)).max(0.0)
}

/// Compute the composite DRC subscore (0-100).
///
/// Mirrors `_compute_drc_score`'s arithmetic verbatim: start at 100.0,
/// subtract `error_count * 15` and `warning_count * 3` (exact integer
/// arithmetic promoted at the subtraction), clamped to `[0, 100]` with
/// the constant-first `max(0.0, min(100.0, score))`.
///
/// # Returns
///
/// The DRC subscore in `[0, 100]`.
pub fn drc_score(error_count: i64, warning_count: i64) -> f64 {
    let score = 100.0 - error_count as f64 * 15.0 - warning_count as f64 * 3.0;
    (100.0_f64.min(score)).max(0.0)
}

/// Compute the weighted overall quality score.
///
/// Mirrors `compute_quality_score`'s overall chain verbatim:
/// `0.5 * placement_score + 0.5 * drc_score` when no routing score is
/// available, else `0.4 * placement_score + 0.4 * drc_score +
/// 0.2 * routing_score` (both left-to-right, no reassociation).
///
/// # Returns
///
/// The overall score in `[0, 100]`.
pub fn overall_score(
    placement_score: f64,
    drc_score: f64,
    routing_score: Option<f64>,
) -> f64 {
    match routing_score {
        Some(rs) => 0.4 * placement_score + 0.4 * drc_score + 0.2 * rs,
        None => 0.5 * placement_score + 0.5 * drc_score,
    }
}

/// Human-readable interpretation of a quality score.
///
/// Mirrors `interpret_score` verbatim: `>= 90` → "excellent",
/// `>= 80` → "good", `>= 60` → "ok", else "poor".  Pure IEEE
/// comparisons — a NaN score fails all three and reads "poor".
pub fn interpret_score(score: f64) -> String {
    if score >= 90.0 {
        "excellent".to_string()
    } else if score >= 80.0 {
        "good".to_string()
    } else if score >= 60.0 {
        "ok".to_string()
    } else {
        "poor".to_string()
    }
}

/// pyo3 bridge for [`placement_score`].
#[pyfunction]
#[allow(clippy::too_many_arguments)]
#[pyo3(signature = (overlap_count, boundary_violations, hv_lv_violations, keepout_violations, clearance_violations, zone_violations, total_wirelength, avg_net_length))]
pub fn placement_score_py(
    overlap_count: i64,
    boundary_violations: i64,
    hv_lv_violations: i64,
    keepout_violations: i64,
    clearance_violations: i64,
    zone_violations: i64,
    total_wirelength: f64,
    avg_net_length: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        placement_score(
            overlap_count,
            boundary_violations,
            hv_lv_violations,
            keepout_violations,
            clearance_violations,
            zone_violations,
            total_wirelength,
            avg_net_length,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge for [`drc_score`].
#[pyfunction]
#[pyo3(signature = (error_count, warning_count))]
pub fn drc_score_py(error_count: i64, warning_count: i64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| drc_score(error_count, warning_count))
        .map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge for [`overall_score`].
#[pyfunction]
#[pyo3(signature = (placement_score, drc_score, routing_score=None))]
pub fn overall_score_py(
    placement_score: f64,
    drc_score: f64,
    routing_score: Option<f64>,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| overall_score(placement_score, drc_score, routing_score))
        .map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge for [`interpret_score`].
#[pyfunction]
#[pyo3(signature = (score))]
pub fn interpret_score_py(score: f64) -> PyResult<String> {
    temper_py_bridge::catch_unwind(|| interpret_score(score))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn placement_perfect_is_100() {
        assert_eq!(placement_score(0, 0, 0, 0, 0, 0, 0.0, 0.0), 100.0);
    }

    #[test]
    fn placement_two_overlaps() {
        // 100 - 40 = 60 exactly.
        assert_eq!(placement_score(2, 0, 0, 0, 0, 0, 0.0, 0.0), 60.0);
    }

    #[test]
    fn placement_clamps_at_zero() {
        // 100 - 400 = -300 → clamped to 0.0.
        assert_eq!(placement_score(20, 0, 0, 0, 0, 0, 0.0, 0.0), 0.0);
    }

    #[test]
    fn placement_wirelength_penalty() {
        // avg_len = 60 → penalty min(10, (60-50)/10) = 1.0 → 99.0
        assert_eq!(placement_score(0, 0, 0, 0, 0, 0, 1.0, 60.0), 99.0);
        // avg_len = 160 → (160-50)/10 = 11 → capped at 10 → 90.0
        assert_eq!(placement_score(0, 0, 0, 0, 0, 0, 1.0, 160.0), 90.0);
        // avg_len = 50 → no penalty (strictly greater)
        assert_eq!(placement_score(0, 0, 0, 0, 0, 0, 1.0, 50.0), 100.0);
        // total_wirelength == 0 → branch skipped even for huge avg_len
        assert_eq!(placement_score(0, 0, 0, 0, 0, 0, 0.0, 1e6), 100.0);
    }

    #[test]
    fn placement_nan_wirelength_skips_penalty() {
        // NaN > 0.0 is false in both CPython and Rust → no penalty.
        assert_eq!(placement_score(0, 0, 0, 0, 0, 0, 1.0, f64::NAN), 100.0);
    }

    #[test]
    fn placement_nan_avg_len_skips_penalty() {
        // avg_len NaN: `avg_len > 50` is False → no penalty → 100.0.
        assert_eq!(placement_score(0, 0, 0, 0, 0, 0, 1.0, f64::NAN), 100.0);
    }

    #[test]
    fn drc_known_values() {
        // 100 - 30 - 9 = 61.0 exactly.
        assert_eq!(drc_score(2, 3), 61.0);
        // 100 - 300 - 120 = -320 → 0.0
        assert_eq!(drc_score(20, 40), 0.0);
    }

    #[test]
    fn overall_weighted_chains() {
        // No routing: (0.5*63.5) + (0.5*41.25) — left-to-right.
        assert_eq!(overall_score(63.5, 41.25, None), 0.5 * 63.5 + 0.5 * 41.25);
        // With routing: ((0.4*63.5) + (0.4*41.25)) + (0.2*88.0)
        let rs = Some(88.0);
        assert_eq!(overall_score(63.5, 41.25, rs), 0.4 * 63.5 + 0.4 * 41.25 + 0.2 * 88.0);
    }

    #[test]
    fn interpretation_thresholds() {
        assert_eq!(interpret_score(90.0), "excellent");
        assert_eq!(interpret_score(89.999), "good");
        assert_eq!(interpret_score(80.0), "good");
        assert_eq!(interpret_score(79.999), "ok");
        assert_eq!(interpret_score(60.0), "ok");
        assert_eq!(interpret_score(59.999), "poor");
        assert_eq!(interpret_score(f64::NAN), "poor");
    }
}
