// Safety check (registered as "safety_creepage" -- name kept stable; see
// note below): isolation-component package-size sanity check.
//
// WHAT THIS DOES NOT DO, stated plainly because the registered name
// invites the opposite reading (found and documented by a 2026-08 dark-
// matter census, docs/evidence/2026-08-14-creepage-figure-integrity.md):
// this rule does NOT measure creepage. Creepage is a distance measured
// ALONG A SURFACE between the nearest copper of two different nets/
// potentials -- this rule never reads two components' positions relative
// to each other, never reads pad/copper geometry, and never computes any
// distance between conductors at all. It reads exactly one component's
// own package bounding box (`max(width, height)`) and compares that
// single number to a threshold. It is a component-selection heuristic
// ("is this declared-isolation part's footprint at least this big"), not
// a creepage measurement, and a passing result here says nothing about
// the real surface-path distance on the board.
//
// The real, IEC-60335-cited, currently-enforced creepage check for this
// board is `scripts/generate_kicad_dru.py`'s generated `.kicad_dru`
// `(constraint creepage (min ...))` rules, verified against kicad-cli
// 10.0.4's real surface-path solver
// (docs/evidence/2026-07-28-drc-creepage-constraint.md). The domain-pair/
// insulation-type-aware `IEC60335_REQUIREMENTS` matrix in
// `packages/temper-placer/src/temper_placer/requirements/validators/
// clearance.py` is a second, independently-sourced correct implementation.
// Neither is affected by this rule's presence, absence, or correctness --
// consult those, not this rule's "safety_creepage" name, for a real
// creepage verdict.
//
// What this rule DOES do, honestly: for a component whose net class is
// declared `safety_category == "iso"` (or, failing that, whose net-class
// name matches one of 8 keywords), it flags a package bounding box under
// `min_iso_width_mm` as too small to plausibly be a real isolation part
// (optocoupler, isolated DC-DC, isolation transformer). That is a crude
// BOM/footprint sanity check, not a distance measurement, and it is
// currently unreachable on this board's real net-class taxonomy (none of
// `packages/temper-placer/configs/netclass_rules.yaml`'s 8 net classes
// declare `safety_category: "iso"` or match the keyword list) --
// docs/evidence/2026-08-08-drc-safety-rule-vacuity-audit.md measured this
// directly.
//
// NOT renamed/removed here: `"safety_creepage"` is asserted verbatim by
// several Python test suites (test_drc_result_coverage.py,
// test_coverage_paydown_v9.py, the *_rust_differential.py suites) and is
// the shape `_drc_result_py_oracle.py` -- a content-hash-pinned
// differential oracle this project's own constraints forbid deleting or
// consolidating -- mirrors. Renaming the identifier is a real, wider fix
// (coordinated update across those files plus whatever re-pins the
// oracle's hash) that this pass deliberately leaves for a dedicated
// follow-up rather than attempting under this task's time/risk budget;
// only the misleading prose above and the violation message below are
// corrected here, which changes no test-visible identifier and no
// enforcement behavior.
//
// Ported from: packages/temper-drc/src/temper_drc/checks/safety/creepage.py
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::BoardState;
use crate::constraints::ConstraintSet;
use crate::rules::{violation, DrcCategory, DrcRule, Severity, Violation};

/// Keywords that identify an isolation component.
const ISO_COMPONENT_KEYWORDS: [&str; 8] =
    ["iso", "opto", "coupler", "isolator", "transformer", "adum", "dcdc", "mev1"];

/// Determine if a component is an isolation device.
///
/// Consults `NetClassRules.safety_category` (declared in the SSOT manifest) first.
/// Falls back to keyword substring matching on net_class name.
fn is_iso_component(comp: &crate::board::Component, board: &BoardState) -> bool {
    // Prefer declared safety_category from the model
    if let Some(rules) = board.net_class_rules.get(&comp.net_class)
        && let Some(ref sc) = rules.safety_category
    {
        return sc == "iso";
    }
    // Keyword fallback
    let lc = comp.net_class.0.to_lowercase();
    ISO_COMPONENT_KEYWORDS.iter().any(|k| lc.contains(k))
}

pub struct CreepageCheck {
    min_iso_width_mm: f64,
}

impl CreepageCheck {
    /// Create a new CreepageCheck with the given minimum isolation width.
    pub fn new(min_iso_width_mm: f64) -> Self {
        Self { min_iso_width_mm }
    }
}

impl DrcRule for CreepageCheck {
    fn name(&self) -> &str {
        "safety_creepage"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Safety
    }

    fn description(&self) -> &str {
        // NOT a creepage (surface-path distance) measurement -- see this
        // file's header comment. This checks one declared-isolation
        // component's own package bounding box against a minimum size,
        // nothing more. The real creepage enforcement for this board is
        // scripts/generate_kicad_dru.py's generated .kicad_dru `creepage`
        // constraint (kicad-cli DRC).
        "Isolation-component package-size sanity check (NOT a creepage/surface-path measurement -- see module header comment)."
    }

