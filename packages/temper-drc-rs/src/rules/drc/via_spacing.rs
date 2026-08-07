// DRC check: via-to-via spacing.
//
// For each via pair, computes edge-to-edge distance (center distance minus
// sum of radii). Minimum spacing = max(via1.pad, via2.pad) with a floor of
// 0.6mm. Emits DRC_VIA_001 CRITICAL.  Degenerate: 0 vias → empty vec.
//
// Ported from: packages/temper-drc/src/temper_drc/checks/drc/via_spacing.py
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};
use geo::EuclideanDistance;

/// Default minimum via spacing in mm (used when via pads are very small).
const DEFAULT_VIA_SPACING_MM: f64 = 0.6;

#[derive(Default)]
pub struct ViaSpacingCheck;

impl ViaSpacingCheck {
    pub fn new() -> Self {
        Self
    }
}
impl DrcRule for ViaSpacingCheck {
    fn name(&self) -> &str {
        "drc_via_spacing"
    }
    fn category(&self) -> DrcCategory {
        DrcCategory::Drc
    }
    fn description(&self) -> &str {
        "Check via-to-via spacing against pad diameters."
    }
    fn check(&self, board: &BoardState, _constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();
        let vias = &board.vias;

        // Half-pad per via, hoisted out of the pair loop (used in every pair).
        let half_pads: Vec<f64> = vias.iter().map(|v| v.pad / 2.0).collect();

        for i in 0..vias.len() {
            for j in (i + 1)..vias.len() {
                let va = &vias[i];
                let vb = &vias[j];

                let min_spacing = va.pad.max(vb.pad).max(DEFAULT_VIA_SPACING_MM);

                // Decision identity: edge_to_edge < min_spacing
                //   ⇔ center_dist - half_sum < min_spacing
                //   ⇔ sqrt(dx²+dy²) < half_sum + min_spacing
                //   ⇔ dx²+dy² < (half_sum + min_spacing)²   (all terms ≥ 0)
                // Squared-space comparison avoids the sqrt for every pair;
                // exact values are recomputed on the violation path only.
                let dx = va.position.x() - vb.position.x();
                let dy = va.position.y() - vb.position.y();
                let t = (half_pads[i] + half_pads[j]) + min_spacing;
                if dx * dx + dy * dy >= t * t {
                    continue;
                }

                // Violation path: recompute exact values for the message.
                let center_dist = va.position.euclidean_distance(&vb.position);
                let edge_to_edge = center_dist - (va.pad / 2.0 + vb.pad / 2.0);

                violations.push(violation(
                    Severity::Critical,
                    "DRC_VIA_001",
                    &format!(
                        "Via spacing violation: via on {} (net {}) to via on {} (net {}): edge-to-edge = {:.3}mm, required {:.3}mm",
                        va.from_layer, va.net, vb.from_layer, vb.net, edge_to_edge, min_spacing,
                    ),
                    DrcCategory::Drc,
                    "drc_via_spacing",
                    vec![va.net.0.clone(), vb.net.0.clone()],
                    crate::rules::location_midpoint(&va.position, &vb.position, None),
                    serde_json::json!({
                        "edge_to_edge_mm": edge_to_edge,
                        "center_distance_mm": center_dist,
                        "min_spacing_mm": min_spacing,
                        "va_pad_mm": va.pad,
                        "vb_pad_mm": vb.pad,
                    }),
                ));
            }
        }
        violations
    }
}
