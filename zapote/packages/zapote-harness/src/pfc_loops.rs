//! Exact source/native closure checks for the PFC switching loops.
//!
//! This is deliberately a topology and evidence check.  A graph path proves
//! that the saved copper joins two package terminals; it does not prove that
//! the path is the high-frequency current path, its inductance, or its EMI
//! performance.  Those remain explicit indeterminate obligations.

use crate::pfc_paths::BoundGraph;
use std::collections::{BTreeSet, VecDeque};
use zapote_core::{CheckReport, Finding, Status};
use zapote_erc::source_circuit::Circuit;

const TOPOLOGY: &str = "DRC.PFC.LOOP_TOPOLOGY";
const GEOMETRY: &str = "DRC.PFC.LOOP_GEOMETRY";
const INDUCTANCE: &str = "DRC.PFC.LOOP_INDUCTANCE";

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct LoopLeg {
    pub from: &'static str,
    pub to: &'static str,
}

#[derive(Clone, Copy, Debug, PartialEq, Eq)]
pub struct LoopSpec<'a> {
    pub name: &'static str,
    pub legs: &'a [LoopLeg],
}

// Pin numbers are from the authored PowerEntryUnit source.  The diode's
// anodes are pins 1 and 3; pin 2 is the common cathode.
pub const BOOST_COMMUTATION: LoopSpec = LoopSpec {
    name: "boost commutation",
    legs: &[
        LoopLeg {
            from: "q_boost.2",
            to: "d_boost.1",
        },
        LoopLeg {
            from: "q_boost.2",
            to: "d_boost.3",
        },
        LoopLeg {
            from: "d_boost.2",
            to: "c_hf.1",
        },
        LoopLeg {
            from: "c_hf.2",
            to: "q_boost.3",
        },
    ],
};

pub const BOOST_GATE: LoopSpec = LoopSpec {
    name: "boost gate drive",
    legs: &[
        LoopLeg {
            from: "pfc.8",
            to: "r_gate.1",
        },
        LoopLeg {
            from: "r_gate.2",
            to: "q_boost.1",
        },
        LoopLeg {
            from: "q_boost.3",
            to: "pfc.1",
        },
    ],
};

pub const BOOST_ON_INPUT: LoopSpec = LoopSpec {
    name: "boost on-state input",
    legs: &[
        LoopLeg {
            from: "bridge.4",
            to: "l_boost.1",
        },
        LoopLeg {
            from: "l_boost.2",
            to: "q_boost.2",
        },
        LoopLeg {
            from: "q_boost.3",
            to: "shunt.1",
        },
        LoopLeg {
            from: "shunt.2",
            to: "bridge.1",
        },
    ],
};

// The synchronous bridge has two distinct line-frequency paths.  The
// controller's VR/GND sense pins are not power terminals, so these paths bind
// the MOSFET drain/source pins and preserve the rectifier-side shunt return.
pub const ACTIVE_ON_HL_LR: LoopSpec = LoopSpec {
    name: "active rectifier positive half-cycle (HL/LR)",
    legs: &[
        LoopLeg {
            from: "q_hl.2",
            to: "l_boost.1",
        },
        LoopLeg {
            from: "l_boost.2",
            to: "q_boost.2",
        },
        LoopLeg {
            from: "q_boost.3",
            to: "shunt.1",
        },
        LoopLeg {
            from: "shunt.2",
            to: "q_lr.3",
        },
        LoopLeg {
            from: "q_lr.2",
            to: "cmc.3",
        },
        // RECTIFIER_L is fed through either the NTC or the relay bypass;
        // retain both physical input branches instead of using bridge.1,
        // which is only the controller's voltage-sense tap.
        LoopLeg {
            from: "q_hl.3",
            to: "ntc.2",
        },
        LoopLeg {
            from: "q_hl.3",
            to: "bypass.3",
        },
    ],
};

