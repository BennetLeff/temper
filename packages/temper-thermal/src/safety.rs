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

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use temper_py_bridge;

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

/// pyo3 bridge for [`estimate_filter_delay`].
///
/// CPython's `math.log(1.0 - threshold)` raises
/// `ValueError("math domain error")` when `1.0 - threshold <= 0.0`
/// (including `-0.0`), but NOT for NaN (returns NaN) or +inf.  The
/// reference's `r <= 0 || c <= 0` guard returns `0.0` BEFORE the log,
/// so the raise can only fire for strictly-positive r and c — this
/// wrapper replicates that order exactly.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (r_ohms, c_farads, threshold_fraction))]
pub fn estimate_filter_delay_py(
    r_ohms: f64,
    c_farads: f64,
    threshold_fraction: f64,
) -> PyResult<f64> {
    // The reference's guard order: `r <= 0 or c <= 0` returns 0.0 first.
    if r_ohms <= 0.0 || c_farads <= 0.0 {
        return Ok(0.0);
    }
    // CPython `math.log(1.0 - threshold)` domain semantics: x <= 0.0
    // raises ValueError("math domain error"); NaN flows through.
    let log_arg = 1.0 - threshold_fraction;
    if log_arg <= 0.0 {
        return Err(temper_py_bridge::py_value_err("math domain error"));
    }
    temper_py_bridge::catch_unwind(|| estimate_filter_delay(r_ohms, c_farads, threshold_fraction))
        .map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge for [`estimate_fault_response_time`].
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (loop_inductance_nh, filter_delay_us, comparator_delay_ns, mcu_latency_ns))]
pub fn estimate_fault_response_time_py(
    loop_inductance_nh: f64,
    filter_delay_us: f64,
    comparator_delay_ns: f64,
    mcu_latency_ns: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        estimate_fault_response_time(
            loop_inductance_nh,
            filter_delay_us,
            comparator_delay_ns,
            mcu_latency_ns,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge for [`is_safety_timing_valid`].
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (response_time_us, max_limit_us))]
pub fn is_safety_timing_valid_py(response_time_us: f64, max_limit_us: f64) -> PyResult<bool> {
    temper_py_bridge::catch_unwind(|| is_safety_timing_valid(response_time_us, max_limit_us))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn zero_inputs_short_circuit() {
        assert_eq!(estimate_filter_delay(0.0, 1e-6, 0.632), 0.0);
        assert_eq!(estimate_filter_delay(1e3, 0.0, 0.632), 0.0);
        assert_eq!(estimate_filter_delay(-1.0, 1e-6, 0.632), 0.0);
    }

    #[test]
    fn one_time_constant() {
        // threshold = 1 - 1/e → t = -RC * ln(1/e) = RC
        let t = estimate_filter_delay(1000.0, 1e-6, 1.0 - 1.0 / std::f64::consts::E);
        assert!((t - 1e-3).abs() < 1e-12, "got {t}");
    }

    #[test]
    fn fault_response_known_value() {
        // 150 ns + 200 ns = 350 ns → 0.35 µs digital delay
        let t = estimate_fault_response_time(10.0, 2.5, 150.0, 200.0);
        assert_eq!(t, 2.85);
    }

    #[test]
    fn safety_limit_boundary() {
        assert!(is_safety_timing_valid(10.0, 10.0));
        assert!(!is_safety_timing_valid(10.1, 10.0));
        assert!(!is_safety_timing_valid(f64::NAN, 10.0));
    }
}
