// Safety check: HV/LV separation — edge-to-edge distance between HV and LV
// components must be >= hv_clearance_mm.
//
// Safety requirements (IEC 60335) demand large clearances between
// mains-connected circuitry and user-accessible low voltage logic.
//
// Ported from: packages/temper-drc/src/temper_drc/checks/safety/hv_lv_separation.py
//
// Origin: U4 of docs/plans/2026-06-30-003-feat-temper-drc-rs-engine-plan.md

use crate::board::{BoardState, Component};
use crate::constraints::ConstraintSet;
use crate::rules::{location_midpoint, violation, DrcCategory, DrcRule, Severity, Violation};

/// Keywords that classify a net class as High Voltage.
const HV_KEYWORDS: [&str; 5] = ["hv", "line", "ac", "neutral", "mains"];

/// Keywords that classify a net class as Low Voltage.
const LV_KEYWORDS: [&str; 6] = ["lv", "signal", "3v3", "5v", "gnd", "analog"];

/// Determine the safety category of a component's net class.
///
/// Consults `NetClassRules.safety_category` (declared in the SSOT manifest) first.
/// Falls back to keyword substring matching for undeclared net classes.
fn resolve_safety_category(comp: &Component, board: &BoardState) -> Option<&'static str> {
    // Prefer declared safety_category from the model
    if let Some(rules) = board.net_class_rules.get(&comp.net_class)
        && let Some(ref sc) = rules.safety_category
    {
        return match sc.as_str() {
            "HV" => Some("HV"),
            "LV" => Some("LV"),
            "AC" => Some("HV"), // AC treated as HV-side for separation
            _ => None,
        };
    }
    // Keyword fallback
    let lc = comp.net_class.0.to_lowercase();
    if HV_KEYWORDS.iter().any(|k| lc.contains(k)) {
        Some("HV")
    } else if LV_KEYWORDS.iter().any(|k| lc.contains(k)) {
        Some("LV")
    } else {
        None
    }
}

#[derive(Default)]
pub struct HVLVSeparationCheck;

impl HVLVSeparationCheck {
    pub fn new() -> Self {
        Self
    }
}

impl DrcRule for HVLVSeparationCheck {
    fn name(&self) -> &str {
        "safety_hv_lv_separation"
    }

    fn category(&self) -> DrcCategory {
        DrcCategory::Safety
    }

    fn description(&self) -> &str {
        "Ensure critical separation between HV and LV domains for safety compliance."
    }