pub const ACTIVE_ON_HR_LL: LoopSpec = LoopSpec {
    name: "active rectifier negative half-cycle (HR/LL)",
    legs: &[
        LoopLeg {
            from: "q_hr.2",
            to: "l_boost.1",
        },
        LoopLeg {
            from: "l_boost.2",
            to: "q_boost.2",
        },
        LoopLeg {
            from: "q_boost.3",
            to: "shunt.1",
        },
        LoopLeg {
            from: "shunt.2",
            to: "q_ll.3",
        },
        LoopLeg {
            from: "q_ll.2",
            to: "ntc.2",
        },
        LoopLeg {
            from: "q_ll.2",
            to: "bypass.3",
        },
        LoopLeg {
            from: "q_hr.3",
            to: "cmc.3",
        },
    ],
};

pub const RULES: [&str; 3] = [TOPOLOGY, GEOMETRY, INDUCTANCE];
pub const REQUIRED: &[LoopSpec] = &[BOOST_COMMUTATION, BOOST_GATE, BOOST_ON_INPUT];

fn connected(bound: &BoundGraph, from: usize, to: usize, net: &str) -> Option<Vec<String>> {
    let mut queue = VecDeque::from([from]);
    let mut seen = BTreeSet::from([from]);
    let mut via = std::collections::BTreeMap::<usize, (usize, String)>::new();
    while let Some(node) = queue.pop_front() {
        if node == to {
            let mut path = Vec::new();
            let mut cursor = to;
            while cursor != from {
                let (previous, edge) = via.get(&cursor)?;
                path.push(edge.clone());
                cursor = *previous;
            }
            path.reverse();
            return Some(path);
        }
        for edge in bound
            .graph
            .edges
            .iter()
            .filter(|e| e.net == net && (e.from == node || e.to == node))
        {
            let next = if edge.from == node {
                edge.to
            } else {
                edge.from
            };
            if seen.insert(next) {
                via.insert(next, (node, edge.id.clone()));
                queue.push_back(next);
            }
        }
    }
    None
}

