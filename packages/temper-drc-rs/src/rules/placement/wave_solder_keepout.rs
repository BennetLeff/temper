// Placement check: wave solder keepout.
//
// Bottom-side SMD components must be placed >5 mm away from THT (through-hole)
// pads. If no bottom-side SMD components exist, zero violations are returned.
//
// Origin: U6 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::{BoardSide, BoardState, Component, PackageType};
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};

/// Minimum keepout distance between bottom-side SMD and THT pads (mm).
const KEEPOUT_MM: f64 = 5.0;

#[derive(Default)]
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

        // Collect bottom-side SMD components (all components — mechanical too).
        let all_comps: Vec<&Component> = board.all_components().collect();
        let bottom_smd: Vec<&&Component> = all_comps
            .iter()
            .filter(|c| c.side == BoardSide::Bottom && c.package_type != PackageType::Tht)
            .collect();

        // Collect THT components (all).
        let tht_components: Vec<&&Component> = all_comps
            .iter()
            .filter(|c| c.package_type == PackageType::Tht)
            .collect();

        if bottom_smd.is_empty() || tht_components.is_empty() {
            return violations;
        }

        // Precompute each component's bbox expanded by KEEPOUT_MM. The
        // distance between expanded bboxes is a lower bound on the true
        // polygon edge-to-edge distance (expanded bbox ⊇ footprint bbox ⊇
        // polygon, so the min over a superset of point pairs is ≤ the polygon
        // distance; board.rs:590-614), so a pair whose expanded bboxes are
        // ≥ KEEPOUT_MM apart can never violate and skips the full
        // edge_distance_to polygon sweep.
        let smd_bboxes: Vec<geo::Rect<f64>> = bottom_smd
            .iter()
            .map(|c| expand_rect(&c.footprint_bbox(), KEEPOUT_MM))
            .collect();
        let tht_bboxes: Vec<geo::Rect<f64>> = tht_components
            .iter()
            .map(|c| expand_rect(&c.footprint_bbox(), KEEPOUT_MM))
            .collect();

        for (s_idx, smd) in bottom_smd.iter().enumerate() {
            for (t_idx, tht) in tht_components.iter().enumerate() {
                if rect_edge_distance(&smd_bboxes[s_idx], &tht_bboxes[t_idx]) >= KEEPOUT_MM {
                    continue;
                }
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
                        vec![smd.refdes.0.clone(), tht.refdes.0.clone()],
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

/// Expand a Rect by `margin` on all sides.
///
/// Local copy of the helper in drc/courtyard.rs (that module is private);
/// kept in sync — bbox expansion must be identical for both rules.
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

/// Minimum Euclidean distance between two axis-aligned rectangles.
///
/// Mirror of the (private) board::rect_edge_distance — same formula, so the
/// gate compares against the exact same distance the bbox fallback path of
/// edge_distance_to() would report.
fn rect_edge_distance(r1: &geo::Rect<f64>, r2: &geo::Rect<f64>) -> f64 {
    let dx = if r1.max().x < r2.min().x {
        r2.min().x - r1.max().x
    } else if r2.max().x < r1.min().x {
        r1.min().x - r2.max().x
    } else {
        0.0
    };
    let dy = if r1.max().y < r2.min().y {
        r2.min().y - r1.max().y
    } else if r2.max().y < r1.min().y {
        r1.min().y - r2.max().y
    } else {
        0.0
    };
    (dx * dx + dy * dy).sqrt()
}
