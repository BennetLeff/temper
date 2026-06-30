// Routing check: stitching via density in ground copper zones.
//
// Computes max_spacing_mm = 15.0 mm (λ/20 at 100 MHz). For each ground-connected
// copper zone, finds all vias whose net contains "GND" (or the zone net contains
// "GND").  Checks the maximum gap between adjacent ground vias within each zone;
// if the gap exceeds max_spacing_mm, emits a WARNING.
//
// Degenerate case: 0 ground vias → empty violations vec.
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};

use geo::{Coord, EuclideanDistance, Intersects, Point};

/// Maximum allowed spacing between adjacent ground-stitching vias (mm).
///
/// λ/20 at 100 MHz ≈ 15 mm  (free-space wavelength 3e8 / 100e6 = 3.0 m).
const MAX_SPACING_MM: f64 = 15.0;

/// Returns true if the net name indicates a ground connection.
fn is_gnd_net(net: &str) -> bool {
    let lc = net.to_lowercase();
    lc.contains("gnd")
}

pub struct StitchingViaDensityCheck;

impl StitchingViaDensityCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for StitchingViaDensityCheck {
    fn name(&self) -> &str {
        "routing_stitching_via_density"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Emc
    }

    fn description(&self) -> &str {
        "Check that ground-stitching vias in copper zones are spaced ≤ λ/20 (15 mm @ 100 MHz)."
    }

    fn check(&self, board: &BoardState, _constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        // Collect ground vias: vias whose net contains "GND".
        let gnd_vias: Vec<Point<f64>> = board
            .vias
            .iter()
            .filter(|v| is_gnd_net(&v.net))
            .map(|v| v.position)
            .collect();

        // Degenerate: no ground vias → nothing to check.
        if gnd_vias.is_empty() {
            return violations;
        }

        // Examine each copper zone that is ground-connected.
        for zone in &board.zones {
            if !is_gnd_net(&zone.net) {
                continue;
            }

            // Find all ground vias that lie inside this zone polygon.
            // Use Coord for intersects check since Polygon does not
            // directly implement Intersects<Point>.
            let zone_vias: Vec<&Point<f64>> = gnd_vias
                .iter()
                .filter(|p| zone.polygon.intersects(&Coord { x: p.x(), y: p.y() }))
                .collect();

            if zone_vias.len() < 2 {
                // Need at least 2 vias to measure a gap.
                continue;
            }

            // Compute the maximum nearest-neighbour gap among the vias in this
            // zone by measuring the Euclidean distance between every pair and
            // tracking the largest one.
            let mut max_gap = 0.0_f64;
            for i in 0..zone_vias.len() {
                for j in (i + 1)..zone_vias.len() {
                    let d = zone_vias[i].euclidean_distance(zone_vias[j]);
                    if d > max_gap {
                        max_gap = d;
                    }
                }
            }

            // Find the bounding centroid of the zone vias for the location
            // reported with the violation.
            let centroid_x: f64 = zone_vias.iter().map(|p| p.x()).sum::<f64>() / zone_vias.len() as f64;
            let centroid_y: f64 = zone_vias.iter().map(|p| p.y()).sum::<f64>() / zone_vias.len() as f64;

            if max_gap > MAX_SPACING_MM {
                violations.push(violation(
                    Severity::Warning,
                    "ROUTING_STITCH_001",
                    &format!(
                        "Ground zone '{}' on {} has via gap {:.2} mm exceeding max {} mm.",
                        zone.net, zone.layer, max_gap, MAX_SPACING_MM,
                    ),
                    DrcCategory::Emc,
                    "routing_stitching_via_density",
                    vec![zone.net.0.clone()],
                    Some(crate::rules::Location {
                        x: Some(centroid_x),
                        y: Some(centroid_y),
                        layer: Some(zone.layer.clone()),
                    }),
                    serde_json::json!({
                        "max_gap_mm": max_gap,
                        "max_spacing_mm": MAX_SPACING_MM,
                        "via_count": zone_vias.len(),
                        "zone_net": zone.net,
                    }),
                ));
            }
        }

        violations
    }
}
