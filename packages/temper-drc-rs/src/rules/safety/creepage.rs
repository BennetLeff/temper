// Safety check: creepage — isolation components must have minimum package width.
//
// Checks isolation components (optocouplers, transformers, isolators, etc.)
// to ensure their package provides sufficient physical distance across the
// isolation barrier (minimum package width >= min_iso_width_mm).
//
// Ported from: packages/temper-drc/src/temper_drc/checks/safety/creepage.py
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};

/// Keywords that identify an isolation component.
const ISO_COMPONENT_KEYWORDS: [&str; 8] =
    ["iso", "opto", "coupler", "isolator", "transformer", "adum", "dcdc", "mev1"];

/// Determine if a net class or footprint indicates an isolation component.
fn is_iso_component(net_class: &str) -> bool {
    let lc = net_class.to_lowercase();
    ISO_COMPONENT_KEYWORDS.iter().any(|k| lc.contains(k))
}

pub struct CreepageCheck {
    min_iso_width_mm: f64,
}

impl CreepageCheck {
    /// Create a new CreepageCheck with the given minimum isolation width.
    pub fn new(min_iso_width_mm: f64) -> Self {
        Self { min_iso_width_mm }
    }
}

impl DrcRule for CreepageCheck {
    fn name(&self) -> &str {
        "safety_creepage"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Safety
    }

    fn description(&self) -> &str {
        "Verify isolation component width for creepage safety."
    }

    fn check(&self, board: &BoardState, _constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        for comp in board.all_components() {
            if !is_iso_component(&comp.net_class) {
                continue;
            }

            // For an isolation component, the max(width, height) defines
            // the separation distance across the barrier (matching Python).
            let package_width = comp.width.max(comp.height);

            if package_width < self.min_iso_width_mm {
                let layer = if comp.side == crate::board::BoardSide::Top {
                    "F.Cu"
                } else {
                    "B.Cu"
                };

                violations.push(violation(
                    Severity::Error,
                    "SAF_CRP_001",
                    &format!(
                        "Creepage violation: component {} width {:.1}mm < {:.1}mm",
                        comp.refdes, package_width, self.min_iso_width_mm,
                    ),
                    DrcCategory::Safety,
                    "safety_creepage",
                    vec![comp.refdes.0.clone()],
                    Some(crate::rules::Location {
                        x: Some(comp.center.x()),
                        y: Some(comp.center.y()),
                        layer: Some(layer.to_string()),
                    }),
                    serde_json::json!({
                        "actual_width_mm": package_width,
                        "required_width_mm": self.min_iso_width_mm,
                    }),
                ));
            }
        }

        violations
    }
}
