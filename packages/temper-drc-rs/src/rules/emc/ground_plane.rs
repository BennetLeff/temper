// EMC check: ground plane — noisy components must be within ground zones.
//
// Verifies that noisy or high-speed components (switching, power, clock, etc.)
// are positioned within zones designated as ground/return.
//
// Ported from: packages/temper-drc/src/temper_drc/checks/emc/ground_plane.py
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};

/// Keywords identifying noisy component classes that need ground plane coverage.
const NOISY_KEYWORDS: [&str; 5] = ["power", "switching", "clock", "pwm", "high_freq"];

/// Keywords identifying ground/return zones.
const GND_KEYWORDS: [&str; 3] = ["gnd", "ground", "return"];

/// Returns true if the net class is noisy (needs ground plane).
fn is_noisy(net_class: &str) -> bool {
    let lc = net_class.to_lowercase();
    NOISY_KEYWORDS.iter().any(|k| lc.contains(k))
}

/// Returns true if the zone name indicates it is a ground/return zone.
fn is_gnd_zone(zone_name: &str) -> bool {
    let lc = zone_name.to_lowercase();
    GND_KEYWORDS.iter().any(|k| lc.contains(k))
}

#[derive(Default)]
pub struct GroundPlaneCheck;

impl GroundPlaneCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for GroundPlaneCheck {
    fn name(&self) -> &str {
        "emc_ground_plane"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Emc
    }

    fn description(&self) -> &str {
        "Ensure high-di/dt or high-speed components have a ground plane return path."
    }

    fn check(&self, board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        // Identify ground zones by name keyword matching
        let gnd_zone_names: Vec<&str> = constraints
            .zones
            .iter()
            .filter(|z| is_gnd_zone(&z.name))
            .map(|z| z.name.as_str())
            .collect();

        // Check each noisy component
        for comp in &board.electrical_components {
            if !is_noisy(&comp.net_class) {
                continue;
            }

            // Check if this component's net class matches any gnd zone's net classes
            let inside_gnd = constraints.zones.iter().any(|zone| {
                if !is_gnd_zone(&zone.name) {
                    return false;
                }
                zone.net_classes.iter().any(|zc| zc.as_str() == comp.net_class.0.as_str())
            });

            if !inside_gnd {
                let layer = if comp.side == crate::board::BoardSide::Top {
                    "F.Cu"
                } else {
                    "B.Cu"
                };

                violations.push(violation(
                    Severity::Error,
                    "EMC_GND_001",
                    &format!(
                        "Noisy component {} ({}) is not placed over a ground plane.",
                        comp.refdes, comp.net_class,
                    ),
                    DrcCategory::Emc,
                    "emc_ground_plane",
                    vec![comp.refdes.0.clone()],
                    Some(crate::rules::Location {
                        x: Some(comp.center.x()),
                        y: Some(comp.center.y()),
                        layer: Some(layer.to_string()),
                    }),
                    serde_json::json!({
                        "component_class": comp.net_class,
                        "available_gnd_zones": gnd_zone_names,
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
    use std::collections::BTreeMap;

    fn make_board(components: Vec<Component>) -> BoardState {
        BoardState {
            width_mm: 100.0,
            height_mm: 100.0,
            margin_mm: 3.0,
            electrical_components: components,
            mechanical_components: vec![],
            nets: vec![],
            net_class_rules: BTreeMap::new(),
            traces: vec![],
            vias: vec![],
            zones: vec![],
        }
    }

    fn make_component(refdes: &str, x: f64, y: f64, net_class: &str) -> Component {
        Component {
            refdes: ComponentRef(refdes.into()),
            center: Point::new(x, y),
            rotation: 0.0,
            side: BoardSide::Top,
            width: 10.0,
            height: 10.0,
            net_class: NetClassName(net_class.into()),
            power_dissipation_w: None,
            package_type: PackageType::Smd,
            is_magnetic: false,
            is_electrolytic: false,
            vent_direction: None,
            footprint_polygon: None,
        }
    }

    #[cfg_attr(test, test)]
    fn ground_plane_empty_board_no_violations() {
        let board = make_board(vec![]);
        let constraints = ConstraintSet::default();
        let check = GroundPlaneCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "empty board must produce 0 violations"
        );
    }

    #[cfg_attr(test, test)]
    fn ground_plane_noisy_in_ground_zone_no_violation() {
        let comp = make_component("C1", 0.0, 0.0, "power_switching");
        let board = make_board(vec![comp]);
        let constraints = ConstraintSet {
            zones: vec![ZoneDefinition {
                name: "GND_plane".into(),
                net_classes: vec!["power_switching".into()],
            }],
            ..Default::default()
        };
        let check = GroundPlaneCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "noisy component in ground zone must have 0 violations, got {}",
            violations.len()
        );
    }

    #[cfg_attr(test, test)]
    fn ground_plane_noisy_not_in_ground_zone_violation() {
        let comp = make_component("C1", 50.0, 50.0, "power_switching");
        let board = make_board(vec![comp]);
        let constraints = ConstraintSet {
            zones: vec![ZoneDefinition {
                name: "GND_plane".into(),
                net_classes: vec!["analog".into()],
            }],
            ..Default::default()
        };
        let check = GroundPlaneCheck::new();
        let violations = check.check(&board, &constraints);
        assert_eq!(
            violations.len(),
            1,
            "noisy component without ground zone must produce 1 violation"
        );
        let v = &violations[0];
        assert_eq!(v.code, "EMC_GND_001");
        assert_eq!(v.severity, Severity::Error);
        assert_eq!(v.category, DrcCategory::Emc);
    }

    #[cfg_attr(test, test)]
    fn ground_plane_non_noisy_no_violation() {
        let comp = make_component("C1", 0.0, 0.0, "Signal");
        let board = make_board(vec![comp]);
        let constraints = ConstraintSet::default();
        let check = GroundPlaneCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "non-noisy component must produce 0 violations"
        );
    }

    #[cfg_attr(test, test)]
    fn ground_plane_multiple_zones_noisy_in_one() {
        let comp = make_component("C1", 0.0, 0.0, "clock");
        let board = make_board(vec![comp]);
        let constraints = ConstraintSet {
            zones: vec![
                ZoneDefinition {
                    name: "power_zone".into(),
                    net_classes: vec!["power".into()],
                },
                ZoneDefinition {
                    name: "GND_return".into(),
                    net_classes: vec!["clock".into()],
                },
            ],
            ..Default::default()
        };
        let check = GroundPlaneCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "noisy component in one of multiple ground zones must have 0 violations"
        );
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("rules::emc::ground_plane::tests::ground_plane_empty_board_no_violations", ground_plane_empty_board_no_violations),
        ("rules::emc::ground_plane::tests::ground_plane_noisy_in_ground_zone_no_violation", ground_plane_noisy_in_ground_zone_no_violation),
        ("rules::emc::ground_plane::tests::ground_plane_noisy_not_in_ground_zone_violation", ground_plane_noisy_not_in_ground_zone_violation),
        ("rules::emc::ground_plane::tests::ground_plane_non_noisy_no_violation", ground_plane_non_noisy_no_violation),
        ("rules::emc::ground_plane::tests::ground_plane_multiple_zones_noisy_in_one", ground_plane_multiple_zones_noisy_in_one),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
