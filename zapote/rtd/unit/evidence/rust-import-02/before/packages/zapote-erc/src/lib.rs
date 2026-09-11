//! RTD source/connectivity, firmware correspondence, and fault checks.

use std::collections::BTreeMap;
use zapote_core::{CheckReport, FaultScenario, Finding, RunInput};

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
                    expected_detected: false
                },
                true
            ),
            "blind_spot_open_sense_plus"
        );
    }
}
