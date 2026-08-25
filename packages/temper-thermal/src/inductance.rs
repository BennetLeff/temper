//! Parasitic loop-inductance estimation kernels (Wave 4, Phase A #4).
//!
//! Ports the pure scalar arithmetic of
//! `temper_placer/physics/inductance.py` (the `estimate_loop_inductance`
//! estimator) to Rust.  The Python module keeps its public API and
//! delegates the arithmetic here.
//!
//! ## `estimate_gate_inductance` — deleted 2026-08-17
//!
//! A sibling estimator, `estimate_gate_inductance(source_to_gate_dist_mm,
//! return_dist_mm)`, lived here from this crate's original Python source
//! (`60a0ff099`, 2025-12-26) through the Wave 4 Rust port. It had no
//! production caller for its entire lifetime: its only intended consumer,
//! `metrics/physics.py::measure_emi`'s `i == 0` "gate drive" loop branch,
//! called the generic `estimate_loop_inductance` instead (a bug present
//! from the same authoring commit — never fixed, never exercised).
//! `measure_emi` itself, and the `PipelineOrchestrator` that called it,
//! were deleted as dead code by `1060584b7` (2026-07-10, "retire the old
//! iterative pipeline"), a deliberate, verified refactor unrelated to this
//! kernel. The board's actual (separately incomplete) gate-drive-loop
//! physics check is `placer/cp_sat/gates.py::PhysicsGate`'s sub-check 2,
//! which measures routed trace geometry via
//! `physics.gate_drive.gate_drive_loop_area`/`gate_drive_spacing` — a
//! module that does not exist anywhere in this repo, so that check is
//! permanently `UNMEASURED` today regardless of this estimator. Neither
//! formula is applied to the gate-drive loop in production; see
//! `docs/evidence/2026-08-17-gate-inductance-and-unwired-kernels.md` for
//! the full trace. Deleted rather than wired: wiring it into still-dead
//! `measure_emi` would satisfy the unwired-kernel gate's coarse AST-
//! reference check without restoring any live behavior.
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
//!   — no reassociation, no fusing.
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

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn loop_inductance_base_case() {
        // 100 mm², 40 mm perimeter, 0.4 mm height, rf = 1.2:
        // L_area ≈ 314 nH → L_total = (157 + 8) * 1.2 = 198 nH.
        let got = estimate_loop_inductance(100.0, 40.0, 0.4, 1.2);
        assert!((got - 198.0).abs() < 0.1, "got {got}");
    }

    #[cfg_attr(test, test)]
    fn loop_inductance_zero_height_is_self_only() {
        // h = 0 → area term exactly 0.0 → L_total = (0.0 + p*0.2) * rf
        // = p * 0.2 * rf exactly (adding 0.0 is exact, as in CPython).
        assert_eq!(estimate_loop_inductance(100.0, 40.0, 0.0, 1.2), 40.0 * 0.2 * 1.2);
        // Negative h also selects the 0 arm.
        assert_eq!(estimate_loop_inductance(100.0, 40.0, -0.4, 1.2), 40.0 * 0.2 * 1.2);
    }

    #[cfg_attr(test, test)]
    fn loop_inductance_nan_h_selects_zero_arm() {
        // NaN > 0.0 is false in both CPython and Rust → 0 area term.
        assert_eq!(estimate_loop_inductance(100.0, 40.0, f64::NAN, 1.2), 40.0 * 0.2 * 1.2);
    }

    #[cfg_attr(test, test)]
    fn loop_inductance_zero_routing_factor_is_exactly_zero() {
        // (finite sum) * 0.0 == 0.0 exactly on both sides.
        assert_eq!(estimate_loop_inductance(100.0, 40.0, 0.4, 0.0), 0.0);
    }

    #[cfg_attr(test, test)]
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

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("inductance::tests::loop_inductance_base_case", loop_inductance_base_case),
        ("inductance::tests::loop_inductance_zero_height_is_self_only", loop_inductance_zero_height_is_self_only),
        ("inductance::tests::loop_inductance_nan_h_selects_zero_arm", loop_inductance_nan_h_selects_zero_arm),
        ("inductance::tests::loop_inductance_zero_routing_factor_is_exactly_zero", loop_inductance_zero_routing_factor_is_exactly_zero),
        ("inductance::tests::mu0_chain_matches_named_constant", mu0_chain_matches_named_constant),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
