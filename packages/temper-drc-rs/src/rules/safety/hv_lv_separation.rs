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
    let nc = crate::board::NetClassName(comp.net_class.0.clone());
    if let Some(rules) = board.net_class_rules.get(&nc) {
        if let Some(ref sc) = rules.safety_category {
            return match sc.as_str() {
                "HV" => Some("HV"),
                "LV" => Some("LV"),
                "AC" => Some("HV"), // AC treated as HV-side for separation
                _ => None,
            };
        }
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

        for i in 0..n {
            for j in (i + 1)..n {
                let a = &comps[i];
                let b = &comps[j];

                let a_cat = resolve_safety_category(a, board);
                let b_cat = resolve_safety_category(b, board);

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
