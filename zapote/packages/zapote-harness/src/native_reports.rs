//! Validate captured KiCad reports without treating absent fields as empty results.
//! This checks report content and command coverage, not tool authenticity or freshness.
//!
//! Besides the four category counts, every KiCad violation becomes its own
//! finding (`NATIVE.<CATEGORY>.<type>`) carrying KiCad's severity, message,
//! located items and, when KiCad states them, actual/required values.
use serde::{Deserialize, Serialize};
use zapote_core::{CheckReport, Finding};

/// One KiCad ERC/DRC entry, parsed strictly: a missing field is a contract
/// failure, never an empty result.
#[derive(Clone, Debug, Serialize)]
pub struct NativeViolation {
    /// `ERC`, `DRC`, `UNCONNECTED` or `SCHEMATIC_PARITY`.
    pub category: &'static str,
    pub kind: String,
    pub severity: String,
    pub description: String,
    /// ERC sheet path; `None` for board reports.
    pub sheet: Option<String>,
    pub items: Vec<NativeItem>,
    /// Marked excluded in KiCad by the designer, with their comment.
    pub excluded: bool,
    pub comment: Option<String>,
}

#[derive(Clone, Debug, Serialize)]
pub struct NativeItem {
    pub description: String,
    pub x_mm: f64,
    pub y_mm: f64,
    pub uuid: String,
}

#[derive(Deserialize)]
#[serde(deny_unknown_fields)]
struct RawViolation {
    #[serde(rename = "type")]
    kind: String,
    severity: String,
    description: String,
    items: Vec<RawItem>,
    // KiCad 10 writes these only for designer exclusions.
    #[serde(default)]
    excluded: Option<bool>,
    #[serde(default)]
    comment: Option<String>,
}

#[derive(Deserialize)]
struct RawItem {
    description: String,
    pos: RawPos,
    #[serde(default)]
    uuid: String,
}

#[derive(Deserialize)]
struct RawPos {
    x: f64,
    y: f64,
}

fn parse_violation(
    value: &serde_json::Value,
    category: &'static str,
    sheet: Option<&str>,
) -> Result<NativeViolation, String> {
    let raw: RawViolation = serde_json::from_value(value.clone())
        .map_err(|e| format!("{category}: malformed violation entry: {e}"))?;
    // `items` must be present but may be empty: KiCad 10 reports some
    // silk_overlap violations with no located items (native-19 captures).
    if raw.kind.is_empty() || raw.description.is_empty() {
        return Err(format!("{category}: violation without type or description"));
    }
    if raw.items.iter().any(|i| !i.pos.x.is_finite() || !i.pos.y.is_finite()) {
        return Err(format!("{category}: violation item without a finite position"));
    }
    Ok(NativeViolation {
        category,
        kind: raw.kind,
        severity: raw.severity,
        description: raw.description,
        sheet: sheet.map(str::to_owned),
        excluded: raw.excluded.unwrap_or(false),
        comment: raw.comment.filter(|c| !c.is_empty()),
        items: raw
            .items
            .into_iter()
            .map(|i| NativeItem {
                description: i.description,
                x_mm: i.pos.x,
                y_mm: i.pos.y,
                uuid: i.uuid,
            })
            .collect(),
    })
}

/// Every violation in the reports, in report order. Fails on the first
/// malformed entry so callers cannot mistake a parse gap for a clean board.
pub fn violations(erc: &str, drc: &str) -> Result<Vec<NativeViolation>, String> {
    let e: Erc = serde_json::from_str(erc).map_err(|e| format!("ERC schema: {e}"))?;
    let d: Drc = serde_json::from_str(drc).map_err(|e| format!("DRC schema: {e}"))?;
    collect(&e, &d)
}

fn collect(e: &Erc, d: &Drc) -> Result<Vec<NativeViolation>, String> {
    let mut all = Vec::new();
    for sheet in &e.sheets {
        for v in &sheet.violations {
            all.push(parse_violation(v, "ERC", Some(&sheet.path))?);
        }
    }
    for (category, list) in [
        ("DRC", &d.violations),
        ("UNCONNECTED", &d.unconnected_items),
        ("SCHEMATIC_PARITY", &d.schematic_parity),
    ] {
        for v in list {
            all.push(parse_violation(v, category, None)?);
        }
    }
    Ok(all)
}

