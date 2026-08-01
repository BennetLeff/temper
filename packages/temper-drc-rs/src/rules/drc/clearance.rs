// DRC check: component-to-component clearance.
//
// Iterates all component pairs from board.all_components(), computes
// edge-to-edge distance via edge_distance_to(), looks up the required
// minimum clearance from constraints.clearances (matching net classes),
// and emits DRC_CLR_001 for any pair below the threshold.
//
// Ported from: packages/temper-drc/src/temper_drc/checks/drc/clearance.py
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use std::collections::HashMap;

use crate::board::{BoardState, Component, NetClassName, NetClassRules};
use crate::constraints::ConstraintSet;
use crate::rules::{clearance_between, violation, DrcCategory, DrcRule, Severity, Violation};

/// Look up (with memoization) the required clearance between two components'
/// net classes. The cache key is normalized (class_a <= class_b) because
/// clearance_between() is symmetric, so each unordered class pair is computed
/// once regardless of which component order is encountered first.
fn required_for(
    a: &Component,
    b: &Component,
    cache: &mut HashMap<(NetClassName, NetClassName), f64>,
    constraints: &ConstraintSet,
    net_class_rules: &HashMap<NetClassName, NetClassRules>,
) -> f64 {
    let key = if a.net_class <= b.net_class {
        (a.net_class.clone(), b.net_class.clone())
    } else {
        (b.net_class.clone(), a.net_class.clone())
    };
    *cache.entry(key).or_insert_with(|| {
        clearance_between(constraints, net_class_rules, &a.net_class, &b.net_class)
    })
}

#[derive(Default)]
pub struct ClearanceCheck;

impl ClearanceCheck {
    pub fn new() -> Self {
        Self
    }
}
impl DrcRule for ClearanceCheck {
    fn name(&self) -> &str {
        "drc_clearance"
    }
    fn category(&self) -> DrcCategory {
        DrcCategory::Drc
    }
    fn description(&self) -> &str {
        "Check component-to-component clearance against net class rules."
    }
    fn check(&self, board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();
        let components: Vec<&crate::board::Component> = board.all_components().collect();

        // Precompute each component's footprint bbox once. The bbox distance
        // between two components is a lower bound on the true polygon
        // edge-to-edge distance (a polygon is contained in its width/height
        // bbox; board.rs:590-614 derives this), so pairs whose bboxes are
        // already farther apart than the required clearance can never violate
        // and skip the expensive full-polygon edge sweep.
        let bboxes: Vec<geo::Rect<f64>> = components.iter().map(|c| c.footprint_bbox()).collect();
        let mut required_cache: HashMap<(NetClassName, NetClassName), f64> = HashMap::new();

        for i in 0..components.len() {
            for j in (i + 1)..components.len() {
                let a = components[i];
                let b = components[j];
                let required = required_for(
                    a,
                    b,
                    &mut required_cache,
                    constraints,
                    &board.net_class_rules,
                );

                let ba = &bboxes[i];
                let bb = &bboxes[j];
                let bbox_dist = {
                    let dx = (ba.min().x - bb.max().x)
                        .max(0.0)
                        .max((bb.min().x - ba.max().x).max(0.0));
                    let dy = (ba.min().y - bb.max().y)
                        .max(0.0)
                        .max((bb.min().y - ba.max().y).max(0.0));
                    dx.hypot(dy)
                };
                if bbox_dist > required {
                    continue;
                }

                let dist = a.edge_distance_to(b);
                if dist <= required {
                    violations.push(violation(
                        Severity::Critical,
                        "DRC_CLR_001",
                        &format!(
                            "Clearance violation: {} ({}) to {} ({}) = {:.3}mm, required {:.3}mm",
                            a.refdes, a.net_class, b.refdes, b.net_class, dist, required,
                        ),
                        DrcCategory::Drc,
                        "drc_clearance",
                        vec![a.refdes.0.clone(), b.refdes.0.clone()],
                        crate::rules::location_midpoint(&a.center, &b.center, None),
                        serde_json::json!({
                            "edge_distance_mm": dist,
                            "required_clearance_mm": required,
                        }),
                    ));
                }
            }
        }
        violations
    }
}

#[cfg(test)]
mod tests {
    use super::*;
    use crate::board::*;
    use crate::constraints::*;
    use geo::polygon;
    use std::collections::HashMap;

    #[test]
    fn clearance_at_exact_threshold_flagged() {
        let board = BoardState {
            width_mm: 100.0,
            height_mm: 100.0,
            margin_mm: 3.0,
            electrical_components: vec![
                Component {
                    refdes: ComponentRef("C1".into()),
                    center: geo::Point::new(0.0, 0.0),
                    rotation: 0.0,
                    side: BoardSide::Top,
                    width: 10.0,
                    height: 10.0,
                    net_class: NetClassName("Signal".into()),
                    power_dissipation_w: None,
                    package_type: PackageType::Smd,
                    is_magnetic: false,
                    is_electrolytic: false,
                    vent_direction: None,
                    footprint_polygon: Some(polygon![
                        (x: -5.0, y: -5.0),
                        (x: 5.0, y: -5.0),
                        (x: 5.0, y: 5.0),
                        (x: -5.0, y: 5.0),
                    ]),
                },
                Component {
                    refdes: ComponentRef("C2".into()),
                    center: geo::Point::new(11.0, 0.0),
                    rotation: 0.0,
                    side: BoardSide::Top,
                    width: 10.0,
                    height: 10.0,
                    net_class: NetClassName("Signal".into()),
                    power_dissipation_w: None,
                    package_type: PackageType::Smd,
                    is_magnetic: false,
                    is_electrolytic: false,
                    vent_direction: None,
                    footprint_polygon: Some(polygon![
                        (x: 6.0, y: -5.0),
                        (x: 16.0, y: -5.0),
                        (x: 16.0, y: 5.0),
                        (x: 6.0, y: 5.0),
                    ]),
                },
            ],
            mechanical_components: vec![],
            nets: vec![],
            net_class_rules: {
                let mut m = HashMap::new();
                m.insert(
                    NetClassName("Signal".into()),
                    NetClassRules {
                        clearance_mm: 1.0,
                        ..NetClassRules::default()
                    },
                );
                m
            },
            traces: vec![],
            vias: vec![],
            zones: vec![],
        };
        // C1 right edge at x=5, C2 left edge at x=6 → gap = 1mm exactly at threshold
        let constraints = ConstraintSet {
            clearances: vec![ClearanceRule {
                from_class: "Signal".into(),
                to_class: "Signal".into(),
                clearance_mm: 1.0,
                description: String::new(),
            }],
            hv_clearance_mm: 10.0,
            board_width: 100.0,
            board_height: 100.0,
            ..Default::default()
        };
        let check = ClearanceCheck::new();
        let violations = check.check(&board, &constraints);
        // At exactly the threshold (gap = clearance), should fire
        assert!(
            !violations.is_empty(),
            "exact-threshold gap of 1mm must fire when clearance = 1mm"
        );
    }
}
