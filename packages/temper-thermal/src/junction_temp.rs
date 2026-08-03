//! Junction-temperature estimation kernel (Wave 4, Phase A #3).
//!
//! Ports the pure scalar arithmetic of
//! `temper_placer/physics/thermal.py::estimate_junction_temp` (the
//! heuristic Tj estimator: edge-distance penalty, copper-spreading
//! benefit, and the `ambient + P * R_total` model) to Rust.  The Python
//! module keeps its public API and delegates the arithmetic here.
//!
//! ## Bit-exactness discipline (Wave 4 catalog entries)
//!
//! The arithmetic mirrors the Python reference's exact f64 operation
//! order so outputs are bit-identical (pinned by the differential suite
//! in `packages/temper-placer/tests/physics/`):
//!
//! - **B5 (Python `max`/`min` first-argument NaN semantics):** the oracle
//!   writes `max(0.0, edge_distance_mm - 5.0)` and
//!   `min(0.5, (copper_area_mm2 / 1000.0) * 0.1)` — the CONSTANT is the
//!   first argument, and CPython's builtin keeps the first argument on a
//!   NaN comparison (`max(0.0, NaN) == 0.0`, `min(0.5, NaN) == 0.5`).
//!   The Rust side mirrors the argument order (`0.0_f64.max(d)` /
//!   `0.5_f64.min(x)`), so the constant is the receiver.  Since the
//!   constants are never NaN this is bit-identical to the opposite
//!   ordering today, but the mirror keeps the invariant if a constant is
//!   ever replaced by a runtime value.
//! - **B7 (f64 operation order):** `edge_penalty = max(0.0, d - 5.0) *
//!   0.2` applies the `* 0.2` to the max RESULT; `copper_benefit` is
//!   `(copper_area_mm2 / 1000.0) * 0.1` — division, then `* 0.1`, then
//!   the `min` — then `R_total` is the left-to-right
//!   `((Rjc + Rch) + Rha_base) + edge_penalty - copper_benefit` chain,
//!   and the final step is `ambient_C + (power_W * R_total)` with the
//!   parenthesized product evaluated first.  No reassociation, no
//!   fusing.
//! - **B8 (denormal underflow):** the crate keeps default IEEE semantics
//!   (no fast-math, no FTZ/DAZ, no `mul_add` fusion); a denormal-band
//!   differential case pins that `power_W * R_total` in the denormal
//!   range matches CPython bit-for-bit.
//!
//! B1/B2/B3/B4/B6 are **not applicable** here: the kernel calls no libm
//! functions (no sqrt/pow/log), divides no constants (no `pi`-style
//! named-constant-vs-division hazard), rounds nothing, and computes no
//! distances.

use pyo3::prelude::*;
use temper_py_bridge;

/// Estimate component junction temperature from placement and environment.
///
/// Mirrors `estimate_junction_temp`'s arithmetic verbatim:
///
/// - `edge_penalty = max(0.0, edge_distance_mm - 5.0) * 0.2` — 0.2 K/W
///   per mm beyond 5 mm from the edge (heatsink mount point).
/// - `copper_benefit = min(0.5, (copper_area_mm2 / 1000.0) * 0.1)` —
///   0.1 K/W reduction per 1000 mm² of copper, capped at 0.5 K/W.
/// - `R_total = Rjc + Rch + Rha_base + edge_penalty - copper_benefit`
///   (left-to-right).
/// - `T_junction = ambient_C + (power_W * R_total)`.
///
/// # Arguments
///
/// * `power_w` — power dissipation (W).
/// * `edge_distance_mm` — distance to the board edge (mm).
/// * `copper_area_mm2` — connected copper pour area (mm²).
/// * `ambient_c` — ambient temperature (°C).
/// * `rjc` — junction-to-case thermal resistance (K/W).
/// * `rch` — case-to-heatsink thermal resistance (K/W).
/// * `rha_base` — base heatsink-to-ambient resistance (K/W).
///
/// # Returns
///
/// Estimated junction temperature in °C.
pub fn estimate_junction_temp(
    power_w: f64,
    edge_distance_mm: f64,
    copper_area_mm2: f64,
    ambient_c: f64,
    rjc: f64,
    rch: f64,
    rha_base: f64,
) -> f64 {
    // edge_penalty = max(0.0, edge_distance_mm - 5.0) * 0.2
    // (B5: constant first, mirroring the Python builtin's first-argument
    // NaN semantics; B7: the * 0.2 applies to the max result.)
    let edge_penalty = 0.0_f64.max(edge_distance_mm - 5.0) * 0.2;

    // copper_benefit = min(0.5, (copper_area_mm2 / 1000.0) * 0.1)
    // (B5: constant first; B7: division then * 0.1 then min.)
    let copper_benefit = 0.5_f64.min((copper_area_mm2 / 1000.0) * 0.1);

    // R_total = Rjc + Rch + Rha_base + edge_penalty - copper_benefit
    // (B7: Python's left-to-right chain, no reassociation.)
    let r_total = ((rjc + rch) + rha_base) + edge_penalty - copper_benefit;

    // T_junction = ambient_C + (power_W * R_total)
    // (B7: parenthesized product evaluated first, then the add.)
    ambient_c + (power_w * r_total)
}

