//! Source-bound current-shunt identity and package contract.
//!
//! This rule deliberately stops at identity and published package limits.  A
//! wattage number is not a thermal approval: board copper area, airflow and
//! the actual surface temperature still need the thermal model.

use crate::power_entry::{self, SHUNT_FOOTPRINT, SHUNT_MPN};
use serde_json::Value;
use zapote_core::{CheckReport, Finding};

pub const RULE: &str = "ERC.PFC.SHUNT_PART";
pub const SHUNT_RESISTANCE_OHM: f64 = 0.010;
pub const SHUNT_TOLERANCE: f64 = 0.01;
pub const SHUNT_TCR_PPM_PER_C: f64 = 75.0;
pub const SHUNT_MAX_OPERATING_C: f64 = 170.0;
pub const SHUNT_NOMINAL_POWER_W: f64 = 5.0;
pub const SHUNT_REQUIRED_COPPER_MM2: f64 = 500.0;
pub const SHUNT_MAX_SURFACE_C: f64 = 100.0;

fn component<'a>(manifest: &'a Value, id: &str) -> Option<&'a Value> {
    manifest["components"]
        .as_array()?
        .iter()
        .find(|c| c["instance_path"].as_str() == Some(id))
}

/// Evaluate the exact shunt package contract in a compiled Atopile source.
/// Unknown identities remain indeterminate, while the known historical
/// WSL2726 10 mΩ/2-pad claim is a hard failure because it is outside the
/// manufacturer's published range and package pin count.
pub fn evaluate_source(source: &str) -> CheckReport {
    let mut findings = Vec::new();
    let mut gaps = Vec::new();
    let manifest: Value = match serde_json::from_str(source) {
        Ok(value) => value,
        Err(error) => {
            findings.push(Finding::fail(
                RULE,
                format!("source manifest is invalid: {error}"),
                "shunt",
            ));
            return CheckReport::from_findings(findings, vec![RULE.into()], gaps);
        }
    };
    let Some(part) = component(&manifest, "shunt") else {
        findings.push(Finding::fail(
            RULE,
            "source has no shunt component",
            "shunt",
        ));
        return CheckReport::from_findings(findings, vec![RULE.into()], gaps);
    };
    let mpn = part["mpn"].as_str().unwrap_or("");
    let value = part["value"].as_str().unwrap_or("");
    let footprint = part["footprint"].as_str().unwrap_or("");

    if mpn == power_entry::LEGACY_SHUNT_MPN {
        findings.push(Finding::fail(
            RULE,
            "WSL2726R0100FEA is unsupported: WSL2726 publishes 0.2–5 mΩ and a 4-terminal package; it does not substantiate a 10 mΩ/2-pad part",
            "shunt",
        ));
        return CheckReport::from_findings(findings, vec![RULE.into()], gaps);
    }
    if mpn != SHUNT_MPN {
        gaps.push(format!(
            "shunt MPN {mpn} has no reviewed manufacturer contract"
        ));
        findings.push(Finding::indeterminate(
            RULE,
            format!("shunt MPN {mpn} is not the reviewed HCSM2818FT10L0 identity"),
            "shunt",
        ));
        return CheckReport::from_findings(findings, vec![RULE.into()], gaps);
    }
    if value != "10mohm" {
        findings.push(Finding::fail(
            RULE,
            format!("HCSM2818FT10L0 value must be 10mohm, got {value}"),
            "shunt",
        ));
    }
    if footprint != SHUNT_FOOTPRINT {
        findings.push(Finding::fail(
            RULE,
            format!("HCSM2818FT10L0 requires footprint {SHUNT_FOOTPRINT}, got {footprint}"),
            "shunt",
        ));
    }
    let census = manifest["footprint_census"].get(footprint);
    let pads = census.and_then(|entry| entry["pads"].as_array());
    let mut pad_names = pads
        .map(|p| p.iter().filter_map(Value::as_str).collect::<Vec<_>>())
        .unwrap_or_default();
    pad_names.sort_unstable();
    if pad_names != ["1", "2"] {
        findings.push(Finding::fail(
            RULE,
            "HCSM2818FT10L0 physical census must contain exactly pads 1 and 2",
            "shunt",
        ));
    }
    let circuit = match power_entry::parse(source) {
        Ok(circuit) => circuit,
        Err(error) => {
            findings.push(Finding::fail(
                RULE,
                format!("source graph is not physically bound: {error}"),
                "shunt",
            ));
            return CheckReport::from_findings(findings, vec![RULE.into()], gaps);
        }
    };
    for pin in ["shunt.1", "shunt.2"] {
        if !circuit.pins.contains_key(pin) {
            findings.push(Finding::fail(
                RULE,
                format!("physical shunt pad {pin} is absent from compiled graph"),
                pin,
            ));
        }
    }
    if findings.is_empty() {
        findings.push(Finding::pass(
            RULE,
            "HCSM2818FT10L0 is 10 mΩ ±1%, 5 W nominal with 500 mm² PCB copper and surface below 100 °C; thermal qualification remains separate",
            "shunt",
        ));
    }
    CheckReport::from_findings(findings, vec![RULE.into()], gaps)
}

