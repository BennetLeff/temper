//! Experiment 00's placement acceptance policy. Native KiCad supplies geometry.
use anyhow::{ensure, Context, Result};
use serde::Deserialize;
use serde_json::{json, Value};
use std::io;

mod routing;

#[derive(Deserialize)]
struct Pad {
    number: String,
    net: String,
    position_mm: [f64; 2],
}

#[derive(Deserialize)]
struct Footprint {
    reference: String,
    position_mm: [f64; 2],
    angle_deg: f64,
    bounds_mm: [f64; 4],
    pads: Vec<Pad>,
}

#[derive(Deserialize)]
struct Measurement {
    kicad_version: String,
    board_sha256: String,
    protected_sha256: String,
    footprints: Vec<Footprint>,
    routing: Option<routing::Measurement>,
}

#[derive(Deserialize)]
struct Contract {
    kicad_version: String,
    protected_sha256: String,
    outline_mm: [f64; 4],
    max_pad_distance_mm: f64,
    #[serde(default)]
    routing: bool,
}

#[derive(Deserialize)]
struct Drc {
    #[serde(rename = "$schema")]
    schema: String,
    coordinate_units: String,
    source: String,
    kicad_version: String,
    violations: Vec<Value>,
    unconnected_items: Vec<Value>,
    ignored_checks: Vec<Value>,
    included_severities: Vec<String>,
    schematic_parity: Vec<Value>,
}

#[derive(Deserialize)]
struct Input {
    measurement: Measurement,
    contract: Contract,
    drc: Drc,
}

fn footprint<'a>(measurement: &'a Measurement, reference: &str) -> Result<&'a Footprint> {
    let mut found = measurement
        .footprints
        .iter()
        .filter(|f| f.reference == reference);
    let fp = found
        .next()
        .with_context(|| format!("missing footprint {reference}"))?;
    ensure!(found.next().is_none(), "duplicate footprint {reference}");
    Ok(fp)
}

fn pad<'a>(fp: &'a Footprint, number: &str) -> Result<&'a Pad> {
    let mut found = fp.pads.iter().filter(|p| p.number == number);
    let pad = found
        .next()
        .with_context(|| format!("missing pad {}.{number}", fp.reference))?;
    ensure!(
        found.next().is_none(),
        "duplicate pad {}.{number}",
        fp.reference
    );
    Ok(pad)
}

fn is_digest(value: &str) -> bool {
    value.len() == 64 && value.bytes().all(|c| c.is_ascii_hexdigit())
}

