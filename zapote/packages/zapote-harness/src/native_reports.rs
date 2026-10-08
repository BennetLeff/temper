//! Validate captured KiCad reports without treating absent fields as empty results.
//! This checks report content and command coverage, not tool authenticity or freshness.
use serde::Deserialize;
use zapote_core::{CheckReport, Finding};

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
    let counts = [
        (
            "NATIVE.ERC",
            e.sheets.iter().map(|s| s.violations.len()).sum::<usize>(),
        ),
        ("NATIVE.DRC", d.violations.len()),
        ("NATIVE.UNCONNECTED", d.unconnected_items.len()),
        ("NATIVE.SCHEMATIC_PARITY", d.schematic_parity.len()),
    ];
    Ok(counts
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
