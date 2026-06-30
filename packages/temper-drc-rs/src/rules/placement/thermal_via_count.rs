// Placement check: thermal via count.
//
// For each Component where power_dissipation_w is Some(x) and x > 0:
// required_vias = (x * 0.7).ceil() as u32.
// Count actual vias from board.vias within component footprint.
// If board.vias is empty → skip, return empty vec (placement-time check).
// If actual < required, emit CRITICAL violation: code DRC_THV_001.
// 0 power components → empty vec.
//
// Origin: U6 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::{BoardState, NetName};
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};

pub struct ThermalViaCountCheck;

impl ThermalViaCountCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for ThermalViaCountCheck {
    fn name(&self) -> &str {
        "placement_thermal_via_count"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Drc
    }

    fn description(&self) -> &str {
        "Validate sufficient thermal vias for power-dissipating components."
    }

    fn check(&self, board: &BoardState, _constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        // Placement-time: no vias yet → skip (empty vec).
        if board.vias.is_empty() {
            return violations;
        }

        for comp in &board.electrical_components {
            let power = match comp.power_dissipation_w {
                Some(p) if p > 0.0 => p,
                _ => continue,
            };

            let required = (power * 0.7).ceil() as u32;

            // Count vias within this component's footprint bounding box
            // that belong to the same net as the component.
            let bbox = comp.footprint_bbox();
            let comp_nets: Vec<&NetName> = board
                .nets
                .iter()
                .filter(|net| net.components.iter().any(|r| r == &comp.refdes))
                .map(|net| &net.name)
                .collect();

            let actual = board
                .vias
                .iter()
                .filter(|v| {
                    v.position.x() >= bbox.min().x
                        && v.position.x() <= bbox.max().x
                        && v.position.y() >= bbox.min().y
                        && v.position.y() <= bbox.max().y
                        && comp_nets.iter().any(|cn| cn.0 == v.net.0)
                })
                .count() as u32;

            if actual < required {
                violations.push(violation(
                    Severity::Critical,
                    "DRC_THV_001",
                    &format!(
                        "{}: requires {} thermal vias (dissipating {:.2} W) but found {}",
                        comp.refdes, required, power, actual
                    ),
                    DrcCategory::Drc,
                    "placement_thermal_via_count",
                    vec![
                        comp.refdes.0.clone(),
                        format!("actual={}", actual),
                        format!("required={}", required),
                    ],
                    Some(crate::rules::Location {
                        x: Some(comp.center.x()),
                        y: Some(comp.center.y()),
                        layer: Some(match comp.side {
                            crate::board::BoardSide::Top => "F.Cu".to_string(),
                            crate::board::BoardSide::Bottom => "B.Cu".to_string(),
                        }),
                    }),
                    serde_json::json!({
                        "power_dissipation_w": power,
                        "required_vias": required,
                        "actual_vias": actual,
                        "deficit": required - actual,
                    }),
                ));
            }
        }

        violations
    }
}
