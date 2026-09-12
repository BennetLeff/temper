//! Source-bound nominal PFC branch-current and native pad-contact screen.
use serde::Serialize;
use std::collections::{BTreeMap, BTreeSet};
use zapote_core::unit::UnitNativeEvidence;
use zapote_core::{CheckReport, Finding};
use zapote_drc::{power_branches as flow, power_contact as contact};
use zapote_erc::{pfc_currents as model, power_entry, source_circuit::Circuit};

pub const RULES: [&str; 3] = [
    "ERC.PFC.BRANCH_WAVEFORMS",
    "DRC.PFC.BRANCH_COPPER",
    "DRC.PFC.PAD_CONTACT",
];
const CAPS: [&str; 5] = ["c1", "c2", "c3", "c4", "c_hf"];
const ENDPOINTS: &[&str] = &[
    "mains.1",
    "mains.2",
    "holder.1",
    "holder.2",
    "cmc.1",
    "cmc.2",
    "cmc.3",
    "cmc.4",
    "ntc.1",
    "ntc.2",
    "bypass.3",
    "bypass.4",
    "bridge.1",
    "bridge.2",
    "bridge.3",
    "bridge.4",
    "l_boost.1",
    "l_boost.2",
    "q_boost.2",
    "q_boost.3",
    "d_boost.1",
    "d_boost.2",
    "d_boost.3",
    "output.1",
    "output.2",
    "shunt.1",
    "shunt.2",
];

#[derive(Debug, Serialize)]
pub struct Branch {
    pub id: String,
    pub net: String,
    pub kind: String,
    pub width_mm: f64,
    /// Zero for an undetermined sharing distribution; never min(vertex RMS).
    pub determined_rms_a: Option<f64>,
    pub rms_envelope_a: f64,
    pub sampled_peak_envelope_a: f64,
    pub nominal_external_capacity_a: Option<f64>,
}
#[derive(Debug, Serialize)]
pub struct PadContact {
    pub endpoint: String,
    pub pad_id: String,
    pub trace_id: String,
    pub geometry: contact::Entry,
    pub branch_rms_envelope_a: f64,
}
#[derive(Debug, Serialize)]
pub struct Report {
    pub checks: CheckReport,
    pub assumptions: Vec<String>,
    pub config: model::Config,
    pub waveform: model::Profile,
    pub branches: Vec<Branch>,
    pub pad_contacts: Vec<PadContact>,
    pub excluded_terminals: Vec<String>,
}

fn inject(
    bound: &crate::pfc_paths::BoundGraph,
    s: &model::Sample,
    relay: f64,
    anode: f64,
    cap: usize,
) -> Result<flow::Sample, String> {
    let mut values = vec![0.; bound.graph.node_count];
    let mut put = |pin: &str, value: f64| -> Result<(), String> {
        let node = bound
            .terminal_nodes
            .get(pin)
            .ok_or_else(|| format!("missing PFC terminal {pin}"))?;
        values[*node] += value;
        Ok(())
    };
    let (i, sw, d, o, c, a) = (
        s.inductor_a,
        s.switch_a,
        s.diode_a,
        s.load_a,
        s.capacitor_a,
        s.line_sign * s.inductor_a,
    );
    for (pin, value) in [
        ("mains.1", a),
        ("holder.1", -a),
        ("holder.2", a),
        ("cmc.1", -a),
        ("mains.2", -a),
        ("cmc.2", a),
        ("cmc.4", a),
        ("ntc.1", -(1. - relay) * a),
        ("bypass.4", -relay * a),
        ("ntc.2", (1. - relay) * a),
        ("bypass.3", relay * a),
        ("bridge.2", -a),
        ("cmc.3", -a),
        ("bridge.3", a),
        ("bridge.4", i),
        ("l_boost.1", -i),
        ("l_boost.2", i),
        ("q_boost.2", -sw),
        ("d_boost.1", -d * anode),
        ("d_boost.3", -d * (1. - anode)),
        ("d_boost.2", d),
        ("output.1", -o),
        ("q_boost.3", sw),
        ("output.2", o),
        ("shunt.1", -i),
        ("shunt.2", i),
        ("bridge.1", -i),
    ] {
        put(pin, value)?;
    }
    for (index, name) in CAPS.iter().enumerate() {
        put(&format!("{name}.1"), if index == cap { -c } else { 0. })?;
        put(&format!("{name}.2"), if index == cap { c } else { 0. })?;
    }
    Ok(flow::Sample {
        weight: s.weight,
        injections_a: values,
    })
}

