// Safety check: isolation — only isolation components in iso zones.
//
// Ensures that only components belonging to the isolation class reside
// within or straddle isolation zones. All other components must stay clear.
//
// Ported from: packages/temper-drc/src/temper_drc/checks/safety/isolation.py
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};

/// Keywords that identify an isolation component.
const ISO_COMPONENT_KEYWORDS: [&str; 8] =
    ["iso", "opto", "coupler", "isolator", "transformer", "adum", "dcdc", "mev1"];

/// Keywords that identify an isolation zone.
const ISO_ZONE_KEYWORDS: [&str; 6] =
    ["iso", "opto", "coupler", "transformer", "gutter", "slot"];

/// Determine if a component is an isolation device.
///
/// Consults `NetClassRules.safety_category` (declared in the SSOT manifest) first.
/// Falls back to keyword substring matching for undeclared net classes.
fn is_iso_component(comp: &crate::board::Component, board: &BoardState) -> bool {
    // Prefer declared safety_category from the model
    if let Some(rules) = board.net_class_rules.get(&comp.net_class)
        && let Some(ref sc) = rules.safety_category
    {
        return sc == "iso";
    }
    // Keyword fallback on net_class and footprint
    let lc = comp.net_class.0.to_lowercase();
    ISO_COMPONENT_KEYWORDS
        .iter()
        .any(|k| lc.contains(k))
}

/// Determine if a zone name indicates it is an isolation zone.
fn is_iso_zone(zone_name: &str) -> bool {
    let lc = zone_name.to_lowercase();
    ISO_ZONE_KEYWORDS.iter().any(|k| lc.contains(k))
}

#[derive(Default)]
pub struct IsolationCheck;

impl IsolationCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for IsolationCheck {
    fn name(&self) -> &str {
        "safety_isolation"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Safety
    }

    fn description(&self) -> &str {
        "Ensure no components reside in isolation zones except isolation devices."
    }

