// EMC check: ground plane — noisy components must be within ground zones.
//
// Verifies that noisy or high-speed components (switching, power, clock, etc.)
// are positioned within zones designated as ground/return.
//
// Ported from: packages/temper-drc/src/temper_drc/checks/emc/ground_plane.py
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};

/// Keywords identifying noisy component classes that need ground plane coverage.
const NOISY_KEYWORDS: [&str; 5] = ["power", "switching", "clock", "pwm", "high_freq"];

/// Keywords identifying ground/return zones.
const GND_KEYWORDS: [&str; 3] = ["gnd", "ground", "return"];

/// Returns true if the net class is noisy (needs ground plane).
fn is_noisy(net_class: &str) -> bool {
    let lc = net_class.to_lowercase();
    NOISY_KEYWORDS.iter().any(|k| lc.contains(k))
}

/// Returns true if the zone name indicates it is a ground/return zone.
fn is_gnd_zone(zone_name: &str) -> bool {
    let lc = zone_name.to_lowercase();
    GND_KEYWORDS.iter().any(|k| lc.contains(k))
}

pub struct GroundPlaneCheck;

impl GroundPlaneCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for GroundPlaneCheck {
    fn name(&self) -> &str {
        "emc_ground_plane"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Emc
    }

    fn description(&self) -> &str {
        "Ensure high-di/dt or high-speed components have a ground plane return path."
    }

    fn check(&self, board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        // Identify ground zones by name keyword matching
        let gnd_zone_names: Vec<&str> = constraints
            .zones
            .iter()
            .filter(|z| is_gnd_zone(&z.name))
            .map(|z| z.name.as_str())
            .collect();

        // Check each noisy component
        for comp in &board.components {
            if !is_noisy(&comp.net_class) {
                continue;
            }

            // Check if this component's net class matches any gnd zone's net classes
            let inside_gnd = constraints.zones.iter().any(|zone| {
                if !is_gnd_zone(&zone.name) {
                    return false;
                }
                zone.net_classes.iter().any(|zc| zc == &comp.net_class)
            });

            if !inside_gnd {
                let layer = if comp.side == crate::board::BoardSide::Top {
                    "F.Cu"
                } else {
                    "B.Cu"
                };

                violations.push(violation(
                    Severity::Error,
                    "EMC_GND_001",
                    &format!(
                        "Noisy component {} ({}) is not placed over a ground plane.",
                        comp.refdes, comp.net_class,
                    ),
                    DrcCategory::Emc,
                    "emc_ground_plane",
                    vec![comp.refdes.clone()],
                    Some(crate::rules::Location {
                        x: Some(comp.center.x()),
                        y: Some(comp.center.y()),
                        layer: Some(layer.to_string()),
                    }),
                    serde_json::json!({
                        "component_class": comp.net_class,
                        "available_gnd_zones": gnd_zone_names,
                    }),
                ));
            }
        }

        violations
    }
}