fn evaluate(input: Input) -> Result<Value> {
    let Input {
        measurement: m,
        contract: c,
        drc,
    } = input;
    ensure!(
        m.kicad_version == c.kicad_version && drc.kicad_version == c.kicad_version,
        "unqualified KiCad version"
    );
    ensure!(
        is_digest(&m.board_sha256)
            && is_digest(&m.protected_sha256)
            && is_digest(&c.protected_sha256),
        "invalid content identity"
    );
    ensure!(
        drc.schema == "https://schemas.kicad.org/drc.v1.json"
            && drc.coordinate_units == "mm"
            && drc.source == "candidate.kicad_pcb",
        "unexpected DRC schema, units, or source"
    );
    ensure!(
        drc.included_severities.iter().any(|s| s == "error")
            && drc.included_severities.iter().any(|s| s == "warning")
            && drc.included_severities.iter().any(|s| s == "exclusion"),
        "incomplete DRC severities"
    );
    // These default ignored checks are outside this two-footprint placement task.
    let allowed_ignored = [
        "missing_courtyard",
        "track_not_centered_on_via",
        "tuning_profile_track_geometries",
        "footprint_filters_mismatch",
        "footprint_type_mismatch",
    ];
    for ignored in &drc.ignored_checks {
        ensure!(
            allowed_ignored.contains(&ignored["key"].as_str().context("invalid ignored check")?),
            "applicable DRC check disabled: {ignored}"
        );
    }
    ensure!(
        c.max_pad_distance_mm.is_finite()
            && c.max_pad_distance_mm > 0.0
            && c.outline_mm.iter().all(|v| v.is_finite())
            && c.outline_mm[0] < c.outline_mm[2]
            && c.outline_mm[1] < c.outline_mm[3],
        "invalid placement contract"
    );
    ensure!(m.footprints.len() == 2, "expected exactly two footprints");
    let cap = footprint(&m, "C9")?;
    let regulator = footprint(&m, "U3")?;
    ensure!(
        cap.pads.len() == 2 && regulator.pads.len() == 6,
        "unexpected pad census"
    );
    for fp in &m.footprints {
        ensure!(
            fp.position_mm
                .iter()
                .chain(fp.bounds_mm.iter())
                .chain([&fp.angle_deg])
                .all(|v| v.is_finite()),
            "nonfinite footprint geometry"
        );
        ensure!(
            fp.bounds_mm[0] < fp.bounds_mm[2] && fp.bounds_mm[1] < fp.bounds_mm[3],
            "invalid footprint bounds"
        );
        for p in &fp.pads {
            ensure!(
                p.position_mm.iter().all(|v| v.is_finite()),
                "nonfinite pad geometry"
            );
        }
    }
    let mut findings = Vec::new();
    if m.protected_sha256 != c.protected_sha256 {
        findings.push(json!({"id": "protected_state_changed"}));
    }
    // Native KiCad may report the admitted 270-degree pose as -90 degrees.
    if ![0.0, 90.0, 180.0, 270.0].contains(&cap.angle_deg.rem_euclid(360.0)) {
        findings.push(json!({"id": "unsupported_orientation"}));
    }
    for fp in &m.footprints {
        let [left, top, right, bottom] = fp.bounds_mm;
        let [x0, y0, x1, y1] = c.outline_mm;
        if left < x0 || top < y0 || right > x1 || bottom > y1 {
            findings.push(json!({"id": format!("outside_outline:{}", fp.reference)}));
        }
    }
    let mut distances = Vec::new();
    for (cap_number, regulator_number, net) in [("1", "3", "+15V"), ("2", "1", "gnd")] {
        let a = pad(cap, cap_number)?;
        let b = pad(regulator, regulator_number)?;
        let pair = format!("C9.{cap_number}:U3.{regulator_number}");
        if a.net != net || b.net != net {
            findings.push(json!({"id": format!("net_mismatch:{pair}")}));
        }
        let distance =
            (a.position_mm[0] - b.position_mm[0]).hypot(a.position_mm[1] - b.position_mm[1]);
        ensure!(distance.is_finite(), "invalid distance measurement");
        distances.push(json!({"pair": pair, "distance_mm": distance}));
        if distance > c.max_pad_distance_mm {
            findings.push(json!({"id": format!("too_distant:{pair}"), "distance_mm": distance}));
        }
    }
    for violation in drc.violations.iter().chain(drc.schematic_parity.iter()) {
        let kind = violation["type"]
            .as_str()
            .context("invalid DRC violation")?;
        let items = violation["items"].as_array().context("missing DRC items")?;
        ensure!(!items.is_empty(), "empty DRC item identities");
        let mut identities = items
            .iter()
            .map(|item| item["uuid"].as_str().context("invalid DRC item identity"))
            .collect::<Result<Vec<_>>>()?;
        identities.sort_unstable();
        findings.push(
            json!({"id": format!("kicad:{kind}:{}", identities.join(":")), "evidence": violation}),
        );
    }
    for item in &drc.unconnected_items {
        ensure!(
            item["type"] == "unconnected_items",
            "unexpected open-connection report"
        );
    }
    if c.routing {
        routing::evaluate(
            m.routing
                .as_ref()
                .context("missing native connectivity evidence")?,
            c.outline_mm,
            &mut findings,
        )?;
        if drc.unconnected_items.len() != 1 {
            findings.push(json!({"id": "unexpected_open_connection_count", "expected": "one remaining U3.5 open connection"}));
        }
    }
    Ok(
        json!({"status": if findings.is_empty() {"pass"} else {"fail"},
        "scope": if c.routing {"two_capacitor_routes"} else {"placement_only"}, "board_sha256": m.board_sha256,
        "distances": distances, "findings": findings,
        "open_connections_outside_scope": drc.unconnected_items.len(),
        "open_connection_evidence": drc.unconnected_items}),
    )
}

fn run() -> Result<Value> {
    let input: Input =
        serde_json::from_reader(io::stdin().lock()).context("invalid measurement input")?;
    evaluate(input)
}

fn main() {
    let result = match run() {
        Ok(result) => result,
        Err(error) => json!({"status": "indeterminate", "error": format!("{error:#}")}),
    };
    println!("{result}");
    if result["status"] == "indeterminate" {
        std::process::exit(2);
    }
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn missing_evidence_cannot_deserialize_as_a_pass() {
        assert!(serde_json::from_str::<Input>("{}").is_err());
    }

    #[test]
    fn partial_digest_is_not_a_content_identity() {
        assert!(!is_digest("0123456789abcdef"));
    }
}
