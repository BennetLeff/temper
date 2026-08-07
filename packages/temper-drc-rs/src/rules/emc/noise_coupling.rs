// EMC check: noise coupling — aggressor vs victim component distance.
//
// Identifies pairs where one component is noisy (power, clock, switching)
// and the other is sensitive (analog, sensor), and validates clearance.
//
// Ported from: packages/temper-drc/src/temper_drc/checks/emc/noise_coupling.py
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{
    clearance_between, location_midpoint, violation, DrcCategory, DrcRule, Severity, Violation,
};

/// Keywords identifying noisy (aggressor) component classes.
const NOISY_KEYWORDS: [&str; 5] = ["power", "clock", "switching", "pwm", "high_freq"];

/// Keywords identifying sensitive (victim) component classes.
const SENSITIVE_KEYWORDS: [&str; 4] = ["analog", "sensor", "small_signal", "victim"];

/// Returns true if the net class is categorized as noisy.
fn is_noisy(net_class: &str) -> bool {
    let lc = net_class.to_lowercase();
    NOISY_KEYWORDS.iter().any(|k| lc.contains(k))
}

/// Returns true if the net class is categorized as sensitive.
fn is_sensitive(net_class: &str) -> bool {
    let lc = net_class.to_lowercase();
    SENSITIVE_KEYWORDS.iter().any(|k| lc.contains(k))
}

#[derive(Default)]
pub struct NoiseCouplingCheck;

impl NoiseCouplingCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for NoiseCouplingCheck {
    fn name(&self) -> &str {
        "emc_noise_coupling"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Emc
    }

    fn description(&self) -> &str {
        "Identify and minimize noise coupling between aggressor and victim components."
    }

    fn check(&self, board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();
        let comps = &board.electrical_components;
        let n = comps.len();

        // Noise/sensitivity classification is pure per component; compute
        // once, not four times per pair.
        let noisy: Vec<bool> = comps.iter().map(|c| is_noisy(&c.net_class)).collect();
        let sensitive: Vec<bool> = comps.iter().map(|c| is_sensitive(&c.net_class)).collect();

        for i in 0..n {
            for j in (i + 1)..n {
                let a = &comps[i];
                let b = &comps[j];

                let a_noisy = noisy[i];
                let b_noisy = noisy[j];
                let a_sensitive = sensitive[i];
                let b_sensitive = sensitive[j];

                let is_noise_case = (a_noisy && b_sensitive) || (b_noisy && a_sensitive);

                if !is_noise_case {
                    continue;
                }

                let required = clearance_between(
                    constraints,
                    &board.net_class_rules,
                    &a.net_class,
                    &b.net_class,
                );

                if required <= 0.0 {
                    continue;
                }

                let dist = a.edge_distance_to(b);

                if dist < required {
                    // Determine which is aggressor and which is victim
                    let (aggressor, victim) = if a_noisy {
                        (&a.refdes, &b.refdes)
                    } else {
                        (&b.refdes, &a.refdes)
                    };

                    violations.push(violation(
                        Severity::Warning,
                        "EMC_NSE_001",
                        &format!(
                            "Noise coupling risk: {:.3}mm < {:.3}mm between {} ({}) and {} ({})",
                            dist, required, a.refdes, a.net_class, b.refdes, b.net_class,
                        ),
                        DrcCategory::Emc,
                        "emc_noise_coupling",
                        vec![a.refdes.0.clone(), b.refdes.0.clone()],
                        location_midpoint(&a.center, &b.center, None),
                        serde_json::json!({
                            "distance_mm": dist,
                            "required_mm": required,
                            "aggressor": aggressor,
                            "victim": victim,
                        }),
                    ));
                }
            }
        }

        violations
    }
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;
    use crate::board::*;
    use crate::constraints::*;
    use geo::Point;
    use std::collections::HashMap;

    fn make_board(components: Vec<Component>, clearance_mm: f64) -> BoardState {
        let mut rules = HashMap::new();
        // Insert net class rules for every net class used in tests so
        // clearance_between() can resolve them in the key-value map.
        let default_rules = NetClassRules {
            clearance_mm,
            ..NetClassRules::default()
        };
        rules.insert(NetClassName("power".into()), default_rules.clone());
        rules.insert(NetClassName("analog".into()), default_rules.clone());
        rules.insert(NetClassName("Signal".into()), default_rules.clone());
        BoardState {
            width_mm: 100.0,
            height_mm: 100.0,
            margin_mm: 3.0,
            electrical_components: components,
            mechanical_components: vec![],
            nets: vec![],
            net_class_rules: rules,
            traces: vec![],
            vias: vec![],
            zones: vec![],
        }
    }

