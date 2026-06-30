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

        for i in 0..n {
            for j in (i + 1)..n {
                let a = &comps[i];
                let b = &comps[j];

                let a_noisy = is_noisy(&a.net_class);
                let b_noisy = is_noisy(&b.net_class);
                let a_sensitive = is_sensitive(&a.net_class);
                let b_sensitive = is_sensitive(&b.net_class);

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
                        vec![a.refdes.clone(), b.refdes.clone()],
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