    fn check(&self, board: &BoardState, _constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();

        for comp in board.all_components() {
            if !is_iso_component(comp, board) {
                continue;
            }

            // NOT a creepage distance: this is the component's own package
            // bounding box (matching the ported Python original), used
            // only as a crude "is this plausibly a real isolation part"
            // footprint-size sanity check. It is never compared against
            // another component's position, so it cannot represent a
            // distance between two conductors.
            let package_width = comp.width.max(comp.height);

            if package_width < self.min_iso_width_mm {
                let layer = if comp.side == crate::board::BoardSide::Top {
                    "F.Cu"
                } else {
                    "B.Cu"
                };

                violations.push(violation(
                    Severity::Error,
                    "SAF_CRP_001",
                    &format!(
                        "Isolation component package too small: {} max(width,height) {:.1}mm < {:.1}mm (package-size heuristic, not a creepage/surface-path measurement)",
                        comp.refdes, package_width, self.min_iso_width_mm,
                    ),
                    DrcCategory::Safety,
                    "safety_creepage",
                    vec![comp.refdes.0.clone()],
                    Some(crate::rules::Location {
                        x: Some(comp.center.x()),
                        y: Some(comp.center.y()),
                        layer: Some(layer.to_string()),
                    }),
                    serde_json::json!({
                        "actual_width_mm": package_width,
                        "required_width_mm": self.min_iso_width_mm,
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
    use crate::constraints::ConstraintSet;
    use std::collections::{BTreeMap, HashMap};

    /// A component whose net class name contains an isolation keyword
    /// ("ISO"), so it is picked up by the keyword fallback in
    /// `is_iso_component` without needing a declared `safety_category`.
    fn iso_component(refdes: &str, width: f64, height: f64) -> Component {
        Component {
            refdes: ComponentRef(refdes.into()),
            center: geo::Point::new(0.0, 0.0),
            rotation: 0.0,
            side: BoardSide::Top,
            width,
            height,
            net_class: NetClassName("ISO_BARRIER".into()),
            power_dissipation_w: None,
            package_type: PackageType::Smd,
            is_magnetic: false,
            is_electrolytic: false,
            vent_direction: None,
            footprint_polygon: None,
        }
    }

    fn board_with(components: Vec<Component>, net_class_rules: BTreeMap<NetClassName, NetClassRules>) -> BoardState {
        BoardState {
            width_mm: 100.0,
            height_mm: 100.0,
            margin_mm: 3.0,
            electrical_components: components,
            mechanical_components: vec![],
            nets: vec![],
            net_class_rules,
            traces: vec![],
            vias: vec![],
            zones: vec![],
        }
    }

    #[cfg_attr(test, test)]
    fn fires_for_undersized_iso_component() {
        // max(3.0, 4.0) = 4.0mm package width < 6.0mm required.
        let board = board_with(vec![iso_component("U1", 3.0, 4.0)], BTreeMap::new());
        let check = CreepageCheck::new(6.0);
        let violations = check.check(&board, &ConstraintSet::default());
        assert_eq!(violations.len(), 1, "undersized isolation package must fire exactly one violation");
        assert_eq!(violations[0].code, "SAF_CRP_001");
        assert!(violations[0].message.contains("U1"), "message should name the offending refdes: {}", violations[0].message);
    }

    #[cfg_attr(test, test)]
    fn does_not_fire_for_oversized_iso_component() {
        let board = board_with(vec![iso_component("U1", 8.0, 8.0)], BTreeMap::new());
        let check = CreepageCheck::new(6.0);
        let violations = check.check(&board, &ConstraintSet::default());
        assert!(violations.is_empty(), "well-sized isolation package must not fire");
    }

    #[cfg_attr(test, test)]
    fn does_not_fire_for_non_iso_component() {
        // Same undersized dimensions as the fires_for_undersized case, but a
        // net class that matches no isolation keyword: specificity half of
        // the fires/does-not-fire pair.
        let mut c = iso_component("R1", 1.0, 1.0);
        c.net_class = NetClassName("Signal".into());
        let board = board_with(vec![c], BTreeMap::new());
        let check = CreepageCheck::new(6.0);
        let violations = check.check(&board, &ConstraintSet::default());
        assert!(violations.is_empty(), "non-isolation component must never trigger the creepage check, regardless of size");
    }

    #[cfg_attr(test, test)]
    fn boundary_exact_threshold_is_compliant() {
        // package_width == min_iso_width_mm exactly must NOT fire: the
        // comparison is strict `<` (`package_width < min_iso_width_mm`),
        // matching the ported Python original
        // (`if package_width < self._min_iso_width_mm`). The requirement is
        // "at least min_iso_width_mm", so equality satisfies it.
        let board = board_with(vec![iso_component("U1", 6.0, 6.0)], BTreeMap::new());
        let check = CreepageCheck::new(6.0);
        let violations = check.check(&board, &ConstraintSet::default());
        assert!(violations.is_empty(), "exact-threshold width (== min_iso_width_mm) must be compliant, not violating");
    }

    #[cfg_attr(test, test)]
    fn boundary_just_below_threshold_fires() {
        let board = board_with(vec![iso_component("U1", 5.999, 5.999)], BTreeMap::new());
        let check = CreepageCheck::new(6.0);
        let violations = check.check(&board, &ConstraintSet::default());
        assert_eq!(violations.len(), 1, "0.001mm under threshold must fire");
    }

    #[cfg_attr(test, test)]
    fn boundary_just_above_threshold_does_not_fire() {
        let board = board_with(vec![iso_component("U1", 6.001, 6.001)], BTreeMap::new());
        let check = CreepageCheck::new(6.0);
        let violations = check.check(&board, &ConstraintSet::default());
        assert!(violations.is_empty(), "0.001mm over threshold must not fire");
    }

    #[cfg_attr(test, test)]
    fn uses_max_of_width_and_height_not_sum_or_min() {
        // width=2.0 (too small alone) but height=8.0 (compliant alone).
        // max(2.0, 8.0) = 8.0 >= 6.0 required -> must NOT fire. This proves
        // the rule takes max(width, height) as the barrier's physical
        // separation distance, matching Python's `max(comp.width,
        // comp.height)` -- not min() (which would wrongly fire here) and
        // not width+height (which would wrongly pass a genuinely undersized
        // single dimension in other cases).
        let board = board_with(vec![iso_component("U1", 2.0, 8.0)], BTreeMap::new());
        let check = CreepageCheck::new(6.0);
        let violations = check.check(&board, &ConstraintSet::default());
        assert!(violations.is_empty(), "max(width, height) should govern the creepage distance, not min() or width alone");
    }

    #[cfg_attr(test, test)]
    fn declared_safety_category_iso_is_honored_without_keyword_match() {
        // Net class name has no isolation keyword at all, but the SSOT
        // manifest declares safety_category = "iso" explicitly. The
        // declared category must take precedence and still trigger the
        // check for an undersized package.
        let mut c = iso_component("U1", 3.0, 3.0);
        c.net_class = NetClassName("CLASS_X".into());
        let mut rules = BTreeMap::new();
        rules.insert(
            NetClassName("CLASS_X".into()),
            NetClassRules { safety_category: Some("iso".into()), ..NetClassRules::default() },
        );
        let board = board_with(vec![c], rules);
        let check = CreepageCheck::new(6.0);
        let violations = check.check(&board, &ConstraintSet::default());
        assert_eq!(violations.len(), 1, "declared safety_category=iso must be honored even without a keyword match");
    }

    #[cfg_attr(test, test)]
    fn declared_safety_category_overrides_keyword_match() {
        // Net class name DOES contain the "iso" keyword, but the SSOT
        // manifest explicitly declares a non-iso safety_category. Per the
        // code's documented precedence ("Prefer declared safety_category
        // from the model"), the declared value wins and the keyword
        // fallback is never consulted -- so an undersized package here must
        // NOT fire.
        let mut c = iso_component("U1", 1.0, 1.0);
        c.net_class = NetClassName("ISO_LOOKALIKE".into());
        let mut rules = BTreeMap::new();
        rules.insert(
            NetClassName("ISO_LOOKALIKE".into()),
            NetClassRules { safety_category: Some("power".into()), ..NetClassRules::default() },
        );
        let board = board_with(vec![c], rules);
        let check = CreepageCheck::new(6.0);
        let violations = check.check(&board, &ConstraintSet::default());
        assert!(
            violations.is_empty(),
            "a declared non-iso safety_category must override the 'iso' keyword substring match"
        );
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("rules::safety::creepage::tests::fires_for_undersized_iso_component", fires_for_undersized_iso_component),
        ("rules::safety::creepage::tests::does_not_fire_for_oversized_iso_component", does_not_fire_for_oversized_iso_component),
        ("rules::safety::creepage::tests::does_not_fire_for_non_iso_component", does_not_fire_for_non_iso_component),
        ("rules::safety::creepage::tests::boundary_exact_threshold_is_compliant", boundary_exact_threshold_is_compliant),
        ("rules::safety::creepage::tests::boundary_just_below_threshold_fires", boundary_just_below_threshold_fires),
        ("rules::safety::creepage::tests::boundary_just_above_threshold_does_not_fire", boundary_just_above_threshold_does_not_fire),
        ("rules::safety::creepage::tests::uses_max_of_width_and_height_not_sum_or_min", uses_max_of_width_and_height_not_sum_or_min),
        ("rules::safety::creepage::tests::declared_safety_category_iso_is_honored_without_keyword_match", declared_safety_category_iso_is_honored_without_keyword_match),
        ("rules::safety::creepage::tests::declared_safety_category_overrides_keyword_match", declared_safety_category_overrides_keyword_match),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
