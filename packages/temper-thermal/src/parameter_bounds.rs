//! Parameter-bound kernels (Wave 4, Phase 4).
//!
//! Ports the classification and corner arithmetic of
//! `temper_placer/physics/parameter_bounds.py` (the L2 verified-interval
//! soundness surface: the monotonicity CLASSIFICATION of a swept
//! parameter name into +1 / −1 / 0 with its `because` citation, and the
//! per-bound `worst_case_value` selection) to Rust.  The Python module
//! keeps its public API (`ParameterBound`, `ThermalSoundnessResult`,
//! `build_thermal_parameter_bounds`'s prereg/FDM-config introspection
//! and the literal ambient_C / h_sink_min bounds,
//! `compute_thermal_soundness`'s corner FDM solve and message
//! building); the classification and the worst-case selection delegate
//! here.
//!
//! ## Bit-exactness discipline
//!
//! - The classification is STRING matching (the reference's
//!   `param_lower = parameter.lower()` with the three keyword
//!   disjunctions in order: power/dissipation/p_loss → +1,
//!   junction_to_case/r_theta/thermal_resistance → +1,
//!   heatspread/spread/copper → −1, else 0).  Rust `to_lowercase` and
//!   `contains` replicate CPython's `lower()`/`in` for the ASCII
//!   parameter names the prereg manifests carry (documented divergence:
//!   CPython's `str.lower` applies Unicode case folding — the repo's
//!   parameter names are ASCII; a non-ASCII name would classify
//!   differently and is a standing divergence to re-check).
//! - `worst_case_value` is the reference's property: mono > 0 → max,
//!   mono < 0 → min, else max.
//! - The `because` citation strings are reproduced VERBATIM from the
//!   reference (including the double spaces after sentence periods),
//!   with the parameter name interpolated exactly as the reference's
//!   f-strings.
//!
//! R24 (physics-gated): this module IS the soundness-gate surface for
//! the thermal FDM corner bound (L2).  It is not a CP-SAT constraint
//! encoder, but its Chebyshev-style soundness claim (the worst-case
//! corner bounds all interior configurations for provably-monotone
//! parameters, via the M-matrix monotonicity proof) is documented in
//! VERIFICATION.md; the kernels pin the classification/selection
//! arithmetic bit-exactly.

#[cfg(feature = "python")]
use pyo3::prelude::*;
#[cfg(feature = "python")]
use pyo3::types::{PyAny, PyString};
#[cfg(feature = "python")]
use temper_py_bridge;

/// Classify a swept parameter into a monotonicity direction (+1 / −1 /
/// 0) with its `because` citation.  Mirrors
/// `build_thermal_parameter_bounds`'s keyword classification verbatim
/// (order matters: power-family first, then R_θ-family, then
/// heatspread-family, else unknown).  `unit` is the reference's
/// `pr.because` passthrough for matched parameters and `"unknown"`
/// for unmatched.
///
/// Returns `(monotonicity, unit, because)`.
pub fn classify_parameter(param_name: &str, source_because: &str) -> (i64, String, String) {
    let param_lower = param_name.to_lowercase();

    if param_lower.contains("power")
        || param_lower.contains("dissipation")
        || param_lower.contains("P_loss")
    {
        let because = format!(
            "b = Q_vec + h*T_amb; A unchanged.  A^{{-1}} >= 0 \
             (M-matrix property), so T = A^{{-1}} b increases \
             monotonically in Q component-wise.  -> \
             T_j INCREASING in {param_name}"
        );
        return (1, source_because.to_string(), because);
    }

    if param_lower.contains("junction_to_case")
        || param_lower.contains("r_theta")
        || param_lower.contains("thermal_resistance")
    {
        let because = format!(
            "R_theta = 1/h for through-plane sink.  \
             d T / d h_i = A^{{-1}} e_i (T_amb - T_i) <= 0 \
             when T_i >= T_amb (M-matrix inverse non-negativity).  \
             Higher R_theta -> lower h -> higher T_j.  -> \
             T_j INCREASING in {param_name}"
        );
        return (1, source_because.to_string(), because);
    }

    if param_lower.contains("heatspread")
        || param_lower.contains("spread")
        || param_lower.contains("copper")
    {
        let because = format!(
            "Larger heatspread -> more copper coverage -> higher \
             effective k_eff -> lower thermal resistance -> lower \
             T_j.  Scaling k_field by alpha > 1 gives A(alpha) >= \
             A(1) component-wise (M-matrix ordering), so \
             A(alpha)^{{-1}} <= A(1)^{{-1}}, b unchanged, hence \
             T(alpha) <= T.  -> T_j DECREASING in {param_name}"
        );
        return (-1, source_because.to_string(), because);
    }

    let because = format!(
        "No monotonicity proof for '{param_name}'; \
         corner-bound is NOT a guarantee for this parameter."
    );
    (0, "unknown".to_string(), because)
}

/// Per-bound worst-case corner values.  Mirrors
/// `ParameterBound.worst_case_value` verbatim: mono > 0 → max,
/// mono < 0 → min, mono == 0 → max (conservative, not a guarantee).
/// `monos` are `f64` — the reference's `b.monotonicity > 0` comparison
/// accepts ANY comparable (ints, floats, bools, numpy scalars all
/// coerce; pass 2 P2: the previous `i64` bridge raised TypeError for a
/// float monotonicity the oracle arithmetic accepted).
pub fn worst_case_values(mins: &[f64], maxs: &[f64], monos: &[f64]) -> Vec<f64> {
    mins.iter()
        .zip(maxs.iter())
        .zip(monos.iter())
        .map(|((&min, &max), &mono)| if mono < 0.0 { min } else { max })
        .collect()
}

