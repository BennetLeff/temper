// Placement check: wave solder keepout.
//
// Bottom-side SMD components must be placed >5 mm away from THT (through-hole)
// pads. If no bottom-side SMD components exist, zero violations are returned.
//
// Origin: U6 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::{BoardSide, BoardState, PackageType};
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};

/// Minimum keepout distance between bottom-side SMD and THT pads (mm).
const KEEPOUT_MM: f64 = 5.0;

pub struct WaveSolderKeepoutCheck;

impl WaveSolderKeepoutCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for WaveSolderKeepoutCheck {
    fn name(&self) -> &str {
        "placement_wave_solder_keepout"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Dfm
    }

    fn description(&self) -> &str {
        "Bottom-side SMD components must be >5 mm from THT pads."
    }

    fn check(&self, board: &BoardState, _constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        // Collect bottom-side SMD components.
        let bottom_smd: Vec<_> = board
            .components
            .iter()
            .filter(|c| c.side == BoardSide::Bottom && c.package_type != PackageType::Tht)
            .collect();

        // Collect THT components (top or bottom — THT goes through all layers).
        let tht_components: Vec<_> = board
            .components
            .iter()
            .filter(|c| c.package_type == PackageType::Tht)
            .collect();

        if bottom_smd.is_empty() || tht_components.is_empty() {
            return violations;
        }

        for smd in &bottom_smd {
            for tht in &tht_components {
                let dist = smd.edge_distance_to(tht);
                if dist < KEEPOUT_MM {
                    violations.push(violation(
                        Severity::Error,
                        "DFM_WSK_001",
                        &format!(
                            "Bottom-side SMD {} is {:.3} mm from THT pad {} (< {} mm)",
                            smd.refdes, dist, tht.refdes, KEEPOUT_MM
                        ),
                        DrcCategory::Dfm,
                        "placement_wave_solder_keepout",
                        vec![smd.refdes.clone(), tht.refdes.clone()],
                        Some(crate::rules::Location {
                            x: Some((smd.center.x() + tht.center.x()) / 2.0),
                            y: Some((smd.center.y() + tht.center.y()) / 2.0),
                            layer: Some("B.Cu".to_string()),
                        }),
                        serde_json::json!({
                            "distance_mm": dist,
                            "required_mm": KEEPOUT_MM,
                            "bottom_smd": smd.refdes,
                            "tht_component": tht.refdes,
                        }),
                    ));
                }
            }
        }

        violations
    }
}
