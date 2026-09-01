//! Safety-interlock timing kernels (Wave 4, Phase 4).
//!
//! Ports the pure scalar arithmetic of
//! `temper_placer/physics/safety.py` (`estimate_filter_delay`,
//! `estimate_fault_response_time`, `is_safety_timing_valid`) to Rust.
//! The Python module keeps its public API and delegates the arithmetic
//! here.
//!
//! ## Bit-exactness discipline (Wave 4 catalog entries)
//!
//! - **B1 (host libm via dlsym):** `math.log(1.0 - threshold)` resolves
//!   to the host Python runtime's libm `log` via `hostmath`
//!   (dlsym; std fallback on wasm32).
//! - **B7 (f64 operation order):** `tau = r * c`; `-tau * log(...)` is
//!   `(-tau) * log(1.0 - threshold)` (unary minus binds before the
//!   multiply, exactly like CPython).  `(comparator_delay_ns +
//!   mcu_latency_ns) * 1e-3` keeps the parenthesized sum before the
//!   multiply; `filter_delay_us + digital_delay_us` is the final
//!   left-to-right add.
//! - **Branch parity:** the `<= 0` guards are IEEE comparisons (false
//!   for NaN — NaN inputs flow through, matching the reference).
//!   `is_safety_timing_valid` is a plain IEEE `<=`.
//!
//! R24 (physics-gated): N/A as a *constraint encoding* — safety-timing
//! estimators, not CP-SAT constraints; the applicable contract is
//! bit-exact parity (R1a).


use crate::hostmath;

/// IEEE `fneg` as an opaque call so the optimizer cannot fold it into a
/// neighboring multiply.
///
/// The oracle evaluates `(-tau) * log(1.0 - threshold)`: the unary minus
/// is a standalone sign flip on `tau`, and only THEN is the product taken.
/// LLVM reassociates `-tau * log(...)` into `(r * (-c)) * log(...)` when
/// the negation is written inline (DAGCombine sinks the `fneg` into the
/// innermost multiply).  For FINITE values the two are bit-identical (a
/// sign flip commutes with a multiply), but for a NaN `tau` the compiled
/// sign differs: the hardware propagates the NaN operand's own sign, so
/// `(-tau) * log` yields a NEGATIVE NaN while `(r * (-c)) * log` yields a
/// POSITIVE one (the NaN rides on `r`, whose sign was never flipped).
/// CPython's `-tau * math.log(...)` executes the standalone flip, and the
/// differential suite pins the resulting NaN sign bit.  `#[inline(never)]`
/// keeps the `fneg` as its own instruction (x86: `xorpd` with the sign
/// mask) at the call site; `-x` inlined would be re-folded and diverge
/// again.  Measured 2026-08-10: only this structure reproduces the
/// oracle's NaN payload sign for all four non-finite argument positions.
#[inline(never)]
fn negate(x: f64) -> f64 {
    -x
}

/// Estimate the time delay of an RC low-pass filter.  Mirrors
/// `estimate_filter_delay` verbatim: `tau = r * c`;
/// `(-tau) * log(1.0 - threshold)` (B7); the `r <= 0 || c <= 0` guard
/// returns `0.0` (IEEE comparisons — NaN flows through).
pub fn estimate_filter_delay(r_ohms: f64, c_farads: f64, threshold_fraction: f64) -> f64 {
    if r_ohms <= 0.0 || c_farads <= 0.0 {
        return 0.0;
    }

    let tau = r_ohms * c_farads;
    negate(tau) * hostmath::log(1.0 - threshold_fraction)
}

/// Estimate the total time to trigger a safety interlock (µs).  Mirrors
/// `estimate_fault_response_time` verbatim: the first argument is
/// unused by the reference (accepted for API stability); the result is
/// `filter_delay_us + ((comparator_delay_ns + mcu_latency_ns) * 1e-3)`
/// (B7).
pub fn estimate_fault_response_time(
    _loop_inductance_nh: f64,
    filter_delay_us: f64,
    comparator_delay_ns: f64,
    mcu_latency_ns: f64,
) -> f64 {
    let digital_delay_us = (comparator_delay_ns + mcu_latency_ns) * 1e-3;
    filter_delay_us + digital_delay_us
}

/// Check whether a fault-response time is within the safety limit.
/// Mirrors `is_safety_timing_valid` verbatim: `response <= max_limit`
/// (IEEE comparison, false for NaN).
pub fn is_safety_timing_valid(response_time_us: f64, max_limit_us: f64) -> bool {
    response_time_us <= max_limit_us
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn zero_inputs_short_circuit() {
        assert_eq!(estimate_filter_delay(0.0, 1e-6, 0.632), 0.0);
        assert_eq!(estimate_filter_delay(1e3, 0.0, 0.632), 0.0);
        assert_eq!(estimate_filter_delay(-1.0, 1e-6, 0.632), 0.0);
    }

    #[cfg_attr(test, test)]
    fn one_time_constant() {
        // threshold = 1 - 1/e → t = -RC * ln(1/e) = RC
        let t = estimate_filter_delay(1000.0, 1e-6, 1.0 - 1.0 / std::f64::consts::E);
        assert!((t - 1e-3).abs() < 1e-12, "got {t}");
    }

    #[cfg_attr(test, test)]
    fn fault_response_known_value() {
        // 150 ns + 200 ns = 350 ns → 0.35 µs digital delay
        let t = estimate_fault_response_time(10.0, 2.5, 150.0, 200.0);
        assert_eq!(t, 2.85);
    }

    #[cfg_attr(test, test)]
    fn safety_limit_boundary() {
        assert!(is_safety_timing_valid(10.0, 10.0));
        assert!(!is_safety_timing_valid(10.1, 10.0));
        assert!(!is_safety_timing_valid(f64::NAN, 10.0));
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("safety::tests::zero_inputs_short_circuit", zero_inputs_short_circuit),
        ("safety::tests::one_time_constant", one_time_constant),
        ("safety::tests::fault_response_known_value", fault_response_known_value),
        ("safety::tests::safety_limit_boundary", safety_limit_boundary),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