/// KiCad states limits as `(<constraint> <v> <unit>; actual <v> <unit>)`.
/// Uses the first parenthesised clause that contains "; actual " and its
/// first measurement, so nested `(from ...)` and later clauses (skew/length
/// rules) cannot relabel the values. `actual < 0` (copper collision) is kept.
fn actual_required(description: &str) -> (Option<String>, Option<String>) {
    let clause = description.match_indices('(').find_map(|(open, _)| {
        let rest = &description[open + 1..];
        let mut depth = 0usize;
        let close = rest.char_indices().find_map(|(i, c)| match c {
            '(' => {
                depth += 1;
                None
            }
            ')' if depth == 0 => Some(i),
            ')' => {
                depth -= 1;
                None
            }
            _ => None,
        })?;
        let inner = &rest[..close];
        inner.contains("; actual ").then_some(inner)
    });
    let Some(inner) = clause else {
        return (None, None);
    };
    let (constraint, after) = inner.split_once("; actual ").unwrap();
    let actual_text = after.split(';').next().unwrap_or("").trim();
    let measurement = |text: &str| -> Option<String> {
        let words: Vec<&str> = text.split_whitespace().collect();
        let (n, unit) = (words.len().checked_sub(2)?, words.last()?);
        words[n].parse::<f64>().ok()?;
        Some(format!("{} {unit}", words[n]))
    };
    let actual = if actual_text == "< 0" {
        Some("< 0 mm".to_string())
    } else {
        measurement(actual_text)
    };
    (actual, measurement(constraint.trim()))
}

fn violation_finding(v: &NativeViolation) -> Finding {
    let object = v
        .items
        .iter()
        .map(|i| {
            let short = i.uuid.get(..8).unwrap_or(&i.uuid);
            format!("{} @ ({:.3}, {:.3}) [{short}]", i.description, i.x_mm, i.y_mm)
        })
        .collect::<Vec<_>>()
        .join("; ");
    let object = if object.is_empty() {
        "no located items reported by KiCad".to_string()
    } else {
        object
    };
    let object = match &v.sheet {
        Some(sheet) => format!("sheet {sheet}: {object}"),
        None => object,
    };
    let (actual, required) = actual_required(&v.description);
    let message = if v.excluded {
        format!(
            "{} (excluded by designer: {})",
            v.description,
            v.comment.as_deref().unwrap_or("no comment")
        )
    } else {
        v.description.clone()
    };
    let mut f = Finding::fail(&format!("NATIVE.{}.{}", v.category, v.kind), message, object);
    f.severity = v.severity.clone();
    f.actual = actual;
    f.required = required;
    f
}

#[derive(Deserialize)]
struct IgnoredCheck {
    key: String,
}

#[derive(Deserialize)]
struct Header {
    #[serde(rename = "$schema")]
    schema: String,
    source: String,
    kicad_version: String,
    included_severities: Vec<String>,
    ignored_checks: Vec<IgnoredCheck>,
}

#[derive(Deserialize)]
struct Sheet {
    path: String,
    violations: Vec<serde_json::Value>,
}

#[derive(Deserialize)]
struct Erc {
    #[serde(flatten)]
    header: Header,
    sheets: Vec<Sheet>,
}

#[derive(Deserialize)]
struct Drc {
    #[serde(flatten)]
    header: Header,
    violations: Vec<serde_json::Value>,
    unconnected_items: Vec<serde_json::Value>,
    schematic_parity: Vec<serde_json::Value>,
}

#[derive(Deserialize)]
struct Command {
    argv: Vec<String>,
    returncode: i32,
}

fn header(h: &Header, kind: &str, permitted_ignored: &[&str]) -> Result<(), String> {
    if h.schema != format!("https://schemas.kicad.org/{kind}.v1.json")
        || h.source.is_empty()
        || h.kicad_version.is_empty()
    {
        return Err(format!(
            "{kind}: missing identity or unsupported report schema"
        ));
    }
    for severity in ["error", "warning", "exclusion"] {
        if !h.included_severities.iter().any(|s| s == severity) {
            return Err(format!("{kind}: report omits {severity} severity"));
        }
    }
    for ignored in &h.ignored_checks {
        if !permitted_ignored.contains(&ignored.key.as_str()) {
            return Err(format!("{kind}: unreviewed ignored check {}", ignored.key));
        }
    }
    Ok(())
}

