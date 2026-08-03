//! Parasitic loop-inductance estimation kernels (Wave 4, Phase A #4).
//!
//! Ports the pure scalar arithmetic of
//! `temper_placer/physics/inductance.py` (the `estimate_loop_inductance`
//! and `estimate_gate_inductance` estimators) to Rust.  The Python
//! module keeps its public API and delegates the arithmetic here.
//!
//! ## Bit-exactness discipline (Wave 4 catalog entries)
//!
//! The arithmetic mirrors the Python reference's exact f64 operation
//! order so outputs are bit-identical (pinned by the differential suite
//! in `packages/temper-placer/tests/physics/`):
//!
//! - **B2 (math.pi family — extension):** the oracle uses the NAMED
//!   constant `math.pi` (the correctly-rounded 53-bit double closest to
//!   pi, 0x400921FB54442D18), which is bit-identical to Rust's
//!   `std::f64::consts::PI`.  The B2 pitfall (`PI / 2.0` vs
//!   `FRAC_PI_2` — a division that rounds once more) does NOT arise
//!   because the oracle never divides pi; the three-op chain
//!   `4 * math.pi * 1e-7` is `(4.0 * PI) * 1e-7` on both sides.
//!   `MU_0` is computed at call time inside the reference function (a
//!   function-body local), so it is re-evaluated per call exactly as
//!   here.
//! - **B7 (f64 operation order):** `MU_0 * area_m2 / h_m` is the
//!   left-to-right `(mu_0 * area_m2) / h_m` chain; `L_area_H * 1e9` and
//!   `perimeter_mm * 0.2` are single multiplies; the final
//!   `(L_area_nH * 0.5 + L_self_nH) * routing_factor` keeps the
//!   parenthesized sum evaluated BEFORE the multiply by `routing_factor`
//!   — no reassociation, no fusing.  `estimate_gate_inductance` is the
//!   left-to-right `(a + b) + 5.0` add chain, then `* 0.8`.
//! - **B8 (denormal underflow):** the crate keeps default IEEE semantics
//!   (no fast-math, no FTZ/DAZ, no `mul_add` fusion); a denormal-band
//!   differential case pins that `mu_0 * area_m2` in the denormal range
//!   matches CPython bit-for-bit.
//!
//! Branch semantics match Python's comparisons exactly: `h_m > 0.0` is
//! the same IEEE comparison on both sides — false for 0.0, negative, and
//! NaN, selecting the `0` area term identically.
//!
//! B1 (host libm via dlsym) is **not applicable**: the kernels call no
//! libm functions (no sqrt/pow/log — the only constant is `math.pi`).
//! B3/B4/B5/B6 are likewise not applicable (no rounding, no hypot, no
//! Python `max`/`min`).

use pyo3::prelude::*;
use temper_py_bridge;

/// Estimate parasitic loop inductance (nH) from loop area and perimeter.
///
/// Mirrors `estimate_loop_inductance`'s arithmetic verbatim:
///
/// - `MU_0 = 4 * math.pi * 1e-7` (H/m) — the three-op left-to-right
///   chain `(4.0 * PI) * 1e-7` (B2: named constant, bit-identical to
///   Rust's `PI`).
/// - `area_m2 = loop_area_mm2 * 1e-6`; `h_m = layer_separation_mm * 1e-3`.
/// - `L_area_H = (MU_0 * area_m2 / h_m) if h_m > 0 else 0` — the
///   conditional area term (IEEE `h_m > 0.0` selects the division arm;
///   0.0/negative/NaN select the `0` arm).
/// - `L_area_nH = L_area_H * 1e9`; `L_self_nH = perimeter_mm * 0.2`.
/// - `L_total_nH = (L_area_nH * 0.5 + L_self_nH) * routing_factor` —
///   the parenthesized sum first, then the multiply (B7).
///
/// # Arguments
///
/// * `loop_area_mm2` — geometric area of the loop (mm²).
/// * `perimeter_mm` — perimeter of the loop (mm).
/// * `layer_separation_mm` — signal-to-ground plane separation (mm).
/// * `routing_factor` — non-ideal-routing multiplier (>= 1.0).
///
/// # Returns
///
/// Estimated inductance in nanohenries.
pub fn estimate_loop_inductance(
    loop_area_mm2: f64,
    perimeter_mm: f64,
    layer_separation_mm: f64,
    routing_factor: f64,
) -> f64 {
    // MU_0 = 4 * math.pi * 1e-7 (H/m).  The named constant math.pi is
    // bit-identical to std::f64::consts::PI (both the correctly-rounded
    // 53-bit double closest to pi); the three-op chain is left-to-right
    // (B2 extension, B7).
    let mu_0 = 4.0 * std::f64::consts::PI * 1e-7;

    let area_m2 = loop_area_mm2 * 1e-6;
    let h_m = layer_separation_mm * 1e-3;

    // L_area_H = (MU_0 * area_m2 / h_m) if h_m > 0 else 0
    // (IEEE comparison parity: NaN / 0.0 / negative select the 0 arm.)
    let l_area_h = if h_m > 0.0 { mu_0 * area_m2 / h_m } else { 0.0 };

    let l_area_nh = l_area_h * 1e9;
    let l_self_nh = perimeter_mm * 0.2;

    // (L_area_nH * 0.5 + L_self_nH) * routing_factor — parenthesized
    // sum first, then the multiply by routing_factor (B7).
    (l_area_nh * 0.5 + l_self_nh) * routing_factor
}

