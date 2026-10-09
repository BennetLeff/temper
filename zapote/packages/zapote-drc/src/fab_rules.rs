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

/// One emitted rule: the KiCad constraint it sets and the violation type
/// (also the check key) KiCad reports for it. An empty `text` marks a
/// board-setup rule: the fab copy sets it in the board, not in `.kicad_dru`.
#[derive(Clone, Debug, PartialEq)]
pub struct KicadRule {
    pub name: String,
    pub constraint: String,
    pub violation: String,
    pub text: String,
}

fn rule(name: &str, scope: &str, constraint: &str, min_mm: f64) -> KicadRule {
    let name = format!("{RULE_PREFIX} {name}");
    let text = format!("(rule \"{name}\"{scope} (constraint {constraint} (min {min_mm}mm)))");
    KicadRule { name, constraint: constraint.into(), violation: constraint.into(), text }
}

/// The rules for the limits this pass applies, in `.kicad_dru` order.
pub fn rules(limits: &FabricationLimits) -> Vec<KicadRule> {
    let mut out = Vec::new();
    // General spacing first, then the vendor's pad-specific rows: KiCad keeps
    // the last matching rule, so a pad pair is judged by the row written for it
    // (JLC's SMD pad-to-pad 0.15 mm applies to pads even on 2 oz, where track
    // spacing is 0.16 mm). Arcs are `Track` in KiCad's expressions (measured).
    if let Some(v) = limits.minimum_copper_clearance_mm {
        out.push(rule("copper clearance", "", "clearance", v));
    }
    if let Some(v) = limits.minimum_pad_to_track_mm {
        out.push(rule("pad to track", " (condition \"A.Type == 'Pad' && B.Type == 'Track'\")", "clearance", v));
    }
    if let Some(v) = limits.minimum_smd_pad_to_pad_mm {
        let condition = "A.Type == 'Pad' && A.Pad_Type == 'SMD' && B.Type == 'Pad' && B.Pad_Type == 'SMD'";
        out.push(rule("SMD pad to pad", &format!(" (condition \"{condition}\")"), "clearance", v));
    }
    // A via beside a PTH pad matches both hole rules (KiCad tries A/B both
    // ways) and the last match wins, so the hole rules go loosest first: a
    // shared pair is judged at the stricter limit, never the looser.
    let pth = "A.Type == 'Pad' && A.Pad_Type == 'Through-hole'";
    let mut holes: Vec<(f64, KicadRule)> = [
        ("via hole to copper", "", "A.Type == 'Via'", limits.minimum_via_hole_to_copper_mm),
        ("PTH hole to copper", "", pth, limits.minimum_pth_hole_to_copper_mm),
        (
            "NPTH hole to copper",
            "",
            "A.Type == 'Pad' && A.Pad_Type == 'NPTH, mechanical'",
            limits.minimum_npth_hole_to_copper_mm,
        ),
        ("inner PTH hole to copper", " (layer inner)", pth, limits.minimum_inner_pth_hole_to_copper_mm),
    ]
    .into_iter()
    .filter_map(|(name, layer, condition, v)| {
        Some((v?, rule(name, &format!("{layer} (condition \"{condition}\")"), "hole_clearance", v?)))
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
    // Silk to pad: a silk_clearance rule scoped to pads measures silkscreen to
    // pad (the mask opening) and is reported as `silk_over_copper`; silk to
    // silk stays with the board's own setup (measured on 10.0.4).
    if let Some(v) = limits.minimum_pad_to_silk_mm {
        let mut r = rule("pad to silk", " (condition \"A.Type == 'Pad' || B.Type == 'Pad'\")", "silk_clearance", v);
        r.violation = "silk_over_copper".into();
        out.push(r);
    }
    // Solder-mask web: KiCad has no custom-rule constraint for it. The fab copy
    // sets the board's minimum web width, and KiCad's solder_mask_bridge check
    // then reports mask openings that merge across different nets (measured on
    // 10.0.4; with the board's own 0 mm the same pads are not reported).
    if limits.minimum_solder_mask_web_mm.is_some() {
        out.push(KicadRule {
            name: format!("{RULE_PREFIX} solder mask web"),
            constraint: "solder_mask_min_width".into(),
            violation: "solder_mask_bridge".into(),
            text: String::new(),
        });
    }
    out
}

/// The `.kicad_dru` text for the custom rules in [`rules`], or `None` when
/// there are none.
pub fn kicad_rules(limits: &FabricationLimits) -> Option<String> {
    let list = rules(limits);
    let body: Vec<_> = list.iter().map(|r| r.text.as_str()).filter(|t| !t.is_empty()).collect();
    if body.is_empty() {
        return None;
    }
    Some(format!("(version 1)\n{}\n", body.join("\n")))
}
