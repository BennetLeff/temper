//! RTD source/connectivity, firmware correspondence, and fault checks.

use std::collections::BTreeMap;
use zapote_core::{CheckReport, FaultScenario, Finding, RunInput};

pub mod current_sense;
pub mod gate_drive;
pub mod interlock;
pub mod pfc_control;
pub mod pfc_interfaces;
pub mod power_entry;
pub mod power_stage_models;
pub mod source_circuit;

const ADC_PINS: [&str; 8] = [
    "BIAS", "REFIN_P", "REFIN_N", "ISENSOR", "FORCE_P", "FORCE_N", "RTDIN_P", "RTDIN_N",
];
const ADC_PIN_NUMBERS: [(&str, &str); 20] = [
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
];
const SPI_SIGNALS: [(&str, u16, &str); 5] = [
    ("RTD_SCK", 8, "SCLK"),
    ("RTD_SDI", 11, "SDI"),
    ("RTD_SDO", 12, "SDO"),
    ("RTD_CS_N", 10, "CS_N"),
    ("RTD_DRDY", 9, "DRDY"),
];

pub fn validate(input: &RunInput) -> CheckReport {
    let mut findings = Vec::new();
    let mut gaps = Vec::new();
    let mut checked = Vec::new();
    let required = input.validate();
    if !required.is_empty() {
        for error in required {
            findings.push(Finding::indeterminate("INPUT_SCHEMA", error, "run_input"));
        }
        return CheckReport::from_findings(findings, checked, gaps);
    }
    check_topology(input, &mut findings, &mut checked);
    check_firmware(input, &mut findings, &mut checked);
    check_fault_scenarios(input, &mut findings, &mut gaps, &mut checked);
    CheckReport::from_findings(findings, checked, gaps)
}

