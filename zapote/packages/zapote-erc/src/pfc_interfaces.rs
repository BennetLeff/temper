//! Executable boundary of the standalone PFC unit, not an integration approval.
//!
//! Connector nets are checked against the reviewed interface, independently of
//! source/native agreement. External producers have not been built or qualified;
//! their obligations must remain indeterminate in every common unit run.
use crate::{power_entry, source_circuit::Circuit};
use zapote_core::{CheckReport, Finding};

pub const RULES: [&str; 5] = [
    "ERC.PFC.INTERFACE_PINS",
    "ERC.PFC.BUS_ENVELOPE",
    "ERC.PFC.ISOLATED_BIAS",
    "ERC.PFC.EXTERNAL_SUPERVISOR",
    "ERC.PFC.INPUT_FOLDBACK",
];

const PINS: &[(&str, &str)] = &[
    ("mains.1", "AC_L_RECTIFIED_INPUT"),
    ("mains.2", "AC_N_RECTIFIED_INPUT"),
    ("mains.3", "PE_CHASSIS"),
    ("aux.1", "AUX_15V_IN"),
    ("aux.2", "PFC_BUS_MINUS"),
    ("control.1", "RELAY_BYPASS_CTRL"),
    ("control.2", "PFC_BUS_MINUS"),
    ("permit.1", "HOT_PERMIT_EXTERNAL"),
    ("permit.2", "PFC_BUS_MINUS"),
    ("output.1", "PFC_BUS_PLUS_390V"),
    ("output.2", "PFC_BUS_MINUS"),
];

fn check_pins(source: &str) -> Result<(), String> {
    let circuit = Circuit::parse(source, power_entry::ENTRY)?;
    // Also bind the bus-setpoint model and default-off topology to the reviewed
    // parts; a connector label alone cannot establish either electrical fact.
    power_entry::validate_source(source)?;
    for (endpoint, net) in PINS {
        if circuit.pins.get(*endpoint).map(String::as_str) != Some(*net) {
            return Err(format!("interface {endpoint} must connect to {net}"));
        }
    }
    let output_count = circuit
        .pins
        .keys()
        .filter(|p| p.starts_with("output."))
        .count();
    if output_count != 2 {
        return Err("PFC output must have exactly two pins; no midpoint exists".into());
    }
    Ok(())
}

pub fn validate(source: &str) -> CheckReport {
    let mut findings = vec![match check_pins(source) {
        Ok(()) => Finding::pass(
            RULES[0],
            "11 reviewed connector pins match: single HOT bus, no midpoint; bias, relay and permit returns are PFC_BUS_MINUS, distinct from PE",
            "power-entry.interfaces",
        ),
        Err(error) => Finding::fail(RULES[0], error, "power-entry.interfaces"),
    }];
    let obligations = [
        (RULES[1], "power-entry.output", "The reviewed setpoint is 389.615 V nominal, not a guaranteed maximum. Ripple, overshoot and faults require a source-bound bus envelope before rating downstream consumers. Legacy split-bus consumers are not accepted."),
        (RULES[2], "power-entry.aux", "External regulated 15 V bias must return to HOT PFC_BUS_MINUS. The auxiliary unit, load/startup budget, source architecture and isolation evidence are absent; CTRL_GND or PE cannot substitute for this return."),
        (RULES[3], "power-entry.permit/control", "HOT permit and relay-bypass inputs need isolated external producers and verified startup, precharge, loss-of-bias, reset and fault sequencing. Default-off static topology is not a shutdown timing or stored-energy guarantee."),
        (RULES[4], "power-entry.mains", "15 A RMS and PF 0.99 bound nominal 120 V input to 1782 W before losses. Low-line foldback and fault/inrush currents remain unmodeled; a nominal 1800 W target cannot waive the input-current limit."),
    ];
    for (rule, object, message) in obligations {
        findings.push(Finding::indeterminate(rule, message, object));
    }
    CheckReport::from_findings(
        findings,
        RULES.map(str::to_owned).to_vec(),
        obligations
            .iter()
            .map(|(_, _, message)| (*message).to_owned())
            .collect(),
    )
}

#[cfg(test)]
mod tests {
    use super::*;
    use zapote_core::Status;
    const SOURCE: &str = include_str!("../../../power-entry/shunt-repair/candidate/source-manifest.json");

    #[test]
    fn real_source_has_reviewed_pins_but_no_external_qualification() {
        let report = validate(SOURCE);
        assert_eq!(report.findings[0].status, Status::Pass);
        assert_eq!(report.status, Status::Indeterminate);
        assert_eq!(
            report
                .findings
                .iter()
                .filter(|f| f.status == Status::Indeterminate)
                .count(),
            4
        );
    }

    #[test]
    fn consistent_ground_rename_cannot_turn_hot_return_into_control_ground() {
        let changed = SOURCE.replace("PFC_BUS_MINUS", "CTRL_GND");
        // Topology alone intentionally allows net renames; the external
        // interface contract must still reject this integration hazard.
        assert!(power_entry::validate_source(&changed).is_ok());
        assert_eq!(validate(&changed).findings[0].status, Status::Fail);
    }

    #[test]
    fn old_split_bus_label_is_not_an_accepted_output() {
        let changed = SOURCE.replace("PFC_BUS_PLUS_390V", "HV_PLUS_170V");
        assert_eq!(validate(&changed).findings[0].status, Status::Fail);
    }

    #[test]
    fn every_interface_net_name_is_an_independent_contract() {
        for (_, net) in PINS {
            let changed = SOURCE.replace(net, "UNREVIEWED_INTERFACE");
            assert!(power_entry::validate_source(&changed).is_ok(), "{net}");
            let report = validate(&changed);
            assert!(report.findings.iter().any(|f| f.rule == RULES[0]
                && f.object == "power-entry.interfaces" && f.status == Status::Fail), "{net}");
        }
    }

    #[test]
    fn extra_output_midpoint_is_rejected() {
        let mut source: serde_json::Value = serde_json::from_str(SOURCE).unwrap();
        let output = source["components"].as_array().unwrap().iter()
            .find(|c| c["instance_path"] == "output").unwrap()["reference"].clone();
        source["bridge"]["nets"][0]["nodes"].as_array_mut().unwrap()
            .push(serde_json::json!([output, "3"]));
        assert_eq!(validate(&source.to_string()).findings[0].status, Status::Fail);
    }

    #[test]
    fn missing_source_does_not_remove_external_obligations() {
        let report = validate("{}");
        assert_eq!(report.status, Status::Fail);
        assert_eq!(report.checked_rules.len(), RULES.len());
    }
}