/// Validate exact source pin/net identity and native copper closure.
/// Physical path quality is intentionally not promoted to a pass.
pub fn validate(circuit: &Circuit, bound: &BoundGraph, specs: &[LoopSpec<'_>]) -> CheckReport {
    let mut findings = Vec::new();
    let mut gaps = bound.coverage_gaps.clone();
    for spec in specs {
        for leg in spec.legs {
            let from_net = match circuit.net(leg.from) {
                Ok(net) => net,
                Err(error) => {
                    findings.push(Finding::fail(TOPOLOGY, error, spec.name));
                    continue;
                }
            };
            let to_net = match circuit.net(leg.to) {
                Ok(net) => net,
                Err(error) => {
                    findings.push(Finding::fail(TOPOLOGY, error, spec.name));
                    continue;
                }
            };
            if from_net != to_net {
                findings.push(Finding::fail(
                    TOPOLOGY,
                    format!("{} and {} are on different source nets ({from_net} vs {to_net}); expected a same-net copper leg", leg.from, leg.to),
                    spec.name,
                ));
                continue;
            }
            let (Some(&from), Some(&to)) = (
                bound.terminal_nodes.get(leg.from),
                bound.terminal_nodes.get(leg.to),
            ) else {
                findings.push(Finding::fail(
                    TOPOLOGY,
                    format!(
                        "native graph lacks terminal binding for {}↔{}",
                        leg.from, leg.to
                    ),
                    spec.name,
                ));
                continue;
            };
            let Some(path) = connected(bound, from, to, from_net) else {
                let message = format!(
                    "bound graph has no path for {}↔{} on {from_net}",
                    leg.from, leg.to
                );
                findings.push(if bound.uncertified_nets.contains(from_net) {
                    Finding::indeterminate(TOPOLOGY, message, spec.name)
                } else {
                    Finding::fail(TOPOLOGY, message, spec.name)
                });
                continue;
            };
            if bound.uncertified_nets.contains(from_net) {
                findings.push(Finding::indeterminate(
                    TOPOLOGY,
                    format!(
                        "{}↔{} joins via [{}], but {from_net} has unresolved parallel/finite-width contacts",
                        leg.from, leg.to, path.join(", ")
                    ),
                    spec.name,
                ));
            } else {
                findings.push(Finding::pass(
                    TOPOLOGY,
                    format!(
                        "native copper path closes {}↔{} on {from_net}; edge IDs [{}] are diagnostic only",
                        leg.from, leg.to, path.join(", ")
                    ),
                    spec.name,
                ));
            }
        }
    }
    findings.push(Finding::indeterminate(
        GEOMETRY,
        "endpoint closure does not establish the physical high-frequency loop geometry or area",
        "PFC switching loops",
    ));
    findings.push(Finding::indeterminate(
        INDUCTANCE,
        "no extracted parasitic/loop-inductance model is bound to the endpoint path",
        "PFC switching loops",
    ));
    if !gaps.is_empty() {
        gaps.push(
            "parallel current distribution and endpoint-restricted HF path remain unresolved"
                .into(),
        );
    }
    let report = CheckReport::from_findings(
        findings,
        vec![TOPOLOGY.into(), GEOMETRY.into(), INDUCTANCE.into()],
        gaps,
    );
    debug_assert!(report.status != Status::Pass);
    report
}

/// Common-run entry point; bridge polarity comes from the exact reviewed MPN.
pub fn run(source: &str, native_text: &str, manufacturing: &serde_json::Value) -> CheckReport {
    let result = (|| -> Result<CheckReport, String> {
        zapote_erc::power_entry::validate(source, native_text)?;
        if zapote_drc::native_binding::validate(native_text).status != Status::Pass {
            return Err("native copper is not board-bound".into());
        }
        let circuit = zapote_erc::power_entry::parse(source)?;
        let raw: serde_json::Value =
            serde_json::from_str(native_text).map_err(|e| e.to_string())?;
        if manufacturing["board_sha256"] != raw["board_sha256"] {
            return Err("manufacturing board hash mismatch".into());
        }
        let mut native: zapote_core::unit::UnitNativeEvidence =
            serde_json::from_value(raw.clone()).map_err(|e| e.to_string())?;
        // The full source/native check above already requires these exact NC
        // pads to exist and remain unassigned. They are not conductors in a
        // loop graph; do not remove any other empty-net pad here.
        let no_connects = zapote_erc::power_entry::no_connects(source)?;
        for component in &mut native.components {
            component.footprint_pads.retain(|pad| {
                !no_connects.contains(&format!("{}.{}", component.id, pad.pad).as_str())
            });
        }
        let bound = crate::pfc_paths::build_with_manufacturing(&native, &raw, manufacturing)?;
        let active =
            zapote_erc::power_entry::entry(source)? == zapote_erc::power_entry::ACTIVE_ENTRY;
        if !active {
            let mut on = BOOST_ON_INPUT.legs.to_vec();
            let pins = zapote_erc::power_entry::bridge_pins(&circuit.components["bridge"].mpn)?;
            on[0].from = pins.positive;
            on[3].to = pins.negative;
            return Ok(validate(
                &circuit,
                &bound,
                &[
                    BOOST_COMMUTATION,
                    BOOST_GATE,
                    LoopSpec {
                        name: BOOST_ON_INPUT.name,
                        legs: &on,
                    },
                ],
            ));
        }
        Ok(validate(
            &circuit,
            &bound,
            &[
                BOOST_COMMUTATION,
                BOOST_GATE,
                ACTIVE_ON_HL_LR,
                ACTIVE_ON_HR_LL,
            ],
        ))
    })();
    result.unwrap_or_else(|e| {
        CheckReport::from_findings(
            vec![
                Finding::fail(TOPOLOGY, e, "PFC loops"),
                Finding::indeterminate(GEOMETRY, "input validation failed", "PFC loops"),
                Finding::indeterminate(INDUCTANCE, "input validation failed", "PFC loops"),
            ],
            RULES.map(str::to_owned).to_vec(),
            vec![],
        )
    })
}

#[cfg(test)]
mod tests {
    use super::*;

    #[test]
    fn active_native_loop_adapter_preserves_paths_and_excludes_only_reviewed_nc() {
        let root = std::path::Path::new(env!("CARGO_MANIFEST_DIR"))
            .join("../../power-entry/active-rectifier");
        let source = std::fs::read_to_string(root.join("candidate/source-manifest.json")).unwrap();
        let native = std::fs::read_to_string(root.join(
            "evidence/vsense-diode-side-02/native.json")).unwrap();
        let manufacturing = serde_json::from_slice(&std::fs::read(root.join(
            "evidence/vsense-diode-side-02/common/power-entry/manufacturing-input.json"
        )).unwrap()).unwrap();
        let report = run(&source, &native, &manufacturing);
        assert!(!report.findings.iter().any(|f| f.status == Status::Fail), "{:?}", report.findings);
        assert_eq!(report.findings.iter().filter(|f| f.rule == TOPOLOGY).count(),
            BOOST_COMMUTATION.legs.len() + BOOST_GATE.legs.len()
                + ACTIVE_ON_HL_LR.legs.len() + ACTIVE_ON_HR_LL.legs.len());
        assert_eq!(report.status, Status::Indeterminate);
        let mut changed: serde_json::Value = serde_json::from_str(&native).unwrap();
        let bridge = changed["components"].as_array_mut().unwrap().iter_mut()
            .find(|c| c["id"] == "bridge").unwrap();
        bridge["footprint_pads"].as_array_mut().unwrap().iter_mut()
            .find(|p| p["pad"] == "4").unwrap()["net"] = "RECTIFIER_NEGATIVE".into();
        assert_eq!(run(&source, &changed.to_string(), &manufacturing).status, Status::Fail);
    }

    #[test]
    fn active_rectifier_power_paths_use_switch_terminals_and_split_halves() {
        let source =
            include_str!("../../../power-entry/active-rectifier/candidate/source-manifest.json");
        let circuit = zapote_erc::power_entry::parse(source).unwrap();
        for spec in [ACTIVE_ON_HL_LR, ACTIVE_ON_HR_LL] {
            for leg in spec.legs {
                assert_eq!(
                    circuit.net(leg.from).unwrap(),
                    circuit.net(leg.to).unwrap(),
                    "{}: {} ↔ {}",
                    spec.name,
                    leg.from,
                    leg.to
                );
            }
        }
        assert_eq!(circuit.net("q_hl.2").unwrap(), "RECTIFIER_POSITIVE");
        assert_eq!(circuit.net("q_hr.2").unwrap(), "RECTIFIER_POSITIVE");
        assert_eq!(circuit.net("q_hl.3").unwrap(), "RECTIFIER_L");
        assert_eq!(circuit.net("q_hr.3").unwrap(), "RECTIFIER_R");
        assert_eq!(circuit.net("q_lr.3").unwrap(), "RECTIFIER_NEGATIVE");
        assert_eq!(circuit.net("q_ll.3").unwrap(), "RECTIFIER_NEGATIVE");
        assert_eq!(circuit.net("cmc.3").unwrap(), "RECTIFIER_R");
        assert_eq!(circuit.net("ntc.2").unwrap(), "RECTIFIER_L");
        assert_eq!(circuit.net("bypass.3").unwrap(), "RECTIFIER_L");
        assert_ne!(
            circuit.net("q_boost.3").unwrap(),
            circuit.net("shunt.2").unwrap()
        );
    }
    #[test]
    fn repaired_gbj_uses_its_own_polarity_and_preserves_geometry_obligations() {
        let root =
            std::path::Path::new(env!("CARGO_MANIFEST_DIR")).join("../../power-entry/shunt-repair");
        let source = std::fs::read_to_string(root.join("candidate/source-manifest.json")).unwrap();
        let native = std::fs::read_to_string(root.join("evidence/native-04.json")).unwrap();
        let manufacturing = serde_json::from_slice(
            &std::fs::read(root.join("evidence/manufacturing-04.json")).unwrap(),
        )
        .unwrap();
        let report = run(&source, &native, &manufacturing);
        assert!(
            !report.findings.iter().any(|f| f.status == Status::Fail),
            "{:?}",
            report.findings
        );
        assert_eq!(
            report
                .findings
                .iter()
                .filter(|f| f.rule == TOPOLOGY)
                .count(),
            11
        );
        assert_eq!(report.status, Status::Indeterminate);
        assert!(report
            .findings
            .iter()
            .any(|f| f.rule == GEOMETRY && f.status == Status::Indeterminate));
        assert!(report
            .findings
            .iter()
            .any(|f| f.rule == INDUCTANCE && f.status == Status::Indeterminate));
    }
    #[test]
    fn wrong_diode_cathode_pair_is_rejected_by_source_nets() {
        let source = include_str!("../../../power-entry/candidate/source-manifest.json");
        let circuit = Circuit::parse(source, zapote_erc::power_entry::ENTRY).unwrap();
        let wrong = [LoopSpec {
            name: "wrong diode mapping",
            legs: &[LoopLeg {
                from: "q_boost.2",
                to: "d_boost.2",
            }],
        }];
        let graph = BoundGraph {
            graph: zapote_drc::power_branches::Graph {
                node_count: 0,
                edges: vec![],
            },
            terminal_nodes: Default::default(),
            edge_width_mm: Default::default(),
            edge_kind: Default::default(),
            coverage_gaps: vec![],
            uncertified_nets: Default::default(),
        };
        let report = validate(&circuit, &graph, &wrong);
        assert_eq!(report.findings[0].status, Status::Fail);
        assert!(report.findings[0].message.contains("different source nets"));
    }

    #[test]
    fn anode_leg_closes_only_when_native_edge_exists() {
        let source = include_str!("../../../power-entry/candidate/source-manifest.json");
        let circuit = Circuit::parse(source, zapote_erc::power_entry::ENTRY).unwrap();
        let net = circuit.net("q_boost.2").unwrap().to_owned();
        assert_eq!(net, circuit.net("d_boost.1").unwrap());
        let mut terminals = std::collections::BTreeMap::new();
        terminals.insert("q_boost.2".into(), 0);
        terminals.insert("d_boost.1".into(), 1);
        let edge = zapote_drc::power_branches::Edge {
            id: "trace:sw:0".into(),
            net: net.clone(),
            from: 0,
            to: 1,
        };
        let graph = BoundGraph {
            graph: zapote_drc::power_branches::Graph {
                node_count: 2,
                edges: vec![edge],
            },
            terminal_nodes: terminals.clone(),
            edge_width_mm: Default::default(),
            edge_kind: Default::default(),
            coverage_gaps: vec![],
            uncertified_nets: Default::default(),
        };
        let spec = [LoopSpec {
            name: "anode",
            legs: &[LoopLeg {
                from: "q_boost.2",
                to: "d_boost.1",
            }],
        }];
        assert_eq!(
            validate(&circuit, &graph, &spec).findings[0].status,
            Status::Pass
        );
        let disconnected = BoundGraph {
            graph: zapote_drc::power_branches::Graph {
                node_count: 2,
                edges: vec![],
            },
            ..graph
        };
        assert_eq!(
            validate(&circuit, &disconnected, &spec).findings[0].status,
            Status::Fail
        );
    }

    #[test]
    fn missing_gate_return_or_resistor_binding_fails_closed() {
        let source = include_str!("../../../power-entry/candidate/source-manifest.json");
        let circuit = Circuit::parse(source, zapote_erc::power_entry::ENTRY).unwrap();
        let spec = [BOOST_GATE];
        let mut terminals = std::collections::BTreeMap::new();
        for (i, endpoint) in [
            "pfc.8",
            "r_gate.1",
            "r_gate.2",
            "q_boost.1",
            "q_boost.3",
            "pfc.1",
        ]
        .iter()
        .enumerate()
        {
            terminals.insert((*endpoint).into(), i);
        }
        let graph = BoundGraph {
            graph: zapote_drc::power_branches::Graph {
                node_count: 6,
                edges: vec![],
            },
            terminal_nodes: terminals,
            edge_width_mm: Default::default(),
            edge_kind: Default::default(),
            coverage_gaps: vec![],
            uncertified_nets: Default::default(),
        };
        let report = validate(&circuit, &graph, &spec);
        assert!(report.findings.iter().any(|f| f.status == Status::Fail));
    }
}