fn check_topology(input: &RunInput, findings: &mut Vec<Finding>, checked: &mut Vec<String>) {
    checked.push("ERC.RTD.EXACT_COMPONENTS".into());
    let rtd = &input.rtd;
    let unit = input.applicability == "RTDUnit";
    checked.push("ERC.RTD.BOARD_COMPONENT_BINDING".into());
    let mut bindings = vec![
        (&rtd.adc.component, rtd.adc.mpn.as_str()),
        (&rtd.rref.component, rtd.rref.mpn.as_str()),
    ];
    if !unit {
        bindings.extend([
            (&rtd.connector.component, "B4B-XH-A(LF)(SN)"),
            (&rtd.reference.component, rtd.reference.mpn.as_str()),
        ]);
    }
    for (id, expected_mpn) in bindings {
        match input
            .board
            .components
            .iter()
            .find(|component| &component.id == id)
        {
            Some(component) if component.mpn == expected_mpn => {}
            Some(component) => findings.push(Finding::fail(
                "ERC.RTD.BOARD_COMPONENT_BINDING",
                format!(
                    "board component {} has MPN {}; expected {expected_mpn}",
                    id, component.mpn
                ),
                id.clone(),
            )),
            None => findings.push(Finding::indeterminate(
                "ERC.RTD.BOARD_COMPONENT_BINDING",
                "source contract component is absent from board snapshot",
                id.clone(),
            )),
        }
    }
    for (pin, number) in ADC_PIN_NUMBERS {
        if let Some(net) = rtd.adc.pins.get(pin) {
            if !input.board.connections.iter().any(|connection| {
                connection.component == rtd.adc.component
                    && connection.pin == number
                    && connection.net == *net
            }) {
                findings.push(Finding::fail(
                    "ERC.RTD.BOARD_COMPONENT_BINDING",
                    format!(
                        "board has no {}.pad{} ({pin}) -> {net} connection",
                        rtd.adc.component, number
                    ),
                    format!("{}.pad{number}", rtd.adc.component),
                ));
            }
        } else {
            findings.push(Finding::indeterminate(
                "ERC.RTD.BOARD_COMPONENT_BINDING",
                format!(
                    "MAX31865 manufacturer pad {number} ({pin}) is absent from source contract"
                ),
                format!("{}.pad{number}", rtd.adc.component),
            ));
        }
    }
    for pin in &rtd.connector.pins {
        if !input.board.connections.iter().any(|connection| {
            connection.component == rtd.connector.component
                && connection.pin == pin.number.to_string()
                && connection.net == pin.net
        }) {
            findings.push(Finding::fail(
                "ERC.RTD.BOARD_COMPONENT_BINDING",
                format!(
                    "board has no {}.{} -> {} connection",
                    rtd.connector.component, pin.number, pin.net
                ),
                format!("{}.{}", rtd.connector.component, pin.number),
            ));
        }
    }
    for (pin, net) in [
        ("1", rtd.rref.connections[0].clone()),
        ("2", rtd.rref.connections[1].clone()),
    ] {
        if !input.board.connections.iter().any(|connection| {
            connection.component == rtd.rref.component
                && connection.pin == pin
                && connection.net == net
        }) {
            findings.push(Finding::fail(
                "ERC.RTD.BOARD_COMPONENT_BINDING",
                format!(
                    "board has no {}.{} -> {} connection",
                    rtd.rref.component, pin, net
                ),
                format!("{}.{}", rtd.rref.component, pin),
            ));
        }
    }
    if rtd.adc.mpn != "MAX31865AAP+" {
        findings.push(Finding::fail(
            "ERC.RTD.EXACT_COMPONENTS",
            format!("ADC MPN is {}; MAX31865AAP+ is required", rtd.adc.mpn),
            rtd.adc.component.clone(),
        ));
    }
    checked.push("ERC.RTD.RREF_IDENTITY".into());
    if rtd.rref.mpn.trim().is_empty() || (rtd.rref.resistance_ohm - 430.0).abs() > 0.01 {
        findings.push(Finding::fail(
            "ERC.RTD.RREF_IDENTITY",
            format!(
                "RREF must be 430 Ω {}; observed {}",
                rtd.rref.mpn, rtd.rref.resistance_ohm
            ),
            rtd.rref.component.clone(),
        ));
    }
    checked.push("ERC.RTD.FOUR_WIRE_PINOUT".into());
    {
        let expected = [
            (1, "FORCE+", "FORCE_P"),
            (2, "SENSE+", "RTDIN_P"),
            (3, "SENSE-", "RTDIN_N"),
            (4, "FORCE-", "FORCE_N"),
        ];
        let pin_map: BTreeMap<u8, _> = rtd.connector.pins.iter().map(|p| (p.number, p)).collect();
        for (number, role, adc_pin) in expected {
            match pin_map.get(&number) {
                Some(pin)
                    if pin.role == role
                        && rtd.adc.pins.get(adc_pin).is_some_and(|net| net == &pin.net) => {}
                Some(pin) => findings.push(Finding::fail(
                    "ERC.RTD.FOUR_WIRE_PINOUT",
                    format!(
                        "connector pin {number} is {} / {}, expected {role} on ADC {adc_pin}",
                        pin.role, pin.net
                    ),
                    rtd.connector.component.clone(),
                )),
                None => findings.push(Finding::indeterminate(
                    "ERC.RTD.FOUR_WIRE_PINOUT",
                    format!("connector pin {number} is missing"),
                    rtd.connector.component.clone(),
                )),
            }
        }
    }
    checked.push("ERC.RTD.FORCE_SENSE_SEPARATION".into());
    if rtd.adc.pins.get("FORCE_P") == rtd.adc.pins.get("FORCE_N")
        || rtd.adc.pins.get("RTDIN_P") == rtd.adc.pins.get("RTDIN_N")
    {
        findings.push(Finding::fail(
            "ERC.RTD.FORCE_SENSE_SEPARATION",
            "force or sense pair is electrically shorted",
            rtd.adc.component.clone(),
        ));
    }
    checked.push("ERC.RTD.NATIVE_CONNECTIVITY".into());
    {
        for (net, endpoints) in [
            (
                rtd.adc.pins["FORCE_P"].clone(),
                vec![
                    format!("{}.8", rtd.adc.component),
                    format!("{}.1", rtd.connector.component),
                ],
            ),
            (
                rtd.adc.pins["FORCE_N"].clone(),
                vec![
                    format!("{}.12", rtd.adc.component),
                    format!("{}.4", rtd.connector.component),
                ],
            ),
            (
                rtd.adc.pins["RTDIN_P"].clone(),
                vec![
                    format!("{}.10", rtd.adc.component),
                    format!("{}.2", rtd.connector.component),
                ],
            ),
            (
                rtd.adc.pins["RTDIN_N"].clone(),
                vec![
                    format!("{}.11", rtd.adc.component),
                    format!("{}.3", rtd.connector.component),
                ],
            ),
        ] {
            let clusters: Vec<_> = input
                .board
                .connectivity_clusters
                .iter()
                .filter(|cluster| cluster.net == net && cluster.source == "native")
                .collect();
            if clusters.is_empty() {
                findings.push(Finding::indeterminate(
                    "ERC.RTD.NATIVE_CONNECTIVITY",
                    format!("no native connectivity cluster for net {net}"),
                    net,
                ));
            } else if !clusters.iter().any(|cluster| {
                endpoints
                    .iter()
                    .all(|endpoint| cluster.nodes.iter().any(|node| node == endpoint))
            }) {
                findings.push(Finding::fail(
                    "ERC.RTD.NATIVE_CONNECTIVITY",
                    format!("native copper does not connect all required endpoints on {net}"),
                    net,
                ));
            }
        }
    }
    checked.push("ERC.RTD.ADC_PIN_NETS".into());
    for pin in ADC_PINS {
        if !rtd.adc.pins.contains_key(pin) || rtd.adc.pins[pin].trim().is_empty() {
            findings.push(Finding::indeterminate(
                "ERC.RTD.ADC_PIN_NETS",
                format!("MAX31865 pin {pin} has no source-derived net"),
                rtd.adc.component.clone(),
            ));
        }
    }
    checked.push("ERC.RTD.RREF_TO_REFERENCE_NETWORK".into());
    if rtd.rref.connections
        != [
            rtd.adc.pins.get("REFIN_P").cloned().unwrap_or_default(),
            rtd.adc.pins.get("REFIN_N").cloned().unwrap_or_default(),
        ]
    {
        findings.push(Finding::fail(
            "ERC.RTD.RREF_TO_REFERENCE_NETWORK",
            "RREF must span REFIN+ to REFIN−",
            rtd.rref.component.clone(),
        ));
    }
    if rtd.adc.pins.get("BIAS") != rtd.adc.pins.get("REFIN_P")
        || rtd.adc.pins.get("ISENSOR") != rtd.adc.pins.get("REFIN_N")
    {
        findings.push(Finding::fail(
            "ERC.RTD.RREF_TO_REFERENCE_NETWORK",
            "BIAS/ISENSOR are not tied to the MAX31865 reference network",
            rtd.adc.component.clone(),
        ));
    }
    checked.push("ERC.RTD.SHARED_REFERENCE".into());
    if rtd.reference.mpn != "REF2025AIDDCR" {
        findings.push(Finding::fail(
            "ERC.RTD.SHARED_REFERENCE",
            "REF2025AIDDCR is required for the shared 2.5 V reference",
            rtd.reference.component.clone(),
        ));
    }
    let consumers: Vec<_> = rtd
        .downstream_reference_consumers
        .iter()
        .filter(|c| c.net == rtd.reference.v2_net)
        .collect();
    if !unit && consumers.len() < 2 {
        findings.push(Finding::fail(
            "ERC.RTD.SHARED_REFERENCE",
            "the 2.5 V VREF net must have both downstream OVP and OCP2 consumers",
            rtd.reference.v2_net.clone(),
        ));
    } else if unit && rtd.reference.v2_net.trim().is_empty() {
        findings.push(Finding::indeterminate(
            "ERC.RTD.SHARED_REFERENCE",
            "standalone reference output net is absent from the source contract",
            rtd.reference.component.clone(),
        ));
    }
    checked.push("ERC.RTD.FAULT_OUTPUT".into());
    if rtd.fault_output.active_level != "high"
        || rtd.fault_output.pullup_rail != rtd.local_rail.upstream_net
        || rtd.fault_output.consumers.is_empty()
    {
        findings.push(Finding::fail("ERC.RTD.FAULT_OUTPUT", "RTD_HW_FAULT must be active-high, pulled up to upstream safety rail, and have a named consumer", rtd.fault_output.net.clone()));
    }
}