/// pyo3 bridge for [`estimate_junction_temp`].
#[pyfunction]
#[pyo3(signature = (power_w, edge_distance_mm, copper_area_mm2, ambient_c, rjc, rch, rha_base))]
pub fn estimate_junction_temp_py(
    power_w: f64,
    edge_distance_mm: f64,
    copper_area_mm2: f64,
    ambient_c: f64,
    rjc: f64,
    rch: f64,
    rha_base: f64,
) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| {
        estimate_junction_temp(
            power_w,
            edge_distance_mm,
            copper_area_mm2,
            ambient_c,
            rjc,
            rch,
            rha_base,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn base_case_edge_mounting() {
        // 15 W at 5 mm from edge (no penalty):
        // Tj = 40 + 15 * (0.6 + 0.25 + 1.0) = 40 + 15 * 1.85 = 67.75
        assert_eq!(estimate_junction_temp(15.0, 5.0, 0.0, 40.0, 0.6, 0.25, 1.0), 67.75);
    }

    #[test]
    fn edge_penalty() {
        // 5 mm penalty: 40 + 15 * (1.85 + 1.0) = 82.75
        assert_eq!(estimate_junction_temp(15.0, 10.0, 0.0, 40.0, 0.6, 0.25, 1.0), 82.75);
    }

    #[test]
    fn copper_benefit() {
        // 0.1 K/W benefit: 40 + 15 * 1.75 = 66.25
        assert_eq!(estimate_junction_temp(15.0, 5.0, 1000.0, 40.0, 0.6, 0.25, 1.0), 66.25);
    }

    #[test]
    fn overheating() {
        // 10 mm penalty, 50 W: 40 + 50 * 3.85 = 232.5
        assert_eq!(estimate_junction_temp(50.0, 15.0, 0.0, 40.0, 0.6, 0.25, 1.0), 232.5);
    }

    #[test]
    fn penalty_saturates_below_five_mm() {
        // max(0.0, d - 5.0) is exactly 0.0 for d <= 5.0, so Tj is
        // bit-identical across the saturated range.
        let base = estimate_junction_temp(15.0, 5.0, 0.0, 40.0, 0.6, 0.25, 1.0);
        for edge in [-1e6, -1.0, 0.0, 2.5, 4.999, 5.0] {
            assert_eq!(estimate_junction_temp(15.0, edge, 0.0, 40.0, 0.6, 0.25, 1.0), base);
        }
    }

    #[test]
    fn copper_benefit_saturates_above_5000() {
        // min(0.5, (A/1000)*0.1) is exactly 0.5 for A >= 5000.
        let base = estimate_junction_temp(15.0, 5.0, 5000.0, 40.0, 0.6, 0.25, 1.0);
        for copper in [5000.0, 5000.0001, 1e6, f64::INFINITY] {
            assert_eq!(estimate_junction_temp(15.0, 5.0, copper, 40.0, 0.6, 0.25, 1.0), base);
        }
    }

    #[test]
    fn nan_penalty_keeps_first_argument() {
        // Python `max(0.0, NaN)` keeps the FIRST argument (the constant
        // 0.0) → penalty exactly 0.0 → R_total 1.85 → 67.75.  (B5.)
        let got = estimate_junction_temp(15.0, f64::NAN, 0.0, 40.0, 0.6, 0.25, 1.0);
        assert_eq!(got, 67.75);
    }

    #[test]
    fn nan_copper_benefit_keeps_first_argument() {
        // Python `min(0.5, NaN)` keeps 0.5 → R_total 1.35 → 60.25.  (B5.)
        let got = estimate_junction_temp(15.0, 5.0, f64::NAN, 40.0, 0.6, 0.25, 1.0);
        assert_eq!(got, 60.25);
    }

    #[test]
    fn zero_power_is_exactly_ambient() {
        for ambient in [-40.0, 0.0, 25.0, 100.0] {
            assert_eq!(estimate_junction_temp(0.0, 25.0, 0.0, ambient, 0.6, 0.25, 1.0), ambient);
        }
    }

    #[test]
    fn op_order_product_before_add() {
        // Tj = ambient + (power * R_total): the product is a single
        // rounded op on both sides, then the add — no reassociation.
        let a = estimate_junction_temp(3.0, 5.0, 0.0, 25.0, 0.6, 0.25, 1.0);
        assert_eq!(a, 25.0 + 3.0 * 1.85);
    }
}
