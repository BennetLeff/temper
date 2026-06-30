// Routing check: THT thermal relief verification.
//
// For each component with package_type == THT whose net's max_current_rating
// is ≤ 10.0 A, flags an INFO that thermal relief should be verified.
//
// (Full thermal-relief detection requires pad-plane connection data that
// is not yet available — this check serves as a reminder / audit trail.)
//
// Degenerate case: 0 THT components → empty violations vec.
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::{BoardState, PackageType};
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};

/// Maximum current rating below which thermal relief should be verified.
const MAX_CURRENT_THRESHOLD_A: f64 = 10.0;

pub struct ThtThermalReliefCheck;

impl ThtThermalReliefCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for ThtThermalReliefCheck {
    fn name(&self) -> &str {
        "routing_tht_thermal_relief"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Dfm
    }

    fn description(&self) -> &str {
        "Flag THT components on low-current nets (≤ 10 A) for thermal relief verification."
    }

    fn check(&self, board: &BoardState, _constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        // Degenerate: no components → nothing to check.
        if board.components.is_empty() {
            return violations;
        }

        for comp in &board.components {
            if comp.package_type != PackageType::Tht {
                continue;
            }

            // Look up the net class rules for this component's net class.
            let current_rating = board
                .net_class_rules
                .get(&comp.net_class)
                .and_then(|r| r.max_current_rating);

            match current_rating {
                Some(rating) if rating <= MAX_CURRENT_THRESHOLD_A => {
                    // THT component on a net with max_current_rating ≤ 10 A.
                    let layer = if comp.side == crate::board::BoardSide::Top {
                        "F.Cu"
                    } else {
                        "B.Cu"
                    };

                    violations.push(violation(
                        Severity::Info,
                        "ROUTING_THT_RELIEF_001",
                        &format!(
                            "THT component {} (net class '{}', rated {:.1} A) — \
                             verify thermal relief connection to plane.",
                            comp.refdes, comp.net_class, rating,
                        ),
                        DrcCategory::Dfm,
                        "routing_tht_thermal_relief",
                        vec![comp.refdes.clone(), comp.net_class.clone()],
                        Some(crate::rules::Location {
                            x: Some(comp.center.x()),
                            y: Some(comp.center.y()),
                            layer: Some(layer.to_string()),
                        }),
                        serde_json::json!({
                            "refdes": comp.refdes,
                            "net_class": comp.net_class,
                            "max_current_rating_a": rating,
                            "package_type": "THT",
                        }),
                    ));
                }
                // No rating information or rating > threshold → skip.
                _ => {}
            }
        }

        violations
    }
}