/// Bound to the reviewed source, saved native board and fresh manufacturing
/// receipt. This is a power-stage contribution screen, not total-current or
/// fabrication qualification. Any adapter gap prevents exact certificates.
pub fn run(
    source: &str,
    native_text: &str,
    board: &str,
    manufacturing: &serde_json::Value,
) -> Result<Report, String> {
    power_entry::validate(source, native_text)?;
    let binding = zapote_drc::native_binding::validate(native_text);
    if binding.status != zapote_core::Status::Pass {
        return Err(format!(
            "PFC native document binding: {:?}",
            binding.findings
        ));
    }
    let circuit = Circuit::parse(source, power_entry::ENTRY)?;
    let raw: serde_json::Value = serde_json::from_str(native_text).map_err(|e| e.to_string())?;
    let mut native: UnitNativeEvidence =
        serde_json::from_value(raw.clone()).map_err(|e| e.to_string())?;
    if raw["board_file_utf8"].as_str() != Some(board)
        || manufacturing["board_sha256"].as_str()
            != Some(crate::runner::digest(board.as_bytes()).as_str())
    {
        return Err("PFC native/manufacturing receipt does not bind saved board".into());
    }
    let mut modeled: BTreeSet<String> = ENDPOINTS.iter().map(|s| s.to_string()).collect();
    for cap in CAPS {
        for pin in [1, 2] {
            modeled.insert(format!("{cap}.{pin}"));
        }
    }
    let nets: BTreeSet<String> = modeled
        .iter()
        .map(|p| circuit.net(p).map(str::to_owned))
        .collect::<Result<_, _>>()?;
    native.traces.retain(|t| nets.contains(&t.net));
    native.vias.retain(|t| nets.contains(&t.net));
    native.zones.retain(|t| nets.contains(&t.net));
    native
        .connectivity_clusters
        .retain(|c| nets.contains(&c.net));
    for component in &mut native.components {
        component.footprint_pads.retain(|p| nets.contains(&p.net));
    }
    native.components.retain(|c| !c.footprint_pads.is_empty());
    let bound = crate::pfc_paths::build_with_manufacturing(&native, &raw, manufacturing)?;
    let copper = zapote_drc::stackup::nominal_outer_copper_um(board)?;
    // Exact inductor identity is pinned by power_entry::validate_source. Its
    // 180uH nominal value comes from Würth's 760800301 manufacturer record.
    let config = model::Config {
        line_rms_v: 120.,
        input_rms_limit_a: 15.,
        bus_v: power_entry::nominal_screen()?.bus_setpoint_v,
        inductance_h: 180e-6,
        switching_hz: power_entry::frequency_from_rf(16_200.)?,
        phase_samples: 256,
    };
    let waveform = model::calculate(config)?;
    let mut net_nodes = BTreeMap::<String, BTreeSet<usize>>::new();
    for edge in &bound.graph.edges {
        net_nodes
            .entry(edge.net.clone())
            .or_default()
            .extend([edge.from, edge.to]);
    }
    let mut net_samples: BTreeMap<String, Vec<f64>> = net_nodes
        .keys()
        .map(|n| (n.clone(), vec![0.; waveform.samples.len()]))
        .collect();
    let mut envelopes: Vec<flow::BranchCurrent> = vec![];
    let mut sensitivity = vec![];
    // Vertices bound nonnegative branch fractions at each sample. They do NOT
    // supply a lower bound or imply equal sharing / qualified impedances.
    let mut first_samples: Option<Vec<flow::Sample>> = None;
    for relay in [0., 1.] {
        for anode in [0., 1.] {
            for cap in 0..CAPS.len() {
                let samples = waveform
                    .samples
                    .iter()
                    .map(|s| inject(&bound, s, relay, anode, cap))
                    .collect::<Result<Vec<_>, _>>()?;
                for (net, nodes) in &net_nodes {
                    for (slot, sample) in net_samples.get_mut(net).unwrap().iter_mut().zip(&samples)
                    {
                        let positive = nodes
                            .iter()
                            .map(|&n| sample.injections_a[n].max(0.))
                            .sum::<f64>();
                        *slot = slot.max(positive);
                    }
                }
                let result = flow::analyze(&bound.graph, &samples).map_err(|e| {
                    format!(
                        "{e}; terminals {:?}; coverage {:?}",
                        bound.terminal_nodes, bound.coverage_gaps
                    )
                })?;
                if let Some(first) = &first_samples {
                    // Difference waveforms expose signed sharing sensitivity. Equal
                    // RMS at two vertices alone would miss cancellation in between.
                    let differences: Vec<_> = samples
                        .iter()
                        .zip(first)
                        .map(|(a, b)| flow::Sample {
                            weight: a.weight,
                            injections_a: a
                                .injections_a
                                .iter()
                                .zip(&b.injections_a)
                                .map(|(x, y)| x - y)
                                .collect(),
                        })
                        .collect();
                    let delta = flow::analyze(&bound.graph, &differences)?;
                    for (index, current) in delta.iter().enumerate() {
                        sensitivity[index] = f64::max(sensitivity[index], current.peak_a);
                    }
                    for (a, b) in envelopes.iter_mut().zip(result) {
                        a.rms_a = a.rms_a.max(b.rms_a);
                        a.peak_a = a.peak_a.max(b.peak_a);
                    }
                } else {
                    sensitivity = vec![0.; result.len()];
                    envelopes = result;
                    first_samples = Some(samples);
                }
            }
        }
    }
    let mut findings=vec![Finding::pass(RULES[0],"source-bound ON/OFF waveforms conserve current and feed native branches; sharing vertices and signed sensitivity evaluated","PFC")];
    let mut gaps = bound.coverage_gaps.clone();
    let net_envelopes: BTreeMap<_, _> = net_samples
        .iter()
        .map(|(net, values)| {
            (
                net.clone(),
                (
                    values
                        .iter()
                        .zip(&waveform.samples)
                        .map(|(v, s)| v * v * s.weight)
                        .sum::<f64>()
                        .sqrt(),
                    values.iter().copied().fold(0., f64::max),
                ),
            )
        })
        .collect();
    gaps.push("Zone meshes and unsupported finite-width side contacts have component-current envelopes only; no exact local sharing or minimum-cut certificate".into());
    let branches:Vec<_>=envelopes.iter().enumerate().map(|(index,current)| {
        let kind=&bound.edge_kind[&current.id];
        let width=bound.edge_width_mm[&current.id];
        let net=&bound.graph.edges[index].net;
        let exact=current.exact && sensitivity[index]<1e-8 && !bound.uncertified_nets.contains(net) && !native.zones.iter().any(|z|&z.net==net);
        let (rms_envelope,peak_envelope)=if exact {(current.rms_a,current.peak_a)} else {net_envelopes[net]};
        let capacity=if kind=="trace" {contact::capacity_a(width,copper).ok()} else {None};
        if exact && capacity.is_some_and(|capacity|current.rms_a>capacity) {
            findings.push(Finding::fail(RULES[1],format!("determined nominal power-stage RMS {:.4} A exceeds {:.4} A external-copper screen at {:.4} mm / {:.1} um / assumed 20 C rise",current.rms_a,capacity.unwrap(),width,copper),&current.id));
        }
        Branch{id:current.id.clone(),net:bound.graph.edges[index].net.clone(),kind:kind.clone(),width_mm:width,determined_rms_a:exact.then_some(current.rms_a),rms_envelope_a:rms_envelope,sampled_peak_envelope_a:peak_envelope,nominal_external_capacity_a:capacity}
    }).collect();
    let mut contacts = vec![];
    let pads = manufacturing["input"]["pads"]
        .as_array()
        .ok_or("missing native pad polygons")?;
    for pad in pads {
        let id = pad["id"].as_str().ok_or("native pad missing ID")?;
        let Some((physical, rest)) = id.split_once(':') else {
            continue;
        };
        let Some((reference, pin)) = physical.split_once('.') else {
            continue;
        };
        let Some(instance) = raw["reference_to_instance"][reference].as_str() else {
            continue;
        };
        let endpoint = format!("{instance}.{pin}");
        if !modeled.contains(&endpoint) {
            continue;
        }
        let net = circuit.net(&endpoint)?;
        let layer = rest
            .split_once('@')
            .and_then(|(_, v)| v.split_once(':'))
            .map(|(layer, _)| layer)
            .ok_or("native pad missing layer")?;
        let inner: Vec<zapote_drc::manufacturing::Polygon> =
            serde_json::from_value(pad["inner_copper_polygons"].clone())
                .map_err(|e| format!("missing inside native pad polygon: {e}"))?;
        let drill: Option<zapote_drc::manufacturing::Polygon> =
            serde_json::from_value(pad["drill_polygon"].clone()).map_err(|e| e.to_string())?;
        for trace in native
            .traces
            .iter()
            .filter(|t| t.net == net && t.layer == layer)
        {
            for segment in trace.points_mm.windows(2) {
                let geometry = contact::entry(
                    &inner,
                    drill.as_ref(),
                    segment[0],
                    segment[1],
                    trace.width_mm,
                )?;
                if geometry.certified_chord_mm <= 0. {
                    continue;
                }
                let demand = branches
                    .iter()
                    .filter(|b| b.id.starts_with(&format!("{}:", trace.id)))
                    .map(|b| b.rms_envelope_a)
                    .fold(0., f64::max);
                if !geometry.full_width_chord_observed {
                    gaps.push(format!("{id} / {}: native copper chord {:.4} mm does not certify full {:.4} mm trace chord",trace.id,geometry.certified_chord_mm,trace.width_mm));
                }
                contacts.push(PadContact {
                    endpoint: endpoint.clone(),
                    pad_id: id.into(),
                    trace_id: trace.id.clone(),
                    geometry,
                    branch_rms_envelope_a: demand,
                });
            }
        }
    }
    for endpoint in &modeled {
        if !contacts.iter().any(|c| &c.endpoint == endpoint) {
            gaps.push(format!("{endpoint}: no native pad/trace chord certificate; zone-only/cap-only contacts need a separate certificate"));
        }
    }
    findings.push(Finding::indeterminate(RULES[1],format!("{} native branch records; cycles retain envelopes; nominal external trace screen does not qualify vias, pad barrels, zone bottlenecks, hot copper or transient faults",branches.len()),"PFC"));
    findings.push(Finding::indeterminate(RULES[2],format!("{} actual pad/trace copper chords measured with drill voids excluded; attachment chords do not establish global pad/plane thermal capacity",contacts.len()),"PFC"));
    let excluded = bound
        .terminal_nodes
        .keys()
        .filter(|p| !modeled.contains(*p))
        .cloned()
        .collect();
    let assumptions=vec!["Nominal 120VAC / 15A true RMS ideal steady-state CCM boost; no losses, inrush, shorts, reverse recovery or control transients".into(),"180uH nominal Würth 760800301; saturation/temperature/tolerance require separate corner qualification".into(),"Nonnegative time-varying current shares between NTC/relay, diode anodes, and five DC-link capacitors; no circulating/parasitic currents; no equal-sharing assumption".into(),"Only listed power-stage terminal injections are modeled. EMI/reactive, divider, bleeder, bias/control and gate-drive contributions are excluded, so this cannot certify total trace current".into(),"Native pad inside-polygons minus outside drill polygons; sampled transverse chords are attachment lower bounds, not whole-pad minimum cuts".into()];
    gaps.extend(assumptions.iter().cloned());
    Ok(Report {
        checks: CheckReport::from_findings(findings, RULES.map(str::to_owned).to_vec(), gaps),
        assumptions,
        config,
        waveform,
        branches,
        pad_contacts: contacts,
        excluded_terminals: excluded,
    })
}

