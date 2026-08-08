// ERC check: net connectivity — every net must have at least two connected
// (non-mechanical) components.
//
// Mechanical components (mounting holes, etc.) are excluded from connection
// counts since they carry no electrical nets by design — `Net.components`
// only ever references `board.electrical_components` refdes, so no extra
// filtering is required here.
//
// This was previously a placeholder that computed `_filtered_connection_counts`
// (a real per-net tally) and then discarded it, unconditionally returning
// `vec![]` (2026-08-08 vacuity remediation — see
// `docs/evidence/2026-08-08-drc-safety-rule-vacuity-audit.md`). The algorithm
// below matches the pre-existing, previously-unused
// `rules::oracle::oracle_net_connectivity` reference implementation
// (same threshold, same violation code) so the two can be run head-to-head.
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};

#[derive(Default)]
pub struct NetConnectivityCheck;

impl NetConnectivityCheck {
    pub fn new() -> Self {
        Self
    }
}
impl DrcRule for NetConnectivityCheck {
    fn name(&self) -> &str {
        "erc_net_connectivity"
    }
    fn category(&self) -> DrcCategory {
        DrcCategory::Erc
    }
    fn description(&self) -> &str {
        "Verify each net has at least two connected (non-mechanical) components."
    }
    fn check(&self, board: &BoardState, _constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        // Only electrical components are in board.electrical_components —
        // mechanical components are separated at the type level, so
        // net.components never contains a mechanical refdes.
        for net in &board.nets {
            let count = net.components.len();
            if count < 2 {
                violations.push(violation(
                    Severity::Error,
                    "ERC_NET_001",
                    &format!(
                        "Net '{}' has only {} connected component(s); at least 2 are required \
                         for a complete electrical connection.",
                        net.name, count,
                    ),
                    DrcCategory::Erc,
                    "erc_net_connectivity",
                    net.components.iter().map(|c| c.0.clone()).collect(),
                    None,
                    serde_json::json!({
                        "net_name": net.name.0,
                        "connection_count": count,
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
    use std::collections::HashMap;

    #[cfg_attr(test, test)]
    fn net_connectivity_empty_board_no_violations() {
        let board = BoardState {
            width_mm: 100.0,
            height_mm: 100.0,
            margin_mm: 3.0,
            electrical_components: vec![],
            mechanical_components: vec![],
            nets: vec![],
            net_class_rules: HashMap::new(),
            traces: vec![],
            vias: vec![],
            zones: vec![],
        };
        let constraints = ConstraintSet::default();
        let check = NetConnectivityCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(violations.is_empty(), "empty board must produce 0 violations");
    }

    fn make_component(refdes: &str) -> Component {
        Component {
            refdes: ComponentRef(refdes.into()),
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
            footprint_polygon: None,
        }
    }

    #[cfg_attr(test, test)]
    fn net_connectivity_single_component_net_violation() {
        // A net with exactly 1 connected component is a real ERC finding —
        // this is the fixture the pre-fix stub silently ignored.
        let board = BoardState {
            width_mm: 100.0,
            height_mm: 100.0,
            margin_mm: 3.0,
            electrical_components: vec![make_component("C1")],
            mechanical_components: vec![],
            nets: vec![Net {
                name: NetName("N1".into()),
                components: vec![ComponentRef("C1".into())],
                class: NetClassName("Signal".into()),
                rules: NetClassRules::default(),
            }],
            net_class_rules: HashMap::new(),
            traces: vec![],
            vias: vec![],
            zones: vec![],
        };
        let constraints = ConstraintSet::default();
        let check = NetConnectivityCheck::new();
        let violations = check.check(&board, &constraints);
        assert_eq!(
            violations.len(),
            1,
            "net with 1 connected component must produce 1 violation"
        );
        let v = &violations[0];
        assert_eq!(v.code, "ERC_NET_001");
        assert_eq!(v.severity, Severity::Error);
        assert_eq!(v.category, DrcCategory::Erc);
        assert_eq!(check.name(), "erc_net_connectivity");
        assert_eq!(check.category(), DrcCategory::Erc);
    }

    #[cfg_attr(test, test)]
    fn net_connectivity_zero_component_net_violation() {
        // An entirely unconnected (aliased/orphaned) net also violates.
        let board = BoardState {
            width_mm: 100.0,
            height_mm: 100.0,
            margin_mm: 3.0,
            electrical_components: vec![],
            mechanical_components: vec![],
            nets: vec![Net {
                name: NetName("N_ORPHAN".into()),
                components: vec![],
                class: NetClassName("Signal".into()),
                rules: NetClassRules::default(),
            }],
            net_class_rules: HashMap::new(),
            traces: vec![],
            vias: vec![],
            zones: vec![],
        };
        let constraints = ConstraintSet::default();
        let check = NetConnectivityCheck::new();
        let violations = check.check(&board, &constraints);
        assert_eq!(violations.len(), 1);
        assert_eq!(violations[0].details["connection_count"], 0);
    }

    #[cfg_attr(test, test)]
    fn net_connectivity_two_component_net_no_violation() {
        let board = BoardState {
            width_mm: 100.0,
            height_mm: 100.0,
            margin_mm: 3.0,
            electrical_components: vec![make_component("C1"), make_component("C2")],
            mechanical_components: vec![],
            nets: vec![Net {
                name: NetName("N1".into()),
                components: vec![ComponentRef("C1".into()), ComponentRef("C2".into())],
                class: NetClassName("Signal".into()),
                rules: NetClassRules::default(),
            }],
            net_class_rules: HashMap::new(),
            traces: vec![],
            vias: vec![],
            zones: vec![],
        };
        let constraints = ConstraintSet::default();
        let check = NetConnectivityCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(
            violations.is_empty(),
            "net with 2 connected components must produce 0 violations, got {}",
            violations.len()
        );
    }

    #[cfg_attr(test, test)]
    fn net_connectivity_mixed_nets_only_undersized_flagged() {
        let board = BoardState {
            width_mm: 100.0,
            height_mm: 100.0,
            margin_mm: 3.0,
            electrical_components: vec![
                make_component("C1"),
                make_component("C2"),
                make_component("C3"),
            ],
            mechanical_components: vec![],
            nets: vec![
                Net {
                    name: NetName("GOOD".into()),
                    components: vec![ComponentRef("C1".into()), ComponentRef("C2".into())],
                    class: NetClassName("Signal".into()),
                    rules: NetClassRules::default(),
                },
                Net {
                    name: NetName("BAD".into()),
                    components: vec![ComponentRef("C3".into())],
                    class: NetClassName("Signal".into()),
                    rules: NetClassRules::default(),
                },
            ],
            net_class_rules: HashMap::new(),
            traces: vec![],
            vias: vec![],
            zones: vec![],
        };
        let constraints = ConstraintSet::default();
        let check = NetConnectivityCheck::new();
        let violations = check.check(&board, &constraints);
        assert_eq!(violations.len(), 1);
        assert_eq!(violations[0].details["net_name"], "BAD");
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("rules::erc::net_connectivity::tests::net_connectivity_empty_board_no_violations", net_connectivity_empty_board_no_violations),
        ("rules::erc::net_connectivity::tests::net_connectivity_single_component_net_violation", net_connectivity_single_component_net_violation),
        ("rules::erc::net_connectivity::tests::net_connectivity_zero_component_net_violation", net_connectivity_zero_component_net_violation),
        ("rules::erc::net_connectivity::tests::net_connectivity_two_component_net_no_violation", net_connectivity_two_component_net_no_violation),
        ("rules::erc::net_connectivity::tests::net_connectivity_mixed_nets_only_undersized_flagged", net_connectivity_mixed_nets_only_undersized_flagged),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
