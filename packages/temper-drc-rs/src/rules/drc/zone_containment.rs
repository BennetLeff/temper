// DRC check: zone containment.
//
// For each component, checks whether its center point lies inside any
// copper zone on the board. If the component's net_class is listed in a
// constraint zone's net_classes but the component's center is not inside
// any copper zone polygon, emits DRC_ZON_001 ERROR.
//
// Ported from: packages/temper-drc/src/temper_drc/checks/drc/zone_containment.py
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};
use geo::Contains;

pub struct ZoneContainmentCheck;
impl ZoneContainmentCheck {
    pub fn new() -> Self {
        Self
    }
}
impl DrcRule for ZoneContainmentCheck {
    fn name(&self) -> &str {
        "drc_zone_containment"
    }
    fn category(&self) -> DrcCategory {
        DrcCategory::Drc
    }
    fn description(&self) -> &str {
        "Check that components are inside their designated zones."
    }
    fn check(&self, board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        for comp in board.all_components() {
            // Find constraint zones whose net_classes list this component's net_class
            let matching_zones: Vec<&crate::constraints::ZoneDefinition> = constraints
                .zones
                .iter()
                .filter(|z| {
                    z.net_classes
                        .iter()
                        .any(|nc| nc.as_str() == comp.net_class.0.as_str())
                })
                .collect();

            if matching_zones.is_empty() {
                continue; // No zone requires this component
            }

            // Check if component center is inside any copper zone polygon on the board
            let center = comp.center;
            let is_inside_any_zone = board
                .zones
                .iter()
                .any(|z| z.polygon.contains(&center));

            if !is_inside_any_zone {
                let zone_names: Vec<String> =
                    matching_zones.iter().map(|z| z.name.clone()).collect();
                violations.push(violation(
                    Severity::Error,
                    "DRC_ZON_001",
                    &format!(
                        "Zone containment violation: {} (net class {}) is not inside any copper zone. Expected zones: {:?}",
                        comp.refdes, comp.net_class, zone_names,
                    ),
                    DrcCategory::Drc,
                    "drc_zone_containment",
                    vec![comp.refdes.0.clone()],
                    Some(crate::rules::Location {
                        x: Some(center.x()),
                        y: Some(center.y()),
                        layer: None,
                    }),
                    serde_json::json!({
                        "expected_zones": zone_names,
                        "net_class": comp.net_class.0,
                    }),
                ));
            }
        }
        violations
    }
}