    fn check(&self, board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        // Identify isolation zones by name keyword matching (once, not per
        // component x zone: is_iso_zone lowercases the name on every call).
        let iso_zones: Vec<&crate::constraints::ZoneDefinition> = constraints
            .zones
            .iter()
            .filter(|z| is_iso_zone(&z.name))
            .collect();

        if iso_zones.is_empty() {
            return violations;
        }

        // Check each component against isolation zones
        for comp in board.all_components() {
            let is_iso_device = is_iso_component(comp, board);

            if is_iso_device {
                continue;
            }

            let cx = comp.center.x();
            let cy = comp.center.y();

            // Check if this component's net class places it in an iso zone
            for zone in &iso_zones {
                // If component's net_class matches a zone's net_classes, check containment
                let in_zone_via_net_class = zone.net_classes.iter().any(|zc| zc.as_str() == comp.net_class.0.as_str());

                if in_zone_via_net_class {
                    let layer = if comp.side == crate::board::BoardSide::Top {
                        "F.Cu"
                    } else {
                        "B.Cu"
                    };

                    violations.push(violation(
                        Severity::Error,
                        "SAF_ISO_001",
                        &format!(
                            "Safety violation: Component {} ({}) is in isolation zone '{}'",
                            comp.refdes, comp.net_class, zone.name,
                        ),
                        DrcCategory::Safety,
                        "safety_isolation",
                        vec![comp.refdes.0.clone()],
                        Some(crate::rules::Location {
                            x: Some(cx),
                            y: Some(cy),
                            layer: Some(layer.to_string()),
                        }),
                        serde_json::json!({
                            "zone_name": zone.name,
                            "component_class": comp.net_class,
                        }),
                    ));
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
    use crate::constraints::{ConstraintSet, ZoneDefinition};
    use geo::Point;
    use std::collections::BTreeMap;

    fn component(refdes: &str, x: f64, y: f64, net_class: &str) -> Component {
        Component {
            refdes: ComponentRef(refdes.into()),
            center: Point::new(x, y),
            rotation: 0.0,
            side: BoardSide::Top,
            width: 2.0,
            height: 2.0,
            net_class: NetClassName(net_class.into()),
            power_dissipation_w: None,
            package_type: PackageType::Smd,
            is_magnetic: false,
            is_electrolytic: false,
            vent_direction: None,
            footprint_polygon: None,
        }
    }

    fn board_with(components: Vec<Component>) -> BoardState {
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

    fn constraints_with_zone(zone_name: &str, net_classes: &[&str]) -> ConstraintSet {
        ConstraintSet {
            zones: vec![ZoneDefinition {
                name: zone_name.to_string(),
                net_classes: net_classes.iter().map(|s| s.to_string()).collect(),
            }],
            ..Default::default()
        }
    }

    #[cfg_attr(test, test)]
    fn fires_for_non_iso_component_whose_net_class_matches_the_zone() {
        let board = board_with(vec![component("R1", 5.0, 5.0, "MAINS_LIVE")]);
        let constraints = constraints_with_zone("ISO_GUTTER", &["MAINS_LIVE"]);
        let check = IsolationCheck::new();
        let violations = check.check(&board, &constraints);
        assert_eq!(violations.len(), 1, "component on a net class the isolation zone declares must fire");
        assert_eq!(violations[0].code, "SAF_ISO_001");
        assert!(violations[0].message.contains("R1"));
    }

    #[cfg_attr(test, test)]
    fn does_not_fire_for_iso_device_even_when_its_net_class_matches() {
        // Isolation devices (optocouplers, transformers, ...) are exactly
        // the components allowed to straddle an isolation zone -- they must
        // be exempt even though their net class is exactly what the zone
        // declares.
        let board = board_with(vec![component("U1", 5.0, 5.0, "OPTO_ISO")]);
        let constraints = constraints_with_zone("ISO_GUTTER", &["OPTO_ISO"]);
        let check = IsolationCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(violations.is_empty(), "an isolation device must be exempt from its own isolation zone");
    }

    #[cfg_attr(test, test)]
    fn does_not_fire_when_net_class_is_not_declared_on_the_zone() {
        let board = board_with(vec![component("R1", 5.0, 5.0, "SIGNAL")]);
        let constraints = constraints_with_zone("ISO_GUTTER", &["MAINS_LIVE"]);
        let check = IsolationCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(violations.is_empty(), "a net class absent from the zone's declared list must not fire");
    }

    #[cfg_attr(test, test)]
    fn does_not_fire_when_zone_name_has_no_isolation_keyword() {
        // Zone identification is name-keyword-gated (ISO_ZONE_KEYWORDS);
        // a "zone" whose name matches no keyword is never treated as an
        // isolation zone at all, regardless of net_classes overlap.
        let board = board_with(vec![component("R1", 5.0, 5.0, "MAINS_LIVE")]);
        let constraints = constraints_with_zone("POWER_PLANE", &["MAINS_LIVE"]);
        let check = IsolationCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(violations.is_empty(), "a non-isolation-named zone must not gate any component");
    }

    #[cfg_attr(test, test)]
    fn no_iso_zones_declared_yields_no_violations() {
        let board = board_with(vec![component("R1", 5.0, 5.0, "MAINS_LIVE")]);
        let check = IsolationCheck::new();
        let violations = check.check(&board, &ConstraintSet::default());
        assert!(violations.is_empty());
    }

    // -----------------------------------------------------------------
    // DEFECT (reported, not fixed -- see task report): this check has no
    // spatial containment test at all.
    //
    // The docstring says "Ensures that only components belonging to the
    // isolation class ... reside within or straddle these zones", and the
    // emitted message says "is in isolation zone '{name}'" -- but
    // `constraints::ZoneDefinition` (constraints.rs) carries only `name`
    // and `net_classes`; it has NO geometry field. Contrast with the
    // Python-facing `ZoneDefinition` PyO3 class in `drc_contracts.rs`
    // (`pub bounds: Py<PyAny>`), which mirrors the original Python check's
    // `zone.bounds` / `x_min <= cx <= x_max and y_min <= cy <= y_max`
    // spatial test. Any `bounds` value supplied by the PCL/Python layer is
    // silently dropped by serde when it lands in `ConstraintSet.zones`
    // (constraints::ZoneDefinition has no field to deserialize it into).
    //
    // The net effect: `check()` below fires purely on "does this
    // component's net class appear in the zone's declared net_classes
    // list", with **no reference to the component's or the zone's
    // position** -- proven here by placing the component far outside the
    // board entirely. A real geometric containment bug (e.g. a component
    // sitting inside the physical isolation gutter but on an
    // undeclared net class) would be silently missed, and a component
    // nowhere near the gutter is silently flagged as "in isolation zone"
    // when it shares a net class name with one.
    // -----------------------------------------------------------------
    #[cfg_attr(test, test)]
    fn bug_fires_regardless_of_component_position_no_spatial_containment_check() {
        // Component sits at (1e5, 1e5) -- nowhere near any plausible board
        // area (board is 100mm x 100mm) or physical isolation slot -- yet
        // the check still fires solely because its net class matches the
        // zone's declared net_classes list. This documents current
        // behavior; see the block comment above for why it is a
        // suspected defect, not intended semantics.
        let board = board_with(vec![component("R1", 1.0e5, 1.0e5, "MAINS_LIVE")]);
        let constraints = constraints_with_zone("ISO_GUTTER", &["MAINS_LIVE"]);
        let check = IsolationCheck::new();
        let violations = check.check(&board, &constraints);
        assert_eq!(
            violations.len(),
            1,
            "current implementation fires purely on net-class membership, with no spatial containment test whatsoever"
        );
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("rules::safety::isolation::tests::fires_for_non_iso_component_whose_net_class_matches_the_zone", fires_for_non_iso_component_whose_net_class_matches_the_zone),
        ("rules::safety::isolation::tests::does_not_fire_for_iso_device_even_when_its_net_class_matches", does_not_fire_for_iso_device_even_when_its_net_class_matches),
        ("rules::safety::isolation::tests::does_not_fire_when_net_class_is_not_declared_on_the_zone", does_not_fire_when_net_class_is_not_declared_on_the_zone),
        ("rules::safety::isolation::tests::does_not_fire_when_zone_name_has_no_isolation_keyword", does_not_fire_when_zone_name_has_no_isolation_keyword),
        ("rules::safety::isolation::tests::no_iso_zones_declared_yields_no_violations", no_iso_zones_declared_yields_no_violations),
        ("rules::safety::isolation::tests::bug_fires_regardless_of_component_position_no_spatial_containment_check", bug_fires_regardless_of_component_position_no_spatial_containment_check),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