    fn make_component(refdes: &str, x: f64, y: f64, net_class: &str) -> Component {
        Component {
            refdes: ComponentRef(refdes.into()),
            center: Point::new(x, y),
            rotation: 0.0,
            side: BoardSide::Top,
            width: 10.0,
            height: 10.0,
            net_class: NetClassName(net_class.into()),
            power_dissipation_w: None,
            package_type: PackageType::Smd,
            is_magnetic: false,
            is_electrolytic: false,
            vent_direction: None,
            footprint_polygon: None,
        }
    }

    #[cfg_attr(test, test)]
    fn noise_coupling_empty_board_no_violations() {
        let board = make_board(vec![], 5.0);
        let constraints = ConstraintSet::default();
        let check = NoiseCouplingCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "empty board must produce 0 violations"
        );
    }

    #[cfg_attr(test, test)]
    fn noise_coupling_far_apart_no_violation() {
        // Noisy ("power") and sensitive ("analog") 50mm apart
        // edge_distance ≈ 50 - 10 = 40mm > clearance 5mm
        let c1 = make_component("C1", 0.0, 0.0, "power");
        let c2 = make_component("C2", 50.0, 0.0, "analog");
        let board = make_board(vec![c1, c2], 5.0);
        let constraints = ConstraintSet::default();
        let check = NoiseCouplingCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "distant pair must produce 0 violations, got {}",
            violations.len()
        );
    }

    #[cfg_attr(test, test)]
    fn noise_coupling_close_pair_violation() {
        // Noisy ("power") and sensitive ("analog") 12mm apart
        // edge_distance ≈ 12 - 10 = 2mm < clearance 5mm
        let c1 = make_component("C1", 0.0, 0.0, "power");
        let c2 = make_component("C2", 12.0, 0.0, "analog");
        let board = make_board(vec![c1, c2], 5.0);
        let constraints = ConstraintSet::default();
        let check = NoiseCouplingCheck::new();
        let violations = check.check(&board, &constraints);
        assert_eq!(
            violations.len(),
            1,
            "close noisy-sensitive pair must produce 1 violation"
        );
        let v = &violations[0];
        assert_eq!(v.code, "EMC_NSE_001");
        assert_eq!(v.severity, Severity::Warning);
        assert_eq!(v.category, DrcCategory::Emc);
    }

    #[cfg_attr(test, test)]
    fn noise_coupling_non_noisy_sensitive_no_violation() {
        // Both components are "Signal" (not noisy, not sensitive)
        let c1 = make_component("C1", 0.0, 0.0, "Signal");
        let c2 = make_component("C2", 11.0, 0.0, "Signal");
        let board = make_board(vec![c1, c2], 5.0);
        let constraints = ConstraintSet::default();
        let check = NoiseCouplingCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "non-noisy/sensitive pair must produce 0 violations"
        );
    }

    #[cfg_attr(test, test)]
    fn noise_coupling_at_threshold_exact_violation() {
        // Two 10mm-wide components, 10mm apart center-to-center
        // edge_distance = 10 - 5 - 5 = 0mm < clearance 5mm → violation
        let c1 = make_component("C1", 0.0, 0.0, "power");
        let c2 = make_component("C2", 10.0, 0.0, "analog");
        let board = make_board(vec![c1, c2], 5.0);
        let constraints = ConstraintSet::default();
        let check = NoiseCouplingCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            !violations.is_empty(),
            "touching noisy-sensitive pair must produce a violation"
        );
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("rules::emc::noise_coupling::tests::noise_coupling_empty_board_no_violations", noise_coupling_empty_board_no_violations),
        ("rules::emc::noise_coupling::tests::noise_coupling_far_apart_no_violation", noise_coupling_far_apart_no_violation),
        ("rules::emc::noise_coupling::tests::noise_coupling_close_pair_violation", noise_coupling_close_pair_violation),
        ("rules::emc::noise_coupling::tests::noise_coupling_non_noisy_sensitive_no_violation", noise_coupling_non_noisy_sensitive_no_violation),
        ("rules::emc::noise_coupling::tests::noise_coupling_at_threshold_exact_violation", noise_coupling_at_threshold_exact_violation),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
