// Safety check: isolation — only isolation components in iso zones.
//
// Ensures that only components belonging to the isolation class reside
// within or straddle isolation zones. All other components must stay clear.
//
// Ported from: packages/temper-drc/src/temper_drc/checks/safety/isolation.py
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};

/// Keywords that identify an isolation component.
const ISO_COMPONENT_KEYWORDS: [&str; 8] =
    ["iso", "opto", "coupler", "isolator", "transformer", "adum", "dcdc", "mev1"];

/// Keywords that identify an isolation zone.
const ISO_ZONE_KEYWORDS: [&str; 6] =
    ["iso", "opto", "coupler", "transformer", "gutter", "slot"];

/// Determine if a net class indicates an isolation component.
fn is_iso_component(net_class: &str) -> bool {
    let lc = net_class.to_lowercase();
    ISO_COMPONENT_KEYWORDS.iter().any(|k| lc.contains(k))
}

/// Determine if a zone name indicates it is an isolation zone.
fn is_iso_zone(zone_name: &str) -> bool {
    let lc = zone_name.to_lowercase();
    ISO_ZONE_KEYWORDS.iter().any(|k| lc.contains(k))
}

pub struct IsolationCheck;

impl IsolationCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for IsolationCheck {
    fn name(&self) -> &str {
        "safety_isolation"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Safety
    }

    fn description(&self) -> &str {
        "Ensure no components reside in isolation zones except isolation devices."
    }

    fn check(&self, board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        // Identify isolation zones by name keyword matching
        let iso_zone_names: Vec<&str> = constraints
            .zones
            .iter()
            .filter(|z| is_iso_zone(&z.name))
            .map(|z| z.name.as_str())
            .collect();

        if iso_zone_names.is_empty() {
            return violations;
        }

        // Check each component against isolation zones
        for comp in &board.components {
            let is_iso_device = is_iso_component(&comp.net_class);

            if is_iso_device {
                continue;
            }

            let cx = comp.center.x();
            let cy = comp.center.y();

            // Check if this component's net class places it in an iso zone
            for zone in &constraints.zones {
                if !is_iso_zone(&zone.name) {
                    continue;
                }

                // If component's net_class matches a zone's net_classes, check containment
                let in_zone_via_net_class = zone.net_classes.iter().any(|zc| zc == &comp.net_class);

                if in_zone_via_net_class {
                    let layer = if comp.side == crate::board::BoardSide::Top {
                        "F.Cu"
                    } else {
                        "B.Cu"
                    };

                    violations.push(violation(
                        Severity::Error,
                        "SAF_ISO_001",
                        &format!(
                            "Safety violation: Component {} ({}) is in isolation zone '{}'",
                            comp.refdes, comp.net_class, zone.name,
                        ),
                        DrcCategory::Safety,
                        "safety_isolation",
                        vec![comp.refdes.clone()],
                        Some(crate::rules::Location {
                            x: Some(cx),
                            y: Some(cy),
                            layer: Some(layer.to_string()),
                        }),
                        serde_json::json!({
                            "zone_name": zone.name,
                            "component_class": comp.net_class,
                        }),
                    ));
                }
            }
        }

        violations
    }
}