/// pyo3 bridge for [`classify_parameter`].
///
/// `param_name` is accepted as any Python object: the reference calls
/// `parameter.lower()`, which raises `AttributeError("'<type>' object
/// has no attribute 'lower'")` for ANY non-str — NOT the TypeError a
/// `String` extraction would produce (pass 2 P2).  The bridge
/// replicates the reference's class AND message (via the object's
/// type name, e.g. `'NoneType'`, `'int'`, `'list'`).
///
/// `source_because` stays narrowed to `str` (documented deviation):
/// the reference passes ANY object through as the `unit` for matched
/// parameters (`None` included); the prereg manifests always carry a
/// str and the shim always passes one, so this only affects direct
/// kernel callers — recorded, not widened.
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (param_name, source_because))]
pub fn classify_parameter_py(
    param_name: Bound<'_, PyAny>,
    source_because: String,
) -> PyResult<(i64, String, String)> {
    use pyo3::exceptions::PyAttributeError;
    use pyo3::types::PyAnyMethods;
    if !param_name.is_instance_of::<PyString>() {
        let ty = param_name.get_type().name()?;
        return Err(PyAttributeError::new_err(format!(
            "'{ty}' object has no attribute 'lower'"
        )));
    }
    let name: String = param_name.extract()?;
    temper_py_bridge::catch_unwind(|| classify_parameter(&name, &source_because))
        .map_err(temper_py_bridge::panic_to_err)
}

/// pyo3 bridge for [`worst_case_values`].
#[cfg(feature = "python")]
#[pyfunction]
#[pyo3(signature = (mins, maxs, monos))]
pub fn worst_case_values_py(
    mins: Vec<f64>,
    maxs: Vec<f64>,
    monos: Vec<f64>,
) -> PyResult<Vec<f64>> {
    temper_py_bridge::catch_unwind(|| worst_case_values(&mins, &maxs, &monos))
        .map_err(temper_py_bridge::panic_to_err)
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;

    #[cfg_attr(test, test)]
    fn classify_power_family() {
        let (m, unit, because) = classify_parameter("power_dissipation_w", "Power sweep range");
        assert_eq!(m, 1);
        assert_eq!(unit, "Power sweep range");
        assert!(because.contains("T_j INCREASING in power_dissipation_w"));
    }

    #[cfg_attr(test, test)]
    fn classify_rtheta_family() {
        let (m, _, because) = classify_parameter("junction_to_case_c_per_w", "R_theta sweep");
        assert_eq!(m, 1);
        assert!(because.contains("T_j INCREASING in junction_to_case_c_per_w"));
        let (m, _, _) = classify_parameter("r_theta_cs_k_per_w", "x");
        assert_eq!(m, 1);
        let (m, _, _) = classify_parameter("thermal_resistance_xy", "x");
        assert_eq!(m, 1);
    }

    #[cfg_attr(test, test)]
    fn classify_heatspread_family() {
        let (m, _, because) = classify_parameter("max_heatspread_mm", "Heatspread range");
        assert_eq!(m, -1);
        assert!(because.contains("T_j DECREASING in max_heatspread_mm"));
        let (m, _, _) = classify_parameter("copper_fraction", "x");
        assert_eq!(m, -1);
        let (m, _, _) = classify_parameter("spread_angle", "x");
        assert_eq!(m, -1);
    }

    #[cfg_attr(test, test)]
    fn classify_unknown() {
        let (m, unit, because) = classify_parameter("wind_speed", "x");
        assert_eq!(m, 0);
        assert_eq!(unit, "unknown");
        assert!(because.contains("No monotonicity proof for 'wind_speed'"));
    }

    #[cfg_attr(test, test)]
    fn classify_precedence_order() {
        // "power_heatspread_mm" matches the POWER family first.
        let (m, _, _) = classify_parameter("power_heatspread_mm", "x");
        assert_eq!(m, 1);
        // "spread" must NOT reclassify a power param already matched.
        let (m, _, _) = classify_parameter("thermal_resistance_spread", "x");
        assert_eq!(m, 1); // r_theta family checked before heatspread
    }

    #[cfg_attr(test, test)]
    fn worst_case_selection() {
        let v = worst_case_values(&[1.0, 2.0, 3.0], &[10.0, 20.0, 30.0], &[1.0, -1.0, 0.0]);
        assert_eq!(v, vec![10.0, 2.0, 30.0]);
        // f64 monos match the reference's `b.monotonicity > 0` (any
        // comparable coerces — floats/bools; pass 2 P2).
        let v = worst_case_values(&[1.0], &[10.0], &[1.5]);
        assert_eq!(v, vec![10.0]);
        let v = worst_case_values(&[1.0], &[10.0], &[-0.5]);
        assert_eq!(v, vec![1.0]);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("parameter_bounds::tests::classify_power_family", classify_power_family),
        ("parameter_bounds::tests::classify_rtheta_family", classify_rtheta_family),
        ("parameter_bounds::tests::classify_heatspread_family", classify_heatspread_family),
        ("parameter_bounds::tests::classify_unknown", classify_unknown),
        ("parameter_bounds::tests::classify_precedence_order", classify_precedence_order),
        ("parameter_bounds::tests::worst_case_selection", worst_case_selection),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