    fn check(&self, board: &BoardState, constraints: &ConstraintSet) -> Vec<Violation> {
        let mut violations = Vec::new();
        let required_gap = constraints.hv_clearance_mm;
        let comps: Vec<&Component> = board.all_components().collect();
        let n = comps.len();

        // Safety category is pure per component; resolve once, not per pair.
        let cats: Vec<Option<&'static str>> = comps
            .iter()
            .map(|c| resolve_safety_category(c, board))
            .collect();

        for i in 0..n {
            for j in (i + 1)..n {
                let a = &comps[i];
                let b = &comps[j];

                let a_cat = cats[i];
                let b_cat = cats[j];

                let is_a_hv = a_cat == Some("HV");
                let is_b_hv = b_cat == Some("HV");
                let is_a_lv = a_cat == Some("LV");
                let is_b_lv = b_cat == Some("LV");

                // Check if one is HV and the other is LV
                if (is_a_hv && is_b_lv) || (is_b_hv && is_a_lv) {
                    let dist = a.edge_distance_to(b);

                    if dist < required_gap {
                        violations.push(violation(
                            Severity::Critical,
                            "SAF_HVL_001",
                            &format!(
                                "HV/LV Safety violation: gap {:.2}mm < {:.2}mm between {} (HV) and {} (LV)",
                                dist, required_gap, a.refdes, b.refdes,
                            ),
                            DrcCategory::Safety,
                            "safety_hv_lv_separation",
                            vec![a.refdes.0.clone(), b.refdes.0.clone()],
                            location_midpoint(&a.center, &b.center, None),
                            serde_json::json!({
                                "actual_gap_mm": dist,
                                "required_gap_mm": required_gap,
                                "class_a": a.net_class,
                                "class_b": b.net_class,
                            }),
                        ));
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
    use crate::constraints::ConstraintSet;
    use geo::{polygon, Point};
    use std::collections::HashMap;

    /// An axis-aligned square, half-extent `half` on each side.
    fn axis_square(refdes: &str, cx: f64, cy: f64, half: f64, net_class: &str) -> Component {
        Component {
            refdes: ComponentRef(refdes.into()),
            center: Point::new(cx, cy),
            rotation: 0.0,
            side: BoardSide::Top,
            width: half * 2.0,
            height: half * 2.0,
            net_class: NetClassName(net_class.into()),
            power_dissipation_w: None,
            package_type: PackageType::Smd,
            is_magnetic: false,
            is_electrolytic: false,
            vent_direction: None,
            footprint_polygon: Some(polygon![
                (x: cx - half, y: cy - half),
                (x: cx + half, y: cy - half),
                (x: cx + half, y: cy + half),
                (x: cx - half, y: cy + half),
            ]),
        }
    }

    /// A square rotated 45 degrees (a diamond), with vertices at
    /// `(cx +/- r, cy)` and `(cx, cy +/- r)` -- i.e. `r` is the
    /// half-diagonal, and the shape's edges run at 45 degrees to the board
    /// axes. Deliberately non-axis-aligned, and (via `r`) an independently
    /// sized footprint from whatever it is compared against, so a
    /// center-to-center distance and a true edge-to-edge distance diverge.
    fn diamond(refdes: &str, cx: f64, cy: f64, r: f64, net_class: &str) -> Component {
        Component {
            refdes: ComponentRef(refdes.into()),
            center: Point::new(cx, cy),
            rotation: 45.0,
            side: BoardSide::Top,
            width: r * 2.0,
            height: r * 2.0,
            net_class: NetClassName(net_class.into()),
            power_dissipation_w: None,
            package_type: PackageType::Smd,
            is_magnetic: false,
            is_electrolytic: false,
            vent_direction: None,
            footprint_polygon: Some(polygon![
                (x: cx - r, y: cy),
                (x: cx, y: cy - r),
                (x: cx + r, y: cy),
                (x: cx, y: cy + r),
            ]),
        }
    }

    fn board_with(components: Vec<Component>) -> BoardState {
        BoardState {
            width_mm: 200.0,
            height_mm: 200.0,
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

    fn constraints_with_gap(hv_clearance_mm: f64) -> ConstraintSet {
        ConstraintSet { hv_clearance_mm, ..Default::default() }
    }

    #[cfg_attr(test, test)]
    fn fires_on_true_edge_gap_even_though_centers_are_far_apart() {
        // HV1: a 20mm x 20mm axis-aligned square centered at the origin;
        // its right edge is the vertical segment x=10, y in [-10, 10].
        //
        // LV1: a 16mm-diagonal diamond (rotated 45 degrees, so genuinely
        // non-axis-aligned, and a different size/shape from HV1) centered
        // at (18.5, 0). Its leftmost vertex is at (18.5 - 8, 0) = (10.5, 0)
        // -- 0.5mm from HV1's right edge.
        //
        // Center-to-center distance is 18.5mm -- comfortably clear of the
        // 3mm required gap, so a naive center-distance implementation
        // would (wrongly) report this pair as compliant. The true
        // edge-to-edge gap is only 0.5mm: a genuine, dangerous violation.
        // This is exactly the case that would catch a wrong/naive
        // implementation and the fires-when-it-should half of this rule's
        // coverage.
        let hv = axis_square("HV1", 0.0, 0.0, 10.0, "MAINS_LIVE");
        let lv = diamond("LV1", 18.5, 0.0, 8.0, "GND_LOGIC");
        let center_dist: f64 = 18.5_f64.hypot(0.0);
        assert!(center_dist > 3.0, "sanity: centers must be farther apart than the required gap");

        let board = board_with(vec![hv, lv]);
        let constraints = constraints_with_gap(3.0);
        let check = HVLVSeparationCheck::new();
        let violations = check.check(&board, &constraints);

        assert_eq!(violations.len(), 1, "true edge gap of 0.5mm < 3mm required must fire");
        assert_eq!(violations[0].code, "SAF_HVL_001");
        assert!(violations[0].message.contains("HV1"));
        assert!(violations[0].message.contains("LV1"));
        let actual_gap = violations[0].details["actual_gap_mm"].as_f64().expect("actual_gap_mm present");
        assert!((actual_gap - 0.5).abs() < 0.01, "expected ~0.5mm true edge gap, got {actual_gap}");
    }

    #[cfg_attr(test, test)]
    fn does_not_fire_when_true_edge_gap_exceeds_threshold() {
        // Same shapes as above, moved apart so the true edge gap (7mm) is
        // comfortably over the 3mm requirement.
        let hv = axis_square("HV1", 0.0, 0.0, 10.0, "MAINS_LIVE");
        let lv = diamond("LV1", 25.0, 0.0, 8.0, "GND_LOGIC");
        let board = board_with(vec![hv, lv]);
        let constraints = constraints_with_gap(3.0);
        let check = HVLVSeparationCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(violations.is_empty(), "7mm true edge gap must not fire against a 3mm requirement");
    }

    #[cfg_attr(test, test)]
    fn does_not_fire_for_hv_hv_pair_regardless_of_gap() {
        // Two HV components overlapping (0mm gap) -- the rule only checks
        // HV-vs-LV pairs, so this must never fire even though the gap is
        // far below any plausible threshold.
        let a = axis_square("HV1", 0.0, 0.0, 10.0, "MAINS_LIVE");
        let b = axis_square("HV2", 5.0, 0.0, 10.0, "AC_LINE");
        let board = board_with(vec![a, b]);
        let constraints = constraints_with_gap(3.0);
        let check = HVLVSeparationCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(violations.is_empty(), "HV-HV pairs are out of scope for this rule");
    }

    #[cfg_attr(test, test)]
    fn does_not_fire_for_lv_lv_pair_regardless_of_gap() {
        let a = axis_square("R1", 0.0, 0.0, 10.0, "SIGNAL");
        let b = axis_square("R2", 5.0, 0.0, 10.0, "GND");
        let board = board_with(vec![a, b]);
        let constraints = constraints_with_gap(3.0);
        let check = HVLVSeparationCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(violations.is_empty(), "LV-LV pairs are out of scope for this rule");
    }

    #[cfg_attr(test, test)]
    fn does_not_fire_for_unclassified_net_classes() {
        // Neither net class matches any HV or LV keyword and neither
        // declares a safety_category: the pair must be skipped entirely,
        // even directly overlapping.
        let a = axis_square("X1", 0.0, 0.0, 10.0, "MISC_A");
        let b = axis_square("X2", 5.0, 0.0, 10.0, "MISC_B");
        let board = board_with(vec![a, b]);
        let constraints = constraints_with_gap(3.0);
        let check = HVLVSeparationCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(violations.is_empty(), "unclassified net classes must not be evaluated by this rule");
    }

    #[cfg_attr(test, test)]
    fn boundary_exact_threshold_gap_is_compliant() {
        // Diamond positioned so its nearest vertex is exactly 3.0mm from
        // HV1's right edge (x=10): center at (10 + 8 + 3.0, 0) = (21.0, 0),
        // vertex at (21.0 - 8, 0) = (13.0, 0), gap = 13.0 - 10.0 = 3.0mm.
        //
        // The comparison is strict `<` (`dist < required_gap`), matching
        // the ported Python original (`if dist < required_gap`). The
        // requirement is "gap must be at least required_gap", so an exact
        // match is compliant and must NOT fire.
        let hv = axis_square("HV1", 0.0, 0.0, 10.0, "MAINS_LIVE");
        let lv = diamond("LV1", 21.0, 0.0, 8.0, "GND_LOGIC");
        let board = board_with(vec![hv, lv]);
        let constraints = constraints_with_gap(3.0);
        let check = HVLVSeparationCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(violations.is_empty(), "exact-threshold gap (== required_gap) must be compliant, not violating");
    }

    #[cfg_attr(test, test)]
    fn boundary_just_below_threshold_fires() {
        let hv = axis_square("HV1", 0.0, 0.0, 10.0, "MAINS_LIVE");
        let lv = diamond("LV1", 20.999, 0.0, 8.0, "GND_LOGIC");
        let board = board_with(vec![hv, lv]);
        let constraints = constraints_with_gap(3.0);
        let check = HVLVSeparationCheck::new();
        let violations = check.check(&board, &constraints);
        assert_eq!(violations.len(), 1, "0.001mm under the required gap must fire");
    }

    #[cfg_attr(test, test)]
    fn boundary_just_above_threshold_does_not_fire() {
        let hv = axis_square("HV1", 0.0, 0.0, 10.0, "MAINS_LIVE");
        let lv = diamond("LV1", 21.001, 0.0, 8.0, "GND_LOGIC");
        let board = board_with(vec![hv, lv]);
        let constraints = constraints_with_gap(3.0);
        let check = HVLVSeparationCheck::new();
        let violations = check.check(&board, &constraints);
        assert!(violations.is_empty(), "0.001mm over the required gap must not fire");
    }

    #[cfg_attr(test, test)]
    fn declared_safety_category_hv_and_lv_are_honored_without_keywords() {
        // Net class names carry no HV/LV keyword at all; classification
        // comes solely from the declared safety_category in
        // net_class_rules.
        let hv = axis_square("HV1", 0.0, 0.0, 10.0, "CLASS_A");
        let lv = diamond("LV1", 18.5, 0.0, 8.0, "CLASS_B");
        let mut board = board_with(vec![hv, lv]);
        let mut rules = HashMap::new();
        rules.insert(
            NetClassName("CLASS_A".into()),
            NetClassRules { safety_category: Some("HV".into()), ..NetClassRules::default() },
        );
        rules.insert(
            NetClassName("CLASS_B".into()),
            NetClassRules { safety_category: Some("LV".into()), ..NetClassRules::default() },
        );
        board.net_class_rules = rules;
        let constraints = constraints_with_gap(3.0);
        let check = HVLVSeparationCheck::new();
        let violations = check.check(&board, &constraints);
        assert_eq!(violations.len(), 1, "declared HV/LV safety_category must be honored without any keyword match");
    }

    #[cfg_attr(test, test)]
    fn declared_safety_category_ac_is_treated_as_hv() {
        let ac = axis_square("AC1", 0.0, 0.0, 10.0, "CLASS_AC");
        let lv = diamond("LV1", 18.5, 0.0, 8.0, "CLASS_B");
        let mut board = board_with(vec![ac, lv]);
        let mut rules = HashMap::new();
        rules.insert(
            NetClassName("CLASS_AC".into()),
            NetClassRules { safety_category: Some("AC".into()), ..NetClassRules::default() },
        );
        rules.insert(
            NetClassName("CLASS_B".into()),
            NetClassRules { safety_category: Some("LV".into()), ..NetClassRules::default() },
        );
        board.net_class_rules = rules;
        let constraints = constraints_with_gap(3.0);
        let check = HVLVSeparationCheck::new();
        let violations = check.check(&board, &constraints);
        assert_eq!(violations.len(), 1, "declared safety_category='AC' must be treated as HV for this rule");
    }

    // --- BEGIN generated by scripts/gen_wasm_test_registry.py: tests ---
    /// Every `#[test]` in this module, as a callable the `wasm32`
    /// entry point can invoke by index.  Generated because these
    /// functions are private to this module and unreachable from
    /// anywhere a registry could otherwise live.
    pub const WASM_TESTS: &[(&str, fn())] = &[
        ("rules::safety::hv_lv_separation::tests::fires_on_true_edge_gap_even_though_centers_are_far_apart", fires_on_true_edge_gap_even_though_centers_are_far_apart),
        ("rules::safety::hv_lv_separation::tests::does_not_fire_when_true_edge_gap_exceeds_threshold", does_not_fire_when_true_edge_gap_exceeds_threshold),
        ("rules::safety::hv_lv_separation::tests::does_not_fire_for_hv_hv_pair_regardless_of_gap", does_not_fire_for_hv_hv_pair_regardless_of_gap),
        ("rules::safety::hv_lv_separation::tests::does_not_fire_for_lv_lv_pair_regardless_of_gap", does_not_fire_for_lv_lv_pair_regardless_of_gap),
        ("rules::safety::hv_lv_separation::tests::does_not_fire_for_unclassified_net_classes", does_not_fire_for_unclassified_net_classes),
        ("rules::safety::hv_lv_separation::tests::boundary_exact_threshold_gap_is_compliant", boundary_exact_threshold_gap_is_compliant),
        ("rules::safety::hv_lv_separation::tests::boundary_just_below_threshold_fires", boundary_just_below_threshold_fires),
        ("rules::safety::hv_lv_separation::tests::boundary_just_above_threshold_does_not_fire", boundary_just_above_threshold_does_not_fire),
        ("rules::safety::hv_lv_separation::tests::declared_safety_category_hv_and_lv_are_honored_without_keywords", declared_safety_category_hv_and_lv_are_honored_without_keywords),
        ("rules::safety::hv_lv_separation::tests::declared_safety_category_ac_is_treated_as_hv", declared_safety_category_ac_is_treated_as_hv),
    ];
    // --- END generated by scripts/gen_wasm_test_registry.py: tests ---
}
