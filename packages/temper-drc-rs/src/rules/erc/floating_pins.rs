// ERC check: floating pins — every component must belong to at least one net.
//
// Components not referenced in any net are flagged as warnings.
//
// Ported from: packages/temper-drc/src/temper_drc/checks/erc/floating_pins.py
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use std::collections::HashSet;

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};

pub struct FloatingPinsCheck;

impl FloatingPinsCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for FloatingPinsCheck {
    fn name(&self) -> &str {
        "erc_floating_pins"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Erc
    }

    fn description(&self) -> &str {
        "Identify components that are not connected to any net."
    }

    fn check(&self, board: &BoardState, _constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        // Build set of all connected component refdes
        let connected: HashSet<&str> = board
            .nets
            .values()
            .flat_map(|refs| refs.iter().map(|s| s.as_str()))
            .collect();

        // Check each component in the board
        for comp in &board.components {
            // Skip mechanical components (mounting holes, etc.) — they have
            // no electrical nets by design and should not trigger floating pins.
            if comp.is_mechanical {
                continue;
            }
            if !connected.contains(comp.refdes.as_str()) {
                let layer = if comp.side == crate::board::BoardSide::Top {
                    "F.Cu"
                } else {
                    "B.Cu"
                };

                violations.push(violation(
                    Severity::Warning,
                    "ERC_FLT_001",
                    &format!(
                        "Component '{}' is not connected to any net (floating).",
                        comp.refdes,
                    ),
                    DrcCategory::Erc,
                    "erc_floating_pins",
                    vec![comp.refdes.clone()],
                    Some(crate::rules::Location {
                        x: Some(comp.center.x()),
                        y: Some(comp.center.y()),
                        layer: Some(layer.to_string()),
                    }),
                    serde_json::json!({
                        "ref": comp.refdes,
                    }),
                ));
            }
        }

        violations
    }
}