/// Estimate gate-drive loop inductance (nH) from source/return distances.
///
/// Mirrors `estimate_gate_inductance`'s arithmetic verbatim: the
/// left-to-right add chain `(source_to_gate_dist_mm + return_dist_mm) +
/// 5.0`, then `* 0.8` (B7).
///
/// # Arguments
///
/// * `source_to_gate_dist_mm` — driver-output-to-gate distance (mm).
/// * `return_dist_mm` — source-to-driver-ground return distance (mm).
///
/// # Returns
///
/// Estimated gate-drive loop inductance in nanohenries.
pub fn estimate_gate_inductance(source_to_gate_dist_mm: f64, return_dist_mm: f64) -> f64 {
    // perimeter = source_to_gate_dist_mm + return_dist_mm + 5.0 (+5 mm
    // for internal coupling), then * 0.8 nH/mm (B7: left-to-right adds).
    (source_to_gate_dist_mm + return_dist_mm + 5.0) * 0.8
}

/// pyo3 bridge for [`estimate_loop_inductance`].
#[pyfunction]
#[pyo3(signature = (loop_area_mm2, perimeter_mm, layer_separation_mm, routing_factor))]
pub fn estimate_loop_inductance_py(
    loop_area_mm2: f64,
    perimeter_mm: f64,
    layer_separation_mm: f64,
    routing_factor: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        estimate_loop_inductance(
            loop_area_mm2,
            perimeter_mm,
            layer_separation_mm,
            routing_factor,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge for [`estimate_gate_inductance`].
#[pyfunction]
#[pyo3(signature = (source_to_gate_dist_mm, return_dist_mm))]
pub fn estimate_gate_inductance_py(
    source_to_gate_dist_mm: f64,
    return_dist_mm: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        estimate_gate_inductance(source_to_gate_dist_mm, return_dist_mm)
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn loop_inductance_base_case() {
        // 100 mm², 40 mm perimeter, 0.4 mm height, rf = 1.2:
        // L_area ≈ 314 nH → L_total = (157 + 8) * 1.2 = 198 nH.
        let got = estimate_loop_inductance(100.0, 40.0, 0.4, 1.2);
        assert!((got - 198.0).abs() < 0.1, "got {got}");
    }

    #[test]
    fn loop_inductance_zero_height_is_self_only() {
        // h = 0 → area term exactly 0.0 → L_total = (0.0 + p*0.2) * rf
        // = p * 0.2 * rf exactly (adding 0.0 is exact, as in CPython).
        assert_eq!(estimate_loop_inductance(100.0, 40.0, 0.0, 1.2), 40.0 * 0.2 * 1.2);
        // Negative h also selects the 0 arm.
        assert_eq!(estimate_loop_inductance(100.0, 40.0, -0.4, 1.2), 40.0 * 0.2 * 1.2);
    }

    #[test]
    fn loop_inductance_nan_h_selects_zero_arm() {
        // NaN > 0.0 is false in both CPython and Rust → 0 area term.
        assert_eq!(estimate_loop_inductance(100.0, 40.0, f64::NAN, 1.2), 40.0 * 0.2 * 1.2);
    }

    #[test]
    fn loop_inductance_zero_routing_factor_is_exactly_zero() {
        // (finite sum) * 0.0 == 0.0 exactly on both sides.
        assert_eq!(estimate_loop_inductance(100.0, 40.0, 0.4, 0.0), 0.0);
    }

    #[test]
    fn gate_inductance_known_value() {
        // (10 + 10 + 5) * 0.8 = 20.0 exactly.
        assert_eq!(estimate_gate_inductance(10.0, 10.0), 20.0);
    }

    #[test]
    fn gate_inductance_zero_distances() {
        // (0 + 0 + 5.0) * 0.8 = 4.0 (the +5 mm internal coupling term).
        assert_eq!(estimate_gate_inductance(0.0, 0.0), 4.0);
    }

    #[test]
    fn gate_inductance_op_order() {
        // The add chain is (a + b) + 5.0, then * 0.8 — pin the exact
        // chain so a reassociation (e.g. (a + 5.0) + b) cannot slip in.
        let a = 0.12345678901234567;
        let b = 987.6543210987654;
        assert_eq!(estimate_gate_inductance(a, b), (a + b + 5.0) * 0.8);
    }

    #[test]
    fn mu0_chain_matches_named_constant() {
        // 4 * math.pi * 1e-7 with Rust's PI is the same double as the
        // CPython oracle's chain (B2 extension: named constant is
        // bit-identical; verified against the oracle in the differential
        // suite, and structurally here).
        let mu_0 = 4.0 * std::f64::consts::PI * 1e-7;
        // area = 1.0 mm², h = 1.0 mm, perim = 0, rf = 1.0:
        // L_total = (mu_0 * 1e-6 / 1e-3 * 1e9 * 0.5) * 1.0
        let got = estimate_loop_inductance(1.0, 0.0, 1.0, 1.0);
        let expected = (mu_0 * 1e-6 / 1e-3 * 1e9 * 0.5) * 1.0;
        assert_eq!(got, expected);
    }
}
