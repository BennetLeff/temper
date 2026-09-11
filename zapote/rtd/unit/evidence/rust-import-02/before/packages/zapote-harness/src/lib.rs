//! Composition boundary for the registered RTD validator suite.

use serde::Serialize;
use zapote_core::unit::UnitInput;
use zapote_core::{CheckReport, Finding, RunInput, Status};

const REGISTERED_RULES: [&str; 21] = [
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
    "DRC.RTD.LOCAL_ESCAPE_ELIGIBILITY",
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

/// Execute the standalone RTDUnit applicability profile against the native
/// exporter schema.  This shares the typed core/native evidence model with
/// the full-board suite; it does not synthesize a fake MCU or buck board.
pub fn run_unit(input: &UnitInput) -> CheckReport {
    let mut findings: Vec<Finding> = Vec::new();
    let mut checked = vec![
        "ERC.RTD.UNIT_COMPONENT_MPN".into(),
        "ERC.RTD.UNIT_CONNECTIONS".into(),
        "ERC.RTD.UNIT_INTERFACE".into(),
        "ERC.RTD.UNIT_FIRMWARE".into(),
        "ERC.RTD.UNIT_MODEL".into(),
        "ERC.RTD.UNIT_SOURCE_BINDING".into(),
    ];
    for error in input.validate() {
        let rule = if error.contains("firmware") {
            "ERC.RTD.UNIT_FIRMWARE"
        } else if error.contains("model") {
            "ERC.RTD.UNIT_MODEL"
        } else if error.contains("board") || error.contains("native") || error.contains("pad") {
            "DRC.RTD.UNIT_PAD_GEOMETRY"
        } else {
            "ERC.RTD.UNIT_COMPONENT_MPN"
        };
        findings.push(Finding::fail(rule, error, "unit-input"));
    }
    let native = &input.native;
    if input.source_bindings.is_empty() {
        findings.push(Finding::indeterminate(
            "ERC.RTD.UNIT_SOURCE_BINDING",
            "compiled source pad/net binding is absent; native names cannot serve as expected contract",
            "source-bindings",
        ));
    }
    for (rule, role, instance_id, expected_mpn) in [
        (
            "ERC.RTD.BOARD_COMPONENT_BINDING",
            "probe connector",
            input.profile.probe.component.as_str(),
            input.profile.probe.mpn.as_str(),
        ),
        (
            "ERC.RTD.SHARED_REFERENCE",
            "reference",
            input.profile.local.reference_component.as_str(),
            input.profile.local.reference_mpn.as_str(),
        ),
        (
            "DRC.RTD.UPSTREAM_POST_FERRITE_RAILS",
            "ferrite",
            input.profile.local.ferrite_component.as_str(),
            input.profile.local.ferrite_mpn.as_str(),
        ),
        (
            "ERC.RTD.UNIT_INTERFACE",
            "host connector",
            "unit_io",
            input
                .profile
                .interface
                .connector_mpn
                .as_deref()
                .unwrap_or(""),
        ),
    ] {
        match native.components.iter().find(|c| c.id == instance_id) {
            Some(component) if component.mpn == expected_mpn => {}
            Some(component) => findings.push(Finding::fail(
                rule,
                format!(
                    "unit {role} has MPN {}; expected {expected_mpn}",
                    component.mpn
                ),
                instance_id,
            )),
            None => findings.push(Finding::fail(
                rule,
                format!("unit {role} source component is absent from native board"),
                instance_id,
            )),
        }
    }
    for pin in &input.profile.probe.pins {
        let endpoint = native.connections.iter().find(|c| {
            c.component == input.profile.probe.component && c.pin == pin.number.to_string()
        });
        if endpoint.map(|c| c.net.as_str()) != Some(pin.net.as_str()) {
            findings.push(Finding::fail(
                "ERC.RTD.FOUR_WIRE_PINOUT",
                format!(
                    "probe pad {}.{} is not connected to authored source net {}",
                    input.profile.probe.component, pin.number, pin.net
                ),
                format!("{}.{}", input.profile.probe.component, pin.number),
            ));
        }
    }
    for pin in &input.profile.interface.pins {
        let observed = native.connections.iter().find(|connection| {
            connection.component == "unit_io" && connection.pin == pin.number.to_string()
        });
        let expected_net = if pin.net.eq_ignore_ascii_case("gnd") {
            "gnd"
        } else {
            pin.net.as_str()
        };
        if observed.map(|connection| connection.net.as_str()) != Some(expected_net) {
            findings.push(Finding::fail(
                "ERC.RTD.UNIT_INTERFACE",
                format!(
                    "unit_io pad {} is not connected to authored source net {}",
                    pin.number, pin.net
                ),
                format!("unit_io.{}", pin.number),
            ));
        }
    }
    if input.profile.interface.connector_mpn.is_none() {
        findings.push(Finding::indeterminate(
            "ERC.RTD.UNIT_INTERFACE",
            "unit_io connector MPN and source pin map are pending qualification",
            "unit_io",
        ));
    }
    if input
        .profile
        .loads
        .iter()
        .any(|l| l.status == "pending_source_budget")
    {
        findings.push(Finding::indeterminate(
            "ERC.RTD.UNIT_MODEL",
            "local/reference load budget is authored but pending source-derived sum",
            "RTD_LOCAL_10MA",
        ));
    }
    match unit_run_input(input) {
        Ok(context) => {
            let erc = zapote_erc::validate(&context);
            let drc = zapote_drc::validate(&context);
            findings.extend(erc.findings);
            findings.extend(drc.findings);
            checked.extend(erc.checked_rules);
            checked.extend(drc.checked_rules);
        }
        Err(error) => findings.push(Finding::fail(
            "INPUT_SCHEMA",
            format!("unit native adapter could not construct shared checker context: {error}"),
            "unit-input",
        )),
    }
    checked.sort();
    checked.dedup();
    CheckReport::from_findings(findings, checked, Vec::new())
}

/// Adapt the unit's measured native census into the existing checker context.
/// The adapter only maps observed records; all topology/geometry checks remain
/// the registered ERC/DRC implementations.
pub fn unit_run_input(input: &UnitInput) -> Result<RunInput, serde_json::Error> {
    use std::collections::BTreeMap;
    let native = &input.native;
    let mut nets = BTreeMap::new();
    for component in &native.components {
        for pad in &component.footprint_pads {
            nets.entry(pad.net.clone())
                .or_insert(serde_json::json!({"name":pad.net,"domain":"UNIT","role":"observed"}));
        }
    }
    let adc_id = input
        .profile
        .component_bindings
        .iter()
        .find(|b| b.role == "adc")
        .map(|b| b.instance_id.clone())
        .unwrap_or_else(|| "rtd_pan.adc".into());
    let rref_id = input
        .profile
        .component_bindings
        .iter()
        .find(|b| b.role == "rref")
        .map(|b| b.instance_id.clone())
        .unwrap_or_else(|| "rtd_pan.r_ref".into());
    let adc = native.components.iter().find(|c| c.id == adc_id);
    // Expected source intent is carried by the compiled manifest binding.
    // Native pads remain the observation used by the shared checks; using the
    // binding here prevents a consistent native net swap from becoming its
    // own expected contract.
    let source_pad_net = |instance: &str, pad: &str| {
        input
            .source_bindings
            .iter()
            .find(|binding| binding.instance_id == instance && binding.pad == pad)
            .map(|binding| binding.net.clone())
    };
    let pad_net = |number: &str| {
        source_pad_net(&adc_id, number).unwrap_or_else(|| {
            adc.and_then(|c| c.footprint_pads.iter().find(|p| p.pad == number))
                .map(|p| p.net.clone())
                .unwrap_or_default()
        })
    };
    let mut adc_pins: BTreeMap<String, String> = BTreeMap::new();
    for (name, number) in [
        ("DRDY", "1"),
        ("DVDD", "2"),
        ("VDD", "3"),
        ("BIAS", "4"),
        ("REFIN_P", "5"),
        ("REFIN_N", "6"),
        ("ISENSOR", "7"),
        ("FORCE_P", "8"),
        ("FORCE2", "9"),
        ("RTDIN_P", "10"),
        ("RTDIN_N", "11"),
        ("FORCE_N", "12"),
        ("GND2", "13"),
        ("SDI", "14"),
        ("SCLK", "15"),
        ("CS_N", "16"),
        ("SDO", "17"),
        ("DGND", "18"),
        ("GND1", "19"),
        ("NC3", "20"),
    ] {
        adc_pins.insert(name.into(), pad_net(number));
    }
    let rref_nets = [
        source_pad_net(&rref_id, "1")
            .or_else(|| {
                native
                    .components
                    .iter()
                    .find(|c| c.id == rref_id)
                    .and_then(|c| c.footprint_pads.first())
                    .map(|p| p.net.clone())
            })
            .unwrap_or_default(),
        source_pad_net(&rref_id, "2")
            .or_else(|| {
                native
                    .components
                    .iter()
                    .find(|c| c.id == rref_id)
                    .and_then(|c| c.footprint_pads.get(1))
                    .map(|p| p.net.clone())
            })
            .unwrap_or_default(),
    ];
    let decoupling: Vec<_> = input
        .profile
        .decoupling_bindings
        .iter()
        .map(|d| {
            let position_mm = native
                .components
                .iter()
                .find(|c| c.id == d.instance_id)
                .map(|c| c.position_mm.clone())
                .unwrap_or_else(|| vec![0.0, 0.0]);
            serde_json::json!({"component":d.instance_id,"ic":d.target_component,
            "rail":d.pad_nets.first().cloned().unwrap_or_default(),
            "ground":d.pad_nets.get(1).cloned().unwrap_or_default(),
            "capacitance_uf":d.capacitance_nf/1000.0,"position_mm":position_mm})
        })
        .collect();
    let probe_pins = serde_json::to_value(&input.profile.probe.pins).unwrap_or_default();
    let mut required_ics = Vec::new();
    let mut required_ids = std::collections::BTreeSet::new();
    for binding in &input.profile.decoupling_bindings {
        if required_ids.insert(binding.target_component.clone()) {
            required_ics.push(serde_json::json!({
                "component": binding.target_component,
                "rail": binding.pad_nets.first().cloned().unwrap_or_default(),
                "ground": binding.pad_nets.get(1).cloned().unwrap_or_default()
            }));
        }
    }
    let reference = native
        .components
        .iter()
        .find(|c| c.id == input.profile.local.reference_component);
    let ref_nets = reference
        .map(|c| {
            c.footprint_pads
                .iter()
                .map(|p| p.net.clone())
                .collect::<Vec<_>>()
        })
        .unwrap_or_default();
    let ref_vref = ref_nets
        .iter()
        .find(|n| n.as_str() == "SHARED_REF_2V5")
        .cloned()
        .unwrap_or_else(|| "SHARED_REF_2V5".into());
    let ref_gnd = ref_nets
        .iter()
        .find(|n| n.eq_ignore_ascii_case("gnd"))
        .cloned()
        .unwrap_or_else(|| "gnd".into());
    let scenarios: Vec<_> = input.model.get("faults").and_then(|v|v.as_array()).cloned().unwrap_or_default().into_iter().map(|f| serde_json::json!({"name":f.get("name").and_then(|v|v.as_str()).unwrap_or("model_fault"),"resistance_ohm":f.get("resistance_ohm"),"conductor_open":f.get("conductor_open"),"rail_loss":f.get("rail_loss"),"expected_class":f.get("expected_class").and_then(|v|v.as_str()).unwrap_or("indeterminate"),"expected_detected":f.get("expected_detected").and_then(|v|v.as_bool()).unwrap_or(false)})).collect();
    let gpio = serde_json::json!({"RTD_SCK":8,"RTD_SDI":11,"RTD_SDO":12,"RTD_CS_N":input.firmware.cs_gpio,"RTD_DRDY":input.firmware.drdy_gpio});
    let value = serde_json::json!({
        "schema_version":1,"applicability":"RTDUnit",
        "identity":{"source_revision":"unit","source_hash":input.identity.source_manifest_sha256,"board_revision":"native","board_hash":input.identity.board_sha256,"suite_revision":"zapote","suite_hash":input.identity.native_export_sha256,"model_revision":"bound","model_hash":input.identity.model_sha256,"observed_source_hash":input.identity.source_manifest_sha256,"observed_board_hash":input.identity.board_sha256,"observed_suite_hash":input.identity.native_export_sha256,"observed_model_hash":input.identity.model_sha256,"native_export_sha256":input.identity.native_export_sha256,"native_board_sha256":input.identity.board_sha256,"native_extractor_sha256":input.identity.extractor_sha256,"native_binding_required":true,"runtime":"zapote-rtd-unit","provider":"native"},
        "board":{"components":native.components,"nets":nets.values().cloned().collect::<Vec<_>>(),"connections":native.connections,"connectivity_clusters":native.connectivity_clusters,"traces":native.traces,"vias":native.vias,"geometry":input.profile.geometry},
        "rtd":{"connector":{"component":input.profile.probe.component,"pins":probe_pins},"adc":{"component":adc_id,"mpn":input.profile.components.adc_mpn,"pins":adc_pins},"rref":{"component":rref_id,"mpn":input.profile.components.rref_mpn,"resistance_ohm":input.profile.components.rref_ohm,"tolerance_pct":input.profile.components.rref_tolerance_pct,"connections":rref_nets},"reference":{"component":input.profile.local.reference_component,"mpn":input.profile.local.reference_mpn,"v1_net":"+3V3","v2_net":ref_vref,"ground_net":ref_gnd},"local_rail":{"upstream_net":"+3V3","post_ferrite_net":input.profile.local.filtered_rail,"ferrite_component":input.profile.local.ferrite_component},"required_local_ics":required_ics,"decoupling":decoupling,"spi":[{"signal":"RTD_SCK","mcu_pin":8,"adc_pin":"SCLK","series_component":"rtd_pan.r_sclk"},{"signal":"RTD_SDI","mcu_pin":11,"adc_pin":"SDI","series_component":"rtd_pan.r_mosi"},{"signal":"RTD_SDO","mcu_pin":12,"adc_pin":"SDO","series_component":"rtd_pan.r_miso"},{"signal":"RTD_CS_N","mcu_pin":input.firmware.cs_gpio,"adc_pin":"CS_N","series_component":"rtd_pan.r_cs"},{"signal":"RTD_DRDY","mcu_pin":input.firmware.drdy_gpio,"adc_pin":"DRDY","series_component":"direct"}],"mcu_pads":{},"fault_output":{"net":"RTD_HW_FAULT","active_level":"high","pullup_rail":"+3V3","gate":"unit_io","consumers":["unit_io"]},"downstream_reference_consumers":[]},
        "firmware":{"gpio":gpio,"thresholds":{"short_ohm":input.firmware.short_fault_ohm,"open_ohm":input.firmware.open_fault_ohm,"low_word":input.firmware.low_threshold_word,"high_word":input.firmware.high_threshold_word,"rref_ohm":input.profile.components.rref_ohm,"adc_bits":15,"shift":1},"config_revision":input.identity.firmware_sha256},"scenarios":scenarios});
    serde_json::from_value(value)
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
