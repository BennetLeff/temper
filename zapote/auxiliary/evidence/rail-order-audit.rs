//! Netlist and fault-matrix audit for the lab-only HOT rail-order fixture.
//! This checks connector topology and required observations, not analog behavior.

use std::collections::{BTreeMap, BTreeSet};
use std::env;
use std::fs;

type Pins = BTreeSet<(String, String)>;
type Nets = BTreeMap<String, Pins>;

const COMPONENTS: &[&str] = &[
    "J1", "J2", "J3", "TP1", "TP2", "TP3", "TP4", "TP5", "TP6", "TP7", "TP8", "TP9", "TP10",
];

const EVENT_TRACES: &[(&str, &str)] = &[
    ("cold_aux_first", "RESET>AUX_ON>CHECK_OFF"),
    ("cold_logic_first", "RESET>LOGIC5_ON>CHECK_OFF"),
    ("partial_logic", "RESET>AUX_ON>LOGIC5_PARTIAL>CHECK_OFF"),
    ("aux_loss", "RESET>RAILS_ON>ARM>AUX_LOSS>CHECK_OFF"),
    ("logic_loss", "RESET>RAILS_ON>ARM>LOGIC5_LOSS>CHECK_OFF"),
    (
        "repeated_hiccup",
        "RESET>RAILS_ON>ARM>AUX_LOSS>AUX_RECOVER>AUX_LOSS>AUX_RECOVER>CHECK_OFF",
    ),
    (
        "brownout_recover",
        "RESET>RAILS_ON>ARM>LOGIC5_BROWNOUT>LOGIC5_RECOVER>CHECK_OFF",
    ),
    ("stuck_high_request", "RESET>RAILS_ON>REQUEST_HIGH>CHECK_OFF"),
    (
        "ena_stuck_high",
        "RESET>RAILS_ON>ARM>LOGIC5_LOSS>INJECT_ENA_HIGH>CHECK_REJECT",
    ),
    (
        "fresh_rearm",
        "RESET>RAILS_ON>ARM>LOGIC5_LOSS>LOGIC5_RECOVER>CHECK_OFF>REQUEST_LOW>ARM_FRESH>REQUEST_HIGH>CHECK_ELIGIBLE",
    ),
];

// Pin the observation contract separately from the editable capture matrix.
// A syntactically valid row must not be able to weaken a required OFF or
// fresh-rearm observation while retaining the same event trace.
const EXPECTED_ROWS: &[(&str, &str)] = &[
    ("cold_aux_first", "cold_aux_first\tnominal\toff\tlow\tnone\tnone\toff_le_0p8\toff_after_discharge\tcapture_required"),
    ("cold_logic_first", "cold_logic_first\toff\tnominal\tlow\tnone\tnone\tunpowered\toff_after_discharge\tcapture_required"),
    ("partial_logic", "partial_logic\tnominal\tpartial\thigh\tstale\tnone\toff_le_0p8\toff_after_discharge\tcapture_required"),
    ("aux_loss", "aux_loss\toff\tnominal\thigh\tstale\tnone\tunpowered\toff_after_discharge\tcapture_required"),
    ("logic_loss", "logic_loss\tnominal\toff\thigh\tstale\tnone\toff_le_0p8\toff_after_discharge\tcapture_required"),
    ("repeated_hiccup", "repeated_hiccup\tnominal\tnominal\thigh\tstale\tnone\toff_le_0p8\toff_after_discharge\tcapture_required"),
    ("brownout_recover", "brownout_recover\tnominal\tnominal\thigh\tstale\tnone\toff_le_0p8\toff_after_discharge\tcapture_required"),
    ("stuck_high_request", "stuck_high_request\tnominal\tnominal\thigh\tnone\tnone\toff_le_0p8\toff_after_discharge\tcapture_required"),
    ("ena_stuck_high", "ena_stuck_high\tnominal\toff\thigh\tstale\tena_high\toff_le_0p8\toff_after_discharge\treject_if_observed"),
    ("fresh_rearm", "fresh_rearm\tnominal\tnominal\thigh\tfresh\tnone\teligible_ge_2p3\tconditional_on_pwm\tcapture_required"),
];

