// DRC check: component overlap.
//
// Iterates all component pairs where a.same_layer(b). Calls a.overlaps(b)
// and emits DRC_OVL_001 CRITICAL if true.
//
// Ported from: packages/temper-drc/src/temper_drc/checks/drc/component_overlap.py
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};

pub struct ComponentOverlapCheck;
impl ComponentOverlapCheck {
    pub fn new() -> Self {
        Self
    }
}
impl DrcRule for ComponentOverlapCheck {
    fn name(&self) -> &str {
        "drc_component_overlap"
    }
    fn category(&self) -> DrcCategory {
        DrcCategory::Drc
    }
    fn description(&self) -> &str {
        "Check for overlapping components on the same layer."
    }
    fn check(&self, board: &BoardState, _constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();
        let components: Vec<&crate::board::Component> = board.all_components().collect();

        for i in 0..components.len() {
            for j in (i + 1)..components.len() {
                let a = components[i];
                let b = components[j];
                if !a.same_layer(b) {
                    continue;
                }
                if a.overlaps(b) {
                    let layer_label = if a.side == crate::board::BoardSide::Top {
                        "Top"
                    } else {
                        "Bottom"
                    };
                    violations.push(violation(
                        Severity::Critical,
                        "DRC_OVL_001",
                        &format!(
                            "Component overlap: {} overlaps {} on {}",
                            a.refdes, b.refdes, layer_label,
                        ),
                        DrcCategory::Drc,
                        "drc_component_overlap",
                        vec![a.refdes.0.clone(), b.refdes.0.clone()],
                        crate::rules::location_midpoint(&a.center, &b.center, None),
                        serde_json::json!({}),
                    ));
                }
            }
        }
        violations
    }
}
