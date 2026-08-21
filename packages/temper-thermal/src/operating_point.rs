//! Coupled-load operating-point kernels (Wave 4, Phase 4).
//!
//! Bit-exact port of the numeric core of
//! `temper_placer/physics/operating_point.py`: the continuous coupling
//! model `L_eff(k)`, the thermal chain and ceiling arithmetic of
//! `compute_extremes`, and the interior bounding-soundness scan of
//! `_interior_bounding_soundness_check`.
//!
//! The Python module keeps its public API, its `OperatingPointConfig`
//! dataclass and validation, the `Gate`/`GateResult`/`Violation`
//! construction (those pyclasses live in `temper-design-bundle`), the
//! SPICE cross-check, and the `_coupling_l_eff_fn` test hook — Python
//! evaluates the (possibly injected) coupling model and hands the
//! resulting `L_eff` values here, so a non-monotone override still
//! exercises the same arithmetic.
//!
//! The per-device power itself is **not** recomputed here: it already
//! delegates to [`crate::device_power`] through
//! `physics/device_power.py`, so `compute_extremes` passes the value in
//! and there remains exactly one power-source formula (issue #140).
//!
//! # Bit-exactness discipline (Wave-4 catalog)
//!
//! - **B5:** `max(di_dt_k0, di_dt_k1)` and `min(l_loop_max_k0,
//!   l_loop_max_k1)` are CPython *builtins*, which keep the first
//!   argument when a comparison is false — including on NaN.
//!   [`crate::hostmath::py_max`] and [`py_min`] mirror that; `f64::max`/
//!   `f64::min` would discard NaN and silently disagree.
//! - **B7:** every chain keeps the reference's grouping and order:
//!   `(R_jc + R_cs) + R_sa`, `T_amb + (P * R_th_total)`,
//!   `L_coil * (1 - k) + L_leakage * k`, `V_BR * derate`,
//!   `v_br_derated - V_bus`, `num / di_dt`, and the guard factors
//!   `endpoint_worst * (1.0 + 1e-12)` / `* (1.0 - 1e-12)`.
//! - **B8:** default IEEE semantics; a denormal `L_eff` is pinned by the
//!   differential suite rather than flushed.
//!
//! B1–B4, B6, B9, B10 are not applicable: the kernel calls no libm
//! transcendental, rounds nothing, computes no distance, and returns no
//! repr strings.

use crate::hostmath::py_max;

#[cfg(feature = "python")]
use pyo3::prelude::*;

/// CPython's builtin `min(a, b)` — the first argument wins whenever the
/// comparison `b < a` is false, NaN included.
#[inline]
fn py_min(a: f64, b: f64) -> f64 {
    if b < a {
        b
    } else {
        a
    }
}

/// `_INTERIOR_GRID_POINTS` — the coupling grid `k = 0.00, 0.10, …, 1.00`.
pub const INTERIOR_GRID_POINTS: usize = 11;

/// Effective inductance at coupling coefficient `k`:
/// `L_eff(k) = L_coil·(1 − k) + L_leakage·k`.
///
/// # Soundness (R24 — Chebyshev-style conservative bound)
///
/// `L_eff` is affine in `k` with `L_eff(0) = L_coil > 0` and
/// `L_eff(1) = L_leakage > 0` (both enforced by
/// `_validate_config`).  An affine function on `[0, 1]` is bounded by
/// its endpoints, and it is strictly positive throughout because both
/// endpoints are, so:
///
/// * `di/dt(k) = V_bus / L_eff(k)` is monotone in `k` (`1/x` is monotone
///   on `x > 0`), hence `di/dt(k) ≤ max(di/dt(0), di/dt(1))` for all
///   `k ∈ [0, 1]`;
/// * `L_loop_max(k) = (V_BR·derate − V_bus) / (di/dt(k))` is monotone
///   for the same reason, hence
///   `L_loop_max(k) ≥ min(L_loop_max(0), L_loop_max(1))`;
/// * `P_device` and `T_j` do not depend on `k` at all.
///
/// The endpoint pair is therefore a **conservative bound** on every
/// interior coupling value: the gate never reports a `di/dt` lower, or
/// an `L_loop_max` higher, than some interior `k` actually achieves.
/// [`audit_bounding`] is the post-solve recompute of exactly this claim,
/// and `bmc_interior_bounding_holds` in the test module below is its
/// BMC-exhaustive validation on small `N`.
#[inline]
pub fn l_eff(l_coil: f64, l_leakage: f64, k: f64) -> f64 {
    l_coil * (1.0 - k) + l_leakage * k
}

/// The `k`-independent scalars `compute_extremes` derives once.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ThermalChain {
    /// `R_theta_jc + R_theta_cs + R_theta_sa` (K/W), left to right.
    pub r_th_total: f64,
    /// `V_BR * derate` (V).
    pub v_br_derated: f64,
    /// `T_amb + P_device * R_th_total` (°C).
    pub t_j: f64,
}

/// The `k`-dependent half of an `_ExtremePoint`.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct ExtremePoint {
    /// `V_bus / L_eff` (A/s).
    pub di_dt: f64,
    /// `(V_BR·derate − V_bus) / (di/dt)`, or `0.0` when the numerator is
    /// non-positive (H).
    pub l_loop_max: f64,
    /// `T_j ≤ T_j_max and L_loop_max ≥ min_feasible_L_loop`.
    pub feasible: bool,
}

/// `compute_extremes`'s `R_th_total` / `v_br_derated` / `T_j` block.
#[inline]
pub fn thermal_chain(
    p_device: f64,
    t_amb: f64,
    r_theta_jc: f64,
    r_theta_cs: f64,
    r_theta_sa: f64,
    v_br: f64,
    derate: f64,
) -> ThermalChain {
    // B7: Python's left-to-right `a + b + c`.
    let r_th_total = (r_theta_jc + r_theta_cs) + r_theta_sa;
    let v_br_derated = v_br * derate;
    // B7: the product is a single rounded op, then the add.
    let t_j = t_amb + p_device * r_th_total;
    ThermalChain { r_th_total, v_br_derated, t_j }
}

/// `compute_extremes`'s inner `_extreme` closure.
#[inline]
pub fn extreme_point(
    v_bus: f64,
    l_eff_value: f64,
    chain: ThermalChain,
    t_j_max: f64,
    min_feasible_l_loop: f64,
) -> ExtremePoint {
    let di_dt = v_bus / l_eff_value;
    let num = chain.v_br_derated - v_bus;
    // `0.0 if num <= 0 else num / di_dt_val` — a NaN numerator makes
    // `num <= 0` false in both languages, so NaN takes the division.
    let l_loop_max = if num <= 0.0 { 0.0 } else { num / di_dt };
    let feasible = chain.t_j <= t_j_max && l_loop_max >= min_feasible_l_loop;
    ExtremePoint { di_dt, l_loop_max, feasible }
}

/// The interior coupling grid the soundness check samples: `k = i/(N−1)`
/// for `i` in `1..N−1` (the endpoints are covered separately).
pub fn interior_k_grid(n_points: usize) -> Vec<f64> {
    if n_points < 2 {
        return Vec::new();
    }
    let div = (n_points - 1) as f64;
    (1..n_points - 1).map(|i| (i as f64) / div).collect()
}

/// One interior sample's verdict.
#[derive(Clone, Copy, Debug, PartialEq)]
pub struct InteriorSample {
    /// The coupling coefficient sampled.
    pub k: f64,
    /// `V_bus / L_eff(k)`.
    pub di_dt: f64,
    /// The interior `L_loop_max`.
    pub l_loop_max: f64,
    /// `l_loop_max < min_feasible_L_loop` — a ceiling the endpoints passed.
    pub breaches_min_feasible: bool,
    /// `di_dt > endpoint_worst_di_dt * (1 + 1e-12)`.
    pub worse_di_dt: bool,
    /// `l_loop_max < endpoint_worst_L_loop_max * (1 − 1e-12)`.
    pub worse_l_loop_max: bool,
}

/// The endpoint envelope plus every interior sample's verdict.
#[derive(Clone, Debug, Default, PartialEq)]
pub struct InteriorScan {
    /// `False` when an endpoint `L_eff` was non-positive — the reference
    /// returns no violations at all in that case.
    pub evaluated: bool,
    /// `max(di_dt(0), di_dt(1))` (CPython builtin `max`).
    pub endpoint_worst_di_dt: f64,
    /// `min(L_loop_max(0), L_loop_max(1))` (CPython builtin `min`).
    pub endpoint_worst_l_loop_max: f64,
    /// `L_loop_max` at `k = 0` — carried for the violation message.
    pub l_loop_max_k0: f64,
    /// `L_loop_max` at `k = 1` — carried for the violation message.
    pub l_loop_max_k1: f64,
    /// Samples whose `L_eff` was positive, in grid order.
    pub samples: Vec<InteriorSample>,
}

/// `_interior_bounding_soundness_check`'s arithmetic.
///
/// `samples` carries `(k, L_eff(k))` for the interior grid; Python
/// evaluates the coupling model (which may be the injected
/// `_coupling_l_eff_fn` test hook) so a deliberately non-monotone model
/// still reaches this scan.
pub fn interior_scan(
    v_bus: f64,
    v_br: f64,
    derate: f64,
    min_feasible_l_loop: f64,
    l_eff_k0: f64,
    l_eff_k1: f64,
    samples: &[(f64, f64)],
) -> InteriorScan {
    let v_br_derated = v_br * derate;
    let num = v_br_derated - v_bus;

    if l_eff_k0 <= 0.0 || l_eff_k1 <= 0.0 {
        return InteriorScan::default();
    }

    let di_dt_k0 = v_bus / l_eff_k0;
    let di_dt_k1 = v_bus / l_eff_k1;
    // B5: CPython's builtin max/min, first-argument-wins on NaN.
    let endpoint_worst_di_dt = py_max(di_dt_k0, di_dt_k1);

    let l_loop_max_k0 = if num > 0.0 { num / di_dt_k0 } else { 0.0 };
    let l_loop_max_k1 = if num > 0.0 { num / di_dt_k1 } else { 0.0 };
    let endpoint_worst_l_loop_max = py_min(l_loop_max_k0, l_loop_max_k1);

    let mut out = InteriorScan {
        evaluated: true,
        endpoint_worst_di_dt,
        endpoint_worst_l_loop_max,
        l_loop_max_k0,
        l_loop_max_k1,
        samples: Vec::with_capacity(samples.len()),
    };

    for &(k, l_eff_val) in samples {
        if l_eff_val <= 0.0 {
            continue;
        }
        let di_dt = v_bus / l_eff_val;
        let l_loop_max = if num > 0.0 { num / di_dt } else { 0.0 };
        out.samples.push(InteriorSample {
            k,
            di_dt,
            l_loop_max,
            breaches_min_feasible: l_loop_max < min_feasible_l_loop,
            worse_di_dt: di_dt > endpoint_worst_di_dt * (1.0 + 1e-12),
            worse_l_loop_max: l_loop_max < endpoint_worst_l_loop_max * (1.0 - 1e-12),
        });
    }
    out
}

// ---------------------------------------------------------------------------
// R24 post-solve audit
// ---------------------------------------------------------------------------

/// A recomputed-from-inputs disagreement with what the gate reported.
#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub enum AuditFinding {
    /// The reported `T_j` is not `T_amb + P·ΣR` recomputed from inputs.
    JunctionTemperatureMismatch,
    /// The reported `di/dt` at an endpoint is not `V_bus / L_eff`.
    SlewRateMismatch,
    /// The reported `L_loop_max` at an endpoint is not
    /// `(V_BR·derate − V_bus) / (di/dt)`.
    LoopInductanceCeilingMismatch,
    /// Some interior `k` achieves a *worse* `di/dt` than both endpoints
    /// — the endpoint-only bounding claim is unsound.
    InteriorSlewRateExceedsEnvelope,
    /// Some interior `k` achieves a *worse* `L_loop_max` than both
    /// endpoints.
    InteriorLoopCeilingBelowEnvelope,
    /// The reported feasibility flag disagrees with the recomputed one.
    FeasibilityMismatch,
}