const EXPECTED: &[(&str, &[(&str, &str)])] = &[
    ("aux_protected", &[("J1", "1"), ("J3", "1"), ("TP1", "1")]),
    ("hot_logic5", &[("J2", "1"), ("J3", "2"), ("TP2", "1")]),
    (
        "hot0",
        &[("J1", "2"), ("J2", "2"), ("J3", "3"), ("TP3", "1")],
    ),
    ("driver_permission", &[("J3", "4"), ("TP4", "1")]),
    ("ena_node", &[("J3", "5"), ("TP5", "1")]),
    ("en_shunt_base", &[("J3", "6"), ("TP6", "1")]),
    ("pfc_pwm", &[("J3", "7"), ("TP7", "1")]),
    ("stw_gate", &[("J3", "8"), ("TP8", "1")]),
    ("hot_run_q", &[("J3", "9"), ("TP9", "1")]),
    ("hot_session_q", &[("J3", "10"), ("TP10", "1")]),
];

fn quoted_after<'a>(line: &'a str, key: &str) -> Result<&'a str, String> {
    let rest = line
        .split_once(key)
        .ok_or_else(|| format!("missing {key} in {line}"))?
        .1;
    rest.split_once('"')
        .map(|(value, _)| value)
        .ok_or_else(|| format!("unclosed {key} in {line}"))
}

fn parse_netlist(input: &str) -> Result<Nets, String> {
    let mut nets = Nets::new();
    let mut active: Option<String> = None;
    for line in input.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("(net (code ") {
            let name = quoted_after(trimmed, "(name \"")?.to_owned();
            if nets.insert(name.clone(), Pins::new()).is_some() {
                return Err(format!("duplicate net {name}"));
            }
            active = Some(name);
        } else if trimmed.starts_with("(node ") {
            let name = active.as_ref().ok_or("node before net")?;
            let reference = quoted_after(trimmed, "(ref \"")?.to_owned();
            let pin = quoted_after(trimmed, "(pin \"")?.to_owned();
            let pins = nets.get_mut(name).ok_or("active net missing")?;
            if !pins.insert((reference, pin)) {
                return Err(format!("duplicate node on {name}"));
            }
        }
    }
    if nets.is_empty() {
        return Err("no generated KiCad netlist nets found".into());
    }
    Ok(nets)
}

fn audit_components(input: &str) -> Result<(), String> {
    let mut found = BTreeSet::new();
    for line in input.lines() {
        let trimmed = line.trim();
        if trimmed.starts_with("(comp (ref \"") {
            let reference = quoted_after(trimmed, "(ref \"")?;
            if !found.insert(reference) {
                return Err(format!("duplicate component {reference}"));
            }
        }
    }
    let expected: BTreeSet<_> = COMPONENTS.iter().copied().collect();
    if found != expected {
        return Err(format!(
            "component set mismatch: expected {expected:?}; found {found:?}"
        ));
    }
    Ok(())
}

fn audit_nets(nets: &Nets) -> Result<(), String> {
    if nets.len() != EXPECTED.len() {
        return Err(format!(
            "expected {} distinct nets, found {}",
            EXPECTED.len(),
            nets.len()
        ));
    }
    for (name, expected) in EXPECTED {
        let found = nets
            .get(*name)
            .ok_or_else(|| format!("missing net {name}"))?;
        let expected: Pins = expected
            .iter()
            .map(|(reference, pin)| (reference.to_string(), pin.to_string()))
            .collect();
        if found != &expected {
            return Err(format!(
                "{name} nodes mismatch: expected {expected:?}; found {found:?}"
            ));
        }
    }
    Ok(())
}

