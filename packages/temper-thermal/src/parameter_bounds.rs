//! Parameter-bound kernels (Wave 4, Phase 4).
//!
//! Rust-owned pure kernels for monotonicity classification and worst-case
//! corner selection. The former Python parameter-bounds module had no
//! production callers; its PyO3 compatibility surface and binding-only
//! solver adapters were removed in the deletion campaign. These small
//! kernels remain available to Rust callers and the WASM property/test tier.

/// Classify a swept parameter into a monotonicity direction (+1 / -1 / 0)
/// with its `because` citation.
///
/// The family checks intentionally preserve the reference order: power,
/// junction-to-case/thermal resistance, then heat spreading/copper.
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

/// Per-bound worst-case corner values.
pub fn worst_case_values(mins: &[f64], maxs: &[f64], monos: &[f64]) -> Vec<f64> {
    mins.iter()
        .zip(maxs.iter())
        .zip(monos.iter())
        .map(|((&min, &max), &mono)| if mono < 0.0 { min } else { max })
        .collect()
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
        let (m, _, _) = classify_parameter("power_heatspread_mm", "x");
        assert_eq!(m, 1);
        let (m, _, _) = classify_parameter("thermal_resistance_spread", "x");
        assert_eq!(m, 1);
    }

    #[cfg_attr(test, test)]
    fn worst_case_selection() {
        let v = worst_case_values(&[1.0, 2.0, 3.0], &[10.0, 20.0, 30.0], &[1.0, -1.0, 0.0]);
        assert_eq!(v, vec![10.0, 2.0, 30.0]);
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
