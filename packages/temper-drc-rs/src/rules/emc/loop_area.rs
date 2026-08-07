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

#[derive(Default)]
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

            if let Some(max_area) = loop_constraint.max_area_mm2
                && area > max_area
            {
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

        violations
    }
}

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;
    use crate::board::*;
    use crate::constraints::*;
    use geo::Point;
    use std::collections::HashMap;

    fn make_board(components: Vec<Component>, nets: Vec<Net>) -> BoardState {
        BoardState {
            width_mm: 100.0,
            height_mm: 100.0,
            margin_mm: 3.0,
            electrical_components: components,
            mechanical_components: vec![],
            nets,
            net_class_rules: {
                let mut m = HashMap::new();
                m.insert(
                    NetClassName("Signal".into()),
                    NetClassRules::default(),
                );
                m
            },
            traces: vec![],
            vias: vec![],
            zones: vec![],
        }
    }

    fn make_component(refdes: &str, x: f64, y: f64) -> Component {
        Component {
            refdes: ComponentRef(refdes.into()),
            center: Point::new(x, y),
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
            footprint_polygon: None,
        }
    }

    #[cfg_attr(test, test)]
    fn loop_area_empty_board_no_violations() {
        let board = make_board(vec![], vec![]);
        let constraints = ConstraintSet {
            critical_loops: vec![LoopConstraint {
                name: "switch_loop".into(),
                nets: vec!["N1".into()],
                max_area_mm2: Some(100.0),
                weight: 1.0,
            }],
            ..Default::default()
        };
        let check = LoopAreaCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "empty board must produce 0 violations, got {}",
            violations.len()
        );
    }

    #[cfg_attr(test, test)]
    fn loop_area_under_threshold_no_violations() {
        // Two components 5mm apart → loop bbox area = 5*10 = 50mm² < 200mm² max
        let c1 = make_component("C1", 0.0, 0.0);
        let c2 = make_component("C2", 5.0, 0.0);
        let net = Net {
            name: NetName("N1".into()),
            components: vec![ComponentRef("C1".into()), ComponentRef("C2".into())],
            class: NetClassName("Signal".into()),
            rules: NetClassRules::default(),
        };
        let board = make_board(vec![c1, c2], vec![net]);
        let constraints = ConstraintSet {
            critical_loops: vec![LoopConstraint {
                name: "switch_loop".into(),
                nets: vec!["N1".into()],
                max_area_mm2: Some(200.0),
                weight: 1.0,
            }],
            ..Default::default()
        };
        let check = LoopAreaCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "loop under threshold must have 0 violations, got {}",
            violations.len()
        );
    }

    #[cfg_attr(test, test)]
    fn loop_area_over_threshold_violation() {
        // Two components 50mm apart in X, 10mm apart in Y
        // → loop bbox area = 50*10 = 500mm² > 200mm² max
        let c1 = make_component("C1", 0.0, 0.0);
        let c2 = make_component("C2", 50.0, 10.0);
        let net = Net {
            name: NetName("N1".into()),
            components: vec![ComponentRef("C1".into()), ComponentRef("C2".into())],
            class: NetClassName("Signal".into()),
            rules: NetClassRules::default(),
        };
        let board = make_board(vec![c1, c2], vec![net]);
        let constraints = ConstraintSet {
            critical_loops: vec![LoopConstraint {
                name: "switch_loop".into(),
                nets: vec!["N1".into()],
                max_area_mm2: Some(200.0),
                weight: 1.0,
            }],
            ..Default::default()
        };
        let check = LoopAreaCheck::new();
        let violations = check.check(&board, &constraints);
        assert_eq!(
            violations.len(),
            1,
            "loop over threshold must produce 1 violation"
        );
        let v = &violations[0];
        assert_eq!(v.code, "EMC_LPA_001");
        assert_eq!(v.severity, Severity::Warning);
        assert_eq!(v.category, DrcCategory::Emc);
    }

    #[cfg_attr(test, test)]
    fn loop_area_no_max_no_violations() {
        let c1 = make_component("C1", 0.0, 0.0);
        let c2 = make_component("C2", 100.0, 0.0);
        let net = Net {
            name: NetName("N1".into()),
            components: vec![ComponentRef("C1".into()), ComponentRef("C2".into())],
            class: NetClassName("Signal".into()),
            rules: NetClassRules::default(),
        };
        let board = make_board(vec![c1, c2], vec![net]);
        let constraints = ConstraintSet {
            critical_loops: vec![LoopConstraint {
                name: "switch_loop".into(),
                nets: vec!["N1".into()],
                max_area_mm2: None,
                weight: 1.0,
            }],
            ..Default::default()
        };
        let check = LoopAreaCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "no max_area must produce 0 violations, got {}",
            violations.len()
        );
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("rules::emc::loop_area::tests::loop_area_empty_board_no_violations", loop_area_empty_board_no_violations),
        ("rules::emc::loop_area::tests::loop_area_under_threshold_no_violations", loop_area_under_threshold_no_violations),
        ("rules::emc::loop_area::tests::loop_area_over_threshold_violation", loop_area_over_threshold_violation),
        ("rules::emc::loop_area::tests::loop_area_no_max_no_violations", loop_area_no_max_no_violations),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
