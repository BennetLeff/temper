//! Fault-loop connectivity check.
//!
//! An element can carry current in a declared loop only when **at least two of
//! its terminals** lie on that loop's nets. A two-terminal element needs both; a
//! three-terminal device such as a MOSFET qualifies on its two power terminals
//! even when its gate sits on a control net.
//!
//! # This is a necessary connectivity check, and nothing more
//!
//! Two terminals on the loop's nets is **consistent with** conduction. It does
//! not prove a conductive path, a device state, a current direction, or a current
//! distribution. A model that satisfies this check has not thereby been shown to
//! be physically right, and peak current and energy distribution stay unresolved
//! wherever the model lacks defensible inputs.
//!
//! Motivating error: an AR-FAULT capacitor-discharge model placed energy in the
//! current-sense shunt, whose second terminal sits on the bridge return while the
//! internal loop runs capacitors -> shorted boost diode -> switch -> capacitors.
//! The check rejects that assignment. It would not have caught a wrong magnitude
//! on an element that is genuinely in the loop.

use serde::Deserialize;
use std::collections::{BTreeMap, BTreeSet};

#[derive(Debug, Clone, Deserialize)]
pub struct NetInfo {
    /// `[reference, pin]` pairs on this net.
    pub nodes: Vec<(String, String)>,
}

/// Netlist evidence in the shape the campaign's `netlist_fault_loop.json` uses.
#[derive(Debug, Clone, Deserialize)]
pub struct NetlistEvidence {
    pub netlist_evidence: BTreeMap<String, NetInfo>,
}

impl NetlistEvidence {
    /// Element reference -> the nets its terminals sit on.
    pub fn element_nets(&self) -> BTreeMap<String, BTreeSet<String>> {
        let mut membership: BTreeMap<String, BTreeSet<String>> = BTreeMap::new();
        for (net, info) in &self.netlist_evidence {
            for (reference, _pin) in &info.nodes {
                membership
                    .entry(reference.clone())
                    .or_default()
                    .insert(net.clone());
            }
        }
        membership
    }
}

/// One message per element that carries a non-zero assignment but cannot conduct
/// in the declared loop. An empty result means every assignment is at least
/// connectivity-consistent — not that the model is correct.
pub fn loop_inconsistencies(
    evidence: &NetlistEvidence,
    loop_nets: &BTreeSet<String>,
    assignments: &BTreeMap<String, f64>,
) -> Vec<String> {
    let membership = evidence.element_nets();
    let mut failures = Vec::new();
    for (reference, value) in assignments {
        if *value == 0.0 {
            continue;
        }
        match membership.get(reference) {
            None => failures.push(format!(
                "{reference} carries {value} but has no terminals in the netlist evidence"
            )),
            Some(nets) => {
                let on_loop = nets.intersection(loop_nets).count();
                if on_loop < 2 {
                    failures.push(format!(
                        "{reference} carries {value} but only {on_loop} of its terminals \
                         {nets:?} lie on the declared loop {loop_nets:?}"
                    ));
                }
            }
        }
    }
    failures
}

#[cfg(test)]
mod tests {
    use super::*;

    fn evidence() -> NetlistEvidence {
        let raw = r#"{
          "netlist_evidence": {
            "PFC_BUS_PLUS_390V": {"nodes": [["U10","2"],["U36","1"],["U37","1"]]},
            "PFC_BUS_MINUS": {"nodes": [["U9","3"],["U12","1"],["U36","2"],["U37","2"]]},
            "a1": {"nodes": [["U10","1"],["U9","2"],["U8","2"]]},
            "q_boost-g": {"nodes": [["U9","1"]]},
            "minus": {"nodes": [["U12","2"],["U1","3"]]},
            "plus": {"nodes": [["U8","1"],["U1","1"]]}
          }
        }"#;
        serde_json::from_str(raw).expect("evidence parses")
    }

    fn loop_nets() -> BTreeSet<String> {
        ["PFC_BUS_PLUS_390V", "PFC_BUS_MINUS", "a1"]
            .iter()
            .map(|s| (*s).to_string())
            .collect()
    }

    fn assignments(pairs: &[(&str, f64)]) -> BTreeMap<String, f64> {
        pairs.iter().map(|(k, v)| ((*k).to_string(), *v)).collect()
    }

    #[test]
    fn a_shunt_outside_the_loop_is_rejected() {
        // the motivating error: energy assigned to the shunt in the internal loop
        let failures = loop_inconsistencies(
            &evidence(),
            &loop_nets(),
            &assignments(&[("U9", 145.0), ("U12", 34.0)]),
        );
        assert_eq!(failures.len(), 1, "{failures:?}");
        assert!(failures[0].contains("U12"), "{failures:?}");
    }

    #[test]
    fn a_two_terminal_element_on_the_loop_is_accepted() {
        let failures = loop_inconsistencies(
            &evidence(),
            &loop_nets(),
            &assignments(&[("U10", 145.0), ("U36", 30.0), ("U37", 20.0), ("U9", 100.0)]),
        );
        assert!(failures.is_empty(), "{failures:?}");
    }

    #[test]
    fn a_three_terminal_device_qualifies_on_two_power_terminals() {
        // U9's gate sits on q_boost-g, outside the loop
        assert!(loop_inconsistencies(&evidence(), &loop_nets(), &assignments(&[("U9", 1.0)])).is_empty());
    }

    #[test]
    fn an_element_absent_from_the_netlist_is_rejected() {
        let failures = loop_inconsistencies(&evidence(), &loop_nets(), &assignments(&[("U99", 1.0)]));
        assert!(failures.iter().any(|f| f.contains("U99")), "{failures:?}");
    }

    #[test]
    fn a_zero_assignment_is_ignored() {
        assert!(loop_inconsistencies(&evidence(), &loop_nets(), &assignments(&[("U12", 0.0)])).is_empty());
    }

    #[test]
    fn a_device_outside_the_loop_is_rejected() {
        let failures = loop_inconsistencies(&evidence(), &loop_nets(), &assignments(&[("U1", 40.0)]));
        assert_eq!(failures.len(), 1, "{failures:?}");
    }
}
