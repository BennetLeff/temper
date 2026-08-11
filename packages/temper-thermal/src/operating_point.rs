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