fn command(text: &str, kind: &str, source: &str) -> Result<(), String> {
    let c: Command = serde_json::from_str(text).map_err(|e| e.to_string())?;
    let domain = if kind == "erc" { "sch" } else { "pcb" };
    if c.returncode != 0
        || c.argv.get(1).map(String::as_str) != Some(domain)
        || c.argv.get(2).map(String::as_str) != Some(kind)
        || c.argv
            .last()
            .and_then(|s| std::path::Path::new(s).file_name())
            != std::path::Path::new(source).file_name()
    {
        return Err(format!("{kind}: command failed or report source differs"));
    }
    let required: &[&str] = if kind == "erc" {
        &["--severity-all"]
    } else {
        &["--severity-all", "--all-track-errors", "--schematic-parity"]
    };
    if required
        .iter()
        .any(|flag| !c.argv.iter().any(|a| a == flag))
    {
        return Err(format!("{kind}: incomplete native command flags"));
    }
    Ok(())
}

fn inspect(
    erc: &str,
    drc: &str,
    erc_command: &str,
    drc_command: &str,
) -> Result<Vec<Finding>, String> {
    let e: Erc = serde_json::from_str(erc).map_err(|e| format!("ERC schema: {e}"))?;
    let d: Drc = serde_json::from_str(drc).map_err(|e| format!("DRC schema: {e}"))?;
    // These are the explicitly recorded KiCad 10 defaults in our real capture.
    // A new suppression must be reviewed; no arbitrary ignored check is accepted.
    header(
        &e.header,
        "erc",
        &[
            "single_global_label",
            "four_way_junction",
            "simulation_model_issue",
            "footprint_filter",
        ],
    )?;
    header(
        &d.header,
        "drc",
        &[
            "missing_courtyard",
            "track_not_centered_on_via",
            "tuning_profile_track_geometries",
            "footprint_filters_mismatch",
            "footprint_type_mismatch",
        ],
    )?;
    command(erc_command, "erc", &e.header.source)?;
    command(drc_command, "drc", &d.header.source)?;
    if e.sheets.is_empty() || e.sheets.iter().any(|s| s.path.is_empty()) {
        return Err("ERC contains no identified schematic sheet".into());
    }
    let each = collect(&e, &d)?;
    let counts = [
        (
            "NATIVE.ERC",
            e.sheets.iter().map(|s| s.violations.len()).sum::<usize>(),
        ),
        ("NATIVE.DRC", d.violations.len()),
        ("NATIVE.UNCONNECTED", d.unconnected_items.len()),
        ("NATIVE.SCHEMATIC_PARITY", d.schematic_parity.len()),
    ];
    let summaries = counts
        .into_iter()
        .map(|(rule, count)| {
            if count == 0 {
                Finding::pass(
                    rule,
                    "0 reported findings across all requested severities",
                    "native report",
                )
            } else {
                Finding::fail(
                    rule,
                    format!("{count} reported findings, including exclusions"),
                    "native report",
                )
            }
        })
        .collect::<Vec<_>>();
    Ok(summaries
        .into_iter()
        .chain(each.iter().map(violation_finding))
        .collect())
}

/// Check the declared native construction profile. The caller must bind the
/// reports and command receipts to the current saved input hashes separately.
pub fn validate(erc: &str, drc: &str, erc_command: &str, drc_command: &str) -> CheckReport {
    let findings = inspect(erc, drc, erc_command, drc_command).unwrap_or_else(|error| {
        vec![Finding::fail(
            "NATIVE.REPORT_CONTRACT",
            error,
            "native reports",
        )]
    });
    CheckReport::from_findings(
        findings,
        vec![
            "NATIVE.REPORT_CONTRACT".into(),
            "NATIVE.ERC".into(),
            "NATIVE.DRC".into(),
            "NATIVE.UNCONNECTED".into(),
            "NATIVE.SCHEMATIC_PARITY".into(),
        ],
        vec![],
    )
}
