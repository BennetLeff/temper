// EMC check: loop area — bounding-box area of critical loop components.
//
// Checks that the bounding box area of all components connected to the
// nets defined in a LoopConstraint does not exceed the maximum area.
//
// Ported from: packages/temper-drc/src/temper_drc/checks/emc/loop_area.py
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use std::collections::HashSet;

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};

pub struct LoopAreaCheck;

impl LoopAreaCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for LoopAreaCheck {
    fn name(&self) -> &str {
        "emc_loop_area"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Emc
    }

    fn description(&self) -> &str {
        "Minimize radiated emissions by checking critical loop areas."
    }

    fn check(&self, board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        for loop_constraint in &constraints.critical_loops {
            // Collect all unique component refdes involved in this loop's nets
            let mut involved_refs: HashSet<&str> = HashSet::new();
            for net_name in &loop_constraint.nets {
                if let Some(net) = board.net_by_name(net_name) {
                    for r in &net.components {
                        involved_refs.insert(&*r.0);
                    }
                }
            }

            if involved_refs.len() < 2 {
                continue;
            }

            // Calculate bounding box of all involved components
            let mut min_x = f64::MAX;
            let mut min_y = f64::MAX;
            let mut max_x = f64::MIN;
            let mut max_y = f64::MIN;
            let mut valid = false;

            for refdes in &involved_refs {
                if let Some(comp) = board.electrical_components.iter().find(|c| c.refdes.0 == *refdes) {
                    min_x = min_x.min(comp.center.x());
                    min_y = min_y.min(comp.center.y());
                    max_x = max_x.max(comp.center.x());
                    max_y = max_y.max(comp.center.y());
                    valid = true;
                }
            }

            if !valid {
                continue;
            }

            let width = (max_x - min_x).max(0.0);
            let height = (max_y - min_y).max(0.0);
            let area = width * height;

            if let Some(max_area) = loop_constraint.max_area_mm2 {
                if area > max_area {
                    violations.push(violation(
                        Severity::Warning,
                        "EMC_LPA_001",
                        &format!(
                            "Critical loop '{}' area {:.2}mm² > {:.2}mm²",
                            loop_constraint.name, area, max_area,
                        ),
                        DrcCategory::Emc,
                        "emc_loop_area",
                        involved_refs.iter().map(|s| s.to_string()).collect(),
                        Some(crate::rules::Location {
                            x: Some((min_x + max_x) / 2.0),
                            y: Some((min_y + max_y) / 2.0),
                            layer: None,
                        }),
                        serde_json::json!({
                            "loop_name": loop_constraint.name,
                            "actual_area_mm2": area,
                            "max_area_mm2": max_area,
                            "nets": loop_constraint.nets,
                        }),
                    ));
                }
            }
        }

        violations
    }
}
