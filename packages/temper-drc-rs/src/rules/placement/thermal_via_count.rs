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

#[derive(Default)]
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

#[cfg(any(test, feature = "wasm-registry"))]
#[allow(dead_code, unused_imports, clippy::unwrap_used, clippy::expect_used)]
pub(crate) mod tests {
    use super::*;
    use crate::board::*;
    use crate::constraints::*;
    use geo::Point;
    use std::collections::BTreeMap;

    fn make_board(components: Vec<Component>, vias: Vec<Via>, nets: Vec<Net>) -> BoardState {
        BoardState {
            width_mm: 100.0,
            height_mm: 100.0,
            margin_mm: 3.0,
            electrical_components: components,
            mechanical_components: vec![],
            nets,
            net_class_rules: BTreeMap::new(),
            traces: vec![],
            vias,
            zones: vec![],
        }
    }

    fn make_component(
        refdes: &str,
        x: f64,
        y: f64,
        power_w: Option<f64>,
        net_class: &str,
    ) -> Component {
        Component {
            refdes: ComponentRef(refdes.into()),
            center: Point::new(x, y),
            rotation: 0.0,
            side: BoardSide::Top,
            width: 20.0,
            height: 20.0,
            net_class: NetClassName(net_class.into()),
            power_dissipation_w: power_w,
            package_type: PackageType::Smd,
            is_magnetic: false,
            is_electrolytic: false,
            vent_direction: None,
            footprint_polygon: None,
        }
    }

    fn make_via(x: f64, y: f64, net: &str) -> Via {
        Via {
            net: NetName(net.into()),
            position: Point::new(x, y),
            drill: 0.3,
            pad: 0.6,
            from_layer: "F.Cu".into(),
            to_layer: "B.Cu".into(),
        }
    }

    #[cfg_attr(test, test)]
    fn thermal_via_count_empty_vias_no_violations() {
        // Early return: no vias → skip
        let comp = make_component("C1", 0.0, 0.0, Some(10.0), "power");
        let board = make_board(vec![comp], vec![], vec![]);
        let constraints = ConstraintSet::default();
        let check = ThermalViaCountCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "empty vias must produce 0 violations (placement-time skip)"
        );
    }

    #[cfg_attr(test, test)]
    fn thermal_via_count_no_power_component_no_violation() {
        let comp = make_component("C1", 0.0, 0.0, None, "Signal");
        let via = make_via(0.0, 0.0, "Signal");
        let board = make_board(vec![comp], vec![via], vec![]);
        let constraints = ConstraintSet::default();
        let check = ThermalViaCountCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "no-power component must produce 0 violations"
        );
    }

    #[cfg_attr(test, test)]
    fn thermal_via_count_insufficient_vias_violation() {
        // 10W → required = ceil(10 * 0.7) = ceil(7.0) = 7 vias
        // 1 via → insufficient
        let comp = make_component("C1", 0.0, 0.0, Some(10.0), "power");
        let via = make_via(0.0, 0.0, "power");
        let net = Net {
            name: NetName("power".into()),
            components: vec![ComponentRef("C1".into())],
            class: NetClassName("power".into()),
            rules: NetClassRules::default(),
        };
        let board = make_board(vec![comp], vec![via], vec![net]);
        let constraints = ConstraintSet::default();
        let check = ThermalViaCountCheck::new();
        let violations = check.check(&board, &constraints);
        assert_eq!(
            violations.len(),
            1,
            "insufficient vias must produce 1 violation, got {}",
            violations.len()
        );
        let v = &violations[0];
        assert_eq!(v.code, "DRC_THV_001");
        assert_eq!(v.severity, Severity::Critical);
    }

    #[cfg_attr(test, test)]
    fn thermal_via_count_sufficient_vias_no_violation() {
        // 1W → required = ceil(1 * 0.7) = ceil(0.7) = 1 via
        // 1 via exactly → sufficient
        let comp = make_component("C1", 0.0, 0.0, Some(1.0), "power");
        let via = make_via(0.0, 0.0, "power");
        let net = Net {
            name: NetName("power".into()),
            components: vec![ComponentRef("C1".into())],
            class: NetClassName("power".into()),
            rules: NetClassRules::default(),
        };
        let board = make_board(vec![comp], vec![via], vec![net]);
        let constraints = ConstraintSet::default();
        let check = ThermalViaCountCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "sufficient vias must produce 0 violations, got {}",
            violations.len()
        );
    }

    #[cfg_attr(test, test)]
    fn thermal_via_count_via_outside_footprint_not_counted() {
        // 10W → required = 7 vias. Via outside bbox → not counted → violation
        let comp = make_component("C1", 0.0, 0.0, Some(10.0), "power");
        let via = make_via(50.0, 50.0, "power"); // far outside 20x20 bbox
        let net = Net {
            name: NetName("power".into()),
            components: vec![ComponentRef("C1".into())],
            class: NetClassName("power".into()),
            rules: NetClassRules::default(),
        };
        let board = make_board(vec![comp], vec![via], vec![net]);
        let constraints = ConstraintSet::default();
        let check = ThermalViaCountCheck::new();
        let violations = check.check(&board, &constraints);
        assert_eq!(
            violations.len(),
            1,
            "via outside footprint should not count toward requirement"
        );
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("rules::placement::thermal_via_count::tests::thermal_via_count_empty_vias_no_violations", thermal_via_count_empty_vias_no_violations),
        ("rules::placement::thermal_via_count::tests::thermal_via_count_no_power_component_no_violation", thermal_via_count_no_power_component_no_violation),
        ("rules::placement::thermal_via_count::tests::thermal_via_count_insufficient_vias_violation", thermal_via_count_insufficient_vias_violation),
        ("rules::placement::thermal_via_count::tests::thermal_via_count_sufficient_vias_no_violation", thermal_via_count_sufficient_vias_no_violation),
        ("rules::placement::thermal_via_count::tests::thermal_via_count_via_outside_footprint_not_counted", thermal_via_count_via_outside_footprint_not_counted),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