/// R24 post-solve audit: recompute the gate's ceilings from the raw
/// configuration and re-derive the bounding claim on a dense interior
/// sweep.
///
/// This is the audit half of the R24 discipline for the operating-point
/// surface: nothing here reads the encoder's intermediate state, so a
/// drift between the encoded bound and the physical quantity surfaces as
/// a finding rather than a silent pass.
///
/// `interior_samples` is a dense `(k, L_eff(k))` sweep — pass the
/// production model for a soundness check, or an injected non-monotone
/// one to prove the audit is fail-capable.
#[allow(clippy::too_many_arguments, reason = "audits every reported quantity at once")]
pub fn audit_bounding(
    p_device: f64,
    t_amb: f64,
    r_theta_jc: f64,
    r_theta_cs: f64,
    r_theta_sa: f64,
    v_br: f64,
    derate: f64,
    v_bus: f64,
    t_j_max: f64,
    min_feasible_l_loop: f64,
    l_eff_k0: f64,
    l_eff_k1: f64,
    reported_t_j: f64,
    reported: [ExtremePoint; 2],
    interior_samples: &[(f64, f64)],
) -> Vec<AuditFinding> {
    let mut findings = Vec::new();
    let chain = thermal_chain(p_device, t_amb, r_theta_jc, r_theta_cs, r_theta_sa, v_br, derate);
    if chain.t_j != reported_t_j {
        findings.push(AuditFinding::JunctionTemperatureMismatch);
    }

    let recomputed = [
        extreme_point(v_bus, l_eff_k0, chain, t_j_max, min_feasible_l_loop),
        extreme_point(v_bus, l_eff_k1, chain, t_j_max, min_feasible_l_loop),
    ];
    for (got, want) in reported.iter().zip(recomputed.iter()) {
        if got.di_dt != want.di_dt {
            findings.push(AuditFinding::SlewRateMismatch);
        }
        if got.l_loop_max != want.l_loop_max {
            findings.push(AuditFinding::LoopInductanceCeilingMismatch);
        }
        if got.feasible != want.feasible {
            findings.push(AuditFinding::FeasibilityMismatch);
        }
    }

    let scan = interior_scan(
        v_bus,
        v_br,
        derate,
        min_feasible_l_loop,
        l_eff_k0,
        l_eff_k1,
        interior_samples,
    );
    if scan.evaluated {
        if scan.samples.iter().any(|s| s.worse_di_dt) {
            findings.push(AuditFinding::InteriorSlewRateExceedsEnvelope);
        }
        if scan.samples.iter().any(|s| s.worse_l_loop_max) {
            findings.push(AuditFinding::InteriorLoopCeilingBelowEnvelope);
        }
    }
    findings
}

// ---------------------------------------------------------------------------
// pyo3 bridge
// ---------------------------------------------------------------------------

/// pyo3 bridge for [`l_eff`].
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (l_coil, l_leakage, k))]
pub fn operating_point_l_eff_py(l_coil: f64, l_leakage: f64, k: f64) -> PyResult<f64> {
    temper_py_bridge::catch_unwind(|| l_eff(l_coil, l_leakage, k))
        .map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge for [`interior_k_grid`].
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (n_points))]
pub fn operating_point_interior_k_grid_py(n_points: usize) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| interior_k_grid(n_points))
        .map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge for [`thermal_chain`] + both [`extreme_point`]s.
