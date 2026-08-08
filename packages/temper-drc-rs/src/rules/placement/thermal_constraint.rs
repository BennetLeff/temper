// Placement check: thermal placement constraints, read from
// `constraints.thermal_constraints` (YAML top-level `thermal:` key).
//
// 2026-08-08 vacuity remediation
// (docs/evidence/2026-08-08-drc-safety-rule-vacuity-audit.md, Task 2): the
// audit found `temper_constraints.yaml`'s `thermal:` section (2 real,
// safety-relevant entries for this board's IGBT half-bridge and LDO/Buck
// spread) had zero consumers among the 27 registered rules, because the
// field name the Rust `ConstraintSet` deserialized into
// (`thermal_properties`, a *different* shape: `{component,
// power_dissipation_w, max_ambient_c}`) did not match the key
// `drc_runner.py::_constraints_to_dict` actually sends
// (`"thermal_constraints"`, shape `{components, prefer_edge, min_spacing_mm,
// max_distance_from_edge_mm, description}`). `serde_json::from_value` has no
// `#[serde(deny_unknown_fields)]` guard on `ConstraintSet`, so the real,
// correctly-populated dict key was silently dropped on every deserialization
// with no error. `constraints::ThermalConstraint` (added alongside this
// rule) now matches the real schema field-for-field, and this rule is the
// first consumer.
//
// Two independent sub-checks per `ThermalConstraint` group:
//   1. `prefer_edge`: every listed component's footprint must be within
//      `max_distance_from_edge_mm` of the nearest board edge.
//   2. `min_spacing_mm`: every pair of listed components must be at least
//      `min_spacing_mm` apart (edge-to-edge), so co-located heat sources
//      don't cluster into a single hot spot.
// A listed component refdes that doesn't exist on the board is reported as
// a single Info advisory (the constraint may reference a part renamed or
// removed from the BOM after the constraint was authored) rather than
// silently ignored or hard-failed.
//
// KNOWN CAVEAT (documented, not silently swallowed): as of this remediation,
// this rule is reachable through `drc_runner.py`'s board-dict builder (used
// by the placement pipeline's `drc_fence.py`/`preflight.py`), which already
// forwards `thermal_constraints` correctly. It is NOT yet reachable through
// `drc_ratchet.py::_run_rust_drc` (the CI ratchet's Rust backend) or
// `validation/drc_oracle.py`'s board-dict builder — both hand-parse
// `pcb/temper.kicad_pcb` directly and never load `temper_constraints.yaml`
// at all, independent of this rule's correctness. Fixing that is the same
// systemic root cause the audit names in Recommendation 5 (shared
// board_dict/constraints_dict construction) and is out of scope for this
// change — flagged here so this rule's real-world reach isn't overstated.
// Separately, `temper_constraints.yaml` itself has a real, human-authored
// duplicate top-level `thermal:` key (lines ~216 and ~405) that silently
// discards the first block per standard YAML last-key-wins semantics —
// documented in this remediation's report, not fixed here (it needs a human
// decision about which block reflects current intent), but the discarding
// is why this rule's real-config exercise surface today is one block only
// (Q1/Q2 edge-only, U_LDO_5V/U_LDO_3V3/U_BUCK spacing-only) rather than
// both authored blocks.

use crate::board::{BoardState, Component};
use crate::constraints::ConstraintSet;
use crate::rules::{location_midpoint, violation, DrcCategory, DrcRule, Location, Severity, Violation};

#[derive(Default)]
pub struct ThermalConstraintCheck;

impl ThermalConstraintCheck {
    pub fn new() -> Self {
        Self
    }
}

/// Minimum distance from `comp`'s footprint edge to the nearest board edge.
fn distance_to_board_edge(comp: &Component, board: &BoardState) -> f64 {
    let bbox = comp.footprint_bbox();
    let left = bbox.min().x;
    let right = board.width_mm - bbox.max().x;
    let top = bbox.min().y;
    let bottom = board.height_mm - bbox.max().y;
    left.min(right).min(top).min(bottom)
}

impl DrcRule for ThermalConstraintCheck {
    fn name(&self) -> &str {
        "placement_thermal_constraint"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Drc
    }

    fn description(&self) -> &str {
        "Verify power-dissipating components satisfy their configured thermal placement \
         constraints (edge proximity, inter-component spacing)."
    }