fn check_firmware(input: &RunInput, findings: &mut Vec<Finding>, checked: &mut Vec<String>) {
    checked.push("ERC.RTD.FIRMWARE_GPIO_CORRESPONDENCE".into());
    checked.push("ERC.RTD.SPI_SERIES_PLACEMENT".into());
    for (signal, expected_pin, adc_pin) in SPI_SIGNALS {
        match input.firmware.gpio.get(signal) {
            Some(pin) if *pin == expected_pin => {}
            Some(pin) => findings.push(Finding::fail(
                "ERC.RTD.FIRMWARE_GPIO_CORRESPONDENCE",
                format!("{signal} uses GPIO {pin}; GPIO {expected_pin} is source-defined"),
                signal,
            )),
            None => findings.push(Finding::indeterminate(
                "ERC.RTD.FIRMWARE_GPIO_CORRESPONDENCE",
                format!("{signal} GPIO is absent"),
                signal,
            )),
        }
        let binding_ok = if signal == "RTD_DRDY" {
            input.rtd.spi.iter().any(|s| {
                s.signal == signal
                    && s.mcu_pin == expected_pin
                    && s.adc_pin == adc_pin
                    && s.series_component == "direct"
            })
        } else {
            input.rtd.spi.iter().any(|s| {
                s.signal == signal
                    && s.mcu_pin == expected_pin
                    && s.adc_pin == adc_pin
                    && !s.series_component.trim().is_empty()
                    && s.series_component != "direct"
            })
        };
        if !binding_ok {
            findings.push(Finding::fail(
                "ERC.RTD.SPI_SERIES_PLACEMENT",
                format!("{signal} lacks the source-derived GPIO/ADC pin/series resistor binding"),
                signal,
            ));
        }
        if input
            .board
            .components
            .iter()
            .any(|component| component.id == "mcu.mcu")
        {
            // The MCU side of each series element retains the firmware signal
            // net name; the ADC side is the source-derived lower-case net.
            let expected_net = signal.to_string();
            let mcu_pad = input
                .rtd
                .mcu_pads
                .get(signal)
                .cloned()
                .unwrap_or_else(|| expected_pin.to_string());
            if !input.board.connections.iter().any(|connection| {
                connection.component == "mcu.mcu"
                    && connection.pin == mcu_pad
                    && connection.net == expected_net
            }) {
                findings.push(Finding::fail(
                    "ERC.RTD.FIRMWARE_GPIO_CORRESPONDENCE",
                    format!("board MCU pin {expected_pin} for {signal} is not connected to ADC net {expected_net}"),
                    format!("mcu.mcu.{mcu_pad}"),
                ));
            }
        }
    }
    if input.applicability == "RTDUnit" {
        // The unit has no MCU copper in scope, but its ten-pin host boundary
        // and the source-defined series parts are real board endpoints.  Check
        // that continuity independently from the firmware GPIO map.
        let host_pins = [
            ("RTD_SCK", "4"),
            ("RTD_SDI", "5"),
            ("RTD_SDO", "6"),
            ("RTD_CS_N", "7"),
            ("RTD_DRDY", "8"),
        ];
        for (signal, host_pin) in host_pins {
            let Some((_, _, adc_pin)) = SPI_SIGNALS.iter().find(|(name, _, _)| *name == signal)
            else {
                continue;
            };
            let host_connected = input.board.connections.iter().any(|connection| {
                connection.component == "unit_io"
                    && connection.pin == host_pin
                    && connection.net == signal
            });
            if !host_connected {
                findings.push(Finding::fail(
                    "ERC.RTD.SPI_SERIES_PLACEMENT",
                    format!("unit_io.{host_pin} has no {signal} source connection"),
                    format!("unit_io.{host_pin}"),
                ));
                continue;
            }
            let adc_net = input
                .rtd
                .adc
                .pins
                .get(*adc_pin)
                .cloned()
                .unwrap_or_default();
            let series = input.rtd.spi.iter().find(|entry| entry.signal == signal);
            let continuity = match series {
                Some(series) if series.series_component == "direct" => {
                    input.board.connections.iter().any(|connection| {
                        connection.component == input.rtd.adc.component && connection.net == adc_net
                    })
                }
                Some(series) => {
                    let nets: std::collections::BTreeSet<_> = input
                        .board
                        .connections
                        .iter()
                        .filter(|connection| connection.component == series.series_component)
                        .map(|connection| connection.net.as_str())
                        .collect();
                    nets.contains(signal) && nets.contains(adc_net.as_str())
                }
                None => false,
            };
            if !continuity {
                findings.push(Finding::fail(
                    "ERC.RTD.SPI_SERIES_PLACEMENT",
                    format!("{signal} host boundary does not reach ADC {adc_pin} through its source series binding"),
                    signal,
                ));
            }
        }
    }
    checked.push("ERC.RTD.FIRMWARE_THRESHOLD_ENCODING".into());
    let t = &input.firmware.thresholds;
    let low = max31865_code(t.short_ohm, t.rref_ohm, true, t.adc_bits) << t.shift;
    let high = max31865_code(t.open_ohm, t.rref_ohm, false, t.adc_bits) << t.shift;
    if t.low_word as u32 != low {
        findings.push(Finding::fail(
            "ERC.RTD.FIRMWARE_THRESHOLD_ENCODING",
            format!(
                "low threshold word {} encodes {low}, expected inclusive ceil encoding",
                t.low_word
            ),
            "MAX31865_LOW_THRESHOLD_WORD",
        ));
    }
    if t.high_word as u32 != high {
        findings.push(Finding::fail(
            "ERC.RTD.FIRMWARE_THRESHOLD_ENCODING",
            format!(
                "high threshold word {} encodes {high}, expected inclusive floor encoding",
                t.high_word
            ),
            "MAX31865_HIGH_THRESHOLD_WORD",
        ));
    }
    if (t.rref_ohm - input.rtd.rref.resistance_ohm).abs() > 0.01 {
        findings.push(Finding::fail(
            "ERC.RTD.FIRMWARE_THRESHOLD_ENCODING",
            "firmware RREF does not equal source-derived RREF",
            "rref",
        ));
    }
}

