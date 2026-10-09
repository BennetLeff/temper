//! Vendor fabrication profiles (`zapote/fab-profiles/*.json`).
//!
//! A profile turns a fab house's published capabilities into
//! [`FabricationLimits`]. Every limit must carry the vendor's text verbatim
//! (and, for a derived value, the derivation), and that text must contain the
//! number it backs, so no figure enters the checks unsourced or misread.
use crate::manufacturing::FabricationLimits;
use std::collections::BTreeMap;

pub const SCHEMA: &str = "zapote.fab-profile.v1";

#[derive(serde::Deserialize)]
#[serde(deny_unknown_fields)]
struct Profile {
    schema: String,
    name: String,
    vendor: String,
    source: String,
    /// Date the source was read (YYYY-MM-DD).
    read: String,
    limits: Limits,
    quotes: BTreeMap<String, String>,
    #[serde(default)]
    derivations: BTreeMap<String, String>,
    #[serde(default)]
    #[allow(dead_code)]
    notes: Vec<String>,
}

#[derive(serde::Deserialize, serde::Serialize)]
#[serde(deny_unknown_fields)]
struct Limits {
    minimum_annular_ring_mm: f64,
    minimum_hole_clearance_mm: f64,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    minimum_via_annular_ring_mm: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    minimum_via_hole_clearance_mm: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    minimum_track_width_mm: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    minimum_via_drill_mm: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    minimum_pth_drill_mm: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    maximum_pth_drill_mm: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    minimum_npth_drill_mm: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    minimum_copper_to_edge_mm: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    maximum_board_mm: Option<[f64; 2]>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    minimum_copper_clearance_mm: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    minimum_via_hole_to_copper_mm: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    minimum_pth_hole_to_copper_mm: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    minimum_npth_hole_to_copper_mm: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    minimum_silk_text_height_mm: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    minimum_silk_line_width_mm: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    minimum_smd_pad_to_pad_mm: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    minimum_pad_to_track_mm: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    minimum_inner_pth_hole_to_copper_mm: Option<f64>,
    #[serde(default, skip_serializing_if = "Option::is_none")]
    minimum_pad_to_silk_mm: Option<f64>,
}

/// Parse and audit a profile; returns limits marked vendor-qualified.
pub fn parse_profile(text: &str) -> Result<FabricationLimits, String> {
    let p: Profile = serde_json::from_str(text).map_err(|e| format!("fab profile: {e}"))?;
    if p.schema != SCHEMA {
        return Err(format!("fab profile: schema must be {SCHEMA}"));
    }
    if [&p.name, &p.vendor, &p.source, &p.read].iter().any(|s| s.trim().is_empty()) {
        return Err("fab profile: name, vendor, source and read date are required".into());
    }
    let values = serde_json::to_value(&p.limits).map_err(|e| e.to_string())?;
    for (key, value) in values.as_object().expect("limits serialize as an object") {
        let quote = p
            .quotes
            .get(key)
            .ok_or_else(|| format!("fab profile {}: {key} has no vendor quote", p.name))?;
        let numbers: Vec<f64> = match value {
            serde_json::Value::Array(items) => items.iter().filter_map(|v| v.as_f64()).collect(),
            other => other.as_f64().into_iter().collect(),
        };
        // Parenthesised text in a vendor quote is a condition or exception
        // ("0.1mm/0.2mm only available for board thickness <=1mm"), never the
        // rule itself, so its numbers cannot back a limit.
        let backing = format!(
            "{} {}",
            outside_parentheses(quote),
            p.derivations.get(key).map_or("", String::as_str)
        );
        let stated = numbers_in(&backing);
        for n in numbers {
            if !n.is_finite() || n < 0.0 || !stated.iter().any(|s| (s - n).abs() < 1e-9) {
                return Err(format!(
                    "fab profile {}: {key} = {n} does not appear in its quote or derivation",
                    p.name
                ));
            }
        }
    }
    for key in p.quotes.keys().chain(p.derivations.keys()) {
        if values.get(key).is_none() {
            return Err(format!("fab profile {}: quote for unknown or unset limit {key}", p.name));
        }
    }
    let l = p.limits;
    Ok(FabricationLimits {
        name: p.name,
        source: format!("{} {} (read {})", p.vendor, p.source, p.read),
        qualified: true,
        minimum_annular_ring_mm: l.minimum_annular_ring_mm,
        minimum_hole_clearance_mm: l.minimum_hole_clearance_mm,
        // Fabrication profiles do not qualify an assembly process.
        assembly_process: String::new(),
        minimum_via_annular_ring_mm: l.minimum_via_annular_ring_mm,
        minimum_via_hole_clearance_mm: l.minimum_via_hole_clearance_mm,
        minimum_track_width_mm: l.minimum_track_width_mm,
        minimum_via_drill_mm: l.minimum_via_drill_mm,
        minimum_pth_drill_mm: l.minimum_pth_drill_mm,
        maximum_pth_drill_mm: l.maximum_pth_drill_mm,
        minimum_npth_drill_mm: l.minimum_npth_drill_mm,
        minimum_copper_to_edge_mm: l.minimum_copper_to_edge_mm,
        maximum_board_mm: l.maximum_board_mm,
        minimum_copper_clearance_mm: l.minimum_copper_clearance_mm,
        minimum_via_hole_to_copper_mm: l.minimum_via_hole_to_copper_mm,
        minimum_pth_hole_to_copper_mm: l.minimum_pth_hole_to_copper_mm,
        minimum_npth_hole_to_copper_mm: l.minimum_npth_hole_to_copper_mm,
        minimum_silk_text_height_mm: l.minimum_silk_text_height_mm,
        minimum_silk_line_width_mm: l.minimum_silk_line_width_mm,
        minimum_smd_pad_to_pad_mm: l.minimum_smd_pad_to_pad_mm,
        minimum_pad_to_track_mm: l.minimum_pad_to_track_mm,
        minimum_inner_pth_hole_to_copper_mm: l.minimum_inner_pth_hole_to_copper_mm,
        minimum_pad_to_silk_mm: l.minimum_pad_to_silk_mm,
    })
}

fn outside_parentheses(text: &str) -> String {
    let mut depth = 0usize;
    text.chars()
        .filter(|c| match c {
            '(' => {
                depth += 1;
                false
            }
            ')' => {
                depth = depth.saturating_sub(1);
                false
            }
            _ => depth == 0,
        })
        .collect()
}

/// Every decimal number written in `text` ("0.15/0.25mm" -> 0.15, 0.25).
fn numbers_in(text: &str) -> Vec<f64> {
    text.split(|c: char| !(c.is_ascii_digit() || c == '.'))
        .filter_map(|token| token.trim_matches('.').parse::<f64>().ok())
        .collect()
}

pub fn load_profile(path: &std::path::Path) -> Result<FabricationLimits, String> {
    let text = std::fs::read_to_string(path).map_err(|e| format!("{}: {e}", path.display()))?;
    parse_profile(&text).map_err(|e| format!("{}: {e}", path.display()))
}
