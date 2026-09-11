//! Composition boundary for the registered RTD validator suite.

use serde::Serialize;
use zapote_core::{CheckReport, RunInput, Status};

const REGISTERED_RULES: [&str; 20] = [
    "ERC.RTD.EXACT_COMPONENTS",
    "ERC.RTD.BOARD_COMPONENT_BINDING",
    "ERC.RTD.RREF_IDENTITY",
    "ERC.RTD.FOUR_WIRE_PINOUT",
    "ERC.RTD.FORCE_SENSE_SEPARATION",
    "ERC.RTD.NATIVE_CONNECTIVITY",
    "ERC.RTD.ADC_PIN_NETS",
    "ERC.RTD.RREF_TO_REFERENCE_NETWORK",
    "ERC.RTD.SHARED_REFERENCE",
    "ERC.RTD.FAULT_OUTPUT",
    "ERC.RTD.FIRMWARE_GPIO_CORRESPONDENCE",
    "ERC.RTD.SPI_SERIES_PLACEMENT",
    "ERC.RTD.FIRMWARE_THRESHOLD_ENCODING",
    "ERC.RTD.FAULT_CORNERS",
    "DRC.RTD.UPSTREAM_POST_FERRITE_RAILS",
    "DRC.RTD.FERRITE_SEMANTICS",
    "DRC.RTD.LOCAL_DECOUPLING",
    "DRC.RTD.SENSITIVE_AGGRESSOR_GEOMETRY",
    "DRC.RTD.DOMAIN_BOUNDARY_CONNECTIONS",
    "DRC.RTD.NATIVE_GEOMETRY",
];

#[derive(Debug, Serialize)]
pub struct SuiteReport {
    pub schema_version: u32,
    pub input_hash: String,
    pub identity: zapote_core::Identity,
    pub status: Status,
    pub erc: CheckReport,
    pub drc: CheckReport,
    pub checked_rules: Vec<String>,
    pub coverage_gaps: Vec<String>,
    pub evidence: Evidence,
}

#[derive(Debug, Serialize)]
pub struct Evidence {
    pub source: String,
    pub authoritative: bool,
    pub telemetry: String,
}

pub fn run(input: &RunInput, no_telemetry: bool) -> SuiteReport {
    let erc = zapote_erc::validate(input);
    let drc = zapote_drc::validate(input);
    let mut checked_rules = erc
        .checked_rules
        .iter()
        .chain(drc.checked_rules.iter())
        .cloned()
        .collect::<Vec<_>>();
    checked_rules.sort();
    checked_rules.dedup();
    let mut coverage_gaps = erc
        .coverage_gaps
        .iter()
        .chain(drc.coverage_gaps.iter())
        .cloned()
        .collect::<Vec<_>>();
    let mut findings = erc.findings.iter().chain(drc.findings.iter());
    let mut missing = Vec::new();
    for rule in REGISTERED_RULES {
        if !checked_rules.iter().any(|actual| actual == rule) {
            missing.push(rule.to_string());
        }
    }
    if !missing.is_empty() {
        coverage_gaps.push(format!(
            "unregistered or unexecuted rules: {}",
            missing.join(", ")
        ));
    }
    let status = if findings.any(|f| f.status == Status::Fail) {
        Status::Fail
    } else if erc.status != Status::Pass || drc.status != Status::Pass || !coverage_gaps.is_empty()
    {
        Status::Indeterminate
    } else {
        Status::Pass
    };
    SuiteReport {
        schema_version: 1,
        input_hash: input.canonical_hash(),
        identity: input.identity.clone(),
        status,
        erc,
        drc,
        checked_rules,
        coverage_gaps,
        evidence: Evidence {
            source: "zapote-rtd-rust".into(),
            authoritative: true,
            telemetry: if no_telemetry {
                "disabled".into()
            } else {
                "local-only".into()
            },
        },
    }
}

pub fn parse_input(bytes: &[u8]) -> Result<RunInput, serde_json::Error> {
    serde_json::from_slice(bytes)
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn missing_input_identity_cannot_be_a_pass() {
        let error = parse_input(br#"{"schema_version":1}"#).unwrap_err();
        assert!(error.to_string().contains("identity"));
    }
}