#[cfg(test)]
mod tests {
    use super::*;
    const SOURCE: &str = include_str!("../../../power-entry/candidate/source-manifest.json");
    const NATIVE: &str = include_str!("../../../power-entry/evidence/native-11.json");

    #[test]
    fn source_pin_injections_conserve_every_power_net_and_distinguish_branches() {
        let circuit = Circuit::parse(SOURCE, power_entry::ENTRY).unwrap();
        let mut terminals: Vec<String> = ENDPOINTS.iter().map(|s| s.to_string()).collect();
        for cap in CAPS {
            for pin in [1, 2] {
                terminals.push(format!("{cap}.{pin}"));
            }
        }
        let mut by_net = std::collections::BTreeMap::<String, Vec<usize>>::new();
        for (node, pin) in terminals.iter().enumerate() {
            by_net
                .entry(circuit.net(pin).unwrap().into())
                .or_default()
                .push(node);
        }
        let mut bound = crate::pfc_paths::BoundGraph {
            graph: flow::Graph {
                node_count: terminals.len() + by_net.len(),
                edges: vec![],
            },
            terminal_nodes: terminals
                .iter()
                .enumerate()
                .map(|(i, p)| (p.clone(), i))
                .collect(),
            edge_kind: Default::default(),
            edge_width_mm: Default::default(),
            coverage_gaps: vec![],
            uncertified_nets: Default::default(),
        };
        for (index, (net, nodes)) in by_net.iter().enumerate() {
            for &node in nodes {
                bound.graph.edges.push(flow::Edge {
                    id: terminals[node].clone(),
                    net: net.clone(),
                    from: node,
                    to: terminals.len() + index,
                });
            }
        }
        let profile = model::calculate(model::Config {
            line_rms_v: 120.,
            input_rms_limit_a: 15.,
            bus_v: 390.,
            inductance_h: 180e-6,
            switching_hz: 130_000.,
            phase_samples: 128,
        })
        .unwrap();
        for relay in [0., 0.37, 1.] {
            for anode in [0., 0.61, 1.] {
                for cap in 0..5 {
                    let samples: Vec<_> = profile
                        .samples
                        .iter()
                        .map(|s| inject(&bound, s, relay, anode, cap).unwrap())
                        .collect();
                    let currents = flow::analyze(&bound.graph, &samples).unwrap();
                    let rms = |id: &str| currents.iter().find(|c| c.id == id).unwrap().rms_a;
                    assert!((rms("mains.1") - 15.).abs() < 1e-8);
                    assert!((rms("shunt.1") - 15.).abs() < 1e-8);
                    assert!((rms("q_boost.2") - profile.switch_rms_a).abs() < 1e-8);
                    assert!((rms("d_boost.2") - profile.diode_rms_a).abs() < 1e-8);
                    assert!((rms("output.1") - profile.load_rms_a).abs() < 1e-8);
                    let mut wrong = samples;
                    wrong[0].injections_a[bound.terminal_nodes["bridge.1"]] *= -1.;
                    assert!(flow::analyze(&bound.graph, &wrong).is_err());
                }
            }
        }
    }

