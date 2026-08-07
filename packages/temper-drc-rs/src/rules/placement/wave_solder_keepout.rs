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
pub(crate) fn rect_edge_distance(r1: &geo::Rect<f64>, r2: &geo::Rect<f64>) -> f64 {
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

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;
    use crate::board::*;
    use crate::constraints::*;
    use geo::Point;
    use std::collections::HashMap;

    fn make_board(components: Vec<Component>) -> BoardState {
        BoardState {
            width_mm: 100.0,
            height_mm: 100.0,
            margin_mm: 3.0,
            electrical_components: components,
            mechanical_components: vec![],
            nets: vec![],
            net_class_rules: HashMap::new(),
            traces: vec![],
            vias: vec![],
            zones: vec![],
        }
    }

    fn make_component(
        refdes: &str,
        x: f64,
        y: f64,
        side: BoardSide,
        pkg: PackageType,
    ) -> Component {
        Component {
            refdes: ComponentRef(refdes.into()),
            center: Point::new(x, y),
            rotation: 0.0,
            side,
            width: 10.0,
            height: 10.0,
            net_class: NetClassName("Signal".into()),
            power_dissipation_w: None,
            package_type: pkg,
            is_magnetic: false,
            is_electrolytic: false,
            vent_direction: None,
            footprint_polygon: None,
        }
    }

    #[cfg_attr(test, test)]
    fn wave_solder_empty_board_no_violations() {
        let board = make_board(vec![]);
        let constraints = ConstraintSet::default();
        let check = WaveSolderKeepoutCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(violations.is_empty());
    }

    #[cfg_attr(test, test)]
    fn wave_solder_no_bottom_smd_no_violations() {
        // Top-side SMD and a THT — no bottom SMD, so no violations
        let smd = make_component("C1", 0.0, 0.0, BoardSide::Top, PackageType::Smd);
        let tht = make_component("C2", 6.0, 0.0, BoardSide::Top, PackageType::Tht);
        let board = make_board(vec![smd, tht]);
        let constraints = ConstraintSet::default();
        let check = WaveSolderKeepoutCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "no bottom SMD must produce 0 violations"
        );
    }

    #[cfg_attr(test, test)]
    fn wave_solder_bottom_smd_too_close_to_tht_violation() {
        // Bottom SMD at (0,0), THT at (8,0)
        // edge_distance = 8 - 5 - 5 = -2mm (overlapping) < KEEPOUT_MM
        let smd = make_component("C1", 0.0, 0.0, BoardSide::Bottom, PackageType::Smd);
        let tht = make_component("C2", 8.0, 0.0, BoardSide::Top, PackageType::Tht);
        let board = make_board(vec![smd, tht]);
        let constraints = ConstraintSet::default();
        let check = WaveSolderKeepoutCheck::new();
        let violations = check.check(&board, &constraints);
        assert_eq!(
            violations.len(),
            1,
            "bottom SMD too close to THT must produce 1 violation"
        );
        let v = &violations[0];
        assert_eq!(v.code, "DFM_WSK_001");
        assert_eq!(v.severity, Severity::Error);
    }

    #[cfg_attr(test, test)]
    fn wave_solder_bottom_smd_far_enough_no_violation() {
        // Bottom SMD at (0,0), THT at (30,0)
        // edge_distance = 30 - 5 - 5 = 20mm > 5mm KEEPOUT
        let smd = make_component("C1", 0.0, 0.0, BoardSide::Bottom, PackageType::Smd);
        let tht = make_component("C2", 30.0, 0.0, BoardSide::Top, PackageType::Tht);
        let board = make_board(vec![smd, tht]);
        let constraints = ConstraintSet::default();
        let check = WaveSolderKeepoutCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "far apart must produce 0 violations, got {}",
            violations.len()
        );
    }

    #[cfg_attr(test, test)]
    fn rect_edge_distance_overlapping_zero() {
        let r1 = geo::Rect::new(geo::Coord { x: 0.0, y: 0.0 }, geo::Coord { x: 10.0, y: 10.0 });
        let r2 = geo::Rect::new(geo::Coord { x: 5.0, y: 5.0 }, geo::Coord { x: 15.0, y: 15.0 });
        let dist = rect_edge_distance(&r1, &r2);
        assert!((dist - 0.0).abs() < 1e-9, "overlapping rects distance must be 0");
    }

    #[cfg_attr(test, test)]
    fn rect_edge_distance_separated() {
        let r1 = geo::Rect::new(geo::Coord { x: 0.0, y: 0.0 }, geo::Coord { x: 10.0, y: 10.0 });
        let r2 = geo::Rect::new(geo::Coord { x: 15.0, y: 0.0 }, geo::Coord { x: 25.0, y: 10.0 });
        let dist = rect_edge_distance(&r1, &r2);
        assert!((dist - 5.0).abs() < 1e-9, "separated by 5mm must report 5mm");
    }

    #[cfg_attr(test, test)]
    fn expand_rect_adds_margin() {
        let r = geo::Rect::new(geo::Coord { x: 0.0, y: 0.0 }, geo::Coord { x: 10.0, y: 10.0 });
        let expanded = expand_rect(&r, 2.0);
        assert!((expanded.min().x + 2.0).abs() < 1e-9);
        assert!((expanded.min().y + 2.0).abs() < 1e-9);
        assert!((expanded.max().x - 12.0).abs() < 1e-9);
        assert!((expanded.max().y - 12.0).abs() < 1e-9);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("rules::placement::wave_solder_keepout::tests::wave_solder_empty_board_no_violations", wave_solder_empty_board_no_violations),
        ("rules::placement::wave_solder_keepout::tests::wave_solder_no_bottom_smd_no_violations", wave_solder_no_bottom_smd_no_violations),
        ("rules::placement::wave_solder_keepout::tests::wave_solder_bottom_smd_too_close_to_tht_violation", wave_solder_bottom_smd_too_close_to_tht_violation),
        ("rules::placement::wave_solder_keepout::tests::wave_solder_bottom_smd_far_enough_no_violation", wave_solder_bottom_smd_far_enough_no_violation),
        ("rules::placement::wave_solder_keepout::tests::rect_edge_distance_overlapping_zero", rect_edge_distance_overlapping_zero),
        ("rules::placement::wave_solder_keepout::tests::rect_edge_distance_separated", rect_edge_distance_separated),
        ("rules::placement::wave_solder_keepout::tests::expand_rect_adds_margin", expand_rect_adds_margin),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