///
/// Returns `(T_j, R_th_total, di_dt_k0, L_loop_max_k0, feasible_k0,
/// di_dt_k1, L_loop_max_k1, feasible_k1)`.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (
    p_device, t_amb, r_theta_jc, r_theta_cs, r_theta_sa, v_br, derate, v_bus,
    t_j_max, min_feasible_l_loop, l_coil, l_leakage
))]
#[allow(clippy::too_many_arguments, reason = "flat scalar boundary avoids a dict round-trip")]
#[allow(clippy::type_complexity, reason = "flat tuple mirrors the reference's two _ExtremePoints")]
pub fn operating_point_extremes_py(
    p_device: f64,
    t_amb: f64,
    r_theta_jc: f64,
    r_theta_cs: f64,
    r_theta_sa: f64,
    v_br: f64,
    derate: f64,
    v_bus: f64,
    t_j_max: f64,
    min_feasible_l_loop: f64,
    l_coil: f64,
    l_leakage: f64,
) -> PyResult<(f64, f64, f64, f64, bool, f64, f64, bool)> {
    temper_py_bridge::catch_unwind(|| {
        let chain = thermal_chain(p_device, t_amb, r_theta_jc, r_theta_cs, r_theta_sa, v_br, derate);
        let k0 = extreme_point(v_bus, l_coil, chain, t_j_max, min_feasible_l_loop);
        let k1 = extreme_point(v_bus, l_leakage, chain, t_j_max, min_feasible_l_loop);
        (
            chain.t_j,
            chain.r_th_total,
            k0.di_dt,
            k0.l_loop_max,
            k0.feasible,
            k1.di_dt,
            k1.l_loop_max,
            k1.feasible,
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge for [`interior_scan`].
///
/// Returns `(evaluated, endpoint_worst_di_dt, endpoint_worst_L_loop_max,
/// L_loop_max_k0, L_loop_max_k1, samples)` where each sample is
/// `(k, di_dt, L_loop_max, breaches_min_feasible, worse_di_dt,
/// worse_L_loop_max)`.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (
    v_bus, v_br, derate, min_feasible_l_loop, l_eff_k0, l_eff_k1, samples
))]
#[allow(clippy::too_many_arguments, reason = "flat scalar boundary avoids a dict round-trip")]
#[allow(clippy::type_complexity, reason = "flat tuple mirrors the reference's violation payloads")]
pub fn operating_point_interior_scan_py(
    v_bus: f64,
    v_br: f64,
    derate: f64,
    min_feasible_l_loop: f64,
    l_eff_k0: f64,
    l_eff_k1: f64,
    samples: Vec<(f64, f64)>,
) -> PyResult<(bool, f64, f64, f64, f64, Vec<(f64, f64, f64, bool, bool, bool)>)> {
    temper_py_bridge::catch_unwind(|| {
        let scan = interior_scan(
            v_bus,
            v_br,
            derate,
            min_feasible_l_loop,
            l_eff_k0,
            l_eff_k1,
            &samples,
        );
        (
            scan.evaluated,
            scan.endpoint_worst_di_dt,
            scan.endpoint_worst_l_loop_max,
            scan.l_loop_max_k0,
            scan.l_loop_max_k1,
            scan.samples
                .into_iter()
                .map(|s| {
                    (
                        s.k,
                        s.di_dt,
                        s.l_loop_max,
                        s.breaches_min_feasible,
                        s.worse_di_dt,
                        s.worse_l_loop_max,
                    )
                })
                .collect(),
        )
    })
    .map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge for [`audit_bounding`].  Returns the finding names.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (
    p_device, t_amb, r_theta_jc, r_theta_cs, r_theta_sa, v_br, derate, v_bus,
    t_j_max, min_feasible_l_loop, l_eff_k0, l_eff_k1, reported_t_j,
    reported_k0, reported_k1, interior_samples
))]
#[allow(clippy::too_many_arguments, reason = "audits every reported quantity at once")]
pub fn operating_point_audit_py(
    p_device: f64,
    t_amb: f64,
    r_theta_jc: f64,
    r_theta_cs: f64,
    r_theta_sa: f64,
    v_br: f64,
    derate: f64,
    v_bus: f64,
    t_j_max: f64,
    min_feasible_l_loop: f64,
    l_eff_k0: f64,
    l_eff_k1: f64,
    reported_t_j: f64,
    reported_k0: (f64, f64, bool),
    reported_k1: (f64, f64, bool),
    interior_samples: Vec<(f64, f64)>,
) -> PyResult<Vec<String>> {
    temper_py_bridge::catch_unwind(|| {
        let to_point = |(di_dt, l_loop_max, feasible): (f64, f64, bool)| ExtremePoint {
            di_dt,
            l_loop_max,
            feasible,
        };
        audit_bounding(
            p_device,
            t_amb,
            r_theta_jc,
            r_theta_cs,
            r_theta_sa,
            v_br,
            derate,
            v_bus,
            t_j_max,
            min_feasible_l_loop,
            l_eff_k0,
            l_eff_k1,
            reported_t_j,
            [to_point(reported_k0), to_point(reported_k1)],
            &interior_samples,
        )
        .into_iter()
        .map(|f| format!("{f:?}"))
        .collect()
    })
    .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    // See the note in `thermal_potential::tests`: the crate denies
    // unwrap/expect in production code, and a failing unwrap in a test
    // IS the test failure.  The lift is the generated outer
    // `#[allow(...)]` above; repeating it inner is a
    // `clippy::duplicated_attributes` error.

    use super::*;

    const V_BUS: f64 = 325.0;
    const V_BR: f64 = 1200.0;
    const DERATE: f64 = 0.80;
    const L_COIL: f64 = 100e-6;
    const L_LEAK: f64 = 10e-6;

// --- BEGIN generated by scripts/gen_oracle_freeze.py: operating_point ---
    /// Frozen golden vectors for operating_point numeric kernels
    /// (FREEZE, U4/U5, batch 3 -- retired physics/_operating_point_py_oracle.py).
    /// Regenerate: `python3 scripts/gen_oracle_freeze.py --spec operating_point`
    #[cfg(any(test, feature = "wasm-registry"))]
    #[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
    pub(crate) mod frozen_op_tests {
        use super::*;

        struct FrozenLeCase {
            l_coil: f64, l_leakage: f64, k: f64,
            expected: f64,
            tags: &'static [&'static str],
        }

        const FROZEN_LE_GOLDEN: &[FrozenLeCase] = &[
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F1A36E2EB1C432D_u64), l_leakage: f64::from_bits(0x3EE4F8B588E368F1_u64), k: f64::from_bits(0x0000000000000000_u64),
                expected: f64::from_bits(0x3F1A36E2EB1C432D_u64),
                tags: &["l_eff", "l_eff:k0", "named:k0"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F1A36E2EB1C432D_u64), l_leakage: f64::from_bits(0x3EE4F8B588E368F1_u64), k: f64::from_bits(0x3FF0000000000000_u64),
                expected: f64::from_bits(0x3EE4F8B588E368F1_u64),
                tags: &["l_eff", "l_eff:k1", "named:k1"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F1A36E2EB1C432D_u64), l_leakage: f64::from_bits(0x3EE4F8B588E368F1_u64), k: f64::from_bits(0x3FE0000000000000_u64),
                expected: f64::from_bits(0x3F0CD5F99C38B04B_u64),
                tags: &["l_eff", "l_eff:interior", "named:k_mid"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F0A36E2EB1C432D_u64), l_leakage: f64::from_bits(0x3F0A36E2EB1C432D_u64), k: f64::from_bits(0x3FE0000000000000_u64),
                expected: f64::from_bits(0x3F0A36E2EB1C432D_u64),
                tags: &["l_eff", "l_eff:equal", "l_eff:interior", "named:equal"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F1A36E2EB1C432D_u64), l_leakage: f64::from_bits(0x3EE4F8B588E368F1_u64), k: f64::from_bits(0x3FD5555555555555_u64),
                expected: f64::from_bits(0x3F12599ED7C6FBD4_u64),
                tags: &["l_eff", "l_eff:interior", "named:k_third"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F847AE147AE147B_u64), l_leakage: f64::from_bits(0x3E112E0BE826D695_u64), k: f64::from_bits(0x3FB999999999999A_u64),
                expected: f64::from_bits(0x3F826E9790BF7B37_u64),
                tags: &["l_eff", "l_eff:interior", "named:large"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3E112E0BE826D695_u64), l_leakage: f64::from_bits(0x3D719799812DEA11_u64), k: f64::from_bits(0x3FECCCCCCCCCCCCD_u64),
                expected: f64::from_bits(0x3DDBBC34CF426304_u64),
                tags: &["l_eff", "l_eff:interior", "named:tiny"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F7ED133E8F7855F_u64), l_leakage: f64::from_bits(0x3F79DC1735FF1DA6_u64), k: f64::from_bits(0x3FEFD2119277373B_u64),
                expected: f64::from_bits(0x3F79E334D65858A6_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F80AEE7B9B988DB_u64), l_leakage: f64::from_bits(0x3F7C79EC4EBDCD76_u64), k: f64::from_bits(0x3FC2736B37949148_u64),
                expected: f64::from_bits(0x3F8054AD55CB8FF6_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F5CABE0952AE56E_u64), l_leakage: f64::from_bits(0x3F7AABD17290929F_u64), k: f64::from_bits(0x3FD77356A68D9EB0_u64),
                expected: f64::from_bits(0x3F6CA0D856D81146_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F8416E32F5B05C4_u64), l_leakage: f64::from_bits(0x3F77F72CFA672607_u64), k: f64::from_bits(0x3FBB70232CD51B80_u64),
                expected: f64::from_bits(0x3F83387509DBFE48_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F82784D6D3ACB60_u64), l_leakage: f64::from_bits(0x3F7E83E6D96C8E54_u64), k: f64::from_bits(0x3FE3321DD5A73C3E_u64),
                expected: f64::from_bits(0x3F808B0011972C94_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F8213307A30EA25_u64), l_leakage: f64::from_bits(0x3F72532E91952ADD_u64), k: f64::from_bits(0x3FE595393E08DD70_u64),
                expected: f64::from_bits(0x3F7820A89E2F9A64_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F5C78F44DDA010F_u64), l_leakage: f64::from_bits(0x3F83AB2C8573B64E_u64), k: f64::from_bits(0x3FDDDB763E4250BC_u64),
                expected: f64::from_bits(0x3F7626254613AF96_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F7FB36D34A7A46A_u64), l_leakage: f64::from_bits(0x3F5AAC779DBB06DA_u64), k: f64::from_bits(0x3FE6E91D21734FF9_u64),
                expected: f64::from_bits(0x3F6B8EB6C8E73C58_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F7D7C702D716FD3_u64), l_leakage: f64::from_bits(0x3F618AAF2B804A0B_u64), k: f64::from_bits(0x3FE8F7B1046A20C4_u64),
                expected: f64::from_bits(0x3F6AA58BBC7BF2D0_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F7DFAD4BFDC7EC9_u64), l_leakage: f64::from_bits(0x3F4C602EB56A4203_u64), k: f64::from_bits(0x3FC6944DA75114AC_u64),
                expected: f64::from_bits(0x3F7951290754FA34_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F60A81AFD6BB907_u64), l_leakage: f64::from_bits(0x3F846A374E732A63_u64), k: f64::from_bits(0x3FE4B968B3C956CE_u64),
                expected: f64::from_bits(0x3F7D609ABAE0EFCF_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F748CB3CE0661CE_u64), l_leakage: f64::from_bits(0x3F4F58A8B99FFDC0_u64), k: f64::from_bits(0x3FEE4228AE24A324_u64),
                expected: f64::from_bits(0x3F534B321AFF5726_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F667E465440B096_u64), l_leakage: f64::from_bits(0x3F684DDF5D6D4A46_u64), k: f64::from_bits(0x3FBA9C74AC4F0C30_u64),
                expected: f64::from_bits(0x3F66AE7733BA3180_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F6D479E9882715B_u64), l_leakage: f64::from_bits(0x3F836DD4ED72840E_u64), k: f64::from_bits(0x3FD0F23ECDA60D7C_u64),
                expected: f64::from_bits(0x3F750D70E643002A_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F3BBD6A7B0ACD8A_u64), l_leakage: f64::from_bits(0x3F6CDF9FCDA49D71_u64), k: f64::from_bits(0x3FEF603CD87437B7_u64),
                expected: f64::from_bits(0x3F6C60C85FEDE3BB_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F676286FB54B1A7_u64), l_leakage: f64::from_bits(0x3F8373DED97C34E2_u64), k: f64::from_bits(0x3FEE4C478767D1F5_u64),
                expected: f64::from_bits(0x3F82BA9A22F3B2ED_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F2F7EF61C3E13B9_u64), l_leakage: f64::from_bits(0x3F6394CFC787465A_u64), k: f64::from_bits(0x3FDE973E975045E0_u64),
                expected: f64::from_bits(0x3F54C62FD90A59FA_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F1EC88BF8B11E9E_u64), l_leakage: f64::from_bits(0x3F5F72D15B5B1499_u64), k: f64::from_bits(0x3FEEA9B8BA257A19_u64),
                expected: f64::from_bits(0x3F5E370470F590DD_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F5F744DA96FF939_u64), l_leakage: f64::from_bits(0x3F61DE844EFA1DB0_u64), k: f64::from_bits(0x3FE36AB09EA723CD_u64),
                expected: f64::from_bits(0x3F6106E29D951972_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F69FC889C0E9EE5_u64), l_leakage: f64::from_bits(0x3F3F7EF7372B6FC7_u64), k: f64::from_bits(0x3FE6C2774A302488_u64),
                expected: f64::from_bits(0x3F549BA9F0E4EA77_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F810E27EBE592ED_u64), l_leakage: f64::from_bits(0x3F8241D629C9DD85_u64), k: f64::from_bits(0x3FEBC6B78F861145_u64),
                expected: f64::from_bits(0x3F8219399B2D9410_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F67B92D328F35FD_u64), l_leakage: f64::from_bits(0x3F7AE91E35B633D9_u64), k: f64::from_bits(0x3FC7412FED76CCD8_u64),
                expected: f64::from_bits(0x3F6D3101ED8BC194_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F68E8DCFD3DD4F5_u64), l_leakage: f64::from_bits(0x3F4B0FB725FFFD0C_u64), k: f64::from_bits(0x3FD984B7A7F63C9A_u64),
                expected: f64::from_bits(0x3F61ACCF4E72CEAF_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F7F11544B4804D5_u64), l_leakage: f64::from_bits(0x3F7DEB728B4225C2_u64), k: f64::from_bits(0x3FC91237D33DC350_u64),
                expected: f64::from_bits(0x3F7ED7C45FDBDDFD_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F768E74F4E4A450_u64), l_leakage: f64::from_bits(0x3F6AC12144FC1629_u64), k: f64::from_bits(0x3FED058FB277D075_u64),
                expected: f64::from_bits(0x3F6C768B4C89A961_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F79FC81EF04ABB6_u64), l_leakage: f64::from_bits(0x3F7EEB1C9AC68BE4_u64), k: f64::from_bits(0x3FC0EFD54FAAEAC0_u64),
                expected: f64::from_bits(0x3F7AA3930168D6F4_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F70FBED475332D3_u64), l_leakage: f64::from_bits(0x3F4C0EC88A25E556_u64), k: f64::from_bits(0x3FE503CD64C89DC3_u64),
                expected: f64::from_bits(0x3F60446C22E25A11_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F7E94B45FCBD42C_u64), l_leakage: f64::from_bits(0x3F5C7A1DA6701819_u64), k: f64::from_bits(0x3FD8713D663D4E4C_u64),
                expected: f64::from_bits(0x3F759EE059F98ED1_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F6E73C087DFB783_u64), l_leakage: f64::from_bits(0x3F7801F3F7797DAD_u64), k: f64::from_bits(0x3FE212EA525D9E91_u64),
                expected: f64::from_bits(0x3F742F9C31ACB898_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F722A7199286778_u64), l_leakage: f64::from_bits(0x3F83AADB7F221DAC_u64), k: f64::from_bits(0x3FED2E78E88DF272_u64),
                expected: f64::from_bits(0x3F82BC3356536867_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F2D576B962A2F17_u64), l_leakage: f64::from_bits(0x3F6C30CFB5F3ABFB_u64), k: f64::from_bits(0x3FD85D5B20136676_u64),
                expected: f64::from_bits(0x3F57BC54B9007407_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F40EB39A1DA1F17_u64), l_leakage: f64::from_bits(0x3F6FE37D6CF43782_u64), k: f64::from_bits(0x3FE6BAE12A01D9E6_u64),
                expected: f64::from_bits(0x3F67E04DD334A20A_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F6722E70DC00B4C_u64), l_leakage: f64::from_bits(0x3F731B6CBBEE42A1_u64), k: f64::from_bits(0x3FD7731BC0ED6644_u64),
                expected: f64::from_bits(0x3F6CA9308D56FC44_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F436CCA8EA090C2_u64), l_leakage: f64::from_bits(0x3F78AC0D8FE29CD0_u64), k: f64::from_bits(0x3FDD19E5B09BC236_u64),
                expected: f64::from_bits(0x3F6915CC70696E34_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F7BDE84495BC984_u64), l_leakage: f64::from_bits(0x3F60049465FE2849_u64), k: f64::from_bits(0x3FDB550623D39BD8_u64),
                expected: f64::from_bits(0x3F73633963036D96_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F4967E335101C86_u64), l_leakage: f64::from_bits(0x3F7AB757EC9C02B2_u64), k: f64::from_bits(0x3FDA7DC3AEF1488C_u64),
                expected: f64::from_bits(0x3F69D6E79372086D_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F7AFFC1DE532E94_u64), l_leakage: f64::from_bits(0x3F76A4B055B35630_u64), k: f64::from_bits(0x3FD7AB190F992960_u64),
                expected: f64::from_bits(0x3F79636289BE13B8_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F6E0B7BC9910B0C_u64), l_leakage: f64::from_bits(0x3F784C69ABAC5BE7_u64), k: f64::from_bits(0x3FEA816087EB3EE8_u64),
                expected: f64::from_bits(0x3F76B4AA564514C2_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F7E51AEF35104D9_u64), l_leakage: f64::from_bits(0x3F72F1D60DF444B0_u64), k: f64::from_bits(0x3FE16D06F1528416_u64),
                expected: f64::from_bits(0x3F782002C6EAA1C5_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F714DA3941A61FA_u64), l_leakage: f64::from_bits(0x3F7657E10D316A00_u64), k: f64::from_bits(0x3FDA75B0053EE506_u64),
                expected: f64::from_bits(0x3F736311223FE919_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F609B556BC44271_u64), l_leakage: f64::from_bits(0x3F814662742E0EB0_u64), k: f64::from_bits(0x3FCA1B0A8E614F7C_u64),
                expected: f64::from_bits(0x3F6B500F03931E97_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F8297D212639E4E_u64), l_leakage: f64::from_bits(0x3F3FD612F907F767_u64), k: f64::from_bits(0x3FC4646FF2F07490_u64),
                expected: f64::from_bits(0x3F7F942BA1C3E6C2_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F7B431C60FD83E6_u64), l_leakage: f64::from_bits(0x3F729CBA1C5F01D0_u64), k: f64::from_bits(0x3FD06AF740FD3374_u64),
                expected: f64::from_bits(0x3F790B0ED2286110_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F674380BF1E0398_u64), l_leakage: f64::from_bits(0x3F80553FFDE7BDE8_u64), k: f64::from_bits(0x3FDF4D7B7747082C_u64),
                expected: f64::from_bits(0x3F75EB7449CA176F_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F8398F7550E2E5C_u64), l_leakage: f64::from_bits(0x3F6F24E64120AFD0_u64), k: f64::from_bits(0x3FD48BBCF0FDC1D0_u64),
                expected: f64::from_bits(0x3F7F9C83F16341CF_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F82082B633E867A_u64), l_leakage: f64::from_bits(0x3F6F5C2334827636_u64), k: f64::from_bits(0x3FE53A704D27C2D9_u64),
                expected: f64::from_bits(0x3F768A9FBAFDB9AB_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F5EB36487EA2CB1_u64), l_leakage: f64::from_bits(0x3F606F2F131856FD_u64), k: f64::from_bits(0x3FE0AB03DC7DC842_u64),
                expected: f64::from_bits(0x3F5FD4773FEA967F_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F843B0F28BA821B_u64), l_leakage: f64::from_bits(0x3F67526540A5D19D_u64), k: f64::from_bits(0x3FD69269B6898FAE_u64),
                expected: f64::from_bits(0x3F7E4DCA408DE0CF_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F705BE7160A1DAE_u64), l_leakage: f64::from_bits(0x3F6FA1B1B49E2513_u64), k: f64::from_bits(0x3FCFB9168959F71C_u64),
                expected: f64::from_bits(0x3F7039709084D369_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
            FrozenLeCase {
                l_coil: f64::from_bits(0x3F668C4B2ADA2165_u64), l_leakage: f64::from_bits(0x3F763DF81F46045B_u64), k: f64::from_bits(0x3FD415D797746954_u64),
                expected: f64::from_bits(0x3F6D6EAB48240E28_u64),
                tags: &["l_eff", "l_eff:interior"],
            },
        ];

        struct FrozenTcCase {
            p_device: f64, t_amb: f64,
            r_theta_jc: f64, r_theta_cs: f64, r_theta_sa: f64,
            v_br: f64, derate: f64,
            expected: (f64, f64, f64),
            tags: &'static [&'static str],
        }

        const FROZEN_TC_GOLDEN: &[FrozenTcCase] = &[
            FrozenTcCase {
                p_device: f64::from_bits(0x4030000000000000_u64), t_amb: f64::from_bits(0x4044000000000000_u64),
                r_theta_jc: f64::from_bits(0x3FE3333333333333_u64), r_theta_cs: f64::from_bits(0x3FD0000000000000_u64), r_theta_sa: f64::from_bits(0x3FF0000000000000_u64),
                v_br: f64::from_bits(0x4092C00000000000_u64), derate: f64::from_bits(0x3FE999999999999A_u64),
                expected: (f64::from_bits(0x3FFD99999999999A_u64), f64::from_bits(0x408E000000000000_u64), f64::from_bits(0x4051666666666666_u64)),
                tags: &["named:prod", "thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x0000000000000000_u64), t_amb: f64::from_bits(0x4044000000000000_u64),
                r_theta_jc: f64::from_bits(0x3FE3333333333333_u64), r_theta_cs: f64::from_bits(0x3FD0000000000000_u64), r_theta_sa: f64::from_bits(0x3FF0000000000000_u64),
                v_br: f64::from_bits(0x4092C00000000000_u64), derate: f64::from_bits(0x3FE999999999999A_u64),
                expected: (f64::from_bits(0x3FFD99999999999A_u64), f64::from_bits(0x408E000000000000_u64), f64::from_bits(0x4044000000000000_u64)),
                tags: &["named:zero_power", "thermal:zero_power", "thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x4030000000000000_u64), t_amb: f64::from_bits(0x4039000000000000_u64),
                r_theta_jc: f64::from_bits(0x3FE0000000000000_u64), r_theta_cs: f64::from_bits(0x3FC999999999999A_u64), r_theta_sa: f64::from_bits(0x3FE999999999999A_u64),
                v_br: f64::from_bits(0x4082C00000000000_u64), derate: f64::from_bits(0x3FF0000000000000_u64),
                expected: (f64::from_bits(0x3FF8000000000000_u64), f64::from_bits(0x4082C00000000000_u64), f64::from_bits(0x4048800000000000_u64)),
                tags: &["named:full_derate", "thermal:full_derate", "thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x4024000000000000_u64), t_amb: f64::from_bits(0xC044000000000000_u64),
                r_theta_jc: f64::from_bits(0x3FD3333333333333_u64), r_theta_cs: f64::from_bits(0x3FB999999999999A_u64), r_theta_sa: f64::from_bits(0x3FE0000000000000_u64),
                v_br: f64::from_bits(0x4092C00000000000_u64), derate: f64::from_bits(0x3FE6666666666666_u64),
                expected: (f64::from_bits(0x3FECCCCCCCCCCCCD_u64), f64::from_bits(0x408A400000000000_u64), f64::from_bits(0xC03F000000000000_u64)),
                tags: &["named:neg_amb", "thermal:negative_amb", "thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x4059000000000000_u64), t_amb: f64::from_bits(0x4055400000000000_u64),
                r_theta_jc: f64::from_bits(0x3FB999999999999A_u64), r_theta_cs: f64::from_bits(0x3FA999999999999A_u64), r_theta_sa: f64::from_bits(0x3FC999999999999A_u64),
                v_br: f64::from_bits(0x409A900000000000_u64), derate: f64::from_bits(0x3FE0000000000000_u64),
                expected: (f64::from_bits(0x3FD6666666666667_u64), f64::from_bits(0x408A900000000000_u64), f64::from_bits(0x405E000000000000_u64)),
                tags: &["named:high_power", "thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x402A3CF2EC56B634_u64), t_amb: f64::from_bits(0xC040E388A272BD8C_u64),
                r_theta_jc: f64::from_bits(0x3FD7478FE6A286A3_u64), r_theta_cs: f64::from_bits(0x3FE9FDB28740B018_u64), r_theta_sa: f64::from_bits(0x401B7EF173171277_u64),
                v_br: f64::from_bits(0x4098C044459D3DCB_u64), derate: f64::from_bits(0x3FEC318C723C8454_u64),
                expected: (f64::from_bits(0x402019906134A872_u64), f64::from_bits(0x4095CE8EC6FAA17A_u64), f64::from_bits(0x4051F51A9AA0C900_u64)),
                tags: &["thermal:negative_amb", "thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x405669C51C51A052_u64), t_amb: f64::from_bits(0xC0043125DFC0E420_u64),
                r_theta_jc: f64::from_bits(0x3FF2BA4BFCE55A0F_u64), r_theta_cs: f64::from_bits(0x3FE768A1E1120C83_u64), r_theta_sa: f64::from_bits(0x40134D208C9ECA69_u64),
                v_br: f64::from_bits(0x406E4FBFB02C622D_u64), derate: f64::from_bits(0x3FE74092C644C4D9_u64),
                expected: (f64::from_bits(0x401AE8C7C7FA627D_u64), f64::from_bits(0x4066067C4DA9691F_u64), f64::from_bits(0x4082C4C9C402CA5C_u64)),
                tags: &["thermal:negative_amb", "thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x40497E21B9501795_u64), t_amb: f64::from_bits(0x4025C9A75904E35C_u64),
                r_theta_jc: f64::from_bits(0x3FFF259E18555F8F_u64), r_theta_cs: f64::from_bits(0x3FFEB095CC807107_u64), r_theta_sa: f64::from_bits(0x4023702C07BB50B2_u64),
                v_br: f64::from_bits(0x40918F293A70263F_u64), derate: f64::from_bits(0x3FCD1FBA4610BA0E_u64),
                expected: (f64::from_bits(0x402B2AF284560AC5_u64), f64::from_bits(0x406FF64C86F075AD_u64), f64::from_bits(0x4085FBC9D14EC0AB_u64)),
                tags: &["thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x40554CC8F507A0F0_u64), t_amb: f64::from_bits(0x40523DB780FD693D_u64),
                r_theta_jc: f64::from_bits(0x3FF5E6DCA32D5DD3_u64), r_theta_cs: f64::from_bits(0x3FDFDD3F31B285C0_u64), r_theta_sa: f64::from_bits(0x3FF79F3FD0E12F46_u64),
                v_br: f64::from_bits(0x409A2160BFE433AC_u64), derate: f64::from_bits(0x3FE552AE7D25936C_u64),
                expected: (f64::from_bits(0x400ABEB6203D9744_u64), f64::from_bits(0x4091696B81889EFD_u64), f64::from_bits(0x40765CC24AB123FD_u64)),
                tags: &["thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x405030CD2C1DB393_u64), t_amb: f64::from_bits(0xC040BA35965C73DF_u64),
                r_theta_jc: f64::from_bits(0x3FF775DB354E0C40_u64), r_theta_cs: f64::from_bits(0x3FF2367C2681123D_u64), r_theta_sa: f64::from_bits(0x401692409BB27779_u64),
                v_br: f64::from_bits(0x40974DFFDEC8C741_u64), derate: f64::from_bits(0x3FE665C811CBDEF6_u64),
                expected: (f64::from_bits(0x40207EAB39531F8C_u64), f64::from_bits(0x40904FBFCD364C36_u64), f64::from_bits(0x407F4AAECC0C2B74_u64)),
                tags: &["thermal:negative_amb", "thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x404E974858858552_u64), t_amb: f64::from_bits(0x40444121DF1B413C_u64),
                r_theta_jc: f64::from_bits(0x4001B9361E4B7FCD_u64), r_theta_cs: f64::from_bits(0x3FEAE733C3B15C5A_u64), r_theta_sa: f64::from_bits(0x40134646CBC6C9FD_u64),
                v_br: f64::from_bits(0x4092938553261605_u64), derate: f64::from_bits(0x3FEE64CF4F166A9D_u64),
                expected: (f64::from_bits(0x401F7FC85362B56F_u64), f64::from_bits(0x4091A4D256C731FD_u64), f64::from_bits(0x4080526D1CFF7E70_u64)),
                tags: &["thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x403CEB9DBA001FF9_u64), t_amb: f64::from_bits(0x40491DDB503BBBC0_u64),
                r_theta_jc: f64::from_bits(0x3FFDBD2CC4E90E06_u64), r_theta_cs: f64::from_bits(0x3FF6BB4F7D2F57B5_u64), r_theta_sa: f64::from_bits(0x3FBCEF13E31795A8_u64),
                v_br: f64::from_bits(0x40975B1D451D81D8_u64), derate: f64::from_bits(0x3FDA5B80B53BCB68_u64),
                expected: (f64::from_bits(0x400B23B6C024EF8B_u64), f64::from_bits(0x40833CD0D4209BE2_u64), f64::from_bits(0x40628B00CDA4C764_u64)),
                tags: &["thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x4048B42C0624C59E_u64), t_amb: f64::from_bits(0xC000F1E7B1D0CC40_u64),
                r_theta_jc: f64::from_bits(0x40042EFDA9C5B60E_u64), r_theta_cs: f64::from_bits(0x3FE4192CB00B6680_u64), r_theta_sa: f64::from_bits(0x40216E56377C6FCB_u64),
                v_br: f64::from_bits(0x40840A6034EF4C2F_u64), derate: f64::from_bits(0x3FEA9A335BE5D3ED_u64),
                expected: (f64::from_bits(0x4027BBA86CEE93B6_u64), f64::from_bits(0x4080A9004417F272_u64), f64::from_bits(0x4082416CA3FBE706_u64)),
                tags: &["thermal:negative_amb", "thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x4049ABDA11CFABB8_u64), t_amb: f64::from_bits(0xC0219F106A6B7844_u64),
                r_theta_jc: f64::from_bits(0x4004F8A214EC437A_u64), r_theta_cs: f64::from_bits(0x3FF2D29503A5EFEB_u64), r_theta_sa: f64::from_bits(0x4021A88F082B7A0C_u64),
                v_br: f64::from_bits(0x406D894F522D88F8_u64), derate: f64::from_bits(0x3FC165305E9418CC_u64),
                expected: (f64::from_bits(0x4029410A2DDB48E8_u64), f64::from_bits(0x40400E582B4696B4_u64), f64::from_bits(0x4083FBF359B278EF_u64)),
                tags: &["thermal:negative_amb", "thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x401A78A17534E06A_u64), t_amb: f64::from_bits(0x404665E700D3327E_u64),
                r_theta_jc: f64::from_bits(0x3FC0E3F34A5E0216_u64), r_theta_cs: f64::from_bits(0x3FFA3A5C29D91242_u64), r_theta_sa: f64::from_bits(0x3FD12B3D009C8FEE_u64),
                v_br: f64::from_bits(0x405049F52B0B669B_u64), derate: f64::from_bits(0x3FC042DE58AB5389_u64),
                expected: (f64::from_bits(0x400050D4E9A5FB40_u64), f64::from_bits(0x40208E089ACBDAC5_u64), f64::from_bits(0x404D257E382D93AB_u64)),
                tags: &["thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x40161CE48D9E7447_u64), t_amb: f64::from_bits(0xC039AA9003D354F4_u64),
                r_theta_jc: f64::from_bits(0x400218F1EF98B22E_u64), r_theta_cs: f64::from_bits(0x3FEF4C616F153793_u64), r_theta_sa: f64::from_bits(0x40216E281A494625_u64),
                v_br: f64::from_bits(0x409A46E2550067FF_u64), derate: f64::from_bits(0x3FD2F0DE31212BA7_u64),
                expected: (f64::from_bits(0x4027E92AAD20C62A_u64), f64::from_bits(0x407F1B52CACF6584_u64), f64::from_bits(0x40443680451616CE_u64)),
                tags: &["thermal:negative_amb", "thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x404EA161A2D13923_u64), t_amb: f64::from_bits(0x405057936BA28A18_u64),
                r_theta_jc: f64::from_bits(0x3FDC6942EAE4C53D_u64), r_theta_cs: f64::from_bits(0x3FC1A0AA437996CD_u64), r_theta_sa: f64::from_bits(0x3FF981B0EDC9FA20_u64),
                v_br: f64::from_bits(0x40836C77022CF879_u64), derate: f64::from_bits(0x3FC6C1C4DBAA79F4_u64),
                expected: (f64::from_bits(0x4001680B78792F24_u64), f64::from_bits(0x405BA05EF9E5802D_u64), f64::from_bits(0x4068D51D0C6C50D3_u64)),
                tags: &["thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x40534FCF843E8215_u64), t_amb: f64::from_bits(0xBFD7D68FAA345400_u64),
                r_theta_jc: f64::from_bits(0x4003405BC9D3C839_u64), r_theta_cs: f64::from_bits(0x3FD29D27C07ADBD0_u64), r_theta_sa: f64::from_bits(0x401168C86BC15178_u64),
                v_br: f64::from_bits(0x4081FA1620A6539A_u64), derate: f64::from_bits(0x3FEE096131AEADB9_u64),
                expected: (f64::from_bits(0x401C32C8CCB2E352_u64), f64::from_bits(0x4080DFB9AED14372_u64), f64::from_bits(0x40810180A459C786_u64)),
                tags: &["thermal:negative_amb", "thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x4057F8D90C8D2917_u64), t_amb: f64::from_bits(0xC018B7939104E608_u64),
                r_theta_jc: f64::from_bits(0x3FE218A3257C4412_u64), r_theta_cs: f64::from_bits(0x3FE9C8F13BBC377D_u64), r_theta_sa: f64::from_bits(0x40212784F46DD8DB_u64),
                v_br: f64::from_bits(0x409A26C719FD86BD_u64), derate: f64::from_bits(0x3FD9B97A5D3BA714_u64),
                expected: (f64::from_bits(0x4023E59E3A816094_u64), f64::from_bits(0x408505DFBB64D8BB_u64), f64::from_bits(0x408D9E194B508124_u64)),
                tags: &["thermal:negative_amb", "thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x4041B982F02655D3_u64), t_amb: f64::from_bits(0x405131AB0A67A1E2_u64),
                r_theta_jc: f64::from_bits(0x4002B14E2B614AD2_u64), r_theta_cs: f64::from_bits(0x3FE98B4E0E5F2C45_u64), r_theta_sa: f64::from_bits(0x40129522525BF44D_u64),
                v_br: f64::from_bits(0x40589118B36FA6D4_u64), derate: f64::from_bits(0x3FEDCEEE006869B7_u64),
                expected: (f64::from_bits(0x401F1F3329D87F3E_u64), f64::from_bits(0x4056E25B29182D39_u64), f64::from_bits(0x40758969A8EDF9F0_u64)),
                tags: &["thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x4058810A4CFE0BB5_u64), t_amb: f64::from_bits(0xC0404145A4670923_u64),
                r_theta_jc: f64::from_bits(0x3FF63C3EAAE0BFCE_u64), r_theta_cs: f64::from_bits(0x3FEE5A91544CDB6F_u64), r_theta_sa: f64::from_bits(0x40204A86A538A062_u64),
                v_br: f64::from_bits(0x409108B8CDDCFCA7_u64), derate: f64::from_bits(0x3FDEA902F1C60DD2_u64),
                expected: (f64::from_bits(0x4024F7B78FD98613_u64), f64::from_bits(0x40805224E23D0DF2_u64), f64::from_bits(0x408F1899B52FF000_u64)),
                tags: &["thermal:negative_amb", "thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x40388E0C549E501F_u64), t_amb: f64::from_bits(0x4049D8F1D602D4FC_u64),
                r_theta_jc: f64::from_bits(0x3FDACB9BFB7818D7_u64), r_theta_cs: f64::from_bits(0x3FEFF2AEC52F251A_u64), r_theta_sa: f64::from_bits(0x4005D8665EC8C896_u64),
                v_br: f64::from_bits(0x409977FA1B86EB74_u64), derate: f64::from_bits(0x3FEAFC8E72AE4F8B_u64),
                expected: (f64::from_bits(0x40109742C7C1CA7C_u64), f64::from_bits(0x40957A7D67A266A4_u64), f64::from_bits(0x406331542840A7A8_u64)),
                tags: &["thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x40565180D0AB3707_u64), t_amb: f64::from_bits(0x40522D4EF49A7FDF_u64),
                r_theta_jc: f64::from_bits(0x3FFDDC6BF89653AC_u64), r_theta_cs: f64::from_bits(0x3FE5ED7783F37225_u64), r_theta_sa: f64::from_bits(0x3FFD85182BABA200_u64),
                v_br: f64::from_bits(0x4076164472857967_u64), derate: f64::from_bits(0x3FE226D340DC25EE_u64),
                expected: (f64::from_bits(0x4011960FF98EEBB0_u64), f64::from_bits(0x40690EA58295C428_u64), f64::from_bits(0x407D133EFB0553FD_u64)),
                tags: &["thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x4054B7A98EA3E3DF_u64), t_amb: f64::from_bits(0x4033305CA17E1054_u64),
                r_theta_jc: f64::from_bits(0x3FF4C898A67737C6_u64), r_theta_cs: f64::from_bits(0x3FF7887AD27352D9_u64), r_theta_sa: f64::from_bits(0x40184467C87F40FD_u64),
                v_br: f64::from_bits(0x4071B3BA78C4784D_u64), derate: f64::from_bits(0x3FC2A411E006C8E0_u64),
                expected: (f64::from_bits(0x4021AC56535CF1D2_u64), f64::from_bits(0x40449FB7C604B9B8_u64), f64::from_bits(0x40877BCD3277EBE4_u64)),
                tags: &["thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x405125A6FB4D9ECF_u64), t_amb: f64::from_bits(0xC02336E90DB6A9FE_u64),
                r_theta_jc: f64::from_bits(0x3FDC0E4630467E17_u64), r_theta_cs: f64::from_bits(0x3FE9991D0BED0B53_u64), r_theta_sa: f64::from_bits(0x400A9454DCF08D24_u64),
                v_br: f64::from_bits(0x4093B7073DD5E4D6_u64), derate: f64::from_bits(0x3FDB1F26A49B5618_u64),
                expected: (f64::from_bits(0x40123E3272FA4FDE_u64), f64::from_bits(0x4080B59F39F2B26B_u64), f64::from_bits(0x4072F34C8A39C31A_u64)),
                tags: &["thermal:negative_amb", "thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x4050A2E9989E0E58_u64), t_amb: f64::from_bits(0xBFE339F62E4FEB00_u64),
                r_theta_jc: f64::from_bits(0x3FE2D7FB09A1A6DD_u64), r_theta_cs: f64::from_bits(0x3FFCC0C0DD7A12BA_u64), r_theta_sa: f64::from_bits(0x3FF94BEDD356FE7E_u64),
                v_br: f64::from_bits(0x40792748266E7970_u64), derate: f64::from_bits(0x3FD0A77173A3F341_u64),
                expected: (f64::from_bits(0x400FBC561AD0F253_u64), f64::from_bits(0x405A2E8482B93F1E_u64), f64::from_bits(0x4070761F30E75F62_u64)),
                tags: &["thermal:negative_amb", "thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x404764A4B8238E46_u64), t_amb: f64::from_bits(0x40439138319A4276_u64),
                r_theta_jc: f64::from_bits(0x3FD30C001278E5DC_u64), r_theta_cs: f64::from_bits(0x3FDFFD13D977A084_u64), r_theta_sa: f64::from_bits(0x4010B5432B56CB13_u64),
                v_br: f64::from_bits(0x409813597DFCBCD2_u64), derate: f64::from_bits(0x3FE615E9DEDD02D5_u64),
                expected: (f64::from_bits(0x4013E5D46A15D379_u64), f64::from_bits(0x40909DCA2DE891A2_u64), f64::from_bits(0x4070FDEC569EBD6C_u64)),
                tags: &["thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x4050A92C9A0DF6B2_u64), t_amb: f64::from_bits(0xC01408C4117997B8_u64),
                r_theta_jc: f64::from_bits(0x40057D0509393E5F_u64), r_theta_cs: f64::from_bits(0x3FFFE5F2623459A5_u64), r_theta_sa: f64::from_bits(0x40136EBB58B0F6C1_u64),
                v_br: f64::from_bits(0x40901C6B61A9AD96_u64), derate: f64::from_bits(0x3FED38C942681511_u64),
                expected: (f64::from_bits(0x4023135D3AED562D_u64), f64::from_bits(0x408D6CB0C0BC6046_u64), f64::from_bits(0x4083B4FD6874371A_u64)),
                tags: &["thermal:negative_amb", "thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x401C9F3118FE6C25_u64), t_amb: f64::from_bits(0x4050863A873EF7FD_u64),
                r_theta_jc: f64::from_bits(0x3FFE081E1F24A600_u64), r_theta_cs: f64::from_bits(0x3FEA212149B31BC7_u64), r_theta_sa: f64::from_bits(0x400577B86F45D356_u64),
                v_br: f64::from_bits(0x409066E928D3B0B0_u64), derate: f64::from_bits(0x3FCC8B7A62E6B318_u64),
                expected: (f64::from_bits(0x40158207E8A276A4_u64), f64::from_bits(0x406D43138719CE9B_u64), f64::from_bits(0x405A249D88A050FE_u64)),
                tags: &["thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x4047DE7279779B4F_u64), t_amb: f64::from_bits(0x3FE46CA9CBE2A780_u64),
                r_theta_jc: f64::from_bits(0x400057AEC0C749D3_u64), r_theta_cs: f64::from_bits(0x3FED0FC9B40EBCB1_u64), r_theta_sa: f64::from_bits(0x401789A1B914D1D1_u64),
                v_br: f64::from_bits(0x40840AA553B40805_u64), derate: f64::from_bits(0x3FEDF02673ED5AD5_u64),
                expected: (f64::from_bits(0x4021ABB927FD2728_u64), f64::from_bits(0x4082C00DC10E2AC7_u64), f64::from_bits(0x407A66BD951AAFFF_u64)),
                tags: &["thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x4051ABD76217B78A_u64), t_amb: f64::from_bits(0x4046EDEC63562FF8_u64),
                r_theta_jc: f64::from_bits(0x3FF603310AF3CBC4_u64), r_theta_cs: f64::from_bits(0x3FB417D8EECD4AFF_u64), r_theta_sa: f64::from_bits(0x4001C5BBBED0731C_u64),
                v_br: f64::from_bits(0x4042F9BB5EB5D5E3_u64), derate: f64::from_bits(0x3FEAD3EE302D6D18_u64),
                expected: (f64::from_bits(0x400D68130BC0C356_u64), f64::from_bits(0x403FD1284CBEAC33_u64), f64::from_bits(0x40731AF1BDD4789B_u64)),
                tags: &["thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x40406DDF25B15CB9_u64), t_amb: f64::from_bits(0xC03C98091C1D88FA_u64),
                r_theta_jc: f64::from_bits(0x3FDAD15344FE1210_u64), r_theta_cs: f64::from_bits(0x3FFD65B35850D9AB_u64), r_theta_sa: f64::from_bits(0x401779C4AA2AC46D_u64),
                v_br: f64::from_bits(0x4089B0D0DE059A58_u64), derate: f64::from_bits(0x3FE6E0654A7DE7A7_u64),
                expected: (f64::from_bits(0x402040235A476DFC_u64), f64::from_bits(0x40825DB6A09735C2_u64), f64::from_bits(0x406DCC74BB239783_u64)),
                tags: &["thermal:negative_amb", "thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x405250860B69B81D_u64), t_amb: f64::from_bits(0x4033A9AC66A4A924_u64),
                r_theta_jc: f64::from_bits(0x400775E3570F9B18_u64), r_theta_cs: f64::from_bits(0x3FFD9B412E11AE07_u64), r_theta_sa: f64::from_bits(0x401F57D48A55F8AB_u64),
                v_br: f64::from_bits(0x40989D68ABE1BA2E_u64), derate: f64::from_bits(0x3FD9B9CA51822B73_u64),
                expected: (f64::from_bits(0x40293CCB40B118DC_u64), f64::from_bits(0x4083C9E36BC15949_u64), f64::from_bits(0x408D80B57366A1A3_u64)),
                tags: &["thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x40561C126C793308_u64), t_amb: f64::from_bits(0x402E751E566089CC_u64),
                r_theta_jc: f64::from_bits(0x40003C830B3399C5_u64), r_theta_cs: f64::from_bits(0x3FFC778991BB6A1C_u64), r_theta_sa: f64::from_bits(0x40094F285B3F5D8D_u64),
                v_br: f64::from_bits(0x409A35C3AA5A83CE_u64), derate: f64::from_bits(0x3FD6AAEF14F71644_u64),
                expected: (f64::from_bits(0x401BE3B817A85630_u64), f64::from_bits(0x408290F7F7509753_u64), f64::from_bits(0x4083BEDA5953ACDC_u64)),
                tags: &["thermal_chain"],
            },
            FrozenTcCase {
                p_device: f64::from_bits(0x3FF5F18CFCE34B36_u64), t_amb: f64::from_bits(0x403067E88CB3F79E_u64),
                r_theta_jc: f64::from_bits(0x3FCCCADA0B78132E_u64), r_theta_cs: f64::from_bits(0x3FE667391DF708F5_u64), r_theta_sa: f64::from_bits(0x400A4075857A1EBB_u64),
                v_br: f64::from_bits(0x40947C2A05B6CDCB_u64), derate: f64::from_bits(0x3FE94E05C96D6E4A_u64),
                expected: (f64::from_bits(0x4010D378B6D7B116_u64), f64::from_bits(0x409032F32F3D44BE_u64), f64::from_bits(0x40362CCD8C57BF0E_u64)),
                tags: &["thermal_chain"],
            },
        ];

        struct FrozenEpCase {
            v_bus: f64, l_eff_value: f64,
            chain: ThermalChain,
            t_j_max: f64, min_feasible_l_loop: f64,
            expected: ExtremePoint,
            tags: &'static [&'static str],
        }

        const FROZEN_EP_GOLDEN: &[FrozenEpCase] = &[
            FrozenEpCase {
                v_bus: f64::from_bits(0x4074500000000000_u64), l_eff_value: f64::from_bits(0x3F1A36E2EB1C432D_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x3FFD99999999999A_u64), v_br_derated: f64::from_bits(0x408E000000000000_u64), t_j: f64::from_bits(0x4051666666666666_u64) },
                t_j_max: f64::from_bits(0x4062C00000000000_u64), min_feasible_l_loop: f64::from_bits(0x3E35798EE2308C3A_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x4148CBA800000000_u64), l_loop_max: f64::from_bits(0x3F299C051102029C_u64), feasible: true },
                tags: &["extreme:feasible", "extreme_point", "named:feasible"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x4074500000000000_u64), l_eff_value: f64::from_bits(0x3EE4F8B588E368F1_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x3FFD99999999999A_u64), v_br_derated: f64::from_bits(0x408E000000000000_u64), t_j: f64::from_bits(0x4051666666666666_u64) },
                t_j_max: f64::from_bits(0x4062C00000000000_u64), min_feasible_l_loop: f64::from_bits(0x3E35798EE2308C3A_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x417EFE91FFFFFFFF_u64), l_loop_max: f64::from_bits(0x3EF47CD0DA680217_u64), feasible: true },
                tags: &["extreme:feasible", "extreme_point", "named:infeasible"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x4092C00000000000_u64), l_eff_value: f64::from_bits(0x3F1A36E2EB1C432D_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x3FFD99999999999A_u64), v_br_derated: f64::from_bits(0x408E000000000000_u64), t_j: f64::from_bits(0x4051666666666666_u64) },
                t_j_max: f64::from_bits(0x4062C00000000000_u64), min_feasible_l_loop: f64::from_bits(0x3E35798EE2308C3A_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x4166E36000000000_u64), l_loop_max: f64::from_bits(0x0000000000000000_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme:no_headroom", "extreme:zero_loop", "extreme_point", "named:no_headroom"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x4074500000000000_u64), l_eff_value: f64::from_bits(0x3F1A36E2EB1C432D_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x3FFD99999999999A_u64), v_br_derated: f64::from_bits(0x408E000000000000_u64), t_j: f64::from_bits(0x4039000000000000_u64) },
                t_j_max: f64::from_bits(0x4062C00000000000_u64), min_feasible_l_loop: f64::from_bits(0x3E35798EE2308C3A_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x4148CBA800000000_u64), l_loop_max: f64::from_bits(0x3F299C051102029C_u64), feasible: true },
                tags: &["extreme:feasible", "extreme_point", "named:zero_power"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x4077DCBCE6B43D84_u64), l_eff_value: f64::from_bits(0x3F7A4F03E608E9CF_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x401C1BE9F4729F4C_u64), v_br_derated: f64::from_bits(0x40815C7F24B2ED4B_u64), t_j: f64::from_bits(0x407ACE5272434ECE_u64) },
                t_j_max: f64::from_bits(0x40664D7212318F47_u64), min_feasible_l_loop: f64::from_bits(0x3E72B4259CF683D7_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x40ED063D7D233546_u64), l_loop_max: f64::from_bits(0x3F67F29543AC359F_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x4077A95A9967F43D_u64), l_eff_value: f64::from_bits(0x3F628EC9AF894A01_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x401DF7C639538FD0_u64), v_br_derated: f64::from_bits(0x407C0FD9980FF033_u64), t_j: f64::from_bits(0x407EF62DCCAF3C25_u64) },
                t_j_max: f64::from_bits(0x4057AED1440EC2BF_u64), min_feasible_l_loop: f64::from_bits(0x3EA84A121B60FE29_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x4104667C57A036CE_u64), l_loop_max: f64::from_bits(0x3F3B9C183B11D3FA_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x4079068BEBB7AA8E_u64), l_eff_value: f64::from_bits(0x3F66E212130384F6_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x4013667F161482AF_u64), v_br_derated: f64::from_bits(0x404401CE04BF1E98_u64), t_j: f64::from_bits(0x406A21FBBA33A86E_u64) },
                t_j_max: f64::from_bits(0x4067B4B0405173DE_u64), min_feasible_l_loop: f64::from_bits(0x3E78FE8FD706C883_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x41017F7F73CCA0E6_u64), l_loop_max: f64::from_bits(0x0000000000000000_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme:no_headroom", "extreme:zero_loop", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x407CD426232BDC9D_u64), l_eff_value: f64::from_bits(0x3F7B1C7123BDA7D3_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x4011BB0AA5F2B00B_u64), v_br_derated: f64::from_bits(0x40943AE4593E970C_u64), t_j: f64::from_bits(0x4078D3EEF75749E4_u64) },
                t_j_max: f64::from_bits(0x40689158BC80B320_u64), min_feasible_l_loop: f64::from_bits(0x3E84CE0A9A9C7D57_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x40F1037FD3695C48_u64), l_loop_max: f64::from_bits(0x3F887E730B4A7870_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x4088A7F34F438D7B_u64), l_eff_value: f64::from_bits(0x3F48C747C94F96EB_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x4020B86691ADEA71_u64), v_br_derated: f64::from_bits(0x408B86E2610B8F0D_u64), t_j: f64::from_bits(0x4080F6993E0403A9_u64) },
                t_j_max: f64::from_bits(0x405DE041906A2F1C_u64), min_feasible_l_loop: f64::from_bits(0x3EA407918A9AE9D5_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x412FD789FE1AD272_u64), l_loop_max: f64::from_bits(0x3F1714A77D2408F6_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x407C031F3916BC14_u64), l_eff_value: f64::from_bits(0x3F824423D5899912_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x40258247D3ACDB95_u64), v_br_derated: f64::from_bits(0x407198FA9E661FAD_u64), t_j: f64::from_bits(0x4075724DBAFF9F3C_u64) },
                t_j_max: f64::from_bits(0x405EC0C86E53A29A_u64), min_feasible_l_loop: f64::from_bits(0x3E91A5796E982C54_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x40E88971E45E7833_u64), l_loop_max: f64::from_bits(0x0000000000000000_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme:no_headroom", "extreme:zero_loop", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x40648F362EF62DC2_u64), l_eff_value: f64::from_bits(0x3F4D53242DFB684B_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x401878B4498F16D6_u64), v_br_derated: f64::from_bits(0x408137115A73D7A1_u64), t_j: f64::from_bits(0x4061117A38D3A4EC_u64) },
                t_j_max: f64::from_bits(0x4063623561DCC694_u64), min_feasible_l_loop: f64::from_bits(0x3E994D2CA530F8FF_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x41066F5CA8F184CA_u64), l_loop_max: f64::from_bits(0x3F613933A8EAF74F_u64), feasible: true },
                tags: &["extreme:feasible", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x408032DCB53E8EF5_u64), l_eff_value: f64::from_bits(0x3F7ED3DD1945F8C3_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x401FBEF448B549A7_u64), v_br_derated: f64::from_bits(0x4048F7D864EFEE95_u64), t_j: f64::from_bits(0x407F508582E88194_u64) },
                t_j_max: f64::from_bits(0x406595D2E20FEBFE_u64), min_feasible_l_loop: f64::from_bits(0x3E957BCE2DB90222_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x40F0D09268AC49D1_u64), l_loop_max: f64::from_bits(0x0000000000000000_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme:no_headroom", "extreme:zero_loop", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x405F2A2413CCEEB5_u64), l_eff_value: f64::from_bits(0x3F33B20053845A74_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x401017942C0115D8_u64), v_br_derated: f64::from_bits(0x40922763E32E98E8_u64), t_j: f64::from_bits(0x407A2F106421E4F8_u64) },
                t_j_max: f64::from_bits(0x4063912B9948AF5A_u64), min_feasible_l_loop: f64::from_bits(0x3EAAB366C4396F6F_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x4119513FB839B337_u64), l_loop_max: f64::from_bits(0x3F647BD63FDDDB71_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x40734D3EBEBBC01B_u64), l_eff_value: f64::from_bits(0x3F71E51539AE038D_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x40228E3BE60D251A_u64), v_br_derated: f64::from_bits(0x40840C7350BE1E08_u64), t_j: f64::from_bits(0x407F1A7E70F5126A_u64) },
                t_j_max: f64::from_bits(0x4057DA58C387ABC4_u64), min_feasible_l_loop: f64::from_bits(0x3E622CBA9DEAE0E5_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x40F1420676031DDE_u64), l_loop_max: f64::from_bits(0x3F73479EBEEE8059_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x407BBCE200B14DED_u64), l_eff_value: f64::from_bits(0x3F71108E3436AB9D_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x4022EF19CB8CB4A6_u64), v_br_derated: f64::from_bits(0x408F1C8B17E56AB1_u64), t_j: f64::from_bits(0x407920D76FDCD310_u64) },
                t_j_max: f64::from_bits(0x4055F77A3D54217F_u64), min_feasible_l_loop: f64::from_bits(0x3EA87EE99CF375EC_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x40FA01DB4B575E1A_u64), l_loop_max: f64::from_bits(0x3F753739D108D9A3_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x40577426E9944647_u64), l_eff_value: f64::from_bits(0x3F80BFD7A19F4FAC_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x40151F385118A0F2_u64), v_br_derated: f64::from_bits(0x406C41DDAA45453E_u64), t_j: f64::from_bits(0x4079154205489B52_u64) },
                t_j_max: f64::from_bits(0x405D43814B70B02E_u64), min_feasible_l_loop: f64::from_bits(0x3E594A992B0CC216_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x40C66785322EA67C_u64), l_loop_max: f64::from_bits(0x3F879C3BB88F0897_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x4087438CA25A023F_u64), l_eff_value: f64::from_bits(0x3F83F14880CDE86D_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x40121D78C8F9DDEE_u64), v_br_derated: f64::from_bits(0x40593812333F7895_u64), t_j: f64::from_bits(0x406A224B45714BCF_u64) },
                t_j_max: f64::from_bits(0x4066CF7401512122_u64), min_feasible_l_loop: f64::from_bits(0x3EA82384978133D1_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x40F2AA2C799B6DF4_u64), l_loop_max: f64::from_bits(0x0000000000000000_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme:no_headroom", "extreme:zero_loop", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x4080A9BC776E372A_u64), l_eff_value: f64::from_bits(0x3F83BB33C9DFD30D_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x4018677D80249790_u64), v_br_derated: f64::from_bits(0x408727C70E3B5EDB_u64), t_j: f64::from_bits(0x4083ED3DB7D307FA_u64) },
                t_j_max: f64::from_bits(0x406443D127259857_u64), min_feasible_l_loop: f64::from_bits(0x3E3E0AD506D08926_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x40EB062324B61267_u64), l_loop_max: f64::from_bits(0x3F6EC05136EF9B24_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x40658720F9C141A4_u64), l_eff_value: f64::from_bits(0x3F469F32BC03237F_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x402288C7D3E73251_u64), v_br_derated: f64::from_bits(0x4074DEA0949762EC_u64), t_j: f64::from_bits(0x4087C8D70E0FABE0_u64) },
                t_j_max: f64::from_bits(0x405A85A5D9A9ED64_u64), min_feasible_l_loop: f64::from_bits(0x3E921D5A5316EC04_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x410E73D32F52754A_u64), l_loop_max: f64::from_bits(0x3F453D11A86A0D27_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x4087B9440F9AB4EF_u64), l_eff_value: f64::from_bits(0x3F7318CF2577F83A_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x4022C7AAA6590F8B_u64), v_br_derated: f64::from_bits(0x4083455318B2CEA1_u64), t_j: f64::from_bits(0x4076C5A67382655F_u64) },
                t_j_max: f64::from_bits(0x405A93AA431557C6_u64), min_feasible_l_loop: f64::from_bits(0x3EAF29C7EF56B5E6_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x4103E060235C9BD5_u64), l_loop_max: f64::from_bits(0x0000000000000000_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme:no_headroom", "extreme:zero_loop", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x404EEBFD2E2018F4_u64), l_eff_value: f64::from_bits(0x3F71B1E8A9991ACB_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x40168B6A03A0FE64_u64), v_br_derated: f64::from_bits(0x4022E9FA457D06F4_u64), t_j: f64::from_bits(0x406944E864FD1DA7_u64) },
                t_j_max: f64::from_bits(0x406451AEF6D27ADA_u64), min_feasible_l_loop: f64::from_bits(0x3EAD2B2A4FA7A33A_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x40CBF5BC609EB666_u64), l_loop_max: f64::from_bits(0x0000000000000000_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme:no_headroom", "extreme:zero_loop", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x40600E96710F7216_u64), l_eff_value: f64::from_bits(0x3F6D6E5E994C5B39_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x40261309E47E57A2_u64), v_br_derated: f64::from_bits(0x405F12C32F751A07_u64), t_j: f64::from_bits(0x40848CC8DFCF927F_u64) },
                t_j_max: f64::from_bits(0x405A4DEB617394D2_u64), min_feasible_l_loop: f64::from_bits(0x3EA6AFCF44067D89_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x40E17560628BCDF5_u64), l_loop_max: f64::from_bits(0x0000000000000000_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme:no_headroom", "extreme:zero_loop", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x407618FDB209EA52_u64), l_eff_value: f64::from_bits(0x3F6570DD1B2E8DC4_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x402156F8C4F649D2_u64), v_br_derated: f64::from_bits(0x40810D2780BCA05E_u64), t_j: f64::from_bits(0x40774D2072E28E3F_u64) },
                t_j_max: f64::from_bits(0x405A2AD5D9AB83C5_u64), min_feasible_l_loop: f64::from_bits(0x3E8203B520771C72_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x41007D7688A1EFC3_u64), l_loop_max: f64::from_bits(0x3F574BF4A09A6D2F_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x407552DE93556C3C_u64), l_eff_value: f64::from_bits(0x3F6137FEED08B772_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x4009BAACA46F8063_u64), v_br_derated: f64::from_bits(0x40632BD83D00B1F0_u64), t_j: f64::from_bits(0x40713277DCF0FC8B_u64) },
                t_j_max: f64::from_bits(0x4059304F6DFBB65F_u64), min_feasible_l_loop: f64::from_bits(0x3E98383F7E0718E0_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x4103D07E4945537E_u64), l_loop_max: f64::from_bits(0x0000000000000000_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme:no_headroom", "extreme:zero_loop", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x407C6DFDA8F1F418_u64), l_eff_value: f64::from_bits(0x3F4F7DF43280BCD9_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x4022354E39F2E8EB_u64), v_br_derated: f64::from_bits(0x4077B0E3DC163C04_u64), t_j: f64::from_bits(0x407E30E35D3B9320_u64) },
                t_j_max: f64::from_bits(0x40617C7403D9A9C2_u64), min_feasible_l_loop: f64::from_bits(0x3EAA248EC36A6D38_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x411CE364173E65DD_u64), l_loop_max: f64::from_bits(0x0000000000000000_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme:no_headroom", "extreme:zero_loop", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x4075F403160EBFCD_u64), l_eff_value: f64::from_bits(0x3F7C0D1978DE1BE7_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x4019272D9704DBD9_u64), v_br_derated: f64::from_bits(0x40829B37D80C9648_u64), t_j: f64::from_bits(0x406E0FE14B724BB8_u64) },
                t_j_max: f64::from_bits(0x406114C9C5A59B4D_u64), min_feasible_l_loop: f64::from_bits(0x3E96992101A727D7_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x40E90B2790C622FC_u64), l_loop_max: f64::from_bits(0x3F737F85F6383DA3_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x4088298A41F1F7D5_u64), l_eff_value: f64::from_bits(0x3F7482F3A60C17AF_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x4009C8205C6E72EF_u64), v_br_derated: f64::from_bits(0x408ADAB7E717A9D1_u64), t_j: f64::from_bits(0x403B6B99112D068A_u64) },
                t_j_max: f64::from_bits(0x405B8B184A6F5028_u64), min_feasible_l_loop: f64::from_bits(0x3E903BDFF28714A4_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x4102D906557475E4_u64), l_loop_max: f64::from_bits(0x3F424863AE9E7582_u64), feasible: true },
                tags: &["extreme:feasible", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x4064F6E040E352A0_u64), l_eff_value: f64::from_bits(0x3F7A2A4D42156930_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x402152F2DD5F02FD_u64), v_br_derated: f64::from_bits(0x40914AB0A2CA9C2E_u64), t_j: f64::from_bits(0x4086B99739BFF6FE_u64) },
                t_j_max: f64::from_bits(0x40592BDFE9B3E778_u64), min_feasible_l_loop: f64::from_bits(0x3EAF537E901E0345_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x40D9A3ABBBF2122F_u64), l_loop_max: f64::from_bits(0x3FA24F95B259D72E_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x407B3FFE95F3311D_u64), l_eff_value: f64::from_bits(0x3F8198177EEA8AB2_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x401CD21D3FAE0E31_u64), v_br_derated: f64::from_bits(0x4095957564FDC785_u64), t_j: f64::from_bits(0x40728C3D595533E2_u64) },
                t_j_max: f64::from_bits(0x405A39FB0C3ED8F7_u64), min_feasible_l_loop: f64::from_bits(0x3EA799820B1DC6F4_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x40E8C7EFCEDDA0D8_u64), l_loop_max: f64::from_bits(0x3F93130B2B571DFC_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x4080B92F8855F7C3_u64), l_eff_value: f64::from_bits(0x3F829D5092555DAD_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x401C4ABC3C837097_u64), v_br_derated: f64::from_bits(0x40798B8F30A23F3D_u64), t_j: f64::from_bits(0x4066CB689D84CBE8_u64) },
                t_j_max: f64::from_bits(0x4065D51007BDC64E_u64), min_feasible_l_loop: f64::from_bits(0x3E9E51D41150368E_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x40ECBFBD33FD220C_u64), l_loop_max: f64::from_bits(0x0000000000000000_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme:no_headroom", "extreme:zero_loop", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x4085822D225CA78B_u64), l_eff_value: f64::from_bits(0x3F6D7ED67BFD9536_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x4021327D5D547B48_u64), v_br_derated: f64::from_bits(0x407828AB3109AB15_u64), t_j: f64::from_bits(0x4083B54F8AA89C9A_u64) },
                t_j_max: f64::from_bits(0x4065CD67AD803584_u64), min_feasible_l_loop: f64::from_bits(0x3E91FDD5BD9DB2E7_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x410755B8803D31F6_u64), l_loop_max: f64::from_bits(0x0000000000000000_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme:no_headroom", "extreme:zero_loop", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x407B7CB10867A98F_u64), l_eff_value: f64::from_bits(0x3F83F6009B527DFA_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x401B1BF2FAC4B576_u64), v_br_derated: f64::from_bits(0x405ABACB66A2DDD5_u64), t_j: f64::from_bits(0x407804C71B6D990F_u64) },
                t_j_max: f64::from_bits(0x4065DFD5289EECE0_u64), min_feasible_l_loop: f64::from_bits(0x3EAF8AC100FC532D_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x40E6085DF0FC80C5_u64), l_loop_max: f64::from_bits(0x0000000000000000_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme:no_headroom", "extreme:zero_loop", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x406F4367C0248A41_u64), l_eff_value: f64::from_bits(0x3F7737F21473CEBD_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x400CB1B90514BFCB_u64), v_br_derated: f64::from_bits(0x40956BBDF38EBDB9_u64), t_j: f64::from_bits(0x4076525B221F7D7F_u64) },
                t_j_max: f64::from_bits(0x406190DF14D9E5B5_u64), min_feasible_l_loop: f64::from_bits(0x3E634D5CFB31C639_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x40E58B2EDAB65A7D_u64), l_loop_max: f64::from_bits(0x3F9A03500234FC6D_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme_point"],
            },
            FrozenEpCase {
                v_bus: f64::from_bits(0x4054899FFE08A3D1_u64), l_eff_value: f64::from_bits(0x3F824B39A5A45879_u64),
                chain: ThermalChain { r_th_total: f64::from_bits(0x40029F30738F83DE_u64), v_br_derated: f64::from_bits(0x40833EAAD8E5AB7C_u64), t_j: f64::from_bits(0x406EB10BA238A998_u64) },
                t_j_max: f64::from_bits(0x405E0E452D53F0D0_u64), min_feasible_l_loop: f64::from_bits(0x3E78ACC16C905270_u64),
                expected: ExtremePoint { di_dt: f64::from_bits(0x40C1F66057C7B97D_u64), l_loop_max: f64::from_bits(0x3FADB60B2C72D350_u64), feasible: false },
                tags: &["extreme:infeasible", "extreme_point"],
            },
        ];

        const FROZEN_GRID_N: usize = 11;
        const FROZEN_GRID_EXPECTED: &[(f64)] = &[f64::from_bits(0x3FB999999999999A_u64), f64::from_bits(0x3FC999999999999A_u64), f64::from_bits(0x3FD3333333333333_u64), f64::from_bits(0x3FD999999999999A_u64), f64::from_bits(0x3FE0000000000000_u64), f64::from_bits(0x3FE3333333333333_u64), f64::from_bits(0x3FE6666666666666_u64), f64::from_bits(0x3FE999999999999A_u64), f64::from_bits(0x3FECCCCCCCCCCCCD_u64)];

        #[cfg_attr(test, test)]
        fn frozen_l_eff_matches_golden_corpus() {
            for case in FROZEN_LE_GOLDEN {
                let got = l_eff(case.l_coil, case.l_leakage, case.k);
                assert_eq!(got, case.expected, "tags={:?}", case.tags);
            }
        }

        #[cfg_attr(test, test)]
        fn frozen_thermal_chain_matches_golden_corpus() {
            for case in FROZEN_TC_GOLDEN {
                let got = thermal_chain(case.p_device, case.t_amb,
                    case.r_theta_jc, case.r_theta_cs, case.r_theta_sa,
                    case.v_br, case.derate);
                assert_eq!(got, ThermalChain { r_th_total: case.expected.0, v_br_derated: case.expected.1, t_j: case.expected.2 }, "tags={:?}", case.tags);
            }
        }

        #[cfg_attr(test, test)]
        fn frozen_extreme_point_matches_golden_corpus() {
            for case in FROZEN_EP_GOLDEN {
                let got = extreme_point(case.v_bus, case.l_eff_value,
                    case.chain, case.t_j_max, case.min_feasible_l_loop);
                assert_eq!(got, case.expected, "tags={:?}", case.tags);
            }
        }

        #[cfg_attr(test, test)]
        fn frozen_interior_k_grid_matches() {
            let got = interior_k_grid(FROZEN_GRID_N);
            assert_eq!(got.as_slice(), FROZEN_GRID_EXPECTED);
        }

        #[cfg_attr(test, test)]
        fn frozen_op_corpus_is_non_vacuous() {
            let le_n = FROZEN_LE_GOLDEN.len() as u32;
            let tc_n = FROZEN_TC_GOLDEN.len() as u32;
            let ep_n = FROZEN_EP_GOLDEN.len() as u32;
        let le_count = |t: &str| FROZEN_LE_GOLDEN.iter().filter(|c| c.tags.contains(&t)).count() as u32;
        let tc_count = |t: &str| FROZEN_TC_GOLDEN.iter().filter(|c| c.tags.contains(&t)).count() as u32;
        let ep_count = |t: &str| FROZEN_EP_GOLDEN.iter().filter(|c| c.tags.contains(&t)).count() as u32;
        let grid_present = FROZEN_GRID_N == 11;
            assert!(le_count("l_eff") >= 30, "l_eff: only {}/{} (need >= 30)", le_count("l_eff"), le_n);
            assert!(le_count("l_eff:k0") >= 1, "l_eff:k0: only {}/{} (need >= 1)", le_count("l_eff:k0"), le_n);
            assert!(le_count("l_eff:k1") >= 1, "l_eff:k1: only {}/{} (need >= 1)", le_count("l_eff:k1"), le_n);
            assert!(le_count("l_eff:interior") >= 20, "l_eff:interior: only {}/{} (need >= 20)", le_count("l_eff:interior"), le_n);
            assert!(tc_count("thermal_chain") >= 20, "thermal_chain: only {}/{} (need >= 20)", tc_count("thermal_chain"), tc_n);
            assert!(ep_count("extreme_point") >= 20, "extreme_point: only {}/{} (need >= 20)", ep_count("extreme_point"), ep_n);
            assert!(ep_count("extreme:feasible") >= 3, "extreme:feasible: only {}/{} (need >= 3)", ep_count("extreme:feasible"), ep_n);
            assert!(ep_count("extreme:infeasible") >= 3, "extreme:infeasible: only {}/{} (need >= 3)", ep_count("extreme:infeasible"), ep_n);
            assert!(ep_count("extreme:zero_loop") >= 1, "extreme:zero_loop: only {}/{} (need >= 1)", ep_count("extreme:zero_loop"), ep_n);
            assert!(grid_present, "interior_k_grid: not present");
        }

        // --- BEGIN generated by scripts/gen_wasm_test_registry.py: frozen_op_tests ---
        /// Every `#[test]` in this module, as a callable the `wasm32`
        /// entry point can invoke by index.  Generated because these
        /// functions are private to this module and unreachable from
        /// anywhere a registry could otherwise live.
        pub const WASM_TESTS: &[(&str, fn())] = &[
            ("operating_point::frozen_op_tests::frozen_l_eff_matches_golden_corpus", frozen_l_eff_matches_golden_corpus),
            ("operating_point::frozen_op_tests::frozen_thermal_chain_matches_golden_corpus", frozen_thermal_chain_matches_golden_corpus),
            ("operating_point::frozen_op_tests::frozen_extreme_point_matches_golden_corpus", frozen_extreme_point_matches_golden_corpus),
            ("operating_point::frozen_op_tests::frozen_interior_k_grid_matches", frozen_interior_k_grid_matches),
            ("operating_point::frozen_op_tests::frozen_op_corpus_is_non_vacuous", frozen_op_corpus_is_non_vacuous),
        ];
        // --- END generated by scripts/gen_wasm_test_registry.py: frozen_op_tests ---
    }
// --- END generated by scripts/gen_oracle_freeze.py: operating_point ---

    #[cfg_attr(test, test)]
    fn l_eff_hits_the_endpoints_exactly() {
        assert_eq!(l_eff(L_COIL, L_LEAK, 0.0), L_COIL);
        assert_eq!(l_eff(L_COIL, L_LEAK, 1.0), L_LEAK);
    }

    #[cfg_attr(test, test)]
    fn thermal_chain_matches_the_hand_computation() {
        // R = (0.6 + 0.25) + 1.0 = 1.85; T_j = 40 + 20*1.85 = 77.0
        let chain = thermal_chain(20.0, 40.0, 0.6, 0.25, 1.0, V_BR, DERATE);
        assert_eq!(chain.r_th_total, 1.85);
        assert_eq!(chain.t_j, 77.0);
        assert_eq!(chain.v_br_derated, 960.0);
    }

    #[cfg_attr(test, test)]
    fn extreme_point_zero_numerator_yields_zero_ceiling() {
        // V_BR*derate <= V_bus -> num <= 0 -> L_loop_max is exactly 0.0
        let chain = thermal_chain(1.0, 40.0, 0.6, 0.25, 1.0, 300.0, 1.0);
        let p = extreme_point(400.0, L_COIL, chain, 150.0, 5e-9);
        assert_eq!(p.l_loop_max, 0.0);
        assert!(!p.feasible);
    }

    #[cfg_attr(test, test)]
    fn feasibility_is_inclusive_at_the_exact_floor() {
        // Mutation M15 in the migration PR flipped `l_loop_max >=
        // min_feasible_L_loop` to `>`.  That is only observable when the
        // two are EXACTLY equal, which a randomised sweep will never hit
        // — so pin the equality directly.  V_bus=100, V_BR=200,
        // derate=1.0, L=1e-6 gives L_loop_max exactly 1e-6.
        let chain = thermal_chain(1.0, 40.0, 0.6, 0.25, 1.0, 200.0, 1.0);
        let p = extreme_point(100.0, 1e-6, chain, 150.0, 1e-6);
        assert_eq!(p.l_loop_max, 1e-6, "fixture is not discriminating");
        assert!(
            p.feasible,
            "a ceiling met exactly must count as met; `>` would reject it"
        );
    }

    #[cfg_attr(test, test)]
    fn zero_headroom_branch_choice_is_unobservable() {
        // Mutation M16 (`num <= 0.0` -> `num < 0.0`) survived the
        // differential.  Not a test gap: the two branches differ only at
        // `num == 0.0`, where the taken branch computes `0.0 / di_dt`
        // with `di_dt` finite and positive (V_bus > 0 and L_eff > 0 are
        // both enforced by `_validate_config`) — which is exactly +0.0,
        // the same value the literal branch returns.  Proven here.
        let chain = thermal_chain(1.0, 40.0, 0.6, 0.25, 1.0, 100.0, 1.0);
        assert_eq!(chain.v_br_derated, 100.0);
        for l in [1e-9, 1e-6, 1e-3, 1.0, 1e9] {
            let di_dt = 100.0 / l;
            let literal = 0.0_f64;
            let divided = 0.0_f64 / di_dt;
            assert_eq!(
                literal.to_bits(),
                divided.to_bits(),
                "the zero-headroom branches diverged at L={l}"
            );
            assert_eq!(extreme_point(100.0, l, chain, 150.0, 0.0).l_loop_max, 0.0);
        }
    }

    #[cfg_attr(test, test)]
    fn interior_k_grid_excludes_the_endpoints() {
        let ks = interior_k_grid(INTERIOR_GRID_POINTS);
        assert_eq!(ks.len(), INTERIOR_GRID_POINTS - 2);
        assert_eq!(ks[0], 0.1);
        assert_eq!(ks[ks.len() - 1], 0.9);
        assert!(interior_k_grid(1).is_empty());
        assert!(interior_k_grid(0).is_empty());
    }

    #[cfg_attr(test, test)]
    fn interior_scan_is_silent_for_the_monotone_model() {
        let samples: Vec<(f64, f64)> = interior_k_grid(INTERIOR_GRID_POINTS)
            .into_iter()
            .map(|k| (k, l_eff(L_COIL, L_LEAK, k)))
            .collect();
        let scan = interior_scan(V_BUS, V_BR, DERATE, 5e-9, L_COIL, L_LEAK, &samples);
        assert!(scan.evaluated);
        assert!(scan.samples.iter().all(|s| !s.worse_di_dt));
        assert!(scan.samples.iter().all(|s| !s.worse_l_loop_max));
    }

    #[cfg_attr(test, test)]
    fn interior_scan_returns_nothing_for_a_non_positive_endpoint() {
        let scan = interior_scan(V_BUS, V_BR, DERATE, 5e-9, 0.0, L_LEAK, &[(0.5, 1e-5)]);
        assert!(!scan.evaluated);
        assert!(scan.samples.is_empty());
    }

    #[cfg_attr(test, test)]
    fn interior_scan_catches_a_non_monotone_model() {
        // A model that dips BELOW both endpoints in the interior gives a
        // higher di/dt than either endpoint -> unsound bounding.
        let samples = vec![(0.5, L_LEAK / 10.0)];
        let scan = interior_scan(V_BUS, V_BR, DERATE, 5e-9, L_COIL, L_LEAK, &samples);
        assert!(scan.evaluated);
        assert!(scan.samples[0].worse_di_dt);
        assert!(scan.samples[0].worse_l_loop_max);
    }

    /// **R24 / BMC-exhaustive validation on small N.**
    ///
    /// The soundness claim on [`l_eff`] is that the two endpoints bound
    /// every interior coupling value.  Enumerate an exhaustive lattice of
    /// configurations (both coupling orderings, degenerate `L_coil ==
    /// L_leakage`, several bus/breakdown ratios) crossed with an
    /// exhaustive `k` sweep at 1/1024 resolution, and assert the bound
    /// holds on every one — no sampling, no tolerance.
    #[cfg_attr(test, test)]
    fn bmc_interior_bounding_holds_exhaustively() {
        let inductances = [1e-9, 1e-6, 10e-6, 100e-6, 1e-3];
        let buses = [10.0, 325.0, 600.0];
        let breakdowns = [100.0, 600.0, 1200.0];
        let mut checked = 0_u64;
        for &l_coil in &inductances {
            for &l_leak in &inductances {
                for &v_bus in &buses {
                    for &v_br in &breakdowns {
                        let samples: Vec<(f64, f64)> = (1..1024)
                            .map(|i| {
                                let k = f64::from(i) / 1024.0;
                                (k, l_eff(l_coil, l_leak, k))
                            })
                            .collect();
                        let scan =
                            interior_scan(v_bus, v_br, DERATE, 5e-9, l_coil, l_leak, &samples);
                        assert!(scan.evaluated);
                        for s in &scan.samples {
                            assert!(
                                !s.worse_di_dt,
                                "endpoint bound violated at k={} (L_coil={l_coil}, \
                                 L_leak={l_leak}, V_bus={v_bus}, V_BR={v_br})",
                                s.k
                            );
                            assert!(
                                !s.worse_l_loop_max,
                                "L_loop_max bound violated at k={} (L_coil={l_coil}, \
                                 L_leak={l_leak}, V_bus={v_bus}, V_BR={v_br})",
                                s.k
                            );
                        }
                        checked += scan.samples.len() as u64;
                    }
                }
            }
        }
        assert!(checked > 100_000, "BMC sweep was vacuous: only {checked} samples");
    }

    /// The BMC sweep above is only meaningful if the property CAN fail —
    /// a deliberately non-monotone model must break it (R4 fail-capable).
    #[cfg_attr(test, test)]
    fn bmc_property_is_fail_capable() {
        // A quadratic dip deep enough to push L_eff BELOW both endpoints
        // in a band around k = 0.5: at k = 0.5 the linear model gives
        // 55 uH and the dip removes 50 uH, leaving 5 uH < L_leakage.
        let depth = 200e-6;
        let samples: Vec<(f64, f64)> = (1..1024)
            .map(|i| {
                let k = f64::from(i) / 1024.0;
                (k, l_eff(L_COIL, L_LEAK, k) - depth * k * (1.0 - k))
            })
            .collect();
        let scan = interior_scan(V_BUS, V_BR, DERATE, 5e-9, L_COIL, L_LEAK, &samples);
        assert!(
            scan.samples.iter().any(|s| s.worse_di_dt),
            "non-monotone model went undetected — the BMC property is vacuous"
        );
    }

    #[cfg_attr(test, test)]
    fn audit_is_clean_for_a_consistent_report() {
        let chain = thermal_chain(20.0, 40.0, 0.6, 0.25, 1.0, V_BR, DERATE);
        let k0 = extreme_point(V_BUS, L_COIL, chain, 150.0, 5e-9);
        let k1 = extreme_point(V_BUS, L_LEAK, chain, 150.0, 5e-9);
        let samples: Vec<(f64, f64)> = interior_k_grid(101)
            .into_iter()
            .map(|k| (k, l_eff(L_COIL, L_LEAK, k)))
            .collect();
        let findings = audit_bounding(
            20.0, 40.0, 0.6, 0.25, 1.0, V_BR, DERATE, V_BUS, 150.0, 5e-9, L_COIL, L_LEAK,
            chain.t_j, [k0, k1], &samples,
        );
        assert!(findings.is_empty(), "clean report audited dirty: {findings:?}");
    }

    #[cfg_attr(test, test)]
    fn audit_catches_a_tampered_report() {
        let chain = thermal_chain(20.0, 40.0, 0.6, 0.25, 1.0, V_BR, DERATE);
        let k0 = extreme_point(V_BUS, L_COIL, chain, 150.0, 5e-9);
        let k1 = extreme_point(V_BUS, L_LEAK, chain, 150.0, 5e-9);
        let tampered = ExtremePoint { di_dt: k0.di_dt * 0.5, ..k0 };
        let findings = audit_bounding(
            20.0, 40.0, 0.6, 0.25, 1.0, V_BR, DERATE, V_BUS, 150.0, 5e-9, L_COIL, L_LEAK,
            chain.t_j, [tampered, k1], &[],
        );
        assert!(findings.contains(&AuditFinding::SlewRateMismatch));

        let findings = audit_bounding(
            20.0, 40.0, 0.6, 0.25, 1.0, V_BR, DERATE, V_BUS, 150.0, 5e-9, L_COIL, L_LEAK,
            chain.t_j + 1.0, [k0, k1], &[],
        );
        assert!(findings.contains(&AuditFinding::JunctionTemperatureMismatch));
    }

    #[cfg_attr(test, test)]
    fn py_min_max_keep_the_first_argument_on_nan() {
        assert!(py_min(f64::NAN, 1.0).is_nan());
        assert_eq!(py_min(1.0, f64::NAN), 1.0);
        assert!(py_max(f64::NAN, 1.0).is_nan());
        assert_eq!(py_max(1.0, f64::NAN), 1.0);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("operating_point::tests::l_eff_hits_the_endpoints_exactly", l_eff_hits_the_endpoints_exactly),
        ("operating_point::tests::thermal_chain_matches_the_hand_computation", thermal_chain_matches_the_hand_computation),
        ("operating_point::tests::extreme_point_zero_numerator_yields_zero_ceiling", extreme_point_zero_numerator_yields_zero_ceiling),
        ("operating_point::tests::feasibility_is_inclusive_at_the_exact_floor", feasibility_is_inclusive_at_the_exact_floor),
        ("operating_point::tests::zero_headroom_branch_choice_is_unobservable", zero_headroom_branch_choice_is_unobservable),
        ("operating_point::tests::interior_k_grid_excludes_the_endpoints", interior_k_grid_excludes_the_endpoints),
        ("operating_point::tests::interior_scan_is_silent_for_the_monotone_model", interior_scan_is_silent_for_the_monotone_model),
        ("operating_point::tests::interior_scan_returns_nothing_for_a_non_positive_endpoint", interior_scan_returns_nothing_for_a_non_positive_endpoint),
        ("operating_point::tests::interior_scan_catches_a_non_monotone_model", interior_scan_catches_a_non_monotone_model),
        ("operating_point::tests::bmc_interior_bounding_holds_exhaustively", bmc_interior_bounding_holds_exhaustively),
        ("operating_point::tests::bmc_property_is_fail_capable", bmc_property_is_fail_capable),
        ("operating_point::tests::audit_is_clean_for_a_consistent_report", audit_is_clean_for_a_consistent_report),
        ("operating_point::tests::audit_catches_a_tampered_report", audit_catches_a_tampered_report),
        ("operating_point::tests::py_min_max_keep_the_first_argument_on_nan", py_min_max_keep_the_first_argument_on_nan),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