    fn check(&self, board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        for tc in &constraints.thermal_constraints {
            // Resolve refdes -> Component, tracking any that don't exist on the board.
            let mut found: Vec<&Component> = Vec::new();
            let mut missing: Vec<String> = Vec::new();
            for refdes in &tc.components {
                match board.all_components().find(|c| &c.refdes.0 == refdes) {
                    Some(c) => found.push(c),
                    None => missing.push(refdes.clone()),
                }
            }

            if !missing.is_empty() {
                violations.push(violation(
                    Severity::Info,
                    "DRC_THC_000",
                    &format!(
                        "Thermal constraint '{}' references component(s) not found on the \
                         board: {:?}",
                        tc.description, missing,
                    ),
                    DrcCategory::Drc,
                    "placement_thermal_constraint",
                    missing.clone(),
                    None,
                    serde_json::json!({
                        "missing_components": missing,
                        "group": tc.components,
                    }),
                ));
            }

            // 1. Edge-proximity requirement.
            if tc.prefer_edge {
                for comp in &found {
                    let dist = distance_to_board_edge(comp, board);
                    if dist > tc.max_distance_from_edge_mm {
                        violations.push(violation(
                            Severity::Warning,
                            "DRC_THC_001",
                            &format!(
                                "{} is {:.2} mm from the nearest board edge; thermal \
                                 constraint '{}' requires <= {:.2} mm",
                                comp.refdes, dist, tc.description, tc.max_distance_from_edge_mm,
                            ),
                            DrcCategory::Drc,
                            "placement_thermal_constraint",
                            vec![comp.refdes.0.clone()],
                            Some(Location {
                                x: Some(comp.center.x()),
                                y: Some(comp.center.y()),
                                layer: None,
                            }),
                            serde_json::json!({
                                "distance_to_edge_mm": dist,
                                "max_distance_from_edge_mm": tc.max_distance_from_edge_mm,
                                "group": tc.components,
                            }),
                        ));
                    }
                }
            }

            // 2. Minimum-spacing requirement between every pair in the group.
            if tc.min_spacing_mm > 0.0 {
                for i in 0..found.len() {
                    for j in (i + 1)..found.len() {
                        let a = found[i];
                        let b = found[j];
                        let dist = a.edge_distance_to(b);
                        if dist < tc.min_spacing_mm {
                            violations.push(violation(
                                Severity::Warning,
                                "DRC_THC_002",
                                &format!(
                                    "{} and {} are {:.2} mm apart; thermal constraint '{}' \
                                     requires >= {:.2} mm spacing",
                                    a.refdes, b.refdes, dist, tc.description, tc.min_spacing_mm,
                                ),
                                DrcCategory::Drc,
                                "placement_thermal_constraint",
                                vec![a.refdes.0.clone(), b.refdes.0.clone()],
                                location_midpoint(&a.center, &b.center, None),
                                serde_json::json!({
                                    "actual_spacing_mm": dist,
                                    "required_spacing_mm": tc.min_spacing_mm,
                                    "group": tc.components,
                                }),
                            ));
                        }
                    }
                }
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

    fn make_component(refdes: &str, x: f64, y: f64) -> Component {
        Component {
            refdes: ComponentRef(refdes.into()),
            center: Point::new(x, y),
            rotation: 0.0,
            side: BoardSide::Top,
            width: 4.0,
            height: 4.0,
            net_class: NetClassName("HighCurrent".into()),
            power_dissipation_w: Some(30.0),
            package_type: PackageType::To247,
            is_magnetic: false,
            is_electrolytic: false,
            vent_direction: None,
            footprint_polygon: None,
        }
    }

    #[cfg_attr(test, test)]
    fn thermal_constraint_empty_no_violations() {
        let board = make_board(vec![]);
        let constraints = ConstraintSet::default();
        let check = ThermalConstraintCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(violations.is_empty(), "no thermal constraints must produce 0 violations");
    }

    #[cfg_attr(test, test)]
    fn thermal_constraint_edge_violation() {
        // Board center (50, 50) on a 100x100 board with 3mm margin —
        // distance to nearest edge is 48mm, far over a 10mm max.
        let q1 = make_component("Q1", 50.0, 50.0);
        let board = make_board(vec![q1]);
        let constraints = ConstraintSet {
            thermal_constraints: vec![ThermalConstraint {
                components: vec!["Q1".into()],
                prefer_edge: true,
                min_spacing_mm: 0.0,
                max_distance_from_edge_mm: 10.0,
                description: "IGBTs must be near an edge for thermal interface".into(),
            }],
            ..Default::default()
        };
        let check = ThermalConstraintCheck::new();
        let violations = check.check(&board, &constraints);
        assert_eq!(violations.len(), 1, "component far from edge must produce 1 violation");
        let v = &violations[0];
        assert_eq!(v.code, "DRC_THC_001");
        assert_eq!(v.severity, Severity::Warning);
        assert_eq!(v.category, DrcCategory::Drc);
    }

    #[cfg_attr(test, test)]
    fn thermal_constraint_edge_satisfied_no_violation() {
        // Component near x=0 edge: bbox left edge at x=1-2=-1... use x=3 so
        // bbox spans [1,5], distance to left edge = 1mm <= 10mm max.
        let q1 = make_component("Q1", 3.0, 50.0);
        let board = make_board(vec![q1]);
        let constraints = ConstraintSet {
            thermal_constraints: vec![ThermalConstraint {
                components: vec!["Q1".into()],
                prefer_edge: true,
                min_spacing_mm: 0.0,
                max_distance_from_edge_mm: 10.0,
                description: "near edge".into(),
            }],
            ..Default::default()
        };
        let check = ThermalConstraintCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "component near edge must produce 0 violations, got {}",
            violations.len()
        );
    }

    #[cfg_attr(test, test)]
    fn thermal_constraint_spacing_violation() {
        // Q1 and Q2 5mm apart (bbox edge distance = 5 - 4 = 1mm), required >= 15mm.
        let q1 = make_component("Q1", 10.0, 10.0);
        let q2 = make_component("Q2", 15.0, 10.0);
        let board = make_board(vec![q1, q2]);
        let constraints = ConstraintSet {
            thermal_constraints: vec![ThermalConstraint {
                components: vec!["Q1".into(), "Q2".into()],
                prefer_edge: false,
                min_spacing_mm: 15.0,
                max_distance_from_edge_mm: 1000.0,
                description: "IGBTs dissipate 20-50W each, must be spread apart".into(),
            }],
            ..Default::default()
        };
        let check = ThermalConstraintCheck::new();
        let violations = check.check(&board, &constraints);
        assert_eq!(violations.len(), 1, "too-close IGBT pair must produce 1 violation");
        let v = &violations[0];
        assert_eq!(v.code, "DRC_THC_002");
        assert_eq!(v.severity, Severity::Warning);
    }

    #[cfg_attr(test, test)]
    fn thermal_constraint_spacing_satisfied_no_violation() {
        let q1 = make_component("Q1", 10.0, 10.0);
        let q2 = make_component("Q2", 30.0, 10.0);
        let board = make_board(vec![q1, q2]);
        let constraints = ConstraintSet {
            thermal_constraints: vec![ThermalConstraint {
                components: vec!["Q1".into(), "Q2".into()],
                prefer_edge: false,
                min_spacing_mm: 15.0,
                max_distance_from_edge_mm: 1000.0,
                description: "spread apart".into(),
            }],
            ..Default::default()
        };
        let check = ThermalConstraintCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "sufficiently spread pair must produce 0 violations, got {}",
            violations.len()
        );
    }

    #[cfg_attr(test, test)]
    fn thermal_constraint_missing_component_advisory() {
        let board = make_board(vec![]);
        let constraints = ConstraintSet {
            thermal_constraints: vec![ThermalConstraint {
                components: vec!["Q99".into()],
                prefer_edge: true,
                min_spacing_mm: 0.0,
                max_distance_from_edge_mm: 10.0,
                description: "references a removed part".into(),
            }],
            ..Default::default()
        };
        let check = ThermalConstraintCheck::new();
        let violations = check.check(&board, &constraints);
        assert_eq!(violations.len(), 1);
        assert_eq!(violations[0].code, "DRC_THC_000");
        assert_eq!(violations[0].severity, Severity::Info);
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("rules::placement::thermal_constraint::tests::thermal_constraint_empty_no_violations", thermal_constraint_empty_no_violations),
        ("rules::placement::thermal_constraint::tests::thermal_constraint_edge_violation", thermal_constraint_edge_violation),
        ("rules::placement::thermal_constraint::tests::thermal_constraint_edge_satisfied_no_violation", thermal_constraint_edge_satisfied_no_violation),
        ("rules::placement::thermal_constraint::tests::thermal_constraint_spacing_violation", thermal_constraint_spacing_violation),
        ("rules::placement::thermal_constraint::tests::thermal_constraint_spacing_satisfied_no_violation", thermal_constraint_spacing_satisfied_no_violation),
        ("rules::placement::thermal_constraint::tests::thermal_constraint_missing_component_advisory", thermal_constraint_missing_component_advisory),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