fn max31865_code(resistance: f64, rref: f64, ceil: bool, bits: u8) -> u32 {
    let exact = resistance / rref * (1u32 << bits) as f64;
    let code = if ceil {
        exact.floor() as u32 + 1
    } else {
        exact.floor() as u32
    };
    code.min((1u32 << bits) - 1)
}

fn check_fault_scenarios(
    input: &RunInput,
    findings: &mut Vec<Finding>,
    gaps: &mut Vec<String>,
    checked: &mut Vec<String>,
) {
    checked.push("ERC.RTD.FAULT_CORNERS".into());
    if input.scenarios.is_empty() {
        gaps.push("independent observed fault scenarios are absent; hardware fault coverage is indeterminate".into());
        findings.push(Finding::indeterminate(
            "ERC.RTD.FAULT_CORNERS",
            "no observed fault scenarios were supplied; expected-only model entries cannot establish behavior",
            "fault-observations",
        ));
        return;
    }
    if input.applicability == "RTDUnit" {
        check_unit_fault_observations(input, findings, gaps);
        return;
    }
    for scenario in &input.scenarios {
        let actual = classify_scenario(scenario, input.rtd.fault_output.active_level == "high");
        if actual != scenario.expected_class {
            findings.push(Finding::fail(
                "ERC.RTD.FAULT_CORNERS",
                format!(
                    "scenario {} classified as {actual}, expected {}",
                    scenario.name, scenario.expected_class
                ),
                scenario.name.clone(),
            ));
        }
        if scenario.conductor_open.as_deref() == Some("SENSE+") {
            gaps.push(format!("{}: RTDIN+ cable open is a documented blind spot until the optional bias diagnostic is adopted", scenario.name));
            findings.push(Finding::indeterminate(
                "ERC.RTD.FAULT_CORNERS",
                "RTDIN+ conductor open is not proven by the two paths",
                scenario.name.clone(),
            ));
        } else if actual == "indeterminate_fault" {
            gaps.push(format!(
                "{}: source/model evidence does not establish a detector for this fault",
                scenario.name
            ));
            findings.push(Finding::indeterminate(
                "ERC.RTD.FAULT_CORNERS",
                "fault case is outside the adopted detector model",
                scenario.name.clone(),
            ));
        } else if scenario.expected_detected
            && !actual.starts_with("covered_")
            && actual != "local_rail_loss"
        {
            findings.push(Finding::fail(
                "ERC.RTD.FAULT_CORNERS",
                "expected detected fault has no modeled detector",
                scenario.name.clone(),
            ));
        }
    }
}