fn audit_matrix(input: &str) -> Result<(), String> {
    let header =
        "case\taux\tlogic5\trequest\tarm\tinjection\tena_requirement\tgate_requirement\tverdict\tevents";
    let mut lines = input.lines();
    if lines.next() != Some(header) {
        return Err("fault matrix header mismatch".into());
    }
    let mut cases = BTreeSet::new();
    for line in lines.filter(|line| !line.trim().is_empty()) {
        let columns: Vec<_> = line.split('\t').collect();
        if columns.len() != 10 {
            return Err(format!("wrong column count in {line}"));
        }
        let [case, aux, logic, request, arm, injection, ena, gate, verdict, events] =
            columns.as_slice()
        else {
            return Err("matrix row shape mismatch".into());
        };
        if !cases.insert(*case) {
            return Err(format!("duplicate case {case}"));
        }
        let expected_trace = EVENT_TRACES
            .iter()
            .find(|(name, _)| name == case)
            .ok_or_else(|| format!("unexpected case {case}"))?
            .1;
        if *events != expected_trace {
            return Err(format!("event order mismatch in {case}"));
        }
        let expected_row = EXPECTED_ROWS
            .iter()
            .find(|(name, _)| name == case)
            .ok_or_else(|| format!("missing observation contract for {case}"))?
            .1;
        if line.rsplit_once('\t').map(|(prefix, _)| prefix) != Some(expected_row) {
            return Err(format!("observation contract mismatch in {case}"));
        }
        if !["off", "nominal"].contains(aux) || !["off", "partial", "nominal"].contains(logic) {
            return Err(format!("invalid rail state in {case}"));
        }
        if !["none", "stale", "fresh"].contains(arm) {
            return Err(format!("invalid arm state in {case}"));
        }
        if !["low", "high"].contains(request) || !["none", "ena_high"].contains(injection) {
            return Err(format!("invalid request or injection in {case}"));
        }
        if !["unpowered", "off_le_0p8", "eligible_ge_2p3"].contains(ena)
            || !["off_after_discharge", "conditional_on_pwm"].contains(gate)
        {
            return Err(format!("invalid observation requirement in {case}"));
        }
        if *aux == "off" && *ena != "unpowered" {
            return Err(format!("unpowered AUX treated as driven ENA in {case}"));
        }
        if *aux == "nominal" && (*logic != "nominal" || *arm != "fresh") && *ena != "off_le_0p8" {
            return Err(format!("unsafe ENA requirement in {case}"));
        }
        if *arm != "fresh" && *gate != "off_after_discharge" {
            return Err(format!("stale or absent arm permits gate in {case}"));
        }
        if *arm == "fresh" && (*aux != "nominal" || *logic != "nominal" || *request != "high") {
            return Err(format!("fresh arm on invalid rails/request in {case}"));
        }
        if *injection == "ena_high" && *verdict != "reject_if_observed" {
            return Err(format!("fault-masked ENA accepted in {case}"));
        }
        if *injection != "ena_high" && *verdict != "capture_required" {
            return Err(format!("unmeasured case promoted in {case}"));
        }
    }
    for (name, _) in EVENT_TRACES {
        if !cases.contains(name) {
            return Err(format!("missing fault case {name}"));
        }
    }
    Ok(())
}

fn main() -> Result<(), String> {
    let args: Vec<_> = env::args().collect();
    if args.len() != 3 {
        return Err(
            "usage: rail-order-audit <generated-default.net> <rail-order-cases.tsv>".into(),
        );
    }
    let netlist = fs::read_to_string(&args[1]).map_err(|e| e.to_string())?;
    let matrix = fs::read_to_string(&args[2]).map_err(|e| e.to_string())?;
    audit_components(&netlist)?;
    audit_nets(&parse_netlist(&netlist)?)?;
    audit_matrix(&matrix)?;
    println!("fixture netlist: 10 expected nets and 13 passive components; PASS");
    println!("fault matrix: 10 required cases; CAPTURE REQUIRED; analog status INDETERMINATE");
    Ok(())
}

#[cfg(test)]
mod tests {
    use super::*;