#[cfg(test)]
mod tests {
    use super::*;
    use serde_json::json;
    use zapote_core::Status;

    const SOURCE: &str = include_str!("../../../power-entry/candidate/source-manifest.json");

    fn replacement() -> Value {
        let mut source: Value = serde_json::from_str(SOURCE).unwrap();
        let reference = {
            let shunt = source["components"]
                .as_array_mut()
                .unwrap()
                .iter_mut()
                .find(|c| c["instance_path"] == "shunt")
                .unwrap();
            let reference = shunt["reference"].as_str().unwrap().to_owned();
            shunt["mpn"] = json!(SHUNT_MPN);
            shunt["footprint"] = json!(SHUNT_FOOTPRINT);
            reference
        };
        source["source_attributes"]["shunt"]["mpn"] = json!(SHUNT_MPN);
        source["source_attributes"]["shunt"]["footprint"] = json!(SHUNT_FOOTPRINT);
        let old = source["footprint_census"]
            .as_object_mut()
            .unwrap()
            .remove(power_entry::LEGACY_SHUNT_FOOTPRINT)
            .unwrap();
        source["footprint_census"]
            .as_object_mut()
            .unwrap()
            .insert(SHUNT_FOOTPRINT.into(), old);
        source["bridge"]["components"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .find(|c| c["reference"] == reference)
            .unwrap()["footprint"] = json!(SHUNT_FOOTPRINT);
        source
    }

    #[test]
    fn historical_identity_fails_closed() {
        assert_eq!(evaluate_source(SOURCE).status, Status::Fail);
    }

    #[test]
    fn reviewed_replacement_passes_identity_contract() {
        assert_eq!(
            evaluate_source(&replacement().to_string()).status,
            Status::Pass
        );
    }

    #[test]
    fn package_mutations_never_pass() {
        let source = replacement();
        for (field, bad) in [
            ("mpn", "OTHER"),
            ("value", "9mohm"),
            ("footprint", "temper:wrong"),
        ] {
            let mut changed = source.clone();
            changed["components"]
                .as_array_mut()
                .unwrap()
                .iter_mut()
                .find(|c| c["instance_path"] == "shunt")
                .unwrap()[field] = json!(bad);
            changed["source_attributes"]["shunt"][field] = json!(bad);
            assert_ne!(
                evaluate_source(&changed.to_string()).status,
                Status::Pass,
                "{field}"
            );
        }
    }

    #[test]
    fn pad_census_mutation_fails() {
        let mut source = replacement();
        source["footprint_census"][SHUNT_FOOTPRINT]["pads"] = json!(["1", "2", "3"]);
        assert_eq!(evaluate_source(&source.to_string()).status, Status::Fail);
    }
}