    #[test]
    fn rejects_native_trace_width_that_disagrees_with_saved_board() {
        let mut native: serde_json::Value = serde_json::from_str(NATIVE).unwrap();
        let board = native["board_file_utf8"].as_str().unwrap().to_string();
        native["traces"][0]["width_mm"] = 0.01.into();
        let error = run(SOURCE, &native.to_string(), &board, &serde_json::json!({})).unwrap_err();
        assert!(error.contains("traces differ from saved board"));
    }

    #[test]
    fn saved_pfc_runs_the_model_and_native_contact_measurements() {
        let native: serde_json::Value = serde_json::from_str(NATIVE).unwrap();
        let fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../../validation/p1-current/pfc-pad-fixture.json"
        ))
        .unwrap();
        let report = run(
            SOURCE,
            NATIVE,
            native["board_file_utf8"].as_str().unwrap(),
            &fixture,
        )
        .unwrap();
        assert!(!report.branches.is_empty());
        assert!(!report.pad_contacts.is_empty());
        assert!(report
            .branches
            .iter()
            .any(|b| b.determined_rms_a.is_some_and(|v| (v - 15.).abs() < 1e-6)));
        assert_eq!(report.config.inductance_h, 180e-6);
        assert!(report
            .pad_contacts
            .iter()
            .all(|p| p.geometry.certified_chord_mm <= p.geometry.trace_width_mm + 1e-9));
        assert!(report.checks.checked_rules.iter().any(|r| r == RULES[1]));
        assert!(report
            .branches
            .iter()
            .filter(|b| b.net == "PFC_BUS_MINUS")
            .all(|b| b.determined_rms_a.is_none()));
    }

    #[test]
    fn narrowing_a_saved_six_mm_branch_adds_a_specific_failure() {
        let mut native: serde_json::Value = serde_json::from_str(NATIVE).unwrap();
        let mut fixture: serde_json::Value = serde_json::from_str(include_str!(
            "../../../validation/p1-current/pfc-pad-fixture.json"
        ))
        .unwrap();
        let board = native["board_file_utf8"].as_str().unwrap().to_string();
        let before = run(SOURCE, NATIVE, &board, &fixture).unwrap();
        let uuid = "3a21cb7f-1ccf-4dcc-886e-b105e79be599";
        assert!(!before
            .checks
            .findings
            .iter()
            .any(|f| f.status == zapote_core::Status::Fail && f.object.starts_with(uuid)));
        let uuid_position = board.find(uuid).unwrap();
        let begin = board[..uuid_position].rfind("(segment").unwrap();
        let width_start = begin + board[begin..uuid_position].find("(width ").unwrap();
        let width_end = width_start + board[width_start..].find(')').unwrap() + 1;
        let mut changed = board;
        changed.replace_range(width_start..width_end, "(width 0.2)");
        let trace = native["traces"]
            .as_array_mut()
            .unwrap()
            .iter_mut()
            .find(|t| t["uuid"] == uuid)
            .unwrap();
        trace["width_mm"] = 0.2.into();
        native["board_file_utf8"] = changed.clone().into();
        native["board_sha256"] = crate::runner::digest(changed.as_bytes()).into();
        // Width-only mutation leaves every captured native pad/drill polygon
        // unchanged. Rebind this explicitly derived fixture to the mutant.
        fixture["board_sha256"] = crate::runner::digest(changed.as_bytes()).into();
        let after = run(SOURCE, &native.to_string(), &changed, &fixture).unwrap();
        assert!(after
            .checks
            .findings
            .iter()
            .any(|f| f.status == zapote_core::Status::Fail
                && f.rule == RULES[1]
                && f.object.starts_with(uuid)));
    }
}
