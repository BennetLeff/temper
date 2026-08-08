// DRC check: zone containment.
//
// For each component, checks whether its center point lies inside any
// copper zone on the board. If the component's net_class is listed in a
// constraint zone's net_classes but the component's center is not inside
// any copper zone polygon, emits DRC_ZON_001 ERROR.
//
// Ported from: packages/temper-drc/src/temper_drc/checks/drc/zone_containment.py
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use std::collections::HashMap;

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};
use geo::{BoundingRect, Contains};

#[derive(Default)]
pub struct ZoneContainmentCheck;

impl ZoneContainmentCheck {
    pub fn new() -> Self {
        Self
    }
}
impl DrcRule for ZoneContainmentCheck {
    fn name(&self) -> &str {
        "drc_zone_containment"
    }
    fn category(&self) -> DrcCategory {
        DrcCategory::Drc
    }
    fn description(&self) -> &str {
        "Check that components are inside their designated zones."
    }
    fn check(&self, board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        // Index constraint zones by net class, once. A zone may list several
        // net_classes; each (zone, class) pair is indexed at most once (dedup
        // via ptr equality) so `matching_zones` matches the original per-zone
        // filter exactly, preserving constraint order.
        let mut zones_by_class: HashMap<&str, Vec<&crate::constraints::ZoneDefinition>> =
            HashMap::new();
        for zone in &constraints.zones {
            for nc in &zone.net_classes {
                let entry = zones_by_class.entry(nc.as_str()).or_default();
                if !entry.iter().any(|z| std::ptr::eq(*z, zone)) {
                    entry.push(zone);
                }
            }
        }

        // Bbox per board zone, once. A point outside a polygon's bounding rect
        // cannot be inside the polygon, so this is a sound pre-filter for the
        // point-in-polygon test. Uses inclusive bounds: geo's Rect::contains
        // is strict (> min, < max), but a polygon contains its boundary, so a
        // center exactly on the bbox edge must still fall through to the
        // polygon test.
        let zone_bboxes: Vec<Option<geo::Rect<f64>>> = board
            .zones
            .iter()
            .map(|z| z.polygon.bounding_rect())
            .collect();

        // 2026-08-08 vacuity remediation (Task 4,
        // docs/evidence/2026-08-08-drc-safety-rule-vacuity-audit.md): with no
        // copper-pour polygon data at all (`board.zones` empty — the state
        // every traced real-board invocation path hands this rule today),
        // `.any()` over an empty iterator is unconditionally `false`, so
        // every in-scope component was flagged regardless of its true
        // position — a guaranteed false positive, not a silent pass. That
        // trains reviewers to ignore the check. Containment genuinely cannot
        // be verified without polygon data, so emit one Info advisory (not
        // per-component Errors) instead of lying either "verified clean" or
        // "everyone is guilty" — same posture `routing::IsolationSlotCheck`
        // already takes (`SAF_SLT_001`) for its analogous "zone definition
        // exists but no matching copper polygon" case.
        if board.zones.is_empty() {
            let in_scope: Vec<String> = board
                .all_components()
                .filter(|c| zones_by_class.contains_key(c.net_class.0.as_str()))
                .map(|c| c.refdes.0.clone())
                .collect();
            if !in_scope.is_empty() {
                violations.push(violation(
                    Severity::Info,
                    "DRC_ZON_000",
                    &format!(
                        "Zone containment could not be verified for {} component(s): no copper \
                         zone polygon data was provided (board.zones is empty).",
                        in_scope.len(),
                    ),
                    DrcCategory::Drc,
                    "drc_zone_containment",
                    in_scope,
                    None,
                    serde_json::json!({ "note": "no copper zone polygon data available" }),
                ));
            }
            return violations;
        }

        for comp in board.all_components() {
            let matching_zones: &[&crate::constraints::ZoneDefinition] = zones_by_class
                .get(comp.net_class.0.as_str())
                .map(|v| v.as_slice())
                .unwrap_or(&[]);

            if matching_zones.is_empty() {
                continue; // No zone requires this component
            }

            // Check if component center is inside any copper zone polygon on the board
            let center = comp.center;
            let is_inside_any_zone = board.zones.iter().enumerate().any(|(idx, z)| {
                let bbox_ok = match zone_bboxes[idx] {
                    Some(bbox) => {
                        center.x() >= bbox.min().x
                            && center.x() <= bbox.max().x
                            && center.y() >= bbox.min().y
                            && center.y() <= bbox.max().y
                    }
                    // Empty polygon: bounding_rect() is None, and the polygon
                    // contains nothing — fall through to the exact test.
                    None => true,
                };
                bbox_ok && z.polygon.contains(&center)
            });

            if !is_inside_any_zone {
                let zone_names: Vec<String> =
                    matching_zones.iter().map(|z| z.name.clone()).collect();
                violations.push(violation(
                    Severity::Error,
                    "DRC_ZON_001",
                    &format!(
                        "Zone containment violation: {} (net class {}) is not inside any copper zone. Expected zones: {:?}",
                        comp.refdes, comp.net_class, zone_names,
                    ),
                    DrcCategory::Drc,
                    "drc_zone_containment",
                    vec![comp.refdes.0.clone()],
                    Some(crate::rules::Location {
                        x: Some(center.x()),
                        y: Some(center.y()),
                        layer: None,
                    }),
                    serde_json::json!({
                        "expected_zones": zone_names,
                        "net_class": comp.net_class.0,
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
    use geo::{polygon, Point};

    fn make_board(components: Vec<Component>, zones: Vec<CopperZone>) -> BoardState {
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
            zones,
        }
    }

    fn make_component(refdes: &str, x: f64, y: f64, net_class: &str) -> Component {
        Component {
            refdes: ComponentRef(refdes.into()),
            center: Point::new(x, y),
            rotation: 0.0,
            side: BoardSide::Top,
            width: 4.0,
            height: 4.0,
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
    fn zone_containment_empty_board_no_violations() {
        let board = make_board(vec![], vec![]);
        let constraints = ConstraintSet::default();
        let check = ZoneContainmentCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(violations.is_empty(), "empty board must produce 0 violations");
    }

    #[cfg_attr(test, test)]
    fn zone_containment_no_polygon_data_advisory_not_false_positive() {
        // 2026-08-08 vacuity remediation, Task 4: before the fix, an
        // ACMains-classed component with board.zones == [] (the state every
        // traced real-board invocation path hands this rule) was
        // unconditionally flagged DRC_ZON_001, regardless of true position —
        // a guaranteed false positive. This is the regression test.
        let comp = make_component("T1", 50.0, 50.0, "ACMains");
        let board = make_board(vec![comp], vec![]);
        let constraints = ConstraintSet {
            zones: vec![ZoneDefinition {
                name: "interface_zone".into(),
                net_classes: vec!["ACMains".into()],
            }],
            ..Default::default()
        };
        let check = ZoneContainmentCheck::new();
        let violations = check.check(&board, &constraints);
        assert_eq!(violations.len(), 1, "must produce exactly 1 advisory, not an ERROR");
        assert_eq!(violations[0].code, "DRC_ZON_000");
        assert_eq!(violations[0].severity, Severity::Info);
    }

    #[cfg_attr(test, test)]
    fn zone_containment_inside_zone_no_violation() {
        let comp = make_component("T1", 5.0, 5.0, "ACMains");
        let poly = polygon![
            (x: 0.0, y: 0.0),
            (x: 10.0, y: 0.0),
            (x: 10.0, y: 10.0),
            (x: 0.0, y: 10.0),
        ];
        let zone = CopperZone {
            net: NetName("ACMains".into()),
            layer: "F.Cu".into(),
            polygon: poly,
        };
        let board = make_board(vec![comp], vec![zone]);
        let constraints = ConstraintSet {
            zones: vec![ZoneDefinition {
                name: "interface_zone".into(),
                net_classes: vec!["ACMains".into()],
            }],
            ..Default::default()
        };
        let check = ZoneContainmentCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "component inside its required zone must produce 0 violations, got {}",
            violations.len()
        );
    }

    #[cfg_attr(test, test)]
    fn zone_containment_outside_zone_violation() {
        let comp = make_component("T1", 90.0, 90.0, "ACMains");
        let poly = polygon![
            (x: 0.0, y: 0.0),
            (x: 10.0, y: 0.0),
            (x: 10.0, y: 10.0),
            (x: 0.0, y: 10.0),
        ];
        let zone = CopperZone {
            net: NetName("ACMains".into()),
            layer: "F.Cu".into(),
            polygon: poly,
        };
        let board = make_board(vec![comp], vec![zone]);
        let constraints = ConstraintSet {
            zones: vec![ZoneDefinition {
                name: "interface_zone".into(),
                net_classes: vec!["ACMains".into()],
            }],
            ..Default::default()
        };
        let check = ZoneContainmentCheck::new();
        let violations = check.check(&board, &constraints);
        assert_eq!(violations.len(), 1, "component outside its required zone must produce 1 violation");
        assert_eq!(violations[0].code, "DRC_ZON_001");
        assert_eq!(violations[0].severity, Severity::Error);
    }

    #[cfg_attr(test, test)]
    fn zone_containment_unrelated_net_class_no_violation() {
        // Signal-classed component: no zone requires containment for it, so
        // it must be silent regardless of board.zones state.
        let comp = make_component("R1", 50.0, 50.0, "Signal");
        let board = make_board(vec![comp], vec![]);
        let constraints = ConstraintSet {
            zones: vec![ZoneDefinition {
                name: "interface_zone".into(),
                net_classes: vec!["ACMains".into()],
            }],
            ..Default::default()
        };
        let check = ZoneContainmentCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(violations.is_empty());
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("rules::drc::zone_containment::tests::zone_containment_empty_board_no_violations", zone_containment_empty_board_no_violations),
        ("rules::drc::zone_containment::tests::zone_containment_no_polygon_data_advisory_not_false_positive", zone_containment_no_polygon_data_advisory_not_false_positive),
        ("rules::drc::zone_containment::tests::zone_containment_inside_zone_no_violation", zone_containment_inside_zone_no_violation),
        ("rules::drc::zone_containment::tests::zone_containment_outside_zone_violation", zone_containment_outside_zone_violation),
        ("rules::drc::zone_containment::tests::zone_containment_unrelated_net_class_no_violation", zone_containment_unrelated_net_class_no_violation),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