fn check_unit_fault_observations(
    input: &RunInput,
    findings: &mut Vec<Finding>,
    gaps: &mut Vec<String>,
) {
    let mut conductors = std::collections::BTreeSet::new();
    let mut has_short = false;
    let mut has_local_loss = false;
    let mut has_upstream_loss = false;
    let mut has_healthy = false;
    for scenario in &input.scenarios {
        let Some(observed_class) = scenario.observed_class.as_deref() else {
            findings.push(Finding::fail(
                "ERC.RTD.FAULT_CORNERS",
                "unit fault case is missing independent observed_class",
                scenario.name.clone(),
            ));
            continue;
        };
        let Some(observed_detected) = scenario.observed_detected else {
            findings.push(Finding::fail(
                "ERC.RTD.FAULT_CORNERS",
                "unit fault case is missing independent observed_detected",
                scenario.name.clone(),
            ));
            continue;
        };
        let local_rail_loss = scenario.rail_loss.as_deref() == Some("post_ferrite");
        match scenario.observed_latency_ms {
            Some(latency)
                if latency.is_finite()
                    && latency >= 0.0
                    && latency < input.firmware.fault_latency_limit_ms => {}
            Some(_) => findings.push(Finding::fail(
                "ERC.RTD.FAULT_CORNERS",
                format!(
                    "unit fault latency must be finite and < {} ms",
                    input.firmware.fault_latency_limit_ms
                ),
                scenario.name.clone(),
            )),
            None if local_rail_loss => {}
            None if scenario.observed_detected.unwrap_or(false) => {
                gaps.push(format!(
                    "{} is detected but has no measured latency observation",
                    scenario.name
                ));
                findings.push(Finding::indeterminate(
                    "ERC.RTD.FAULT_CORNERS",
                    "detected case lacks an independent measured latency",
                    scenario.name.clone(),
                ));
            }
            None => {}
        }
        let class_lower = observed_class.to_ascii_lowercase();
        if scenario.name.to_ascii_lowercase().contains("startup") {
            if !scenario.observed_detected.unwrap_or(false)
                || !class_lower.contains("startup")
                || !class_lower.contains("masked")
            {
                findings.push(Finding::fail(
                    "ERC.RTD.FAULT_CORNERS",
                    "startup must remain masked until the first valid sample",
                    scenario.name.clone(),
                ));
            }
            continue;
        }
        if let Some(conductor) = scenario.conductor_open.as_deref() {
            conductors.insert(conductor.to_string());
            if !observed_detected || observed_class.eq_ignore_ascii_case("indeterminate_fault") {
                findings.push(Finding::fail(
                    "ERC.RTD.FAULT_CORNERS",
                    "each conductor-open observation must report a detected hardware fault",
                    scenario.name.clone(),
                ));
            }
        }
        if scenario
            .resistance_ohm
            .is_some_and(|ohm| ohm <= input.firmware.thresholds.short_ohm)
        {
            has_short = true;
            if !observed_detected || observed_class.eq_ignore_ascii_case("indeterminate_fault") {
                findings.push(Finding::fail(
                    "ERC.RTD.FAULT_CORNERS",
                    "short observation must report a detected hardware fault",
                    scenario.name.clone(),
                ));
            }
        }
        match scenario.rail_loss.as_deref() {
            Some("post_ferrite") => {
                has_local_loss = true;
                if !observed_detected || observed_class.eq_ignore_ascii_case("indeterminate_fault")
                {
                    findings.push(Finding::fail(
                        "ERC.RTD.FAULT_CORNERS",
                        "local RTD_AVDD loss must report supervisor/NAND hardware fault",
                        scenario.name.clone(),
                    ));
                }
                let owner = scenario
                    .observed_fault_owner
                    .as_deref()
                    .unwrap_or_default()
                    .to_ascii_lowercase();
                let condition = scenario
                    .observed_detection_condition
                    .as_deref()
                    .unwrap_or_default()
                    .to_ascii_lowercase();
                let powered_result = scenario
                    .observed_powered_comparator_result
                    .as_deref()
                    .unwrap_or_default()
                    .to_ascii_lowercase();
                if owner.is_empty() && condition.is_empty() && powered_result.is_empty() {
                    gaps.push(format!(
                        "{} lacks static TPS389001/NAND detector evidence",
                        scenario.name
                    ));
                    findings.push(Finding::indeterminate(
                        "ERC.RTD.FAULT_CORNERS",
                        "local rail observation has no static detector ownership fields",
                        scenario.name.clone(),
                    ));
                } else if !owner.contains("tps389001")
                    || (!owner.contains("nand") && !owner.contains("lvc1g38"))
                    || !condition.contains("falling_trip")
                    || !condition.contains("rising_clear")
                    || !powered_result.contains("unasserted")
                {
                    findings.push(Finding::fail(
                        "ERC.RTD.FAULT_CORNERS",
                        "local rail observation lacks the authored TPS389001/NAND static detector condition",
                        scenario.name.clone(),
                    ));
                } else {
                    findings.push(Finding::pass(
                        "ERC.RTD.FAULT_CORNERS",
                        "TPS389001 threshold/NAND ownership and powered-comparator static truth are observed",
                        scenario.name.clone(),
                    ));
                    if scenario.observed_latency_ms.is_none() {
                        gaps.push(format!(
                            "{} has conditional nominal timing only; guaranteed maximum remains a physical integration obligation",
                            scenario.name
                        ));
                        findings.push(Finding::indeterminate(
                            "ERC.RTD.FAULT_CORNERS",
                            "static rail detector is proven, but guaranteed worst-case brownout timing was not physically measured",
                            scenario.name.clone(),
                        ));
                    }
                }
            }
            Some("upstream") => {
                has_upstream_loss = true;
                let class = observed_class.to_ascii_lowercase();
                if observed_detected || (!class.contains("disable") && !class.contains("inhibit")) {
                    findings.push(Finding::fail("ERC.RTD.FAULT_CORNERS", "upstream loss must be classified as host disable/inhibit without powered-high claim", scenario.name.clone()));
                }
            }
            _ if scenario.conductor_open.is_none()
                && scenario.rail_loss.is_none()
                && scenario.resistance_ohm.is_none() =>
            {
                has_healthy = true;
                if observed_detected
                    || !(observed_class.eq_ignore_ascii_case("healthy")
                        || class_lower.contains("no_fault"))
                {
                    findings.push(Finding::fail(
                        "ERC.RTD.FAULT_CORNERS",
                        "healthy observation must report no fault",
                        scenario.name.clone(),
                    ));
                }
            }
            _ => {}
        }
    }
    for conductor in ["FORCE+", "FORCE-", "SENSE+", "SENSE-"] {
        if !conductors.contains(conductor) {
            gaps.push(format!(
                "unit fault observations omit required {conductor} conductor-open case"
            ));
            findings.push(Finding::indeterminate(
                "ERC.RTD.FAULT_CORNERS",
                "required independent conductor-open observation is absent",
                conductor,
            ));
        }
    }
    for (present, object, message) in [
        (has_short, "short", "short-circuit observation is absent"),
        (
            has_local_loss,
            "post_ferrite",
            "local RTD_AVDD loss observation is absent",
        ),
        (
            has_upstream_loss,
            "upstream",
            "upstream +3V3 loss observation is absent",
        ),
    ] {
        if !present {
            gaps.push(format!(
                "unit fault observations omit required {object} case"
            ));
            findings.push(Finding::indeterminate(
                "ERC.RTD.FAULT_CORNERS",
                message,
                object,
            ));
        }
    }
    if !has_healthy {
        gaps.push("unit fault observations omit required healthy case".into());
        findings.push(Finding::indeterminate(
            "ERC.RTD.FAULT_CORNERS",
            "healthy observation is absent",
            "healthy",
        ));
    }
}