    fn good_nets() -> Nets {
        EXPECTED
            .iter()
            .map(|(name, pins)| {
                (
                    (*name).to_owned(),
                    pins.iter()
                        .map(|(reference, pin)| (reference.to_string(), pin.to_string()))
                        .collect(),
                )
            })
            .collect()
    }

    #[test]
    fn detects_aux_logic_tie() {
        let mut nets = good_nets();
        nets.get_mut("aux_protected")
            .unwrap()
            .insert(("J2".into(), "1".into()));
        assert!(audit_nets(&nets).is_err());
    }

    #[test]
    fn detects_extra_unconnected_component() {
        let netlist = COMPONENTS
            .iter()
            .chain(["X1"].iter())
            .map(|reference| format!("(comp (ref \"{reference}\")"))
            .collect::<Vec<_>>()
            .join("\n");
        assert!(audit_components(&netlist).is_err());
    }

    #[test]
    fn detects_selv_return_join() {
        let mut nets = good_nets();
        nets.insert("selv_gnd".into(), Pins::new());
        assert!(audit_nets(&nets).is_err());
    }

    #[test]
    fn detects_power_feed_into_probe() {
        let mut nets = good_nets();
        nets.get_mut("ena_node")
            .unwrap()
            .insert(("J1".into(), "1".into()));
        assert!(audit_nets(&nets).is_err());
    }

    #[test]
    fn detects_missing_ena_observation() {
        let mut nets = good_nets();
        nets.get_mut("ena_node")
            .unwrap()
            .remove(&("TP5".into(), "1".into()));
        assert!(audit_nets(&nets).is_err());
    }

    #[test]
    fn rejects_fault_masked_ena() {
        let bad = include_str!("rail-order-cases.tsv")
            .replace("ena_stuck_high\tnominal\toff\thigh\tstale\tena_high\toff_le_0p8\toff_after_discharge\treject_if_observed", "ena_stuck_high\tnominal\toff\thigh\tstale\tena_high\toff_le_0p8\toff_after_discharge\tcapture_required");
        assert!(audit_matrix(&bad).is_err());
    }

    #[test]
    fn rejects_recovery_as_rearm() {
        let bad = include_str!("rail-order-cases.tsv")
            .replace("brownout_recover\tnominal\tnominal\thigh\tstale\tnone\toff_le_0p8\toff_after_discharge", "brownout_recover\tnominal\tnominal\thigh\tstale\tnone\teligible_ge_2p3\tconditional_on_pwm");
        assert!(audit_matrix(&bad).is_err());
    }

    #[test]
    fn rejects_valid_but_weakened_expected_observation() {
        let bad = include_str!("rail-order-cases.tsv").replace(
            "fresh_rearm\tnominal\tnominal\thigh\tfresh\tnone\teligible_ge_2p3\tconditional_on_pwm",
            "fresh_rearm\tnominal\tnominal\thigh\tfresh\tnone\toff_le_0p8\toff_after_discharge",
        );
        assert!(audit_matrix(&bad).is_err());
    }

    #[test]
    fn rejects_early_gate_on_aux_only_trace() {
        let bad = include_str!("rail-order-cases.tsv").replace(
            "cold_aux_first\tnominal\toff\tlow\tnone\tnone\toff_le_0p8\toff_after_discharge",
            "cold_aux_first\tnominal\tnominal\thigh\tfresh\tnone\teligible_ge_2p3\tconditional_on_pwm",
        );
        assert!(audit_matrix(&bad).is_err());
    }

    #[test]
    fn rejects_rearm_before_recovered_request_cycle() {
        let bad = include_str!("rail-order-cases.tsv").replace(
            "CHECK_OFF>REQUEST_LOW>ARM_FRESH>REQUEST_HIGH>CHECK_ELIGIBLE",
            "ARM_FRESH>CHECK_OFF>REQUEST_LOW>REQUEST_HIGH>CHECK_ELIGIBLE",
        );
        assert!(audit_matrix(&bad).is_err());
    }

    #[test]
    fn accepts_declared_fault_matrix() {
        assert!(audit_matrix(include_str!("rail-order-cases.tsv")).is_ok());
    }
}
