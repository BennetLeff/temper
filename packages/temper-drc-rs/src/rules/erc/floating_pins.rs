// ERC check: floating pins — every component must belong to at least one net.
//
// Components not referenced in any net are flagged as warnings.
//
// Ported from: packages/temper-drc/src/temper_drc/checks/erc/floating_pins.py
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use std::collections::HashSet;

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};

#[derive(Default)]
pub struct FloatingPinsCheck;

impl FloatingPinsCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for FloatingPinsCheck {
    fn name(&self) -> &str {
        "erc_floating_pins"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Erc
    }

    fn description(&self) -> &str {
        "Identify components that are not connected to any net."
    }

    fn check(&self, board: &BoardState, _constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        // Build set of all connected component refdes
        let connected: HashSet<&str> = board
            .nets
            .iter()
            .flat_map(|net| net.components.iter().map(|c| &*c.0))
            .collect();

        // Check each electrical component — mechanical components are
        // in board.mechanical_components and not visible here.
        for comp in &board.electrical_components {
            if !connected.contains(&*comp.refdes) {
                let layer = if comp.side == crate::board::BoardSide::Top {
                    "F.Cu"
                } else {
                    "B.Cu"
                };

                violations.push(violation(
                    Severity::Warning,
                    "ERC_FLT_001",
                    &format!(
                        "Component '{}' is not connected to any net (floating).",
                        comp.refdes,
                    ),
                    DrcCategory::Erc,
                    "erc_floating_pins",
                    vec![comp.refdes.0.clone()],
                    Some(crate::rules::Location {
                        x: Some(comp.center.x()),
                        y: Some(comp.center.y()),
                        layer: Some(layer.to_string()),
                    }),
                    serde_json::json!({
                        "ref": comp.refdes,
                    }),
                ));
            }
        }

        violations
    }
}

#[cfg(any(test, feature = "wasm-test-registry"))]
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
            net_class_rules: HashMap::new(),
            traces: vec![],
            vias: vec![],
            zones: vec![],
        }
    }

    fn make_component(refdes: &str) -> Component {
        Component {
            refdes: ComponentRef(refdes.into()),
            center: Point::new(0.0, 0.0),
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
    fn floating_pins_empty_board_no_violations() {
        let board = make_board(vec![], vec![]);
        let constraints = ConstraintSet::default();
        let check = FloatingPinsCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "empty board must produce 0 violations"
        );
    }

    #[cfg_attr(test, test)]
    fn floating_pins_connected_component_no_violation() {
        let c1 = make_component("C1");
        let net = Net {
            name: NetName("N1".into()),
            components: vec![ComponentRef("C1".into())],
            class: NetClassName("Signal".into()),
            rules: NetClassRules::default(),
        };
        let board = make_board(vec![c1], vec![net]);
        let constraints = ConstraintSet::default();
        let check = FloatingPinsCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "connected component must produce 0 violations, got {}",
            violations.len()
        );
    }

    #[cfg_attr(test, test)]
    fn floating_pins_unconnected_component_violation() {
        let c1 = make_component("C1");
        let board = make_board(vec![c1], vec![]);
        let constraints = ConstraintSet::default();
        let check = FloatingPinsCheck::new();
        let violations = check.check(&board, &constraints);
        assert_eq!(
            violations.len(),
            1,
            "unconnected component must produce 1 violation"
        );
        let v = &violations[0];
        assert_eq!(v.code, "ERC_FLT_001");
        assert_eq!(v.severity, Severity::Warning);
        assert_eq!(v.category, DrcCategory::Erc);
    }

    #[cfg_attr(test, test)]
    fn floating_pins_all_components_connected_no_violations() {
        let c1 = make_component("C1");
        let c2 = make_component("C2");
        let c3 = make_component("C3");
        let net1 = Net {
            name: NetName("N1".into()),
            components: vec![ComponentRef("C1".into()), ComponentRef("C2".into())],
            class: NetClassName("Signal".into()),
            rules: NetClassRules::default(),
        };
        let net2 = Net {
            name: NetName("N2".into()),
            components: vec![ComponentRef("C3".into())],
            class: NetClassName("Signal".into()),
            rules: NetClassRules::default(),
        };
        let board = make_board(vec![c1, c2, c3], vec![net1, net2]);
        let constraints = ConstraintSet::default();
        let check = FloatingPinsCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "all connected must produce 0 violations, got {}",
            violations.len()
        );
    }

    #[cfg_attr(test, test)]
    fn floating_pins_mixed_connected_and_floating() {
        let c1 = make_component("C1");
        let c2 = make_component("C2");
        let c3 = make_component("C3");
        let net = Net {
            name: NetName("N1".into()),
            components: vec![ComponentRef("C1".into())],
            class: NetClassName("Signal".into()),
            rules: NetClassRules::default(),
        };
        let board = make_board(vec![c1, c2, c3], vec![net]);
        let constraints = ConstraintSet::default();
        let check = FloatingPinsCheck::new();
        let violations = check.check(&board, &constraints);
        assert_eq!(
            violations.len(),
            2,
            "2 unconnected components must produce 2 violations"
        );
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("rules::erc::floating_pins::tests::floating_pins_empty_board_no_violations", floating_pins_empty_board_no_violations),
        ("rules::erc::floating_pins::tests::floating_pins_connected_component_no_violation", floating_pins_connected_component_no_violation),
        ("rules::erc::floating_pins::tests::floating_pins_unconnected_component_violation", floating_pins_unconnected_component_violation),
        ("rules::erc::floating_pins::tests::floating_pins_all_components_connected_no_violations", floating_pins_all_components_connected_no_violations),
        ("rules::erc::floating_pins::tests::floating_pins_mixed_connected_and_floating", floating_pins_mixed_connected_and_floating),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
