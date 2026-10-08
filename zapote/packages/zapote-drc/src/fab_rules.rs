//! KiCad custom DRC rules for a vendor fab profile (the `zapote-check` fab pass).
//!
//! Some fab limits are best measured by KiCad itself: copper-to-copper
//! spacing, hole-to-copper clearance per hole type and silkscreen text size.
//! These rules run in a separate DRC pass on a *copy* of the board whose
//! `.kicad_dru` holds only them. Measured on KiCad 10.0.4 (2026-10-09): when
//! several custom rules match, the last one wins even if it is looser, and a
//! custom clearance overrides the netclass value, so appending vendor rules
//! to a board's own rules could silently weaken a safety rule. A separate pass
//! keeps both checks intact. Every rule name starts with [`RULE_PREFIX`], which
//! KiCad prints in each violation (`(rule 'zapote fab ...' ...)`), so findings
//! are attributed exactly.
use crate::manufacturing::FabricationLimits;

pub const RULE_PREFIX: &str = "zapote fab";

fn mm(v: f64) -> String {
    format!("{v}mm")
}

/// The `.kicad_dru` text for the limits this pass applies, or `None` when the
/// profile sets none of them (then the pass is not run).
pub fn kicad_rules(limits: &FabricationLimits) -> Option<String> {
    let mut rules = Vec::new();
    let mut rule = |name: &str, scope: &str, constraint: &str, value: Option<f64>| {
        if let Some(v) = value {
            rules.push(format!(
                "(rule \"{RULE_PREFIX} {name}\"{scope} (constraint {constraint} (min {})))",
                mm(v)
            ));
        }
    };
    rule(
        "copper clearance",
        "",
        "clearance",
        limits.minimum_copper_clearance_mm,
    );
    rule(
        "via hole to copper",
        " (condition \"A.Type == 'Via'\")",
        "hole_clearance",
        limits.minimum_via_hole_to_copper_mm,
    );
    rule(
        "PTH hole to copper",
        " (condition \"A.Type == 'Pad' && A.Pad_Type == 'Through-hole'\")",
        "hole_clearance",
        limits.minimum_pth_hole_to_copper_mm,
    );
    rule(
        "NPTH hole to copper",
        " (condition \"A.Type == 'Pad' && A.Pad_Type == 'NPTH, mechanical'\")",
        "hole_clearance",
        limits.minimum_npth_hole_to_copper_mm,
    );
    for (suffix, layer) in [("", "F.SilkS"), (" B", "B.SilkS")] {
        let scope = format!(" (layer \"{layer}\")");
        rule(
            &format!("silk text height{suffix}"),
            &scope,
            "text_height",
            limits.minimum_silk_text_height_mm,
        );
        rule(
            &format!("silk text thickness{suffix}"),
            &scope,
            "text_thickness",
            limits.minimum_silk_line_width_mm,
        );
    }
    if rules.is_empty() {
        None
    } else {
        Some(format!("(version 1)\n{}\n", rules.join("\n")))
    }
}