fn classify_scenario(s: &FaultScenario, active_high: bool) -> String {
    if !active_high {
        return "fault_polarity_error".into();
    }
    if let Some(rail) = &s.rail_loss {
        return match rail.as_str() {
            "upstream" => "upstream_loss_system_disable_required".into(),
            "post_ferrite" => "local_rail_loss".into(),
            _ => "indeterminate_fault".into(),
        };
    }
    if let Some(conductor) = &s.conductor_open {
        return match conductor.as_str() {
            "SENSE+" => "blind_spot_open_sense_plus".into(),
            "FORCE+" | "FORCE-" => "covered_cable_open".into(),
            "SENSE-" => "indeterminate_fault".into(),
            _ => "indeterminate_fault".into(),
        };
    }
    if let Some(ohm) = s.resistance_ohm {
        if ohm <= 10.0 {
            return if active_high {
                "covered_short".into()
            } else {
                "fault_polarity_error".into()
            };
        }
        if ohm >= 300.0 {
            return "covered_open".into();
        }
        return "valid_measurement".into();
    }
    "indeterminate_fault".into()
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn threshold_encoding_matches_board_words() {
        assert_eq!(max31865_code(10.0, 430.0, true, 15) << 1, 1526);
        assert_eq!(max31865_code(300.0, 430.0, false, 15) << 1, 45722);
    }
    #[test]
    fn low_threshold_strictly_exceeds_exact_code() {
        assert_eq!(max31865_code(1.0, 32768.0, true, 15), 2);
        assert_eq!(max31865_code(1.0, 32768.0, false, 15), 1);
    }
    #[test]
    fn asymmetric_fault_cases_keep_documented_blind_spot() {
        assert_eq!(
            classify_scenario(
                &FaultScenario {
                    name: "x".into(),
                    resistance_ohm: None,
                    conductor_open: Some("SENSE+".into()),
                    rail_loss: None,
                    expected_class: "".into(),
                    expected_detected: false,
                    observed_class: None,
                    observed_detected: None,
                    model_latency_ms: None,
                    observed_latency_ms: None,
                    observed_fault_owner: None,
                    observed_detection_condition: None,
                    observed_powered_comparator_result: None,
                },
                true
            ),
            "blind_spot_open_sense_plus"
        );
    }
}

pub mod thermal_sense;
pub mod voltage_sense;

pub mod domain_contract;

pub mod operating_limits;
pub mod pfc_currents;
pub mod pfc_losses;

pub mod pfc_shunt;
pub mod pfc_switching;

pub mod pfc_protection;
pub mod fault_loop;
