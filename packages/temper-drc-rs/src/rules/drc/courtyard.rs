// DRC check: courtyard clearance.
//
// For each component pair on the same layer, expand each bbox by
// COURTYARD_MARGIN (0.05mm). If the expanded bboxes intersect, emit
// DRC_CRT_001 WARNING.
//
// Ported from: packages/temper-drc/src/temper_drc/checks/drc/courtyard.py
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};
use geo::Intersects;

pub struct CourtyardCheck {
    clearance_mm: f64,
}
impl CourtyardCheck {
    pub fn new(clearance_mm: f64) -> Self {
        Self { clearance_mm }
    }
}
impl DrcRule for CourtyardCheck {
    fn name(&self) -> &str {
        "drc_courtyard"
    }
    fn category(&self) -> DrcCategory {
        DrcCategory::Drc
    }
    fn description(&self) -> &str {
        "Check courtyard clearance between components."
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
                let bbox_a = expand_rect(&a.footprint_bbox(), self.clearance_mm);
                let bbox_b = expand_rect(&b.footprint_bbox(), self.clearance_mm);
                if bbox_a.intersects(&bbox_b) {
                    violations.push(violation(
                        Severity::Warning,
                        "DRC_CRT_001",
                        &format!(
                            "Courtyard violation: {} courtyard overlaps {}",
                            a.refdes, b.refdes,
                        ),
                        DrcCategory::Drc,
                        "drc_courtyard",
                        vec![a.refdes.0.clone(), b.refdes.0.clone()],
                        crate::rules::location_midpoint(&a.center, &b.center, None),
                        serde_json::json!({
                            "courtyard_margin_mm": self.clearance_mm,
                        }),
                    ));
                }
            }
        }
        violations
    }
}

/// Expand a Rect by `margin` on all sides.
fn expand_rect(rect: &geo::Rect<f64>, margin: f64) -> geo::Rect<f64> {
    geo::Rect::new(
        geo::Coord {
            x: rect.min().x - margin,
            y: rect.min().y - margin,
        },
        geo::Coord {
            x: rect.max().x + margin,
            y: rect.max().y + margin,
        },
    )
}
