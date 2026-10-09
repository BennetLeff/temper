//! KiCad custom DRC rules for a vendor fab profile (the `zapote-check` fab pass).
//!
//! Some fab limits are best measured by KiCad itself: copper-to-copper
//! spacing, hole-to-copper clearance per hole type and silkscreen text size.
//! These rules run in a separate DRC pass on a *copy* of the board whose
//! `.kicad_dru` holds only them. Measured on KiCad 10.0.4 (2026-10-08): when
//! several custom rules match, the last one wins even if it is looser, and a
//! custom clearance overrides the netclass value, so appending vendor rules
//! to a board's own rules could silently weaken a safety rule. A separate pass
//! keeps both checks intact. Every rule name starts with [`RULE_PREFIX`], which
//! KiCad prints in each violation (`(rule 'zapote fab ...' ...)`), so findings
//! are attributed exactly.
use crate::manufacturing::FabricationLimits;

pub const RULE_PREFIX: &str = "zapote fab";

/// One emitted rule. `constraint` is also the KiCad violation type it reports.
#[derive(Clone, Debug, PartialEq)]
pub struct KicadRule {
    pub name: String,
    pub constraint: String,
    pub text: String,
}

fn rule(name: &str, scope: &str, constraint: &str, min_mm: f64) -> KicadRule {
    let name = format!("{RULE_PREFIX} {name}");
    let text = format!("(rule \"{name}\"{scope} (constraint {constraint} (min {min_mm}mm)))");
    KicadRule { name, constraint: constraint.into(), text }
}

/// The rules for the limits this pass applies, in `.kicad_dru` order.
pub fn rules(limits: &FabricationLimits) -> Vec<KicadRule> {
    let mut out = Vec::new();
    if let Some(v) = limits.minimum_copper_clearance_mm {
        out.push(rule("copper clearance", "", "clearance", v));
    }
    // A via beside a PTH pad matches both hole rules (KiCad tries A/B both
    // ways) and the last match wins, so the hole rules go loosest first: a
    // shared pair is judged at the stricter limit, never the looser.
    let mut holes: Vec<(f64, KicadRule)> = [
        ("via hole to copper", "A.Type == 'Via'", limits.minimum_via_hole_to_copper_mm),
        (
            "PTH hole to copper",
            "A.Type == 'Pad' && A.Pad_Type == 'Through-hole'",
            limits.minimum_pth_hole_to_copper_mm,
        ),
        (
            "NPTH hole to copper",
            "A.Type == 'Pad' && A.Pad_Type == 'NPTH, mechanical'",
            limits.minimum_npth_hole_to_copper_mm,
        ),
    ]
    .into_iter()
    .filter_map(|(name, condition, v)| {
        Some((v?, rule(name, &format!(" (condition \"{condition}\")"), "hole_clearance", v?)))
    })
    .collect();
    holes.sort_by(|a, b| a.0.total_cmp(&b.0));
    out.extend(holes.into_iter().map(|(_, r)| r));
    for (suffix, layer) in [("", "F.SilkS"), (" B", "B.SilkS")] {
        let scope = format!(" (layer \"{layer}\")");
        if let Some(v) = limits.minimum_silk_text_height_mm {
            out.push(rule(&format!("silk text height{suffix}"), &scope, "text_height", v));
        }
        // The vendor's legend line width; KiCad has a custom-rule constraint
        // only for text strokes, so silkscreen graphic lines are not checked.
        if let Some(v) = limits.minimum_silk_line_width_mm {
            out.push(rule(&format!("silk text thickness{suffix}"), &scope, "text_thickness", v));
        }
    }
    out
}

/// The `.kicad_dru` text for [`rules`], or `None` when the profile sets none
/// of these limits (then the pass is not run).
pub fn kicad_rules(limits: &FabricationLimits) -> Option<String> {
    let list = rules(limits);
    if list.is_empty() {
        return None;
    }
    let body: Vec<_> = list.iter().map(|r| r.text.as_str()).collect();
    Some(format!("(version 1)\n{}\n", body.join("\n")))
}
